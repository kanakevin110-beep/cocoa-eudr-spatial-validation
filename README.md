# Cocoa EUDR Spatial Validation & Field-Agent Consistency Check

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![QGIS Core](https://img.shields.io/badge/QGIS-3.28%2B-green.svg)](https://qgis.org/)
[![FOSS4G 2027](https://img.shields.io/badge/FOSS4G-2027--Submission-orange.svg)](https://osgeo.org)

An open-source geospatial toolkit built on **Python and PyQGIS** to clean smallholder cocoa plot polygons, check that the field evidence (GPS track + geotagged photo) is **consistent** with a plot genuinely walked on foot, and screen plots against post-2020 forest loss for EUDR purposes. A farmer-feedback module is planned.

> **Project status:** prototype. Modules marked ✅ are implemented and tested on synthetic data; the module marked 🚧 is planned. See [Section 3](#-3-repository-structure--status).

---

## 📋 1. Project Overview & EUDR Context in Cameroon

The **European Union Deforestation Regulation (EUDR)** requires full geolocation and spatial verification for all cocoa imported into the EU market. Farms established or expanded on land deforested after December 31, 2020, are barred from supply chains.

In Central Africa, and particularly across Cameroon's cocoa-producing regions, field traceability agents face several operational challenges:
* **Field data degradation:** GPS devices and mobile surveys produce raw GPX tracks affected by signal jitter, self-intersecting boundaries, duplicate vertices and micro-overlaps.
* **Armchair mapping & data fraud:** High travel friction in remote forest areas can lead some collectors to digitize boundaries remotely or reuse photos, which compromises audit integrity.
* **Lack of farmer feedback:** Smallholders rarely receive actionable feedback on whether their plot boundaries comply with EUDR rules or how to correct errors.

`cocoa-eudr-spatial-validation` addresses these challenges with **100% Free and Open Source Software (FOSS)**, running directly on **QGIS**.

---

## 🧭 2. Field Survey Assumptions

The consistency checks are calibrated on how plot mapping is actually carried out in the field:

| Parameter | Default | Rationale |
|---|---|---|
| Walking speed while mapping | **≤ 4 km/h** | An agent walks the plot boundary on foot, often through dense plantation. Faster movement suggests a vehicle or a track not walked on the plot. |
| Survey duration for a large plot | **up to ~1 hour** | Mapping a large plot can take about an hour. A long survey is **not** penalised; only durations above 90 min raise an informational warning. |
| Minimum plausible duration | perimeter ÷ 4 km/h (×0.8 margin) | The perimeter cannot be walked faster than the speed limit. At 4 km/h, one hour covers a boundary of roughly 4 km. |
| Photo time window | survey start/end ± 15 min | The photo should be taken during the survey. |
| Photo distance to track | ≤ 100 m | The photo should be taken on or near the walked boundary. |
| Tolerated speed outliers | ≤ 5 % of segments | Absorbs isolated GPS jitter spikes. |

All values are configurable (`DEFAULT_CONFIG` in `src/anti_fraud.py`, or a JSON file passed with `--config`) and should be adjusted to local field conditions.

---

## 🏗️ 3. Repository Structure & Status

```
cocoa-eudr-spatial-validation/
├── LICENSE                        # MIT License file
├── README.md                      # Project documentation
├── requirements.txt               # Notes on dependencies (QGIS provides the core libraries)
│
├── src/
│   ├── __init__.py
│   ├── qgis_env.py                # ✅ Initialises QGIS for standalone use
│   ├── spatial_cleaner.py         # ✅ PyQGIS polygon cleaning & topology repair
│   ├── anti_fraud.py              # ✅ GPX speed + photo EXIF → consistency score
│   ├── eudr_checker.py            # ✅ Forest-loss intersection & risk screening
│   └── notification.py            # 🚧 SMS / WhatsApp feedback to farmers
│
├── scripts/
│   └── run_pipeline.py            # ✅ Runs steps 1-3 for one plot
│
└── data/                          # Synthetic demo data (no real producer data)
    ├── sample_track.gpx           # Demo GPX track
    ├── ground_photo.jpg           # Demo geotagged photo
    └── forest_loss_sample.geojson # Demo forest-loss polygons (2019 and 2022)
```

### Workflow

```
                       [ Field Data Collection ]
              (GPS device GPX tracks / Geo-tagged ground photos)
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. SPATIAL CLEANING ENGINE  ✅   (spatial_cleaner.py)           │
│   - Duplicate / jitter vertex removal                            │
│   - Self-intersection repair (QgsGeometry.makeValid)             │
│   - Coordinate precision normalisation, overlap detection        │
│   - Ellipsoidal area & perimeter                                 │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. CONSISTENCY MODULE  ✅   (anti_fraud.py)                     │
│   - Walking-speed profile (≤ 4 km/h)                             │
│   - Survey duration vs. plot perimeter (large plots ≈ 1 h)       │
│   - Photo EXIF time/position vs. GPX track                       │
│   → Consistency Score (0-100) + verdict                          │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. FOREST-LOSS SCREENING  ✅   (eudr_checker.py)                │
│   - Intersection with forest loss after 31 Dec 2020              │
│   - Overlap in ha and % of plot → screening status               │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. FARMER FEEDBACK  🚧                                          │
│   - Plot diagnostic and boundary-correction recommendations      │
│   - SMS / WhatsApp delivery                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 4. The Consistency Score

`anti_fraud.py` returns a **Consistency Score from 0 to 100**: the share of checks that the field evidence passes.

| Check | Weight |
|---|---|
| Walking speed ≤ 4 km/h | 25 |
| Survey duration ≥ time needed to walk the perimeter | 15 |
| Photo carries EXIF time | 10 |
| Photo carries EXIF GPS position | 10 |
| Photo taken during the survey window | 20 |
| Photo taken near the track (≤ 100 m) | 20 |

Checks that lack the required data (for example, no perimeter supplied) are left out and the score is rescaled.

| Score | Verdict | Meaning |
|---|---|---|
| 90 – 100 | `CONSISTENT` | Evidence is coherent with a plot walked on foot. |
| 50 – 89 | `REVIEW` | Some checks failed; send to a supervisor. |
| 0 – 49 | `INCONSISTENT` | Evidence contradicts a genuine field survey; re-survey recommended. |

> ⚠️ **The score is a screening indicator, not proof of presence.** EXIF metadata and GPX files can be edited. A high score means the evidence is internally coherent; it does not replace supervision, spot checks or satellite cross-validation.

---

## 🌳 5. Forest-Loss Screening & Overall Decision

`eudr_checker.py` intersects the cleaned plot with a polygon layer of forest loss that **you supply** (for example derived from Global Forest Watch / Hansen data, in any CRS and any vector format QGIS reads). Only loss from **2021 onwards** counts, in line with the EUDR cut-off of 31 December 2020. Overlapping loss polygons are merged first, so no area is counted twice.

| Setting | Default | Meaning |
|---|---|---|
| `year_field` | `year` | Attribute holding the loss year (4-digit, or Hansen-style 2-digit such as `22`). |
| `min_year` | `2021` | Earlier loss is ignored. |
| `min_overlap_ha` | `0.005` | Smaller overlaps are treated as positional noise. |
| `high_risk_overlap_pct` | `5.0` | Share of the plot above which the status is `HIGH_RISK`. |

| Status | Meaning |
|---|---|
| `NO_LOSS_DETECTED` | No post-2020 loss overlaps the plot. |
| `REVIEW` | A small overlap exists; check with satellite imagery. |
| `HIGH_RISK` | Overlap at or above the threshold; investigate before the plot enters the supply chain. |

> ⚠️ **This is screening, not a legal compliance decision.** Forest-loss layers also capture shade-tree removal, harvests and fires, so a flag does not prove deforestation, and the absence of a flag does not prove compliance. A person must review every flagged plot.

`run_pipeline.py` combines the steps into one **overall outcome**:

| Outcome | When |
|---|---|
| `RESURVEY_RECOMMENDED` | The plot could not be built, or the consistency verdict is `INCONSISTENT`. |
| `HIGH_RISK` | Forest-loss status is `HIGH_RISK`. |
| `MANUAL_REVIEW` | Consistency verdict or forest-loss status is `REVIEW`, or any warning was raised. |
| `PASSED_SCREENING` | Consistent evidence and no post-2020 loss detected. |

None of these outcomes is an automatic approval: they decide what a supervisor looks at next.

---

## 🧰 6. Installation & Prerequisites

### Prerequisites
* **QGIS 3.28 LTS or newer.** It bundles Python, PyQGIS, GDAL, GEOS and PROJ. No other dependency is required for the implemented modules.

### Option A: inside QGIS (Python Console)
```python
import sys
sys.path.append(r"C:\path\to\cocoa-eudr-spatial-validation")

from src.spatial_cleaner import read_gpx_points, clean_polygon, build_layer, add_to_project
from src.anti_fraud import verify_consistency
from src.eudr_checker import load_loss_layer, check_plot

gpx   = r"C:\path\to\data\sample_track.gpx"
photo = r"C:\path\to\data\ground_photo.jpg"
loss  = r"C:\path\to\data\forest_loss_sample.geojson"

plot = clean_polygon([(x, y) for x, y, _ in read_gpx_points(gpx)])
cons = verify_consistency(gpx, photo, plot["report"]["perimeter_m"],
                          cfg={"photo_default_utc_offset_h": 1})   # Cameroon = UTC+1
eudr = check_plot(plot["geometry"], load_loss_layer(loss))

print(plot["report"]); print(cons["consistency_score"], cons["verdict"]); print(eudr["status"])
add_to_project(build_layer({"plot_1": plot["geometry"]},
                           {"plot_1": {"consistency": cons["consistency_score"],
                                       "loss_overlap_pct": eudr["overlap_pct"],
                                       "eudr_status": eudr["status"]}}))
```

### Option B: standalone (command line)
On Windows, open the **OSGeo4W Shell** installed with QGIS, then:

```bash
git clone https://github.com/kanakevin110-beep/cocoa-eudr-spatial-validation.git
cd cocoa-eudr-spatial-validation

python scripts/run_pipeline.py \
  --gpx data/sample_track.gpx \
  --photo data/ground_photo.jpg \
  --forest-layer data/forest_loss_sample.geojson \
  --plot-id DEMO-001 \
  --out results/DEMO-001.gpkg \
  --report results/DEMO-001.json
```

Each module can also be run on its own: `python src/spatial_cleaner.py`, `python src/anti_fraud.py`, `python src/eudr_checker.py` (add `--help` for options).

---

## 🚀 7. Example Output

Output of `run_pipeline.py` on the synthetic demo data (a ~4 ha square plot walked in 25 minutes):

```text
[INFO] Starting validation pipeline for plot DEMO-001
[STEP 1/3] Cleaning & repairing plot boundary...
  --> Vertices: 151 -> 151
  --> Area: 3.978 ha | Perimeter: 794.8 m
[STEP 2/3] Checking field-evidence consistency...
  --> Speed: max 1.92 km/h (limit 4.0) | duration 25.0 min
  --> Photo distance to track: 2.3 m
  --> CONSISTENCY SCORE: 100/100 (CONSISTENT)
[STEP 3/3] Screening against forest loss after 31 Dec 2020...
  --> Overlap: 0.0 ha (0.0% of plot)
  --> SCREENING STATUS: NO_LOSS_DETECTED
[RESULT] PASSED_SCREENING  (screening only: a person makes the final decision)
[INFO] Plot saved to results/DEMO-001.gpkg
[INFO] Report saved to results/DEMO-001.json
```

Notes on the demo data:
* `forest_loss_sample.geojson` contains a **2019** loss polygon inside the plot; it is ignored because it predates the cut-off. A 2022 polygon lies far from the plot.
* With a 2022 loss polygon covering part of the plot (0.74 ha, 18.5 % of the plot), the status becomes `HIGH_RISK`.
* The same track replayed about 10× faster (≈ 19 km/h) fails the walking-speed and duration checks, and the score falls to 60/100 (`REVIEW`).

> Pass `--config settings.json` to override thresholds, and `--utc-offset 1` (the default) when the camera has no GPS time and stores local time (Cameroon is UTC+1).

---

## 🔒 8. Data Protection

Plot coordinates, farmer names and phone numbers are personal data. This public repository contains **only synthetic demonstration data**. Never commit real producer data.

---

## 📄 9. Open Source License & FOSS4G / OSGeo Contribution

Distributed under the **MIT License**. See `LICENSE` for more information.

### OSGeo / FOSS4G 2027
This project demonstrates the power of **Free and Open Source Software for Geospatial (FOSS4G)** in solving compliance and sustainability challenges in smallholder agriculture across West and Central Africa.

Presented for the **FOSS4G 2027 Travel Grant Program (TGP)** by **Open Source Geospatial Community Advocates in Cameroon**.
