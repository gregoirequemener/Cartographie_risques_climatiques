"""Estime le budget d'exploitation annuel de chaque réseau : base du calcul du risque financier.

data/networks.json → data/finance.json

Le budget d'exploitation (coût complet annuel : personnel, énergie, maintenance, frais de structure)
sert d'assiette aux coûts liés à la chaleur et à l'inondation calculés dans la page. Les fiches
ratpdev.com ne donnent pas ce budget : on l'estime à partir du chiffre le plus fiable disponible
pour chaque réseau, dans cet ordre de préférence :

  1. effectif        × coût complet par employé
  2. flotte          × employés par véhicule × coût complet par employé
  3. longueur (km)   × coût d'exploitation par km de ligne (métro, tramway, train)
  4. voyages / an    × coût par voyage
  5. population      × dépense de transport urbain par habitant
  6. estimation directe, motivée dans le tableau

Les coûts unitaires sont des ordres de grandeur pour la France (euros 2026), corrigés par un
indice de coût du pays (salaires, énergie). Pour changer une hypothèse, modifier les constantes
ou le tableau BASIS ci-dessous puis relancer :

    python scripts/prepare_finance.py && python build.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Coûts unitaires, France, euros 2026
EMP_COST = 95.0          # k€ par employé et par an (coût complet d'exploitation / effectif)
STAFF_PER_VEH = {"bus": 2.3, "tad": 1.3, "car": 1.3}   # employés par véhicule
KM_COST = {"metro": 3.5, "tram": 2.0, "train": 0.8}     # M€ par km de ligne et par an
TRIP_COST = 3.5          # € par voyage (bus urbain)

# Indice de coût d'exploitation par pays (France = 1)
COUNTRY = {
    "France": 1.0, "États-Unis": 1.15, "Italie": 0.9, "Australie": 1.15, "Arabie saoudite": 0.85,
    "Danemark": 1.25, "Suisse": 1.35, "Hong Kong": 0.9, "Afrique du Sud": 0.45, "Singapour": 0.95,
    "Égypte": 0.3, "Maroc": 0.4, "Qatar": 0.85, "Philippines": 0.35, "Canada": 1.05, "Serbie": 0.45,
}

# Base d'estimation par réseau (id → méthode, valeur, [précision])
#   ("emp", effectif[, libellé])   ("veh", véhicules, type)   ("km", km, mode[, libellé])
#   ("voy", voyages/an[, libellé]) ("hab", habitants, €/hab)  ("est", M€/an, motif)
#   ("mix", [(km, mode), ...], libellé) : plusieurs modes ferrés
BASIS = {
    0: ("emp", 280), 1: ("emp", 80), 2: ("emp", 31), 3: ("veh", 12, "bus"), 4: ("emp", 187),
    5: ("emp", 52), 6: ("emp", 86), 7: ("emp", 200), 8: ("emp", 222), 9: ("emp", 116),
    10: ("emp", 320), 11: ("emp", 109), 12: ("emp", 209), 13: ("emp", 1286), 14: ("emp", 65),
    15: ("emp", 36), 16: ("emp", 72), 17: ("emp", 109), 18: ("veh", 9, "bus"), 19: ("emp", 61),
    20: ("emp", 183), 21: ("emp", 29), 22: ("veh", 19, "bus"), 23: ("emp", 857),
    24: ("km", 6.3, "tram", "6,3 km de tramway (Sun Link)"),
    25: ("emp", 50), 26: ("veh", 39, "bus"), 27: ("veh", 77, "bus"), 28: ("emp", 11), 29: ("emp", 66),
    30: ("emp", 9), 31: ("emp", 23), 32: ("emp", 55), 33: ("emp", 254),
    34: ("km", 43, "metro"),
    35: ("km", 26, "metro"),
    36: ("km", 23, "metro"),
    37: ("hab", 213_000, 180),
    38: ("km", 33, "metro"),
    39: ("hab", 280_000, 180),
    40: ("km", 7.3, "metro", "7,3 km de métro automatique (Orlyval)"),
    41: ("hab", 300_000, 180),
    42: ("est", 4.5, "6 lignes de bus et 2 navettes (~0,7 M€ par ligne)"),
    43: ("est", 12, "85 000 départs de car × ~40 km × 3,5 €/km"),
    44: ("veh", 32, "car"),
    45: ("emp", 40),
    46: ("veh", 110, "car"),
    47: ("hab", 60_000, 90),
    48: ("est", 1.5, "téléphérique de 1,2 km, ~263 000 voyages par an"),
    49: ("veh", 43, "bus"),
    50: ("hab", 130_000, 70),
    51: ("hab", 440_000, 150),
    52: ("veh", 92, "car"),
    53: ("hab", 90_000, 80),
    54: ("veh", 35, "bus"),
    55: ("voy", 1_500_000),
    56: ("hab", 105_000, 80),
    57: ("emp", 150), 58: ("emp", 300),
    59: ("hab", 55_000, 70),
    60: ("emp", 170), 61: ("emp", 64), 62: ("veh", 110, "car"), 63: ("emp", 61),
    64: ("emp", 85 / 0.7, "85 conducteurs (~70 % de l’effectif)"),
    65: ("veh", 17, "bus"), 66: ("veh", 52, "bus"), 67: ("emp", 140), 68: ("emp", 200),
    69: ("hab", 77_000, 80),
    70: ("hab", 115_000, 90),
    71: ("voy", 3_200_000),
    72: ("veh", 65, "bus"),
    73: ("voy", 7_000_000),
    74: ("mix", [(32, "metro"), (80, "tram"), (23, "train")], "métro, tramway et Rhônexpress"),
    75: ("km", 30, "tram"),
    76: ("km", 63, "metro", "lignes 1 et 2, ~63 km de métro automatique"),
    77: ("est", 5, "navettes autonomes, ordre de grandeur"),
    78: ("km", 80, "train"),
    79: ("km", 24, "metro"),
    80: ("emp", 3000, "~3 000 équivalents temps plein (sous-traitants inclus)"),
    81: ("km", 75, "tram", "4 lignes, ~75 km de tramway"),
    82: ("km", 19, "tram"),
    83: ("km", 83.7, "train"),
    84: ("voy", 6850 * 365, "6 850 passagers par jour"),
    85: ("emp", 5000),
    86: ("mix", [(76, "metro"), (24, "tram")], "métro et tramway de Lusail"),
    87: ("km", 20.7, "metro"),
    88: ("km", 19, "tram"),
    89: ("km", 69, "metro", "3 lignes, 69 km de métro"),
}
# Réseaux pas encore en service : pas de coût avant l'année de mise en service (fiche ratpdev.com)
START = {35: 2035}

MODE_FR = {"metro": "métro", "tram": "tramway", "train": "voie ferrée"}
VEH_FR = {"bus": "bus", "tad": "véhicules de TAD", "car": "autocars"}


def fr(x: float, d: int = 0) -> str:
    s = f"{x:,.{d}f}".replace(",", " ").replace(".", ",")
    return s


def estimate(n: dict, basis: tuple) -> tuple[float, str]:
    """Budget d'exploitation (M€/an, avant indice pays) et base de calcul lisible."""
    kind, val, *extra = basis
    if kind == "emp":
        lab = extra[0] if extra else f"{fr(val)} employés"
        return val * EMP_COST / 1000, f"{lab} × {fr(EMP_COST)} k€"
    if kind == "veh":
        typ = extra[0]
        return val * STAFF_PER_VEH[typ] * EMP_COST / 1000, f"{fr(val)} {VEH_FR[typ]} × {fr(STAFF_PER_VEH[typ], 1)} employé/véhicule × {fr(EMP_COST)} k€"
    if kind == "km":
        mode = extra[0]
        lab = extra[1] if len(extra) > 1 else f"{fr(val, 1 if val % 1 else 0)} km de {MODE_FR[mode]}"
        return val * KM_COST[mode], f"{lab} × {fr(KM_COST[mode], 1)} M€/km"
    if kind == "voy":
        lab = extra[0] if extra else f"{fr(val / 1e6, 1)} M de voyages par an"
        return val * TRIP_COST / 1e6, f"{lab} × {fr(TRIP_COST, 1)} € par voyage"
    if kind == "hab":
        return val * extra[0] / 1e6, f"~{fr(val)} habitants desservis × {fr(extra[0])} € par habitant"
    if kind == "mix":
        parts = " + ".join(f"{fr(km)} km de {MODE_FR[m]} × {fr(KM_COST[m], 1)} M€" for km, m in val)
        return sum(km * KM_COST[m] for km, m in val), f"{extra[0]} : {parts}"
    if kind == "est":
        return val, extra[0]
    raise ValueError(kind)


