"""
anti_fraud.py - Field-agent consistency checks, PyQGIS version (prototype).

Compares the GPX track walked by the agent with a geotagged photo and computes a
CONSISTENCY SCORE (0-100). The score measures whether the evidence is coherent
(pedestrian speed, realistic survey duration, photo taken during the survey and near
the track). It is a screening indicator, not proof of presence: EXIF data can be edited,
so low or doubtful scores go to human review.

Checks (weights in WEIGHTS):
  1. speed_pedestrian   - walking speed <= 4 km/h (tolerating a few GPS jitter spikes)
  2. duration_plausible - the survey lasted at least the time needed to walk the perimeter
                          at 4 km/h (checked only when the plot perimeter is supplied)
  3. photo_has_time / photo_has_gps - the photo carries EXIF time and position
  4. photo_in_time_window - photo taken during the survey (+/- tolerance)
  5. photo_near_track   - photo taken close to the walked track

Large plots can legitimately take about one hour to map: a long survey is NOT penalised;
it only raises an informational warning beyond `long_survey_warning_min`.

QGIS components used: QgsDistanceArea (ellipsoidal distances); GDAL (bundled with QGIS)
for EXIF. No Pillow needed.

Usage (OSGeo4W Shell or QGIS Python):
    python src/anti_fraud.py --gpx data/sample_track.gpx --photo data/ground_photo.jpg
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

try:
    from .qgis_env import ensure_qgis
except ImportError:  # run as a plain script
    from qgis_env import ensure_qgis

ensure_qgis()
from osgeo import gdal  # noqa: E402
gdal.UseExceptions()
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransformContext  # noqa: E402
from qgis.core import QgsDistanceArea, QgsPointXY  # noqa: E402

DEFAULT_CONFIG = {
    "max_walk_speed_kmh": 4.0,         # walking speed while mapping a plot
    "max_outlier_ratio": 0.05,         # tolerated share of segments above the limit (GPS jitter)
    "min_segment_seconds": 1.0,        # ignore near-simultaneous points
    "duration_margin": 0.8,            # survey must last >= 80 % of perimeter / speed limit
    "long_survey_warning_min": 90,     # a large plot can take ~60 min; warn beyond this
    "photo_time_tolerance_min": 15,    # photo may be this far outside the survey window
    "photo_max_distance_m": 100.0,     # max distance photo <-> nearest track point
    "photo_default_utc_offset_h": 0,   # used when EXIF has no GPS time (Cameroon = +1)
    "verdict_consistent": 90,
    "verdict_review": 50,
}

WEIGHTS = {"speed_pedestrian": 25, "duration_plausible": 15, "photo_has_time": 10,
           "photo_has_gps": 10, "photo_in_time_window": 20, "photo_near_track": 20}


# --------------------------------------------------------------------------- #
# Distances (QGIS, WGS84 ellipsoid)
# --------------------------------------------------------------------------- #
def make_distance_area() -> QgsDistanceArea:
    da = QgsDistanceArea()
    da.setSourceCrs(QgsCoordinateReferenceSystem("EPSG:4326"), QgsCoordinateTransformContext())
    da.setEllipsoid("WGS84")
    return da


def distance_m(da: QgsDistanceArea, lon1, lat1, lon2, lat2) -> float:
    return da.measureLine(QgsPointXY(lon1, lat1), QgsPointXY(lon2, lat2))


# --------------------------------------------------------------------------- #
# GPX (parsed with the standard library: robust UTC timestamps for Garmin files)
# --------------------------------------------------------------------------- #
def _parse_time(text: str | None):
    if not text:
        return None
    dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def read_gpx_points(path: str):
    """Return [(lon, lat, utc_time_or_None)] from track points (falls back to route points)."""
    root = ET.parse(path).getroot()

    def collect(tag):
        out = []
        for el in root.iter():
            if el.tag.split("}")[-1] == tag:
                t = next((c.text for c in el if c.tag.split("}")[-1] == "time"), None)
                out.append((float(el.get("lon")), float(el.get("lat")), _parse_time(t)))
        return out

    return collect("trkpt") or collect("rtept")


def analyze_speed(points, da, cfg=DEFAULT_CONFIG) -> dict:
    if len(points) < 2 or any(p[2] is None for p in points):
        return {"ok": False, "reason": "GPX needs >= 2 points with timestamps"}

    speeds = []
    for (x1, y1, t1), (x2, y2, t2) in zip(points, points[1:]):
        dt = (t2 - t1).total_seconds()
        if dt >= cfg["min_segment_seconds"]:
            speeds.append(distance_m(da, x1, y1, x2, y2) / dt * 3.6)
    if not speeds:
        return {"ok": False, "reason": "No usable segments"}

    ratio = sum(s > cfg["max_walk_speed_kmh"] for s in speeds) / len(speeds)
    duration_min = (points[-1][2] - points[0][2]).total_seconds() / 60
    return {
        "ok": ratio <= cfg["max_outlier_ratio"],
        "limit_kmh": cfg["max_walk_speed_kmh"],
        "max_kmh": round(max(speeds), 2),
        "mean_kmh": round(statistics.fmean(speeds), 2),
        "p95_kmh": round(sorted(speeds)[int(0.95 * (len(speeds) - 1))], 2),
        "outlier_ratio": round(ratio, 3),
        "start": points[0][2].isoformat(),
        "end": points[-1][2].isoformat(),
        "duration_min": round(duration_min, 1),
    }


# --------------------------------------------------------------------------- #
# Photo EXIF (via GDAL, bundled with QGIS)
# --------------------------------------------------------------------------- #
def _numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text or "")]


def _dms(text, ref):
    d, m, s = (_numbers(text) + [0, 0, 0])[:3]
    deg = d + m / 60 + s / 3600
    return -deg if (ref or "").strip() in ("S", "W") else deg


def read_photo_exif(path: str, cfg=DEFAULT_CONFIG) -> dict:
    out = {"time_utc": None, "lat": None, "lon": None, "camera": None}
    ds = gdal.Open(path)
    md = ds.GetMetadata() if ds else {}
    ds = None
    out["camera"] = " ".join(filter(None, [md.get("EXIF_Make", "").strip(),
                                           md.get("EXIF_Model", "").strip()])) or None

    if md.get("EXIF_GPSLatitude") and md.get("EXIF_GPSLongitude"):
        out["lat"] = _dms(md["EXIF_GPSLatitude"], md.get("EXIF_GPSLatitudeRef"))
        out["lon"] = _dms(md["EXIF_GPSLongitude"], md.get("EXIF_GPSLongitudeRef"))

    try:  # prefer GPS date/time (UTC); else DateTimeOriginal + offset
        if md.get("EXIF_GPSDateStamp") and md.get("EXIF_GPSTimeStamp"):
            h, m, s = (_numbers(md["EXIF_GPSTimeStamp"]) + [0, 0, 0])[:3]
            d = datetime.strptime(md["EXIF_GPSDateStamp"].strip(), "%Y:%m:%d")
            out["time_utc"] = d.replace(hour=int(h), minute=int(m), second=int(s), tzinfo=timezone.utc)
        else:
            raw = md.get("EXIF_DateTimeOriginal") or md.get("EXIF_DateTime")
            if raw:
                local = datetime.strptime(raw.strip(), "%Y:%m:%d %H:%M:%S")
                tz = timezone(timedelta(hours=cfg["photo_default_utc_offset_h"]))
                out["time_utc"] = local.replace(tzinfo=tz).astimezone(timezone.utc)
    except ValueError:
        pass
    return out


# --------------------------------------------------------------------------- #
# Combined consistency check
# --------------------------------------------------------------------------- #
def verify_consistency(gpx_path: str, photo_path: str, plot_perimeter_m: float | None = None,
                       cfg: dict | None = None) -> dict:
    """
    Run all checks and return the consistency report.
    plot_perimeter_m: perimeter of the cleaned polygon (from spatial_cleaner), optional.
    """
    cfg = {**DEFAULT_CONFIG, **(cfg or {})}
    da = make_distance_area()
    points = read_gpx_points(gpx_path)
    speed = analyze_speed(points, da, cfg)
    photo = read_photo_exif(photo_path, cfg)
    warnings = []

    checks = {"speed_pedestrian": speed["ok"],
              "photo_has_time": photo["time_utc"] is not None,
              "photo_has_gps": photo["lat"] is not None}

    # duration vs perimeter: cannot walk the perimeter faster than the speed limit
    if plot_perimeter_m and "duration_min" in speed:
        min_minutes = cfg["duration_margin"] * plot_perimeter_m / (cfg["max_walk_speed_kmh"] * 1000 / 60)
        checks["duration_plausible"] = speed["duration_min"] >= min_minutes
        speed["min_expected_min"] = round(min_minutes, 1)
    if speed.get("duration_min", 0) > cfg["long_survey_warning_min"]:
        warnings.append(f"Long survey ({speed['duration_min']} min): check for stops or a second plot")

    # time proximity
    if checks["photo_has_time"] and speed.get("start"):
        tol = timedelta(minutes=cfg["photo_time_tolerance_min"])
        checks["photo_in_time_window"] = (points[0][2] - tol) <= photo["time_utc"] <= (points[-1][2] + tol)
    else:
        checks["photo_in_time_window"] = False

    # space proximity
    dist = None
    if checks["photo_has_gps"]:
        dist = min(distance_m(da, photo["lon"], photo["lat"], x, y) for x, y, _ in points)
        checks["photo_near_track"] = dist <= cfg["photo_max_distance_m"]
    else:
        checks["photo_near_track"] = False

    applicable = {k: w for k, w in WEIGHTS.items() if k in checks}  # skip checks lacking data
    score = round(100 * sum(w for k, w in applicable.items() if checks[k]) / sum(applicable.values()))
    verdict = ("CONSISTENT" if score >= cfg["verdict_consistent"]
               else "REVIEW" if score >= cfg["verdict_review"] else "INCONSISTENT")

    return {
        "consistency_score": score,
        "verdict": verdict,
        "checks": checks,
        "warnings": warnings,
        "speed": speed,
        "photo": {**photo, "time_utc": photo["time_utc"].isoformat() if photo["time_utc"] else None,
                  "distance_to_track_m": round(dist, 1) if dist is not None else None},
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="GPX / photo consistency check")
    ap.add_argument("--gpx", required=True)
    ap.add_argument("--photo", required=True)
    ap.add_argument("--perimeter-m", type=float, help="plot perimeter from spatial_cleaner")
    ap.add_argument("--config", help="optional JSON file overriding thresholds")
    a = ap.parse_args()
    user_cfg = json.load(open(a.config)) if a.config else None
    print(json.dumps(verify_consistency(a.gpx, a.photo, a.perimeter_m, user_cfg),
                     indent=2, ensure_ascii=False))
