# Risques climatiques des réseaux RATP Dev

Carte interactive des risques climatiques physiques (chaleur, inondation) des 90 réseaux exploités par RATP Dev, horizon 2026–2036, sous trois scénarios climatiques (SSP1-2.6, SSP2-4.5, SSP5-8.5). Pour les réseaux français dont les tracés sont publiés en open data, la carte affiche aussi le plan des lignes et les tronçons exposés à chaque aléa.

La page produite est un fichier HTML unique et autonome : toutes les données y sont intégrées et seules les bibliothèques JavaScript (Leaflet, Leaflet.markercluster, topojson-client) viennent du CDN jsDelivr.

**Version 6** : risque financier (coût annuel estimé) pour la chaleur et l'inondation.

## Démarrage rapide

```bash
python build.py                 # écrit docs/index.html (Python 3.9+, aucune dépendance)
open docs/index.html            # ou double-clic sur le fichier
```

Pour publier la carte avec GitHub Pages : *Settings → Pages → Deploy from a branch → `main` / `docs`*.

Pour vérifier la page (facultatif) :

```bash
pip install -r requirements-dev.txt
playwright install chromium
python scripts/check_page.py    # aucune erreur JS, 90 réseaux, 25 plans de réseau, tronçons affichés
```

## Structure

```
build.py                  assemble src/template.html + data/ → docs/index.html
src/template.html         page : mise en page, styles, logique de la carte (Leaflet)
src/vendor/               feuilles de style Leaflet 1.9.4 et Leaflet.markercluster 1.5.3
data/
  references_raw.json     fiches réseaux extraites du site ratpdev.com (« Nos réseaux »)
  networks.json           90 réseaux nettoyés et géolocalisés (généré par scripts/prepare_networks.py)
  finance.json            budget d'exploitation annuel estimé par réseau (généré par scripts/prepare_finance.py)
  corrections.json        corrections apportées aux fiches source, avec leur motif
  climate_raw.json        indicateurs climatiques par réseau (CCKP, CMIP6 0,25°)
  temp_grids.json         grilles mondiales de température (moyenne annuelle, jour le plus chaud), 0,5°, en PNG
  flood.json              inondation (Aqueduct, crue centennale, ~1 km), relief fin autour des réseaux, altitude des points
  water.json              fleuves, rivières et lacs (TopoJSON)
  lines.json.gz           tracés de 25 réseaux français + exposition inondation par sommet
  geo/                    contours pays, États américains, régions et départements français (TopoJSON)
scripts/
  prepare_networks.py     data/references_raw.json → data/networks.json + data/corrections.json
  prepare_finance.py      data/networks.json → data/finance.json (hypothèses de budget par réseau)
  check_page.py           test de fumée de la page construite (Playwright)
docs/index.html           page construite (servie par GitHub Pages)
```

Pour modifier la carte, éditer `src/template.html` puis relancer `python build.py`. Le gabarit contient des marqueurs (`/*__DATA__*/`, `/*__FLOOD__*/`, etc.) remplacés par les données au moment de la construction.

## Méthode (résumé)

La méthode complète est détaillée dans la page, rubrique « Méthode et sources ».

- **Chaleur** : score sur 100 par réseau, construit à partir des jours ≥ 35 °C, des nuits tropicales, des jours de chaleur humide et de la température maximale annuelle. La référence est 1995–2014. Les valeurs sont des médianes multi-modèles CMIP6 (Banque mondiale, CCKP).
- **Inondation** : le score combine la part de surface inondable dans un rayon de 10 km et la hauteur d'eau moyenne. Il porte sur la crue centennale (fluviale et submersion marine) et est corrigé de la topographie : un réseau situé au-dessus des zones inondées voit son score baisser.
- **Tronçons exposés** :
  - *Inondation* : un tronçon est exposé à partir de 0,1 m d'eau en crue centennale. L'exposition est précalculée par sommet, puis interpolée selon l'année et le scénario.
  - *Chaleur* : on prend la température du jour le plus chaud, corrigée de l'altitude du tracé (−0,65 °C par 100 m). Elle se lit de deux façons :
    - par seuils de température (32, 35, 38, 41 °C) ;
    - par écart à la médiane du réseau, pour repérer ses points chauds.
