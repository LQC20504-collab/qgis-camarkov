# CA-Markov Land Change Prediction

QGIS Processing provider for CA-Markov land-use change modelling, with three
algorithms: `camarkov:analyze`, `camarkov:train`, `camarkov:predict`.

The bundled engine runs in a separate Python subprocess so it never loads GDAL
into the QGIS process.

Requires `numpy`, `scipy`, `scikit-learn`, `rasterio` and `matplotlib`.
QGIS 3.28 or newer (validated on 3.40.15 LTR). All input rasters must share
the same grid and CRS.

Full documentation (Chinese), installation notes and troubleshooting:
<https://github.com/LQC20504-collab/qgis-camarkov>

License: GPL-2.0-or-later. The two engine files under `resources/engine/`
remain MIT licensed; see `resources/engine/LICENSE`.
