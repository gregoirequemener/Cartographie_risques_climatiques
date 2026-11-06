### Tests branch

# Risques climatiques des réseaux RATP Dev

Carte interactive des risques climatiques physiques (chaleur, inondation) des 90 réseaux exploités par RATP Dev, horizon 2026–2036, sous trois scénarios climatiques (SSP1-2.6, SSP2-4.5, SSP5-8.5). Pour les réseaux français dont les tracés sont publiés en open data, la carte affiche aussi le plan des lignes et les tronçons exposés à chaque aléa.

La page produite est un fichier HTML unique et autonome : les données et les bibliothèques JavaScript (Leaflet, Leaflet.markercluster, topojson-client) y sont intégrées, elle fonctionne donc hors ligne. Seules les polices viennent de Google Fonts (polices du système à défaut).

**Version 9** : optimisation (démarrage, fluidité, mémoire), fonctionnement hors ligne, numéro de mise à jour dans la version.

## Démarrage rapide

Double-cliquer sur `lancer.command` : il construit la page puis l'ouvre. Ou, dans un terminal :

```bash
python build.py                 # écrit docs/index.html (Python 3.9+, aucune dépendance)
open docs/index.html            # ou double-clic sur le fichier
```

## Version

La version affichée en haut de la page, à droite de l'année, suit la forme **Alpha V0.mois.jour.n** :
- *mois.jour* : date de la dernière mise à jour du code (`src/`, `data/`, `scripts/`, `build.py`) ;
- *n* : numéro de la mise à jour ce jour-là. Il augmente d'un cran chaque fois que `docs/index.html` est reconstruit après une modification du code, et repart à 1 le jour suivant.

`build.py` compare une empreinte du code à celle notée dans `version.json` : reconstruire sans rien changer garde la même version. Une construction d'essai (`python build.py --out autre.html`) affiche la version suivante sans l'enregistrer. `version.json` est à versionner avec le reste, pour que la numérotation suive le dépôt.

Pour publier la carte avec GitHub Pages : *Settings → Pages → Deploy from a branch → `main` / `docs`*.

Pour vérifier la page (facultatif) :

```bash
pip install -r requirements-dev.txt
python scripts/check_page.py --chrome "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# ou, sans Chrome installé : playwright install chromium && python scripts/check_page.py
```

Le test vérifie l'absence d'erreur JavaScript, les 90 réseaux, les 25 plans de réseau, le fond de carte précis, les coûts et voyageurs perturbés de chaque réseau, la bascule du panneau, le format de la version et les tronçons exposés affichés sur Lyon.

## Structure

```
build.py                  assemble src/template.html + data/ + src/vendor/ → docs/index.html, gère la version
version.json              dernière version enregistrée (date, numéro du jour, empreinte du code)
lancer.command            construit puis ouvre la page (double-clic dans le Finder)
src/template.html         page : mise en page, styles, logique de la carte (Leaflet)
src/vendor/               Leaflet 1.9.4, Leaflet.markercluster 1.5.3, topojson-client 3.1.0 (scripts et styles, licences dans LICENCES.md)
data/
  references_raw.json     fiches réseaux extraites du site ratpdev.com (« Nos réseaux »)
  networks.json           90 réseaux nettoyés et géolocalisés (généré par scripts/prepare_networks.py)
  finance.json            budget d'exploitation annuel estimé par réseau (généré par scripts/prepare_finance.py)
  ridership.json          fréquentation annuelle estimée par réseau (généré par scripts/prepare_ridership.py)
  corrections.json        corrections apportées aux fiches source, avec leur motif
  climate_raw.json        indicateurs climatiques par réseau (CCKP, CMIP6 0,25°)
  temp_grids.json         grilles mondiales de température (moyenne annuelle, jour le plus chaud), 0,5°, en PNG
  flood.json              inondation (Aqueduct, crue centennale, ~1 km), relief fin autour des réseaux, altitude des points
  water.json              fleuves, rivières et lacs Natural Earth (TopoJSON), source de basemap.json.gz
  basemap.json.gz         fond de carte : terres, cours d'eau et lacs, précisés autour des réseaux (généré par scripts/prepare_basemap.py)
  lines.json.gz           tracés de 25 réseaux français + exposition inondation par sommet
  geo/                    contours pays, États américains, régions et départements français (TopoJSON)
scripts/
  prepare_networks.py     data/references_raw.json → data/networks.json + data/corrections.json
  prepare_finance.py      data/networks.json → data/finance.json (hypothèses de budget par réseau)
  prepare_ridership.py    data/networks.json + finance.json → data/ridership.json (fréquentation par réseau)
  prepare_basemap.py      fond de carte précis (IGN BD TOPO, Natural Earth 10m) → data/basemap.json.gz
  check_page.py           test de fumée de la page construite (Playwright)
docs/index.html           page construite (servie par GitHub Pages)
```

