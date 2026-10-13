"""
eudr_checker.py - Screening of a plot against a forest-loss layer, PyQGIS version (prototype).

Intersects a cleaned plot polygon with a vector layer of tree-cover / forest-loss polygons
(for example derived from Global Forest Watch / Hansen loss data) and computes the overlap
that occurred AFTER the EUDR cut-off date (31 December 2020).

IMPORTANT - what this is and is not
  * It is a screening indicator. It does not determine legal EUDR compliance.
  * "Forest loss" layers also record the loss of shade trees, harvests and fires; in cocoa
    agroforestry a flag does not prove deforestation, and an absence of flag does not prove
    compliance. Overlaps are meant to be reviewed by a person with satellite imagery.
  * The loss layer is supplied by the user; nothing is downloaded by this module.

Loss layer requirements: polygons, any CRS, optional year attribute (see `year_field`).
Year values may be 4-digit (2022) or Hansen-style 2-digit (22 = 2022).

Usage (OSGeo4W Shell or QGIS Python):
    python src/eudr_checker.py --gpx data/sample_track.gpx --forest-layer data/forest_loss_sample.geojson
"""
from __future__ import annotations

import argparse
import json

try:
    from .qgis_env import ensure_qgis
    from .anti_fraud import make_distance_area, read_gpx_points
    from .spatial_cleaner import clean_polygon
except ImportError:  # run as a plain script
    from qgis_env import ensure_qgis
    from anti_fraud import make_distance_area, read_gpx_points
    from spatial_cleaner import clean_polygon

ensure_qgis()
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeatureRequest,  # noqa: E402
                       QgsGeometry, QgsProject, QgsVectorLayer, QgsWkbTypes)

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")

DEFAULT_CONFIG = {
    "year_field": "year",          # attribute holding the loss year; None = use all polygons
    "min_year": 2021,              # loss before 1 January 2021 is ignored (cut-off 31 Dec 2020)
    "min_overlap_ha": 0.005,       # overlaps below this (50 m2) are treated as positional noise
    "high_risk_overlap_pct": 5.0,  # share of the plot above which risk is HIGH
}


def load_loss_layer(path: str) -> QgsVectorLayer:
    layer = QgsVectorLayer(path, "forest_loss", "ogr")
    if not layer.isValid():
        raise ValueError(f"Cannot open forest-loss layer: {path}")
    if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.PolygonGeometry:
        raise ValueError("The forest-loss layer must contain polygons")
    if not layer.crs().isValid():
        raise ValueError("The forest-loss layer has no CRS; define it before use")
    return layer


def _loss_year(value):
    try:
        y = int(value)
    except (TypeError, ValueError):
        return None
    return 2000 + y if 0 <= y < 100 else y


def check_plot(plot_geom: QgsGeometry, loss_layer: QgsVectorLayer, cfg: dict | None = None) -> dict:
    """Overlap of a plot (EPSG:4326 geometry) with post-cut-off forest loss."""
    cfg = {**DEFAULT_CONFIG, **(cfg or {})}
    da = make_distance_area()
    ctx = QgsProject.instance().transformContext()
    to_wgs = QgsCoordinateTransform(loss_layer.crs(), WGS84, ctx)
    to_layer = QgsCoordinateTransform(WGS84, loss_layer.crs(), ctx)

    year_field = cfg["year_field"]
    has_year = bool(year_field) and loss_layer.fields().indexFromName(year_field) >= 0
    warnings = []
    if year_field and not has_year:
        warnings.append(f"Field '{year_field}' not found: all loss polygons were used")

    request = QgsFeatureRequest().setFilterRect(to_layer.transformBoundingBox(plot_geom.boundingBox()))
    pieces, years, undated = [], set(), 0
    for feat in loss_layer.getFeatures(request):
        if has_year:
            year = _loss_year(feat[year_field])
            if year is None:
                undated += 1                      # unknown year: keep it (conservative)
            elif year < cfg["min_year"]:
                continue
            else:
                years.add(year)
        geom = QgsGeometry(feat.geometry())
        geom.transform(to_wgs)
        if not geom.isGeosValid():
            geom = geom.makeValid()
        if geom.intersects(plot_geom):
            inter = plot_geom.intersection(geom)
            if not inter.isEmpty():
                pieces.append(inter)
    if undated:
        warnings.append(f"{undated} loss polygon(s) without a valid year were counted")

    overlap = QgsGeometry.unaryUnion(pieces) if pieces else None  # union avoids double counting
    plot_ha = da.measureArea(plot_geom) / 10_000
    overlap_ha = da.measureArea(overlap) / 10_000 if overlap is not None else 0.0
    pct = 100 * overlap_ha / plot_ha if plot_ha else 0.0

    if overlap_ha < cfg["min_overlap_ha"]:
        status = "NO_LOSS_DETECTED"
    elif pct >= cfg["high_risk_overlap_pct"]:
        status = "HIGH_RISK"
    else:
        status = "REVIEW"

    return {
        "status": status,
        "plot_area_ha": round(plot_ha, 4),
        "overlap_ha": round(overlap_ha, 4),
        "overlap_pct": round(pct, 2),
        "loss_years": sorted(years),
        "cutoff_year": cfg["min_year"],
        "warnings": warnings,
        "overlap_geometry": overlap if overlap_ha >= cfg["min_overlap_ha"] else None,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Forest-loss screening of a plot built from a GPX track")
    ap.add_argument("--gpx", required=True)
    ap.add_argument("--forest-layer", required=True)
    ap.add_argument("--config", help="optional JSON file overriding thresholds")
    a = ap.parse_args()

    cfg = json.load(open(a.config)) if a.config else None
    plot = clean_polygon([(x, y) for x, y, _ in read_gpx_points(a.gpx)])
    if plot["geometry"] is None:
        raise SystemExit(f"Plot could not be built: {plot['report']}")
    res = check_plot(plot["geometry"], load_loss_layer(a.forest_layer), cfg)
    res.pop("overlap_geometry")
    print(json.dumps(res, indent=2))
