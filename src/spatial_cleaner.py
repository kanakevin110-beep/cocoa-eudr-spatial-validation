"""
spatial_cleaner.py - Plot polygon cleaning and topology repair, PyQGIS version (prototype).

GPX track -> ring -> remove duplicate / jitter vertices -> close ring -> repair
self-intersections (QgsGeometry.makeValid) -> keep main polygon -> normalise precision
-> ellipsoidal area and perimeter (QgsDistanceArea).

Also: remove_overlaps() for neighbouring plots, save_plots() to GeoPackage/GeoJSON,
and add_to_project() to display the result when running inside QGIS.

Usage (OSGeo4W Shell or QGIS Python):
    python src/spatial_cleaner.py --gpx data/sample_track.gpx --out cleaned_plot.gpkg
"""
from __future__ import annotations

import argparse
import json

try:
    from .qgis_env import ensure_qgis
    from .anti_fraud import read_gpx_points, make_distance_area
except ImportError:  # run as a plain script
    from qgis_env import ensure_qgis
    from anti_fraud import read_gpx_points, make_distance_area

ensure_qgis()
from qgis.core import (QgsCoordinateTransformContext, QgsFeature, QgsGeometry,  # noqa: E402
                       QgsPointXY, QgsProject, QgsVectorFileWriter, QgsVectorLayer, QgsWkbTypes)

DEFAULT_CONFIG = {
    "min_vertex_spacing_m": 0.5,   # drop vertices closer than this (GPS jitter / duplicates)
    "coord_decimals": 6,           # ~0.11 m at the equator
    "min_plot_area_ha": 0.01,      # below this the plot is flagged
    "max_plot_area_ha": 50.0,      # above this the plot is flagged (smallholder context)
    "min_overlap_ha": 0.0005,      # overlaps smaller than this are treated as slivers
}


def _polygon_parts(geom: QgsGeometry) -> list[QgsGeometry]:
    """Polygonal parts of any geometry (makeValid can return collections)."""
    if geom.isNull() or geom.isEmpty():
        return []
    parts = geom.asGeometryCollection() if geom.isMultipart() or \
        QgsWkbTypes.geometryType(geom.wkbType()) != QgsWkbTypes.PolygonGeometry else [geom]
    out = []
    for p in parts:
        if QgsWkbTypes.geometryType(p.wkbType()) == QgsWkbTypes.PolygonGeometry:
            out.extend(p.asGeometryCollection() if p.isMultipart() else [p])
    return out


def _largest_polygon(geom: QgsGeometry) -> QgsGeometry | None:
    parts = _polygon_parts(geom)
    return max(parts, key=lambda g: g.area()) if parts else None


def drop_close_vertices(points, min_spacing_m, da):
    """Remove consecutive vertices closer than min_spacing_m."""
    if not points:
        return []
    kept = [points[0]]
    for p in points[1:]:
        if da.measureLine(QgsPointXY(*kept[-1]), QgsPointXY(*p)) >= min_spacing_m:
            kept.append(p)
    return kept


