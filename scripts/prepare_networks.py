"""Prépare le jeu de données des réseaux RATP Dev pour la carte.

Entrée : data/references_raw.json (extrait de l'API du site ratpdev.com, collection "references").
Sortie : data/networks.json + data/corrections.json

Usage : python scripts/prepare_networks.py   (puis python build.py)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
raw = json.loads((ROOT / "data/references_raw.json").read_text(encoding="utf-8"))

# Corrections appliquées aux données source (tracées et affichées dans la carte)
CORRECTIONS = [
    # (ville source, titre contient, champ, nouvelle valeur, motif)
    ("Vienne", "mobilité adaptée", "coords", (45.5255, 4.8740),
     "Point placé dans le département de la Vienne (Poitou) au lieu de Vienne (Isère), siège de Vienne Condrieu Agglomération"),
    ("Québec", "colonne vertébrale", "coords", (46.8139, -71.2080),
     "Point placé au centre de la province de Québec, à ~600 km de la ville"),
    ("Toscane", "ferroviaire de la Toscane", "coords", (43.4633, 11.8796),
     "Point identique à celui d'Autolinee Toscane ; LFI est basée à Arezzo"),
    ("Doha", "croissance de Doha", "coords", (25.2854, 51.5310),
     "Point situé à ~30 km à l'ouest de Doha, en zone désertique"),
    ("Daytona Beach", "écoresponsable", "cl", "Comté de Volusia (Votran)",
     "Client indiqué « Ventura County Transportation Commission » (copie de la fiche Ventura)"),
    ("Comté du Lac", "comté de Lake", "cl", "Comté de Lake, FL", "Coquille « Comté du Lacy »"),
    ("Comté du Lac", "comté de Lake", "ci", "Comté de Lake", "Traduction littérale « Comté du Lac »"),
    ("Tuscon", "Tucson", "ci", "Tucson", "Coquille « Tuscon »"),
    ("Tuscon", "Tucson", "cl", "Agglomération de Tucson", "Coquille « Tuscon »"),
    ("Hong Kong", "Ding Ding", "coords", (22.2815, 114.1700),
     "Point placé sur les collines de Kowloon (≈190 m) ; le tramway longe la rive nord de l'île de Hong Kong, au niveau de la mer"),
]

# Familles de couleur (3 teintes validées CVD) + glyphe par mode principal
PRIMARY_ORDER = [
    ("Métro et métro automatique", "metro"),
    ("Ferroviaire", "train"),
    ("Tramway", "tram"),
    ("Bus et BHNS", "bus"),
    ("Navettes autonomes / PMR / TAD", "tad"),
    ("Transport par câble", "cable"),
    ("Navettes maritimes et fluviales", "boat"),
]

COUNTRY_FIX = {"Etats-Unis": "États-Unis", "Egypte": "Égypte"}

applied = []
out = []
for i, r in enumerate(raw):
    r = dict(r)
    orig_city = r["ci"].strip()
    for city, title_part, field, value, why in CORRECTIONS:
        if orig_city == city and title_part.lower() in r["t"].lower():
            if field == "coords":
                before = f'{r["la"]:.4f}, {r["lo"]:.4f}'
                r["la"], r["lo"] = value
                after = f"{value[0]:.4f}, {value[1]:.4f}"
                label = "Coordonnées"
            else:
                before, after = r[field], value
                r[field] = value
                label = {"cl": "Client", "ci": "Ville"}[field]
            applied.append({"reseau": r["t"], "champ": label, "avant": before, "apres": after, "motif": why})

    zone = r["co"]
    if zone == "France-Suisse":
        pays = "Suisse" if r["ci"] == "Genève" else "France"
    else:
        pays = COUNTRY_FIX.get(zone, zone)

    primary = next(key for label, key in PRIMARY_ORDER if label in r["m"])
    out.append({
        "id": i,
        "t": r["t"].strip(),
        "zone": COUNTRY_FIX.get(zone, zone),
        "pays": pays,
        "ci": r["ci"].strip(),
        "cl": r["cl"].strip(),
        "s": r["s"].strip(),
        "m": r["m"],
        "p": primary,
        "la": round(r["la"], 5),
        "lo": round(r["lo"], 5),
        "kf": [k.strip() for k in r["kf"]],
        "pg": r["pg"],
    })

assert len(out) == 90, len(out)
(ROOT / "data/networks.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
(ROOT / "data/corrections.json").write_text(json.dumps(applied, ensure_ascii=False, indent=1), encoding="utf-8")

from collections import Counter
print("réseaux:", len(out))
print("pays:", Counter(o["pays"] for o in out).most_common())
print("mode principal:", Counter(o["p"] for o in out).most_common())
print("modes (tous):", Counter(m for o in out for m in o["m"]).most_common())
print("corrections appliquées:", len(applied))
for a in applied:
    print("  -", a["champ"], "|", a["reseau"][:50], "|", a["avant"], "->", a["apres"])
