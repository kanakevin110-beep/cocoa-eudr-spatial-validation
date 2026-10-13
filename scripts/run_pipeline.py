"""
run_pipeline.py - Run the validation pipeline for one plot (prototype).

  1. Spatial cleaning        (spatial_cleaner.py)
  2. Consistency check       (anti_fraud.py)   - uses the cleaned plot's perimeter
  3. Forest-loss screening   (eudr_checker.py) - optional, needs --forest-layer
  Step 4 (farmer notification) is not implemented yet.

Run from the OSGeo4W Shell (Windows) or any environment where PyQGIS is available:

    python scripts/run_pipeline.py --gpx data/sample_track.gpx --photo data/ground_photo.jpg \
        --forest-layer data/forest_loss_sample.geojson --plot-id DEMO-001 \
        --utc-offset 1 --out results/DEMO-001.gpkg --report results/DEMO-001.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.anti_fraud import read_gpx_points, verify_consistency  # noqa: E402
from src.eudr_checker import check_plot, load_loss_layer  # noqa: E402
from src.spatial_cleaner import build_layer, clean_polygon, save_plots  # noqa: E402


def decide(plot_report, consistency, eudr) -> str:
    """Overall screening outcome. Always ends with a human decision, never an automatic approval."""
    if consistency["verdict"] == "INCONSISTENT":
        return "RESURVEY_RECOMMENDED"
    if eudr and eudr["status"] == "HIGH_RISK":
        return "HIGH_RISK"
    if (consistency["verdict"] == "REVIEW" or (eudr and eudr["status"] == "REVIEW")
            or plot_report["warnings"] or consistency["warnings"]):
        return "MANUAL_REVIEW"
    return "PASSED_SCREENING" if eudr else "PASSED_CONSISTENCY_ONLY"


def run(args) -> dict:
    cfg = json.load(open(args.config)) if args.config else {}
    cfg.setdefault("photo_default_utc_offset_h", args.utc_offset)
    print("[INFO] Starting validation pipeline for plot", args.plot_id)

    # Step 1 - cleaning
    print("[STEP 1/3] Cleaning & repairing plot boundary...")
    points = read_gpx_points(args.gpx)
    plot = clean_polygon([(x, y) for x, y, _ in points], cfg)
    pr = plot["report"]
    if plot["geometry"] is None:
        print("  --> FAILED:", "; ".join(pr["warnings"]))
        return {"plot_id": args.plot_id, "decision": "RESURVEY_RECOMMENDED", "cleaning": pr}
    print(f"  --> Vertices: {pr['input_vertices']} -> {pr['vertices_after_dedup']}"
          f"{' | repaired self-intersections' if pr.get('repaired') else ''}")
    print(f"  --> Area: {pr['area_ha']} ha | Perimeter: {pr['perimeter_m']} m")
    for w in pr["warnings"]:
        print("  --> WARNING:", w)

    # Step 2 - consistency
    print("[STEP 2/3] Checking field-evidence consistency...")
    cons = verify_consistency(args.gpx, args.photo, pr["perimeter_m"], cfg)
    sp = cons["speed"]
    if "max_kmh" in sp:
        print(f"  --> Speed: max {sp['max_kmh']} km/h (limit {sp['limit_kmh']}) | "
              f"duration {sp['duration_min']} min")
    print(f"  --> Photo distance to track: {cons['photo']['distance_to_track_m']} m")
    print(f"  --> CONSISTENCY SCORE: {cons['consistency_score']}/100 ({cons['verdict']})")
    for w in cons["warnings"]:
        print("  --> WARNING:", w)

    # Step 3 - forest-loss screening
    eudr = None
    if args.forest_layer:
        print("[STEP 3/3] Screening against forest loss after 31 Dec 2020...")
        eudr = check_plot(plot["geometry"], load_loss_layer(args.forest_layer), cfg)
        print(f"  --> Overlap: {eudr['overlap_ha']} ha ({eudr['overlap_pct']}% of plot)")
        print(f"  --> SCREENING STATUS: {eudr['status']}")
        for w in eudr["warnings"]:
            print("  --> WARNING:", w)
    else:
        print("[STEP 3/3] Skipped (no --forest-layer given)")

    decision = decide(pr, cons, eudr)
    print(f"[RESULT] {decision}  (screening only: a person makes the final decision)")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        extra = {"consistency": cons["consistency_score"],
                 "loss_overlap_pct": eudr["overlap_pct"] if eudr else None,
                 "eudr_status": eudr["status"] if eudr else None}
        save_plots(build_layer({args.plot_id: plot["geometry"]}, {args.plot_id: extra}), args.out)
        print("[INFO] Plot saved to", args.out)

    report = {"plot_id": args.plot_id, "decision": decision, "cleaning": pr,
              "consistency": cons, "eudr": {k: v for k, v in eudr.items() if k != "overlap_geometry"}
              if eudr else None}
    if args.report:
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print("[INFO] Report saved to", args.report)
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Validation pipeline for one plot")
    ap.add_argument("--gpx", required=True)
    ap.add_argument("--photo", required=True)
    ap.add_argument("--forest-layer", help="polygon layer of forest loss (GeoJSON/GPKG/SHP)")
    ap.add_argument("--plot-id", default="plot_1")
    ap.add_argument("--utc-offset", type=float, default=1.0,
                    help="camera local-time offset from UTC when EXIF has no GPS time (Cameroon = 1)")
    ap.add_argument("--config", help="JSON file overriding thresholds")
    ap.add_argument("--out", help="output GeoPackage/GeoJSON for the cleaned plot")
    ap.add_argument("--report", help="output JSON report")
    run(ap.parse_args())
