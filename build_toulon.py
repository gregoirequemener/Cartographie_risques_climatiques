"""Assemble la vue 3D « Dépôts du réseau Mistral · risque inondation » en une page HTML autonome.

src/toulon_depots.html + data/toulon_depots.json (scripts/prepare_toulon_depots.py) + three.js (src/vendor/)
+ polices et logotype de la charte (fonctions de build.py) → docs/toulon-depots-inondation.html

La page fonctionne hors ligne : données, photos aériennes, bibliothèques et polices y sont intégrées.

Usage :
    python scripts/prepare_toulon_depots.py   # (re)télécharge et prépare les données (réseau nécessaire)
    python build_toulon.py                    # écrit docs/toulon-depots-inondation.html
    python build_toulon.py --out essai.html   # autre destination
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from build import DATA, DOCS, SRC, font_faces, inline_script, logo, read

LIBS = [
    ("three.min.js", "three.js r147 · MIT · https://threejs.org"),
    ("three-OrbitControls.js", "three.js r147, examples/js/controls/OrbitControls.js · MIT · https://threejs.org"),
]
OUT = DOCS / "toulon-depots-inondation.html"


def build() -> str:
    tpl = read(SRC / "toulon_depots.html")
    if re.search(r"^(<<<<<<<|>>>>>>>) ", tpl, re.M):
        raise SystemExit("src/toulon_depots.html contient des marqueurs de conflit Git")
    data = read(DATA / "toulon_depots.json")
    if "</script" in data.lower():
        raise SystemExit("data/toulon_depots.json contient « </script » : intégration impossible")
    page = tpl
    for marker, value in [
        ("/*__FONTS__*/", font_faces()),
        ("<!--__LOGO__-->", logo()),
        ("/*__DATA__*/", data),
        ("<!--__SCRIPTS__-->", "\n".join(inline_script(SRC / "vendor" / n, lab) for n, lab in LIBS)),
    ]:
        if page.count(marker) != 1:
            raise SystemExit(f"Marqueur absent ou en double dans le gabarit : {marker}")
        page = page.replace(marker, value)
    return page


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text(build(), encoding="utf-8")
    tmp.replace(args.out)
    print(f"{args.out} : {args.out.stat().st_size / 1024:,.0f} Ko".replace(",", " "))


if __name__ == "__main__":
    main()
