# Bibliothèques et polices intégrées à la page

Copies, sans modification, de fichiers publiés : bibliothèques npm téléchargées depuis jsDelivr, polices téléchargées depuis Google Fonts (sous-ensemble latin, format WOFF2). `build.py` les insère dans `docs/index.html`, qui fonctionne ainsi hors ligne.

| Fichier | Bibliothèque ou police | Version | Licence | Source |
|---|---|---|---|---|
| `leaflet.js`, `leaflet.css` | Leaflet | 1.9.4 | BSD-2-Clause | https://leafletjs.com |
| `leaflet.markercluster.js`, `MarkerCluster.css` | Leaflet.markercluster | 1.5.3 | MIT | https://github.com/Leaflet/Leaflet.markercluster |
| `topojson-client.min.js` | topojson-client | 3.1.0 | ISC | https://github.com/topojson/topojson-client |
| `fonts/montserrat-latin.woff2` | Montserrat (graisses 400 à 800), police des titres de la charte RATP Dev | Google Fonts v31 | SIL Open Font License 1.1 (`fonts/OFL-Montserrat.txt`) | https://fonts.google.com/specimen/Montserrat |
| `fonts/carlito-latin-*.woff2` | Carlito (normal, gras, italique), équivalent libre de Calibri, substitut de Parisine Office admis par la charte | Google Fonts v4 | SIL Open Font License 1.1 (`fonts/OFL-Carlito.txt`) | https://fonts.google.com/specimen/Carlito |

Pour changer de version d'une bibliothèque : remplacer le fichier par celui de `https://cdn.jsdelivr.net/npm/<bibliothèque>@<version>/dist/…`, mettre à jour ce tableau et la liste `LIBS` de `build.py`, puis vérifier la page avec `python scripts/check_page.py`.

Pour une police : récupérer l'adresse du fichier « latin » dans `https://fonts.googleapis.com/css2?family=<Police>…` (avec un navigateur récent), remplacer le fichier, puis mettre à jour ce tableau et la liste `FONTS` de `build.py`.
