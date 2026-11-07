"""Estime la fréquentation annuelle de chaque réseau : base du calcul des voyageurs perturbés.

data/networks.json + data/finance.json → data/ridership.json

La fréquentation (voyages par an) sert d'assiette au nombre de voyageurs perturbés par la chaleur et
par l'inondation, calculé dans la page. Pour chaque réseau, par ordre de préférence :

  1. chiffre publié sur ratpdev.com (voyages par an, ou par jour × 365, par mois × 12) ;
  2. estimation motivée quand le chiffre publié manque et que le budget ne suffit pas (métros du Golfe,
     navette d'aéroport, transport scolaire…) ;
  3. budget d'exploitation estimé (data/finance.json) ÷ coût moyen d'un voyage selon le mode.

Les coûts par voyage sont des ordres de grandeur pour la France (euros 2026), calés sur les réseaux dont on
connaît à la fois le budget et la fréquentation ; le budget est d'abord ramené en coûts français (indice pays).
Un voyage est un déplacement en transport collectif : un voyageur qui fait l'aller et le retour compte deux fois.

Usage : python scripts/prepare_ridership.py && python build.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_finance import COUNTRY, KM_COST, fr  # noqa: E402  (même dossier)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Coût d'exploitation moyen d'un voyage, en euros (coûts France)
TRIP_COST = {
    "bus": 3.5,       # réseau urbain de bus
    "tram+bus": 2.0,  # réseau urbain avec tramway
    "car": 8.0,       # autocars interurbains et scolaires, trajets plus longs
    "us_bus": 8.0,    # bus aux États-Unis : fréquentation plus faible à budget égal (médiane des réseaux publiés)
    "tad": 50.0,      # transport à la demande et PMR
    "tram": 1.5, "metro": 1.5,
    "train": 6.0,     # trains régionaux et liaisons express
    "cable": 5.0,
}
KIND_FR = {"bus": "bus urbain", "tram+bus": "réseau avec tramway", "car": "autocar", "us_bus": "bus aux États-Unis",
           "tad": "transport à la demande", "tram": "tramway", "metro": "métro", "train": "train", "cable": "transport par câble"}

# Base par réseau (id → méthode, valeur, [libellé])
#   ("pub", millions de voyages/an, libellé du chiffre publié)
#   ("est", millions de voyages/an, motif)
#   ("cpt", type de réseau)   : budget ÷ coût par voyage
#   ("mix", None)             : réseau ferré mixte, coût par voyage de chaque mode (parts du budget)
M = 1.0
BASIS = {
    0: ("cpt", "us_bus"),
    1: ("pub", 0.3, "300 000 voyages annuels"),
    2: ("cpt", "us_bus"),
    3: ("pub", 0.233, "233 000 voyages annuels"),
    4: ("pub", 1.7, "1,7 M voyages annuels"),
    5: ("pub", 0.115, "115 000 voyages annuels"),
    6: ("pub", 2.0, "2 M voyages annuels"),
    7: ("pub", 1.6, "1,6 M voyages annuels"),
    8: ("pub", 3.0, "3 M voyages annuels"),
    9: ("pub", 0.126, "126 000 voyages annuels"),
    10: ("pub", 4.5, "4,5 M voyages annuels"),
    11: ("pub", 6.5, "6,5 M trajets annuels"),
    12: ("pub", 2.1, "2,1 M voyages annuels"),
    13: ("pub", 21, "21 M voyages annuels"),
    14: ("pub", 0.78, "780 000 trajets annuels"),
    15: ("pub", 0.45, "450 000 voyages annuels"),
    16: ("pub", 0.161, "161 000 voyages annuels"),
    17: ("pub", 1.0, "1 M de voyages annuels"),
    18: ("pub", 0.0733, "73 266 voyageurs annuels"),
    19: ("cpt", "us_bus"),
    20: ("pub", 2.5, "2,5 M voyages annuels"),
    21: ("cpt", "us_bus"),
    22: ("pub", 0.7, "700 000 voyages par an"),
    23: ("est", 17, "18 M de trajets combinés bus + tramway, dont ~1 M en tramway"),
    24: ("est", 1, "~1 M sur les 18 M de trajets combinés bus + tramway"),
    25: ("pub", 0.417, "417 000 voyages annuels"),
    26: ("pub", 5.0, "5 M de trajets par an"),
    27: ("pub", 1.8, "1,8 M voyages annuels"),
    28: ("cpt", "us_bus"),
    29: ("pub", 0.276, "276 000 voyages annuels"),
    30: ("pub", 0.05, "50 000 voyages annuels"),
    31: ("pub", 0.08, "80 000 voyages annuels"),
    32: ("pub", 0.518, "518 114 voyages annuels"),
    33: ("pub", 2.1, "2,1 M de trajets annuels"),
    34: ("pub", 135, "135 M de voyageurs par an"),
    35: ("cpt", "metro"), 36: ("cpt", "metro"),
    37: ("cpt", "tram+bus"),
    38: ("cpt", "metro"),
    39: ("cpt", "tram+bus"),
    40: ("est", 3, "navette d'aéroport (Orlyval), ordre de grandeur"),
    41: ("cpt", "tram+bus"),
    42: ("cpt", "bus"),
    43: ("cpt", "car"), 44: ("cpt", "car"), 45: ("cpt", "car"), 46: ("cpt", "car"),
    47: ("cpt", "bus"),
    48: ("pub", 0.263, "263 000 voyages réalisés"),
    49: ("cpt", "bus"), 50: ("cpt", "bus"), 51: ("cpt", "bus"),
    52: ("est", 3800 * 2 * 180 / 1e6, "3 800 élèves × 2 trajets × 180 jours de classe"),
    53: ("cpt", "bus"),
    54: ("pub", 2.4, "2,4 M de voyageurs par an"),
    55: ("pub", 1.5, "1,5 M de voyageurs par an"),
    56: ("cpt", "bus"),
    57: ("cpt", "car"), 58: ("cpt", "car"),
    59: ("cpt", "bus"), 60: ("cpt", "bus"),
    61: ("cpt", "car"), 62: ("cpt", "car"), 63: ("cpt", "car"),
    64: ("pub", 3.0, "3 M de voyages par an"),
    65: ("pub", 0.888, "888 155 voyages par an"),
    66: ("pub", 2.7, "225 000 passagers par mois × 12"),
    67: ("cpt", "bus"),
    68: ("cpt", "car"),
    69: ("cpt", "bus"), 70: ("cpt", "bus"),
    71: ("pub", 3.2, "3,2 M de voyageurs en 2023"),
    72: ("pub", 7.9, "7,9 M de voyages"),
    73: ("pub", 7.0, "7 M de voyageurs par an"),
    74: ("mix", None),
    75: ("cpt", "tram"),
    76: ("est", 60, "~165 000 voyageurs par jour sur les lignes 1 et 2, ordre de grandeur"),
    77: ("est", 0.3, "1 M de passagers depuis le lancement, ordre de grandeur annuel"),
    78: ("cpt", "train"),
    79: ("cpt", "metro"),
    80: ("pub", 500_000 * 365 / 1e6, "500 000 passagers par jour × 365"),
    81: ("cpt", "tram"),
    82: ("pub", 140_000 * 365 / 1e6, "140 000 voyageurs par jour × 365"),
    83: ("cpt", "train"),
    84: ("pub", 6850 * 365 / 1e6, "6 850 passagers par jour × 365"),
    85: ("cpt", "bus"),
    86: ("est", 55, "~150 000 voyageurs par jour, ordre de grandeur"),
    87: ("est", 110, "~300 000 voyageurs par jour, ordre de grandeur"),
    88: ("cpt", "tram"),
    89: ("cpt", "metro"),
}


def sig(x: float, n: int = 3) -> float:
    """Arrondi à n chiffres significatifs."""
    return float(f"{x:.{n}g}")


def estimate(n: dict, fin: dict, basis: tuple) -> tuple[float, str]:
    """Fréquentation (millions de voyages par an) et base de calcul lisible."""
    kind, val, *extra = basis
    if kind in ("pub", "est"):
        return val, extra[0] + (" (ratpdev.com)" if kind == "pub" else "")
    b0 = fin["b"] / COUNTRY[n["pays"]]  # budget ramené en coûts France
    if kind == "cpt":
        cost = TRIP_COST[val]
        return b0 / cost, f"budget estimé ({fr(fin['b'], 1)} M€) ÷ {fr(cost, 1)} € par voyage ({KIND_FR[val]}, coûts France)"
    if kind == "mix":
        parts = fin["parts"]
        v = sum(b0 * w / TRIP_COST[m] for m, w in parts.items())
        detail = " + ".join(f"{KIND_FR[m]} {fr(TRIP_COST[m], 1)} €" for m in parts)
        return v, f"budget estimé ({fr(fin['b'], 1)} M€) réparti par mode ÷ coût par voyage ({detail})"
    raise ValueError(kind)


def main() -> None:
    # Réseaux exploités seulement : les prospects sont ajoutés ensuite par scripts/prepare_prospects.py (à relancer)
    networks = [n for n in json.loads((DATA / "networks.json").read_text(encoding="utf-8")) if n.get("st") != "prospect"]
    finance = json.loads((DATA / "finance.json").read_text(encoding="utf-8"))["networks"]
    missing = [n["id"] for n in networks if n["id"] not in BASIS]
    if missing:
        raise SystemExit(f"Base de fréquentation manquante pour les réseaux : {missing}")
    out = []
    for n, f in zip(networks, finance):
        v, base = estimate(n, f, BASIS[n["id"]])
        out.append({"v": sig(v), "base": base})
    doc = {
        "_doc": "Fréquentation annuelle estimée par réseau (millions de voyages par an), dans l'ordre de networks.json. "
                "Généré par scripts/prepare_ridership.py.",
        "networks": out,
    }
    (DATA / "ridership.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tot = sum(r["v"] for r in out)
    n_pub = sum(1 for k in BASIS.values() if k[0] == "pub")
    print(f"data/ridership.json : {len(out)} réseaux ({n_pub} chiffres publiés), {fr(tot)} M de voyages par an au total")
    for n, r in sorted(zip(networks, out), key=lambda x: -x[1]["v"])[:12]:
        print(f"  {fr(r['v'], 1):>7} M  {n['ci'][:26]:26}  {r['base']}")


if __name__ == "__main__":
    main()
