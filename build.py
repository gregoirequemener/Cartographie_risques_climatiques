"""Assemble la carte « Risques climatiques des réseaux RATP Dev » en une seule page HTML autonome.

Toutes les données (réseaux, climat, inondation, relief, eau, plans de réseau) sont injectées
dans le gabarit src/template.html. Seules les bibliothèques JavaScript (Leaflet, Leaflet.markercluster,
topojson-client) sont chargées depuis le CDN jsDelivr.

Usage :
    python build.py                       # écrit docs/index.html
    python build.py --out carte.html      # autre destination

Aucune dépendance hors bibliothèque standard (Python 3.9+).
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC, DATA = ROOT / "src", ROOT / "data"

LIBS = [
    "leaflet@1.9.4/dist/leaflet.js",
    "leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js",
    "topojson-client@3.1.0/dist/topojson-client.min.js",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def compact(path: Path) -> str:
    """JSON réécrit sans espaces (mêmes valeurs, poids réduit)."""
    return json.dumps(json.loads(read(path)), ensure_ascii=False, separators=(",", ":"))


def build() -> str:
    tpl = read(SRC / "template.html")
    css = read(SRC / "vendor/leaflet.css") + "\n" + read(SRC / "vendor/MarkerCluster.css")
    geo = "{" + ",".join([
        '"world":' + compact(DATA / "geo/world-countries-50m.json"),
        '"us":' + compact(DATA / "geo/us-states-10m.json"),
        '"frReg":' + compact(DATA / "geo/fr-reg.topo.json"),
        '"frDep":' + compact(DATA / "geo/fr-dep.topo.json"),
    ]) + "}"
    temp = {k: v for k, v in json.loads(read(DATA / "temp_grids.json")).items() if k != "sums"}
    lines_gz = base64.b64encode((DATA / "lines.json.gz").read_bytes()).decode()
    scripts = "\n".join(f'<script src="https://cdn.jsdelivr.net/npm/{lib}"></script>' for lib in LIBS)

    replacements = [
        ("/*__LEAFLET_CSS__*/", css),
        ("/*__DATA__*/", compact(DATA / "networks.json")),
        ("/*__CLIMATE__*/", compact(DATA / "climate_raw.json")),
        ("/*__GEO__*/", geo),
        ("/*__FLOOD__*/", read(DATA / "flood.json")),
        ("/*__WATER__*/", read(DATA / "water.json")),
        ("/*__LINES__*/", lines_gz),
        ("/*__TEMP__*/", json.dumps(temp, separators=(",", ":"))),
        ("<!--__SCRIPTS__-->", scripts),
    ]
    page = tpl
    for marker, value in replacements:
        if marker not in page:
            raise SystemExit(f"Marqueur absent du gabarit : {marker}")
        page = page.replace(marker, value)
    return page


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "docs/index.html", help="fichier HTML à écrire")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(), encoding="utf-8")
    print(f"{args.out} : {args.out.stat().st_size / 1024:,.0f} Ko".replace(",", " "))


if __name__ == "__main__":
    main()