def clean_polygon(points_lonlat, cfg: dict | None = None) -> dict:
    """Clean one plot from [(lon, lat), ...]. Returns {'geometry', 'report'}."""
    cfg = {**DEFAULT_CONFIG, **(cfg or {})}
    da = make_distance_area()
    report = {"input_vertices": len(points_lonlat), "warnings": []}

    ring = drop_close_vertices([(p[0], p[1]) for p in points_lonlat], cfg["min_vertex_spacing_m"], da)
    report["vertices_after_dedup"] = len(ring)
    if len(ring) < 3:
        report["warnings"].append("Fewer than 3 distinct vertices - cannot build a polygon")
        return {"geometry": None, "report": report}

    pts = [QgsPointXY(x, y) for x, y in ring]
    if pts[0] != pts[-1]:
        pts.append(pts[0])  # close the ring
    geom = QgsGeometry.fromPolygonXY([pts])

    report["was_valid"] = geom.isGeosValid()
    if not report["was_valid"]:
        report["validity_issue"] = "; ".join(e.what() for e in geom.validateGeometry()) or "invalid"
        repaired = _largest_polygon(geom.makeValid())
        if repaired is None:
            repaired = _largest_polygon(geom.buffer(0, 5))  # fallback
        if repaired is None:
            report["warnings"].append("Repair failed")
            return {"geometry": None, "report": report}
        report["repaired"] = True
        if repaired.area() < 0.5 * geom.convexHull().area():
            report["warnings"].append("Repair removed a large part of the shape - check manually")
        geom = repaired

    step = 10 ** -cfg["coord_decimals"]
    geom = geom.snappedToGrid(step, step)
    if geom.isEmpty() or not geom.isGeosValid():
        report["warnings"].append("Invalid after precision normalisation")
        return {"geometry": None, "report": report}

    ha = da.measureArea(geom) / 10_000
    report["area_ha"] = round(ha, 4)
    report["perimeter_m"] = round(da.measurePerimeter(geom), 1)
    if ha < cfg["min_plot_area_ha"]:
        report["warnings"].append(f"Very small plot ({ha:.4f} ha)")
    if ha > cfg["max_plot_area_ha"]:
        report["warnings"].append(f"Unusually large plot ({ha:.2f} ha)")
    report["is_valid"] = True
    return {"geometry": geom, "report": report}


def remove_overlaps(plots: dict, cfg: dict | None = None) -> dict:
    """
    Resolve overlaps between plots (the first plot in the dict keeps the contested area).
    Slivers below min_overlap_ha are trimmed; larger overlaps are flagged 'REVIEW'.
    """
    cfg = {**DEFAULT_CONFIG, **(cfg or {})}
    da = make_distance_area()
    ids, result, overlaps = list(plots), dict(plots), []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            inter = result[a].intersection(result[b])
            if inter.isEmpty() or inter.area() == 0:
                continue
            ha = da.measureArea(inter) / 10_000
            sliver = ha < cfg["min_overlap_ha"]
            if sliver:
                cut = _largest_polygon(result[b].difference(inter))
                if cut is not None:
                    result[b] = cut
            overlaps.append({"a": a, "b": b, "area_ha": round(ha, 5),
                             "action": "trimmed" if sliver else "REVIEW"})
    return {"plots": result, "overlaps": overlaps}


def build_layer(plots: dict, attributes: dict | None = None, name="cleaned_plots") -> QgsVectorLayer:
    """In-memory polygon layer (EPSG:4326). attributes: {plot_id: {'area_ha':..., ...}}"""
    layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=plot_id:string&field=area_ha:double"
                           "&field=perimeter_m:double&field=consistency:integer", name, "memory")
    da = make_distance_area()
    feats = []
    for pid, geom in plots.items():
        extra = (attributes or {}).get(pid, {})
        f = QgsFeature(layer.fields())
        f.setGeometry(geom)
        f.setAttributes([pid, round(da.measureArea(geom) / 10_000, 4),
                         round(da.measurePerimeter(geom), 1), extra.get("consistency")])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    return layer


def save_plots(layer: QgsVectorLayer, out_path: str) -> str:
    """Write to GeoPackage (.gpkg) or GeoJSON (.geojson), chosen by extension."""
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG" if out_path.lower().endswith(".gpkg") else "GeoJSON"
    err, msg, *_ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, out_path, QgsProject.instance().transformContext(), opts)
    if err != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Could not write {out_path}: {msg}")
    return out_path


def add_to_project(layer: QgsVectorLayer):
    """Show the layer in the open QGIS project (use inside the QGIS GUI)."""
    QgsProject.instance().addMapLayer(layer)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Clean a plot polygon from a GPX track")
    ap.add_argument("--gpx", required=True)
    ap.add_argument("--out", default="cleaned_plot.gpkg")
    a = ap.parse_args()

    res = clean_polygon([(x, y) for x, y, _ in read_gpx_points(a.gpx)])
    print(json.dumps(res["report"], indent=2))
    if res["geometry"] is not None:
        save_plots(build_layer({"plot_1": res["geometry"]}), a.out)
        print(f"Saved {a.out}")
