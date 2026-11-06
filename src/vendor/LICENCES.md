# Bibliothèques intégrées à la page

Copies, sans modification, des fichiers publiés sur npm (téléchargés depuis jsDelivr). `build.py` les insère dans `docs/index.html`, qui fonctionne ainsi hors ligne.

| Fichier | Bibliothèque | Version | Licence | Source |
|---|---|---|---|---|
| `leaflet.js`, `leaflet.css` | Leaflet | 1.9.4 | BSD-2-Clause | https://leafletjs.com |
| `leaflet.markercluster.js`, `MarkerCluster.css` | Leaflet.markercluster | 1.5.3 | MIT | https://github.com/Leaflet/Leaflet.markercluster |
| `topojson-client.min.js` | topojson-client | 3.1.0 | ISC | https://github.com/topojson/topojson-client |

Pour changer de version : remplacer le fichier par celui de `https://cdn.jsdelivr.net/npm/<bibliothèque>@<version>/dist/…`, mettre à jour ce tableau et la liste `LIBS` de `build.py`, puis vérifier la page avec `python scripts/check_page.py`.