Pour modifier la carte, éditer `src/template.html` puis relancer `python build.py`. Le gabarit contient des marqueurs (`/*__DATA__*/`, `/*__FLOOD__*/`, etc.) remplacés par les données au moment de la construction.

## Performances

Choix qui gardent la page fluide, à préserver lors des évolutions :
- les plans de réseau ne sont construits que pour les réseaux à l'écran, à partir du zoom où ils s'affichent, et au plus une fois par image (curseur d'année, animation). La position de chaque sommet dans la grille des températures et sa correction d'altitude sont calculées une fois par réseau ;
- les cours d'eau et lacs (~300 000 sommets) ne sont créés qu'au premier affichage ;
- le masque de la mer est découpé à la vue : seule la partie visible est redessinée lors d'un déplacement ;
- les données compressées (fond de carte, tracés) sont décodées par le navigateur, sans bloquer l'affichage ; les températures n'apparaissent qu'avec le masque de la mer ;
- si le navigateur ne sait pas décompresser (versions anciennes), la page garde le fond mondial et fonctionne sans plans de réseau.

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
- **Voyageurs perturbés** : ordre de grandeur des voyages retardés, supprimés ou détournés par an (un aller-retour compte deux fois).
  - *Fréquentation* : chiffre publié sur ratpdev.com pour 40 réseaux ; sinon budget estimé ÷ coût moyen d'un voyage selon le mode (1,5 € en métro, 3,5 € en bus urbain, 8 € en autocar…). Détail dans `scripts/prepare_ridership.py`.
  - *Chaleur* : un jour ≥ 35 °C perturbe 3 % (bus) à 15 % (train) des voyages de la journée, taux réduit pour les réseaux déjà habitués aux fortes chaleurs.
  - *Inondation* : jours d'interruption × part du réseau touchée lors d'une crue centennale (hypothèses du risque financier), ramenés à une moyenne annuelle de 2 %.
  - Les hypothèses sont la constante `PAX` de `src/template.html`.

**Limites** :
- Les données sont simplifiées : un point et un rayon de 10 km par réseau, avec une maille de 0,25 à 0,5° pour le climat et d'environ 1 km pour l'inondation.
- Les digues et protections existantes ne sont pas prises en compte.
- Le ruissellement urbain et l'îlot de chaleur urbain ne sont pas modélisés.
- Sur la côte, les mailles mélangent terre et mer et sous-estiment les maxima de température.
- Le fond de carte est précis au mètre autour des réseaux français (BD TOPO). Autour des réseaux étrangers, il reprend Natural Earth au 1:10 M (quelques centaines de mètres d'écart), et ailleurs Natural Earth au 1:50 M.
- Les montants financiers et les voyageurs perturbés sont des ordres de grandeur (incertitude d'un facteur 2 à 3) : budgets et fréquentations estimés, hypothèses forfaitaires, sans inflation, sans croissance du trafic ni partage contractuel des risques. Les orages et le ruissellement urbain, causes fréquentes de perturbations, ne sont pas couverts.

## Sources et licences des données

| Données | Source | Licence |
|---|---|---|
| Fiches réseaux | [ratpdev.com — Nos réseaux](https://www.ratpdev.com/fr/nos-reseaux/) | contenu RATP Dev |
| Climat (CMIP6) | [Banque mondiale, Climate Change Knowledge Portal](https://climateknowledgeportal.worldbank.org/) | CC BY 4.0 |
| Inondation | [WRI Aqueduct Floods v2](https://www.wri.org/data/aqueduct-floods-hazard-maps) | CC BY 4.0 |
| Relief | [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) | attribution des sources (SRTM, etc.) |
| Cours d'eau, lacs, pays | [Natural Earth](https://www.naturalearthdata.com/) via [world-atlas](https://github.com/topojson/world-atlas), et Natural Earth 1:10 M autour des réseaux étrangers | domaine public |
| Trait de côte, cours d'eau et lacs autour des réseaux français | IGN, [BD TOPO](https://geoservices.ign.fr/bdtopo) via la [Géoplateforme](https://data.geopf.fr/) (WFS) | Licence Ouverte |
| États américains | US Census Bureau via [us-atlas](https://github.com/topojson/us-atlas) | domaine public |
| Régions, départements | IGN Admin Express via [france-geojson](https://github.com/gregoiredavid/france-geojson) | Licence Ouverte |
| Tracés GTFS (23 réseaux) | [transport.data.gouv.fr](https://transport.data.gouv.fr/) | Licence Ouverte ou ODbL selon le jeu |
| Métro, funiculaires, tramways TCL | [data.grandlyon.com](https://data.grandlyon.com/) | selon le jeu |
| Orlyval | [Île-de-France Mobilités](https://data.iledefrance-mobilites.fr/) | ODbL |

Les jeux sous ODbL imposent de citer la source et de partager à l'identique les données dérivées, ici `data/lines.json.gz`. Vérifier la licence de chaque jeu avant de rendre le dépôt public.

## Mise à jour des données

`scripts/prepare_networks.py` régénère la liste des réseaux à partir de `data/references_raw.json`.

`scripts/prepare_finance.py` régénère les budgets estimés (`data/finance.json`), puis `scripts/prepare_ridership.py` la fréquentation (`data/ridership.json`) ; à relancer, dans cet ordre, si la liste des réseaux ou les hypothèses changent.

`scripts/prepare_basemap.py` régénère le fond de carte (`data/basemap.json.gz`) ; à relancer si des réseaux ou des tracés sont ajoutés. Il télécharge les données IGN et Natural Earth et demande `shapely` et `geopandas` (`pip install -r requirements-dev.txt`).

Les autres jeux (`climate_raw`, `temp_grids`, `flood`, `water`, `lines`) ont été extraits une fois des sources ci-dessus et sont versionnés tels quels. Leur extraction n'est pas automatisée dans ce dépôt : la plupart des sources sont des services web ou des rasters volumineux.

## Historique

- **v1** : localisation des 90 réseaux.
- **v2** : risque chaleur par réseau, 2026–2036, trois scénarios.
- **v3** : calque des températures (moyenne annuelle, jour le plus chaud), variable selon l'année.
- **v4** : aléa inondation (crue centennale), cours d'eau et lacs, relief, correction topographique.
- **v5** : plans des réseaux français (GTFS) et tronçons exposés par aléa.
- **v6** : risque financier (coût annuel estimé, surcoût dû au réchauffement, cumul) pour la chaleur et l'inondation.
- **v7** : fond de carte précis autour des réseaux (côtes, fleuves et lacs de la BD TOPO en France, Natural Earth 1:10 M ailleurs).
- **v8** : voyageurs perturbés par aléa (fréquentation estimée par réseau, portefeuille, fiches, classement et export).
- **v9** : optimisation (page prête en 0,5 s au lieu de 0,8 s, changement d'année 2 à 3 fois plus rapide, déplacements sans à-coups, mémoire −40 % au démarrage), bibliothèques intégrées (fonctionnement hors ligne), export CSV téléchargé si la copie est refusée, version « Alpha V0.mois.jour.n ».