- **Scénarios** : SSP1-2.6 est approché par RCP4.5 pour l'inondation, car Aqueduct ne fournit que RCP4.5 et RCP8.5.
- **Risque financier** : ordre de grandeur du coût annuel de chaque aléa, en euros 2026, pour chaque année et chaque scénario.
  - *Assiette* : budget d'exploitation annuel estimé de chaque réseau, à partir des chiffres publiés (effectif × 95 k€, flotte, km de ligne, voyages ou population), corrigé d'un indice de coût du pays. Détail dans `scripts/prepare_finance.py`.
  - *Chaleur* : chaque jour ≥ 35 °C, nuit tropicale ou jour de chaleur humide coûte une part du budget journalier (énergie et climatisation, productivité du personnel, maintenance et incidents).
  - *Inondation* : dommages matériels et pertes d'exploitation de la crue centennale (valeur des actifs × part inondable × taux de dommage selon la hauteur d'eau), ramenés à un coût annuel attendu de 2 % de ces pertes.
  - Les coûts unitaires sont les constantes `FIN_HEAT` et `FIN_FLOOD` de `src/template.html`.

**Limites** :
- Les données sont simplifiées : un point et un rayon de 10 km par réseau, avec une maille de 0,25 à 0,5° pour le climat et d'environ 1 km pour l'inondation.
- Les digues et protections existantes ne sont pas prises en compte.
- Le ruissellement urbain et l'îlot de chaleur urbain ne sont pas modélisés.
- Sur la côte, les mailles mélangent terre et mer et sous-estiment les maxima de température.
- Les montants financiers sont des ordres de grandeur (incertitude d'un facteur 2 à 3) : budgets estimés, coûts unitaires forfaitaires, sans inflation ni partage contractuel des risques.

## Sources et licences des données

| Données | Source | Licence |
|---|---|---|
| Fiches réseaux | [ratpdev.com — Nos réseaux](https://www.ratpdev.com/fr/nos-reseaux/) | contenu RATP Dev |
| Climat (CMIP6) | [Banque mondiale, Climate Change Knowledge Portal](https://climateknowledgeportal.worldbank.org/) | CC BY 4.0 |
| Inondation | [WRI Aqueduct Floods v2](https://www.wri.org/data/aqueduct-floods-hazard-maps) | CC BY 4.0 |
| Relief | [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) | attribution des sources (SRTM, etc.) |
| Cours d'eau, lacs, pays | [Natural Earth](https://www.naturalearthdata.com/) via [world-atlas](https://github.com/topojson/world-atlas) | domaine public |
| États américains | US Census Bureau via [us-atlas](https://github.com/topojson/us-atlas) | domaine public |
| Régions, départements | IGN Admin Express via [france-geojson](https://github.com/gregoiredavid/france-geojson) | Licence Ouverte |
| Tracés GTFS (23 réseaux) | [transport.data.gouv.fr](https://transport.data.gouv.fr/) | Licence Ouverte ou ODbL selon le jeu |
| Métro, funiculaires, tramways TCL | [data.grandlyon.com](https://data.grandlyon.com/) | selon le jeu |
| Orlyval | [Île-de-France Mobilités](https://data.iledefrance-mobilites.fr/) | ODbL |

Les jeux sous ODbL imposent de citer la source et de partager à l'identique les données dérivées, ici `data/lines.json.gz`. Vérifier la licence de chaque jeu avant de rendre le dépôt public.

## Mise à jour des données

`scripts/prepare_networks.py` régénère la liste des réseaux à partir de `data/references_raw.json`.

`scripts/prepare_finance.py` régénère les budgets estimés (`data/finance.json`) ; à relancer si la liste des réseaux ou les hypothèses de budget changent.

Les autres jeux (`climate_raw`, `temp_grids`, `flood`, `water`, `lines`) ont été extraits une fois des sources ci-dessus et sont versionnés tels quels. Leur extraction n'est pas automatisée dans ce dépôt : la plupart des sources sont des services web ou des rasters volumineux.

## Historique

- **v1** : localisation des 90 réseaux.
- **v2** : risque chaleur par réseau, 2026–2036, trois scénarios.
- **v3** : calque des températures (moyenne annuelle, jour le plus chaud), variable selon l'année.
- **v4** : aléa inondation (crue centennale), cours d'eau et lacs, relief, correction topographique.
- **v5** : plans des réseaux français (GTFS) et tronçons exposés par aléa.
- **v6** : risque financier (coût annuel estimé, surcoût dû au réchauffement, cumul) pour la chaleur et l'inondation.