def main() -> None:
    # Réseaux exploités seulement : les prospects sont ajoutés ensuite par scripts/prepare_prospects.py (à relancer)
    networks = [n for n in json.loads((DATA / "networks.json").read_text(encoding="utf-8")) if n.get("st") != "prospect"]
    missing = [n["id"] for n in networks if n["id"] not in BASIS]
    if missing:
        raise SystemExit(f"Base d'estimation manquante pour les réseaux : {missing}")
    out = []
    for n in networks:
        b0, base = estimate(n, BASIS[n["id"]])
        k = COUNTRY[n["pays"]]
        if k != 1:
            base += f" × indice pays {fr(k, 2)}"
        row = {"b": round(b0 * k, 2), "base": base}
        kind, val, *_ = BASIS[n["id"]]
        if kind == "mix":  # part de chaque mode dans le budget : sert à pondérer la valeur des actifs
            tot = sum(km * KM_COST[m] for km, m in val)
            row["parts"] = {m: round(km * KM_COST[m] / tot, 3) for km, m in val}
        if n["id"] in START:
            row["from"] = START[n["id"]]
        out.append(row)
    doc = {
        "_doc": "Budget d'exploitation annuel estimé par réseau (M€/an, euros 2026), dans l'ordre de networks.json. "
                "Généré par scripts/prepare_finance.py ; « from » = année de mise en service ; « parts » = part de chaque mode (réseaux mixtes).",
        "networks": out,
    }
    (DATA / "finance.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tot = sum(r["b"] for r in out)
    print(f"data/finance.json : {len(out)} réseaux, budget total estimé {fr(tot)} M€/an")
    for n, r in sorted(zip(networks, out), key=lambda x: -x[1]["b"])[:12]:
        print(f"  {fr(r['b'], 1):>8} M€  {n['ci'][:30]:30}  {r['base']}")


if __name__ == "__main__":
    main()
