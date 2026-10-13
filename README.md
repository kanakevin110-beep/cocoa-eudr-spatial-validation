# Cocoa EUDR Spatial Validation & Real-Time Agent Verification

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![QGIS Core](https://img.shields.io/badge/QGIS-3.28%2B-green.svg)](https://qgis.org/)
[![FOSS4G 2027](https://img.shields.io/badge/FOSS4G-2027--Submission-orange.svg)](https://osgeo.org)

An open-source, end-to-end geospatial pipeline developed in Python and PyQGIS to automate smallholder farm plot polygon cleaning, enforce strict field-agent proof-of-presence (anti-fraud verification), cross-check EUDR zero-deforestation compliance using satellite imagery, and deliver real-time diagnostic SMS/WhatsApp reports to cocoa farmers in Cameroon.

---

## 📋 1. Project Overview & EUDR Context in Cameroon

The **European Union Deforestation Regulation (EUDR)** requires full geolocation and spatial verification for all cocoa imported into the EU market. Farms established or expanded on land deforested after December 31, 2020, are strictly barred from supply chains.

In Central Africa—particularly across Cameroon’s cocoa-producing hubs (Centre, South, South-West, East)—field traceability agents face severe operational challenges:
* **Field Data Degradation:** Mobile GPS devices and KoBoToolbox surveys collect raw GPX tracks hampered by signal jitter, self-intersecting boundaries, duplicate vertices, and micro-overlaps.
* **Armchair Mapping & Data Fraud:** High travel friction in remote forest areas leads some field collectors to digitize farm boundaries remotely or forge field photos ("armchair mapping"), compromising audit integrity.
* **Lack of Farmer Feedback:** Smallholders rarely receive actionable feedback regarding whether their plot boundaries comply with EUDR rules or how to correct boundary errors.

`cocoa-eudr-spatial-validation` solves these challenges using **100% Free and Open Source Software (FOSS)**.

---

## 🏗️ 2. Technical Architecture

```
                       [ Field Data Collection ]
         (KoBoToolbox / GPX Tracks / Ground Geo-Tagged Photos)
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                     1. ANTI-FRAUD MODULE                        │
│   - EXIF Metadata Extraction (Timestamps, GPS, Camera Params)   │
│   - Pedestrian Speed Profile & Anisotropy Analysis (≤ 7 km/h)   │
│   - Spatiotemporal Proximity Check (Photo vs GPX Track)        │
└─────────────────────────────────────────────────────────────────┘
                                 │
                   [ Validated Field Data Only ]
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                 2. SPATIAL CLEANING ENGINE                      │
│   - EPSG:4326 / Coordinate Precision Normalization              │
│   - Polygon Topology Repair (Buffer 0, Self-Intersections)      │
│   - Vertex Smoothing & Micro-Gap/Overlap Elimination            │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              3. EUDR SATELLITE CROSS-CHECK MODULE               │
│   - Spatial Intersection with Forest Cover Loss (Hansen/GFW)     │
│   - Sentinel-2 Multi-temporal Canopy Analysis (Post-2020)       │
│   - Deforestation Risk % Calculation                            │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              4. REAL-TIME FARMER DIAGNOSTIC & SMS               │
│   - Automated Compliance Certificate Generation                 │
│   - Twilio / Africa's Talking API SMS & WhatsApp Alerts         │
│   - Corrective Boundary Recommendation Delivery                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📂 3. Repository Structure

```
cocoa-eudr-spatial-validation/
├── LICENSE                        # MIT License file
├── README.md                      # Complete project documentation
├── requirements.txt               # Python dependency manifest
├── config.json                    # Configuration file for thresholds & paths
│
├── src/                           # Core Python source code
│   ├── __init__.py
│   ├── anti_fraud.py              # EXIF photo verification & GPS speed analyzer
│   ├── spatial_cleaner.py         # PyQGIS & GeoPandas polygon topology repair
│   ├── eudr_checker.py            # Satellite layer intersection & risk scoring
│   └── notification.py            # SMS & WhatsApp alert dispatch engine
│
├── scripts/                       # Executable CLI workflows
│   └── run_pipeline.py            # Master script executing steps 1 through 4
│
├── tests/                         # Unit tests
│   ├── test_anti_fraud.py
│   └── test_spatial_cleaner.py
│
└── data/                          # Sample datasets for demonstration (Anonymized)
    ├── sample_track.gpx           # Raw field GPX survey track
    ├── ground_photo.jpg           # Sample geotagged field photo with EXIF
    └── forest_loss_2020.geojson   # Sample post-2020 deforestation vector layer
```

---

## 🧰 4. Installation & Prerequisites

### Prerequisites
* **Python 3.9+**
* **QGIS 3.28 LTS or newer** (with PyQGIS bindings configured in your environment)
* **GDAL / GEOS / PROJ** system libraries

### Environment Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/<your-username>/cocoa-eudr-spatial-validation.git
   cd cocoa-eudr-spatial-validation
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## 🚀 5. Step-by-Step Usage Guide

### Basic Command Line Execution

To process a single farmer's field survey package (GPX file + Geo-tagged Photo + Producer Metadata):

```bash
python scripts/run_pipeline.py \
  --gpx data/sample_track.gpx \
  --photo data/ground_photo.jpg \
  --farmer-id "CMR-2026-8842" \
  --farmer-phone "+237690000000" \
  --forest-layer data/forest_loss_2020.geojson
```

### Expected Execution Output

```text
[INFO] Starting EUDR Spatial Validation Pipeline...
[STEP 1/4] Running Anti-Fraud Verification...
  --> Photo EXIF Timestamp: 2026-10-12 10:14:32 UTC
  --> GPS Track Time Interval: 10:10:00 to 10:45:12
  --> Max Movement Speed: 3.4 km/h (Pedestrian Verified)
  --> SUCCESS: Physical presence confirmed (100% Trust Score).

[STEP 2/4] Cleaning & Repairing Plot Boundaries...
  --> Repaired 2 self-intersections.
  --> Precision set to 6 decimal places (EPSG:4326).
  --> Total Cleaned Surface Area: 1.84 Ha.

[STEP 3/4] Checking EUDR Deforestation Risk...
  --> Overlay with Forest Cover Loss (Post-Dec 31, 2020)...
  --> Overlap Area: 0.00 Ha (0.0%).
  --> COMPLIANCE STATUS: ZERO DEFORESTATION APPROVED.

[STEP 4/4] Sending Producer Diagnostic Notification...
  --> SMS sent via Africa's Talking API to +237690000000:
      "Bonjour Jean, votre parcelle CMR-2026-8842 (1.84 Ha) est CONFORME EUDR (Zéro Déforestation). Merci de préserver vos arbres d'ombrage."
[INFO] Pipeline completed successfully.
```

---

## 📄 6. Open Source License & FOSS4G / OSGeo Contribution

Distributed under the **MIT License**. See `LICENSE` for more information.

### OSGeo / FOSS4G 2027
This project was designed as part of an initiative to demonstrate the power of **Free and Open Source Software for Geospatial (FOSS4G)** in solving critical compliance and sustainability challenges in smallholder agriculture across West and Central Africa.

Presented for the **FOSS4G 2027 Travel Grant Program (TGP)** by **Open Source Geospatial Community Advocates in Cameroon**.