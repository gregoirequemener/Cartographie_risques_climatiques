"""Assemble la carte « Risques climatiques des réseaux RATP Dev » en une seule page HTML autonome.

Toutes les données (réseaux, budgets et fréquentation estimés, climat, inondation, relief, fond de carte précis,
plans de réseau), les bibliothèques JavaScript (Leaflet, Leaflet.markercluster, topojson-client) et les polices de
la charte graphique RATP Dev (Montserrat ; Carlito, substitut de Calibri) sont copiées dans src/vendor/ et intégrées
au gabarit src/template.html : la page fonctionne entièrement hors ligne.

Logo : le fichier officiel du logotype RATP Dev déposé dans src/logo/ (SVG ou PNG, tel que fourni par la
bibliothèque de logotypes) s'affiche en haut à gauche, dans son cartouche blanc. Sans fichier, rien n'est affiché :
le logotype n'est jamais redessiné.

Version affichée en haut de la page : « Alpha V0.aa.mois.jour.n ».
  - aa.mois.jour : date de la dernière mise à jour du code de l'application (src/, data/, scripts/, build.py),
    l'année sur deux chiffres (26 pour 2026) ;
  - n : numéro de la mise à jour ce jour-là (1, 2, 3…). Il augmente d'un cran chaque fois que la page officielle
    (docs/index.html) est reconstruite après une modification du code ; reconstruire sans modification ne change
    rien. Le dernier état est noté dans version.json.

Usage :
    python build.py                       # écrit docs/index.html et enregistre la version
    python build.py --out carte.html      # autre destination (essai) : la version n'est pas enregistrée

Aucune dépendance hors bibliothèque standard (Python 3.9+).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC, DATA = ROOT / "src", ROOT / "data"
OUT = ROOT / "docs/index.html"
VERSION_FILE = ROOT / "version.json"
CODE = ("src", "data", "scripts", "build.py")  # ce qui compose l'application ; docs/ en est le résultat
IGNORED = {"__pycache__", ".DS_Store"}
MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")

# Bibliothèques intégrées à la page : copies dans src/vendor/ des fichiers publiés sur npm (jsDelivr)
LIBS = [
    ("leaflet.js", "Leaflet 1.9.4 · BSD-2-Clause · https://leafletjs.com"),
    ("leaflet.markercluster.js", "Leaflet.markercluster 1.5.3 · MIT · https://github.com/Leaflet/Leaflet.markercluster"),
    ("topojson-client.min.js", "topojson-client 3.1.0 · ISC · https://github.com/topojson/topojson-client"),
]

# Polices de la charte (sous-ensemble latin de Google Fonts, SIL Open Font License 1.1) : (famille, fichier, style, graisse)
FONTS = [
    ("Montserrat", "montserrat-latin.woff2", "normal", "400 800"),
    ("Carlito", "carlito-latin-400.woff2", "normal", "400"),
    ("Carlito", "carlito-latin-700.woff2", "normal", "700"),
    ("Carlito", "carlito-latin-400-italic.woff2", "italic", "400"),
]
FONT_RANGE = ("U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, "
              "U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD")
LOGO_DIR = SRC / "logo"
LOGO_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def compact(path: Path) -> str:
    """JSON réécrit sans espaces (mêmes valeurs, poids réduit)."""
    return json.dumps(json.loads(read(path)), ensure_ascii=False, separators=(",", ":"))


def code_files() -> list[Path]:
    files: list[Path] = []
    for name in CODE:
        path = ROOT / name
        files += sorted(f for f in path.rglob("*") if f.is_file()) if path.is_dir() else [path]
    return [f for f in files if not IGNORED & set(f.relative_to(ROOT).parts)]


def fingerprint() -> str:
    """Empreinte du contenu du code : change dès qu'un fichier de l'application est modifié, ajouté ou retiré."""
    h = hashlib.sha256()
    for f in code_files():
        h.update(f.relative_to(ROOT).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()[:16]


def _mtime(path: Path) -> float:
    """Date de modification la plus récente d'un fichier ou d'un dossier (0 s'il n'existe plus)."""
    if path.is_dir():
        return max((f.stat().st_mtime for f in path.rglob("*") if f.is_file() and not IGNORED & set(f.parts)), default=0.0)
    return path.stat().st_mtime if path.exists() else 0.0


def last_update() -> date:
    """Date de la dernière mise à jour du code de l'application.

    - fichiers du code modifiés depuis le dernier commit : date de modification la plus récente parmi eux ;
    - sinon : date du dernier commit qui touche le code ;
    - hors dépôt git (archive téléchargée) : date de modification la plus récente des fichiers du code.
    """
    def git(*args: str) -> str:
        return subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout
    try:
        status = git("status", "--porcelain", "--untracked-files=all", "--", *CODE)
        changed = [line[3:].split(" -> ")[-1].strip('"') for line in status.splitlines()]
        changed = [p for p in changed if not IGNORED & set(Path(p).parts)]
        if changed:
            stamps = [_mtime(ROOT / path) for path in changed]
            return date.today() if 0.0 in stamps else date.fromtimestamp(max(stamps))  # suppression : aujourd'hui
        last = git("log", "-1", "--format=%cd", "--date=format:%Y-%m-%d", "--", *CODE).strip()
        if last:
            return date.fromisoformat(last)
    except (OSError, subprocess.CalledProcessError):
        pass
    return date.fromtimestamp(max(_mtime(ROOT / path) for path in CODE))


def version(record: bool) -> tuple[str, str]:
    """Libellé « Alpha V0.aa.mois.jour.n » (aa : année sur deux chiffres) et texte de l'infobulle.

    n repart à 1 chaque nouveau jour de mise à jour et augmente d'un cran à chaque modification du code.
    Avec record=True (page officielle), le nouvel état est enregistré dans version.json.
    """
    try:
        state = json.loads(read(VERSION_FILE))
    except (OSError, ValueError):
        state = {}
    fp = fingerprint()
    if state.get("empreinte") == fp and state.get("date") and state.get("n"):
        d, n = date.fromisoformat(state["date"]), int(state["n"])  # code inchangé : même version
    else:
        d = last_update()
        prev = date.fromisoformat(state["date"]) if state.get("date") else None
        if prev and prev > d:
            d = prev  # une version ne recule jamais
        n = int(state.get("n", 0)) + 1 if prev == d else 1
    label = f"Alpha V0.{d.year % 100:02d}.{d.month}.{d.day}.{n}"
    if record and state.get("empreinte") != fp:
        VERSION_FILE.write_text(json.dumps({"version": label, "date": d.isoformat(), "n": n, "empreinte": fp},
                                           ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    jour = "1er" if d.day == 1 else str(d.day)
    return label, f"Version alpha · code mis à jour le {jour} {MOIS[d.month - 1]} {d.year} · mise à jour n° {n} du jour"


def inline_script(path: Path, label: str) -> str:
    js = read(path)
    if "</script" in js.lower():
        raise SystemExit(f"{path.name} contient « </script », qui fermerait la balise : intégration impossible")
    return f"<script>/*! {label} */\n{js}\n</script>"


def font_faces() -> str:
    """Règles @font-face des polices de la charte, fichiers intégrés à la page (aucun appel réseau)."""
    rules = ["/*! Polices : Montserrat (The Montserrat Project Authors) et Carlito (The Carlito Project Authors), "
             "SIL Open Font License 1.1 · licences dans src/vendor/fonts/ */"]
    for family, name, style, weight in FONTS:
        b64 = base64.b64encode((SRC / "vendor/fonts" / name).read_bytes()).decode()
        rules.append(f'@font-face{{font-family:"{family}";font-style:{style};font-weight:{weight};font-display:swap;'
                     f'src:url(data:font/woff2;base64,{b64}) format("woff2");unicode-range:{FONT_RANGE}}}')
    return "\n".join(rules)


def logo() -> str:
    """Logotype officiel déposé dans src/logo/, intégré tel quel ; chaîne vide s'il n'y en a pas."""
    files = sorted(f for f in LOGO_DIR.glob("*") if f.suffix.lower() in LOGO_TYPES) if LOGO_DIR.is_dir() else []
    if not files:
        return ""
    data = base64.b64encode(files[0].read_bytes()).decode()
    return f'<span class="logo-box"><img class="logo" src="data:{LOGO_TYPES[files[0].suffix.lower()]};base64,{data}" alt="RATP Dev"></span>'


def build(label: str, title: str) -> str:
    tpl = read(SRC / "template.html")
    if re.search(r"^(<<<<<<<|>>>>>>>) ", tpl, re.M):
        raise SystemExit("src/template.html contient des marqueurs de conflit Git : résoudre la fusion avant de construire la page")
    css = read(SRC / "vendor/leaflet.css") + "\n" + read(SRC / "vendor/MarkerCluster.css")
    geo = "{" + ",".join([
        '"world":' + compact(DATA / "geo/world-countries-50m.json"),
        '"us":' + compact(DATA / "geo/us-states-10m.json"),
        '"frReg":' + compact(DATA / "geo/fr-reg.topo.json"),
        '"frDep":' + compact(DATA / "geo/fr-dep.topo.json"),
    ]) + "}"
    temp = {k: v for k, v in json.loads(read(DATA / "temp_grids.json")).items() if k != "sums"}
    gz64 = lambda name: base64.b64encode((DATA / name).read_bytes()).decode()  # noqa: E731
    scripts = "\n".join(inline_script(SRC / "vendor" / name, lab) for name, lab in LIBS)

    replacements = [
        ("<!--__VERSION__-->", label),
        ("__VERSION_TITLE__", title),
        ("/*__LEAFLET_CSS__*/", css),
        ("/*__FONTS__*/", font_faces()),
        ("<!--__LOGO__-->", logo()),
        ("/*__DATA__*/", compact(DATA / "networks.json")),
        ("/*__FINANCE__*/", json.dumps(json.loads(read(DATA / "finance.json"))["networks"], ensure_ascii=False, separators=(",", ":"))),
        ("/*__RIDERSHIP__*/", json.dumps(json.loads(read(DATA / "ridership.json"))["networks"], ensure_ascii=False, separators=(",", ":"))),
        ("/*__LINKS__*/", json.dumps(json.loads(read(DATA / "links.json"))["networks"], ensure_ascii=False, separators=(",", ":"))),
        ("/*__CLIMATE__*/", compact(DATA / "climate_raw.json")),
        ("/*__GEO__*/", geo),
        ("/*__FLOOD__*/", compact(DATA / "flood.json")),
        ("/*__BASEMAP__*/", gz64("basemap.json.gz")),
        ("/*__LINES__*/", gz64("lines.json.gz")),
        ("/*__TEMP__*/", json.dumps(temp, separators=(",", ":"))),
        ("<!--__SCRIPTS__-->", scripts),  # en dernier : le code des bibliothèques n'est pas parcouru par les remplacements
    ]
    page = tpl
    for marker, value in replacements:
        if page.count(marker) != 1:
            raise SystemExit(f"Marqueur absent ou en double dans le gabarit : {marker}")
        page = page.replace(marker, value)
    return page


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT, help="fichier HTML à écrire (par défaut docs/index.html)")
    args = ap.parse_args()
    official = args.out.resolve() == OUT.resolve()
    label, title = version(record=official)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")  # écriture atomique : jamais de page à moitié écrite
    tmp.write_text(build(label, title), encoding="utf-8")
    tmp.replace(args.out)
    print(f"{args.out} : {args.out.stat().st_size / 1024:,.0f} Ko · {label}".replace(",", " ")
          + ("" if official else " (essai : version non enregistrée)"))


if __name__ == "__main__":
    main()
