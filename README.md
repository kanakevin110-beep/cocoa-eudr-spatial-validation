# Cocoa EUDR Spatial Validation & Field-Agent Consistency Check

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![QGIS Core](https://img.shields.io/badge/QGIS-3.28%2B-green.svg)](https://qgis.org/)
[![FOSS4G 2027](https://img.shields.io/badge/FOSS4G-2027--Submission-orange.svg)](https://osgeo.org)

An open-source geospatial toolkit built on **Python and PyQGIS** to clean smallholder cocoa plot polygons, check that the field evidence (GPS track + geotagged photo) is **consistent** with a plot genuinely walked on foot, and prepare EUDR zero-deforestation checks and farmer feedback for cocoa farmers in Cameroon.

> **Project status:** prototype. Modules marked ✅ are implemented and tested on synthetic data; modules marked 🚧 are planned. See [Section 3](#-3-repository-structure--status).

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
├── requirements.txt               # Optional extras (QGIS itself provides the core libraries)
│
├── src/
│   ├── __init__.py
│   ├── qgis_env.py                # ✅ Initialises QGIS for standalone use
│   ├── anti_fraud.py              # ✅ GPX speed + photo EXIF → consistency score
│   ├── spatial_cleaner.py         # ✅ PyQGIS polygon cleaning & topology repair
│   ├── eudr_checker.py            # 🚧 Forest-loss intersection & risk scoring
│   └── notification.py            # 🚧 SMS / WhatsApp feedback to farmers
│
└── data/                          # Synthetic demo data (no real producer data)
    ├── sample_track.gpx           # Demo GPX track
    └── ground_photo.jpg           # Demo geotagged photo
```

### Workflow

```
                       [ Field Data Collection ]
              (GPS device GPX tracks / Geo-tagged ground photos)
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. CONSISTENCY MODULE  ✅   (anti_fraud.py)                     │
│   - Walking-speed profile (≤ 4 km/h)                             │
│   - Survey duration vs. plot perimeter (large plots ≈ 1 h)       │
│   - Photo EXIF time/position vs. GPX track                       │
│   → Consistency Score (0-100) + verdict                          │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. SPATIAL CLEANING ENGINE  ✅   (spatial_cleaner.py)           │
│   - Duplicate / jitter vertex removal                            │
│   - Self-intersection repair (QgsGeometry.makeValid)             │
│   - Coordinate precision normalisation, overlap detection        │
│   - Ellipsoidal area & perimeter                                 │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. EUDR SATELLITE CROSS-CHECK  🚧                               │
│   - Intersection with forest-cover loss after 31 Dec 2020        │
│   - Deforestation risk % per plot                                │
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

## 🧰 5. Installation & Prerequisites

### Prerequisites
* **QGIS 3.28 LTS or newer.** It bundles Python, PyQGIS, GDAL, GEOS and PROJ. No other dependency is required for the implemented modules.

### Option A: inside QGIS (Python Console)
```python
import sys
sys.path.append(r"C:\path\to\cocoa-eudr-spatial-validation")

from src.anti_fraud import verify_consistency
from src.spatial_cleaner import (read_gpx_points, clean_polygon,
                                 build_layer, add_to_project)

pts = read_gpx_points(r"C:\path\to\data\sample_track.gpx")
plot = clean_polygon([(x, y) for x, y, _ in pts])
print(plot["report"])

report = verify_consistency(r"C:\path\to\data\sample_track.gpx",
                            r"C:\path\to\data\ground_photo.jpg",
                            plot_perimeter_m=plot["report"]["perimeter_m"],
                            cfg={"photo_default_utc_offset_h": 1})   # Cameroon = UTC+1
print(report["consistency_score"], report["verdict"])

add_to_project(build_layer({"plot_1": plot["geometry"]},
                           {"plot_1": {"consistency": report["consistency_score"]}}))
```

### Option B: standalone (command line)
On Windows, open the **OSGeo4W Shell** installed with QGIS, then:

```bash
git clone https://github.com/kanakevin110-beep/cocoa-eudr-spatial-validation.git
cd cocoa-eudr-spatial-validation

python src/spatial_cleaner.py --gpx data/sample_track.gpx --out cleaned_plot.gpkg
python src/anti_fraud.py --gpx data/sample_track.gpx --photo data/ground_photo.jpg --perimeter-m 795
```

---

## 🚀 6. Example Output

Illustrative output on the synthetic demo data (a ~4 ha square plot walked in 25 minutes):

```text
$ python src/spatial_cleaner.py --gpx data/sample_track.gpx --out cleaned_plot.gpkg
{
  "input_vertices": 151,
  "vertices_after_dedup": 151,
  "was_valid": true,
  "area_ha": 3.978,
  "perimeter_m": 794.8,
  "is_valid": true
}
Saved cleaned_plot.gpkg

$ python src/anti_fraud.py --gpx data/sample_track.gpx --photo data/ground_photo.jpg --perimeter-m 795
{
  "consistency_score": 100,
  "verdict": "CONSISTENT",
  "speed":  { "limit_kmh": 4.0, "max_kmh": 1.92, "duration_min": 25.0, "min_expected_min": 9.5 },
  "photo":  { "distance_to_track_m": 2.3, ... },
  ...
}
```

The same track replayed at 10× speed (≈ 19 km/h, e.g. on a motorbike) fails the walking-speed check, and the score drops accordingly.

> Pass `--config settings.json` to override thresholds, e.g. `{"photo_default_utc_offset_h": 1}` when the camera has no GPS time and stores local time (Cameroon is UTC+1).

---

## 🔒 7. Data Protection

Plot coordinates, farmer names and phone numbers are personal data. This public repository contains **only synthetic demonstration data**. Never commit real producer data.

---

## 📄 8. Open Source License & FOSS4G / OSGeo Contribution

Distributed under the **MIT License**. See `LICENSE` for more information.

### OSGeo / FOSS4G 2027
This project demonstrates the power of **Free and Open Source Software for Geospatial (FOSS4G)** in solving compliance and sustainability challenges in smallholder agriculture across West and Central Africa.

Presented for the **FOSS4G 2027 Travel Grant Program (TGP)** by **Open Source Geospatial Community Advocates in Cameroon**.
