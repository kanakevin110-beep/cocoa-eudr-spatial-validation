"""
qgis_env.py - Make the PyQGIS modules usable both inside QGIS and as standalone scripts.

* Inside QGIS (Python console / Processing script): QGIS is already initialised, nothing to do.
* Standalone: run from the "OSGeo4W Shell" (Windows) or any environment where `import qgis` works.
  The prefix path is read from QGIS_PREFIX_PATH (set automatically by OSGeo4W / python-qgis.bat).
"""
import os

_app = None  # keep a reference so the QgsApplication is not garbage-collected


def ensure_qgis():
    """Initialise QgsApplication if no QGIS instance is running yet."""
    global _app
    from qgis.core import QgsApplication

    if QgsApplication.instance() is not None:
        return QgsApplication.instance()

    prefix = os.environ.get("QGIS_PREFIX_PATH")
    if prefix:
        QgsApplication.setPrefixPath(prefix, True)
    _app = QgsApplication([], False)  # False = no GUI
    _app.initQgis()
    return _app
