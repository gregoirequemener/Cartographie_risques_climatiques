"""Dépôts bus du réseau Mistral (Toulon) face au risque inondation → data/toulon_depots.json

Prépare les données de la vue 3D « Dépôts Mistral · inondation » (src/toulon_depots.html, build_toulon.py) :
pour chaque site, un bloc de terrain de ~700 m de côté avec le relief, les bâtiments, les routes, la végétation,
les cours d'eau, la photo aérienne, l'emprise cadastrale du dépôt et les hauteurs d'eau des cartes du TRI
Toulon-Hyères (Directive inondation, rapportage 2020) pour quatre scénarios.

Sites (sources publiques) :
  - Dépôt de Brunet (Toulon, rue Octave Virgily) : dépôt et ateliers, siège de RD Toulon Provence Méditerranée.
    Emprise : parcelle cadastrale AX 566 (= « Réseau Mistral - Dépôt de Brunet » dans OpenStreetMap).
  - Dépôt de Brégaillon (La Seyne-sur-Mer, 306 av. Yitzhak Rabin) : dépôt, ateliers, station GNV, photovoltaïque
    (déclaration ICPE de juillet 2023). Emprise : parcelle AD 38 (bâtiment « Réseau Mistral » et cour de remisage).
  - SEMR de Sainte-Musse (Toulon, projet BHNS déclaré d'utilité publique le 9 octobre 2025) : site d'exploitation,
    de maintenance et de remisage de 150 bus sur l'ancien marché de gros de la ZAE Sainte-Musse.
    Emprise indicative : parcelle AW 360 (friche de l'ancien marché de gros), le plan masse n'étant pas publié.

Sources téléchargées (cache dans le dossier temporaire du système) :
  - Géoplateforme IGN : RGE ALTI (WMS-R, valeurs brutes), BD ORTHO (WMS-R), BD TOPO et Parcellaire Express (WFS)
  - Géorisques : surfaces inondables et hauteurs d'eau du TRI (WFS, couches ISO_HT_*)

Prérequis : numpy, shapely >= 2, pyproj, rasterio (pip install -r requirements-dev.txt)
Usage     : python scripts/prepare_toulon_depots.py && python build_toulon.py
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from scipy import ndimage
from pyproj import Transformer
from rasterio import features
from rasterio.transform import from_origin
from shapely import make_valid
from shapely.geometry import LineString, MultiPolygon, Polygon, box, mapping, shape
from shapely.ops import transform as stransform, unary_union

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "toulon_depots.json"
CACHE = Path(tempfile.gettempdir()) / "carto-risques-toulon-cache"
UA = {"User-Agent": "carto-risques-climatiques/1.0 (prepare_toulon_depots.py)"}
GEOPF_WFS = "https://data.geopf.fr/wfs/ows"
GEOPF_WMS = "https://data.geopf.fr/wms-r/wms"
GEORISQUES = "https://www.georisques.gouv.fr/services"
TO93 = Transformer.from_crs(4326, 2154, always_xy=True)
TO84 = Transformer.from_crs(2154, 4326, always_xy=True)

CELLS = 320          # mailles du relief par côté (≈ 2 à 3 m)
ORTHO_PX = 1400      # photo aérienne : pixels par côté
RAYON = 150          # rayon (m) du test de sensibilité au niveau d'eau voisin

SITES = [
    {"id": "brunet", "nom": "Dépôt de Brunet", "commune": "Toulon", "statut": "En service",
     "adresse": "Rue Octave Virgily, 83100 Toulon",
     "role": "Dépôt principal du réseau : remisage, ateliers de maintenance, siège de RD Toulon Provence Méditerranée. "
             "Transformateur installé pour la recharge des bus électriques.",
     "parcelles": ["83137000AX0566"], "centre": (941450, 6229760), "demi": 330},
    {"id": "bregaillon", "nom": "Dépôt de Brégaillon", "commune": "La Seyne-sur-Mer", "statut": "En service",
     "adresse": "306 avenue Yitzhak Rabin, 83500 La Seyne-sur-Mer",
     "role": "Dépôt de l'ouest de la rade : remisage, ateliers, station de recharge GNV (2020), toiture photovoltaïque. "
             "À adapter pour les premiers bus du BHNS.",
     "parcelles": ["83126000AD0038"], "centre": (934330, 6228330), "demi": 420},
    {"id": "sainte-musse", "nom": "SEMR de Sainte-Musse", "commune": "Toulon", "statut": "Projet BHNS",
     "adresse": "ZAE Sainte-Musse, ancien marché de gros, 83100 Toulon",
     "role": "Futur site d'exploitation, de maintenance et de remisage : 150 bus (dont 22 BHNS), poste de contrôle "
             "centralisé, parking relais silo de 510 places. Doit permettre à terme de fermer Brunet. "
             "Emprise indicative (plan masse non publié).",
     "parcelles": ["83137000AW0360"], "centre": (942930, 6230360), "demi": 340},
]

# Scénarios affichés : débordement de cours d'eau (01) et submersion marine (03) combinés (hauteur maximale)
SCENARIOS = [
    {"id": "frequent", "nom": "Crue fréquente", "periode": "10 à 30 ans", "couches": ["01_01FOR", "03_01FOR"]},
    {"id": "moyen", "nom": "Crue moyenne", "periode": "100 à 300 ans", "couches": ["01_02MOY", "03_02MOY"]},
    {"id": "moyen-cc", "nom": "Moyenne + climat", "periode": "100 ans, mer +60 cm", "couches": ["01_02MOY", "03_03MCC"]},
    {"id": "extreme", "nom": "Crue extrême", "periode": "≈ 1 000 ans", "couches": ["01_04FAI", "03_04FAI"]},
]
DEPTH_CODES = {("0", "0.5"): 1, ("0", "1"): 2, ("0.5", "1"): 3, ("1", "2"): 4, ("2", "9999"): 5}
DEPTH_MID = [0, 0.25, 0.5, 0.75, 1.5, 2.5]   # hauteur représentative de chaque code (m)


# ---------- téléchargements ----------
def fetch(url: str) -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / hashlib.sha1(url.encode()).hexdigest()
    if f.exists():
        return f.read_bytes()
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                data = r.read()
            if data:  # réponse vide (Géorisques sans objet) : non mise en cache
                f.write_bytes(data)
            return data
        except Exception as e:
            if attempt == 4:
                raise
            print(f"    nouvel essai ({e})")
            time.sleep(2 ** attempt)
    raise RuntimeError(url)


def bbox84(b):
    w, s = TO84.transform(b[0], b[1]); e, n = TO84.transform(b[2], b[3])
    return w, s, e, n


def geopf(layer: str, b) -> list[dict]:
    w, s, e, n = bbox84(b)
    out, start = [], 0
    while True:
        p = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": layer, "SRSNAME": "EPSG:4326",
             "OUTPUTFORMAT": "application/json", "COUNT": 5000, "STARTINDEX": start,
             "BBOX": f"{s},{w},{n},{e},urn:ogc:def:crs:EPSG::4326"}
        fs = json.loads(fetch(GEOPF_WFS + "?" + urllib.parse.urlencode(p)))["features"]
        out += fs
        if len(fs) < 5000:
            return out
        start += 5000


def tri(layer: str, b) -> list[dict]:
    w, s, e, n = bbox84(b)
    p = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": "ms:" + layer,
         "OUTPUTFORMAT": "application/json; subtype=geojson; charset=utf-8", "SRSNAME": "EPSG:4326",
         "BBOX": f"{s},{w},{n},{e},urn:ogc:def:crs:EPSG::4326"}
    raw = fetch(GEORISQUES + "?" + urllib.parse.urlencode(p))
    return json.loads(raw)["features"] if raw.strip() else []


def wms(layer: str, b, px: int, fmt: str) -> bytes:
    p = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": layer, "STYLES": "", "CRS": "EPSG:2154",
         "BBOX": ",".join(f"{v:.2f}" for v in b), "WIDTH": px, "HEIGHT": px, "FORMAT": fmt}
    return fetch(GEOPF_WMS + "?" + urllib.parse.urlencode(p))


def to93(g):
    return make_valid(stransform(lambda x, y, z=None: TO93.transform(x, y), shape(g)))


def polys(g) -> list[Polygon]:
    if g.is_empty: return []
    if isinstance(g, Polygon): return [g]
    if isinstance(g, MultiPolygon): return list(g.geoms)
    return [p for part in getattr(g, "geoms", []) for p in polys(part)]


def lines(g) -> list[LineString]:
    if g.is_empty: return []
    if isinstance(g, LineString): return [g]
    return [l for part in getattr(g, "geoms", []) for l in lines(part)]


# ---------- encodage compact (coordonnées locales au décimètre) ----------
def ring(coords, cx, cy):
    return [v for x, y in list(coords)[:-1] for v in (round((x - cx) * 10), round((y - cy) * 10))]


def poly_rec(p: Polygon, cx, cy):
    p = p.simplify(0.3)
    if p.is_empty or not isinstance(p, Polygon): return None
    return [ring(p.exterior.coords, cx, cy)] + [ring(r.coords, cx, cy) for r in p.interiors]


def line_rec(l: LineString, cx, cy):
    l = l.simplify(0.5)
    return [v for x, y in l.coords for v in (round((x - cx) * 10), round((y - cy) * 10))]


def b64(a: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


# ---------- un site ----------
def site(S: dict) -> dict:
    cx, cy = S["centre"]; h = S["demi"]
    B = (cx - h, cy - h, cx + h, cy + h)
    R = box(*B)
    res = 2 * h / CELLS
    print(f"• {S['nom']} : maille {res:.2f} m")

    # relief (RGE ALTI, valeurs brutes, première ligne au nord) : sommets de la grille, centrés sur les mailles
    n = CELLS + 1
    raw = wms("ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES", (B[0] - res / 2, B[1] - res / 2, B[2] + res / 2, B[3] + res / 2), n,
              "image/x-bil;bits=32")
    dem = np.frombuffer(raw, dtype="<f4").reshape(n, n).astype(np.float64)
    sea = dem < -50
    dem[sea] = -1.5
    base = float(np.floor(dem[~sea].min())) if (~sea).any() else 0.0

    # emprise du dépôt (parcelles cadastrales)
    par = geopf("CADASTRALPARCELS.PARCELLAIRE_EXPRESS:parcelle", B)
    foot = unary_union([to93(f["geometry"]) for f in par if f["properties"]["idu"] in S["parcelles"]])
    assert not foot.is_empty, S["parcelles"]
    print(f"    emprise {foot.area:,.0f} m²")

    # bâtiments
    blds = []
    for f in geopf("BDTOPO_V3:batiment", B):
        pr = f["properties"]
        g = to93(f["geometry"]).intersection(R)
        for p in polys(g):
            if p.area < 8: continue
            rec = poly_rec(p, cx, cy)
            if not rec: continue
            z0 = pr.get("altitude_minimale_sol")
            ht = pr.get("hauteur") or 4.0
            inside = p.intersection(foot).area > 0.5 * p.area
            blds.append({"p": rec, "h": round(float(ht), 1), "z": None if z0 is None else round(float(z0), 1),
                         "s": 1 if inside else 0, "a": round(p.area), "geom": p,
                         "u": pr.get("usage_1") or "", "n": pr.get("nature") or ""})
    print(f"    {len(blds)} bâtiments, dont {sum(b['s'] for b in blds)} dans l'emprise")

    # routes, végétation, cours d'eau
    roads = []
    for f in geopf("BDTOPO_V3:troncon_de_route", B):
        pr = f["properties"]
        if pr.get("position_par_rapport_au_sol") not in (None, "0", 0): continue
        w = pr.get("largeur_de_chaussee") or {"1": 10, "2": 8, "3": 6, "4": 5}.get(str(pr.get("importance")), 3.5)
        for l in lines(to93(f["geometry"]).intersection(R.buffer(20))):
            roads.append({"l": line_rec(l, cx, cy), "w": round(float(w), 1)})
    veg = []
    for f in geopf("BDTOPO_V3:zone_de_vegetation", B):
        for p in polys(to93(f["geometry"]).intersection(R)):
            rec = poly_rec(p, cx, cy)
            if rec: veg.append(rec)
    hydro = []
    for f in geopf("BDTOPO_V3:troncon_hydrographique", B):
        pr = f["properties"]
        for l in lines(to93(f["geometry"]).intersection(R)):
            hydro.append({"l": line_rec(l, cx, cy), "s": 0 if str(pr.get("position_par_rapport_au_sol")) == "0" else 1,
                          "n": pr.get("cpx_toponyme_de_cours_d_eau") or ""})
    waters = []
    for f in geopf("BDTOPO_V3:surface_hydrographique", B):
        for p in polys(to93(f["geometry"]).intersection(R)):
            rec = poly_rec(p, cx, cy)
            if rec: waters.append(rec)

    # zones inondables du TRI → grille des codes de hauteur, par scénario
    transform = from_origin(B[0] - res / 2, B[3] + res / 2, res, res)
    site_mask = features.rasterize([(mapping(foot), 1)], out_shape=(n, n), transform=transform, dtype="uint8").astype(bool)
    bld_site = [b for b in blds if b["s"]]
    bmask = features.rasterize([(mapping(b["geom"]), 1) for b in bld_site], out_shape=(n, n), transform=transform,
                               dtype="uint8").astype(bool) if bld_site else np.zeros((n, n), bool)
    # masque du site : 1 surface ouverte, 2 + k bâtiment k du site (k = rang dans bld_site)
    smask = site_mask.astype(np.uint8)
    for k, b in enumerate(bld_site[:250]):
        r = features.rasterize([(mapping(b["geom"]), 1)], out_shape=(n, n), transform=transform, dtype="uint8").astype(bool)
        smask[r & site_mask] = 2 + k
        b["k"] = k
    scen_out, rivers = [], {}
    grid = np.zeros((n, n), np.uint8)   # cumulatif : une crue plus rare inonde au moins les zones d'une crue plus fréquente
    zone = []
    for sc in SCENARIOS:
        kinds = set()
        for lay in sc["couches"]:
            for f in tri("ISO_HT_" + lay + "_FXX", tuple(v + d for v, d in zip(B, (-300, -300, 300, 300)))):
                pr = f["properties"]
                code = DEPTH_CODES.get((pr.get("ht_min"), pr.get("ht_max")))
                if not code: continue
                g = to93(f["geometry"])
                zone.append(g)
                if not g.intersects(R): continue
                kinds.add("submersion" if lay.startswith("03") else "debordement")
                if lay.startswith("01") and pr.get("cours_deau"):
                    big = max(polys(g.intersection(R)) or [Polygon()], key=lambda p: p.area)
                    if big.area > rivers.get(pr["cours_deau"], (0, None))[0]:
                        rivers[pr["cours_deau"]] = (big.area, big.representative_point())
                r = features.rasterize([(mapping(g), code)], out_shape=(n, n), transform=transform, dtype="uint8")
                grid = np.maximum(grid, r)
        depth = np.array(DEPTH_MID)[grid]
        # sensibilité : hauteur du sol au-dessus du niveau d'eau le plus bas dans un rayon de 150 m
        # (niveau = sol + hauteur d'eau) ; le niveau le plus bas évite de comparer à un tronçon amont, plus haut
        wet = grid > 0
        if wet.any():
            level = np.where(wet, dem + depth, np.inf)
            low = ndimage.minimum_filter(level, size=int(2 * RAYON / res) + 1, mode="nearest")
            marge = np.clip(dem - low, 0, 25)
            mq = np.where(np.isfinite(low) & ~wet, np.round(marge * 10), 255).astype(np.uint8)
            mq[wet] = 0
        else:
            mq = np.full((n, n), 255, np.uint8)
        site_m = mq[site_mask]
        reach = None if not site_mask.any() or site_m.min() == 255 else round(float(site_m.min()) / 10, 1)
        cell = res * res
        wet_site = site_mask & (grid > 0)
        zone_u = unary_union(zone) if zone else Polygon()
        dist = 0.0 if foot.intersects(zone_u) else (round(foot.distance(zone_u)) if not zone_u.is_empty else None)
        open_mask = site_mask & ~bmask
        flooded_b = [b for b in bld_site if (grid[features.rasterize([(mapping(b["geom"]), 1)], out_shape=(n, n),
                                                                     transform=transform, dtype="uint8").astype(bool)] > 0).any()]
        st = {
            "part": round(float(wet_site.sum() / max(1, site_mask.sum())), 3),
            "surf": round(float(wet_site.sum() * cell)),
            "ouvert": round(float((open_mask & (grid > 0)).sum() * cell)),
            "ouvertTotal": round(float(open_mask.sum() * cell)),
            "bati": len(flooded_b), "batiTotal": len(bld_site),
            "batiSurf": sum(b["a"] for b in flooded_b),
            "hmax": round(float(depth[site_mask].max()), 2) if site_mask.any() else 0,
            "hcode": int(grid[site_mask].max()) if site_mask.any() else 0,
            "h50": round(float((open_mask & (depth >= 0.5)).sum() * cell)),
            "dist": dist, "types": sorted(kinds), "atteint": reach,
        }
        scen_out.append({"id": sc["id"], "g": b64(grid), "m": b64(mq), "st": st})
        print(f"    {sc['nom']:<18} site inondé {st['part']:.0%} · dist {dist} m · atteint à +{reach} m · {st['types']}")

    # photo aérienne (BD ORTHO)
    jpg = wms("ORTHOIMAGERY.ORTHOPHOTOS", B, ORTHO_PX, "image/jpeg")

    dem_q = np.round((dem - base) * 20).astype("<i2")   # 5 cm
    fx, fy = foot.representative_point().coords[0]
    return {
        "id": S["id"], "nom": S["nom"], "commune": S["commune"], "statut": S["statut"], "adresse": S["adresse"],
        "role": S["role"], "parcelles": S["parcelles"], "surface": round(foot.area),
        "centre93": [cx, cy], "centre84": [round(v, 5) for v in TO84.transform(cx, cy)], "demi": h, "n": n, "res": res,
        "base": base, "dem": b64(dem_q), "mer": bool(sea.any()), "masque": b64(smask),
        "emprise": [r for p in polys(foot) for r in [poly_rec(p, cx, cy)] if r],
        "label": [round(fx - cx, 1), round(fy - cy, 1)],
        "bat": [{k: v for k, v in b.items() if k != "geom"} for b in blds],
        "zmin": round(float(dem[site_mask].min()), 1), "zmax": round(float(dem[site_mask].max()), 1),
        "routes": roads, "veg": veg, "hydro": hydro, "eaux": waters,
        "rivieres": [{"n": k, "x": round(v[1].x - cx), "y": round(v[1].y - cy)} for k, v in rivers.items()],
        "scen": scen_out,
        "ortho": "data:image/jpeg;base64," + base64.b64encode(jpg).decode(),
    }


# ---------- tracés du réseau (localisation des sites) ----------
def network_lines() -> list[list[float]]:
    import gzip
    raw = json.loads(gzip.decompress((ROOT / "data" / "lines.json.gz").read_bytes()))
    net = next(x for x in raw["nets"] if x["i"] == 51)
    out = []
    for r in net["r"]:
        for s in r["s"]:
            a = b = 0; pts = []
            for j in range(0, len(s), 2):
                a += s[j]; b += s[j + 1]; pts += [round(b / 1e5, 4), round(a / 1e5, 4)]
            out.append(pts)
    return out


def main() -> None:
    data = {
        "_doc": "Généré par scripts/prepare_toulon_depots.py. Coordonnées locales en décimètres (Lambert 93 − centre du site). "
                "dem : Int16 (cm×5 au-dessus de base), lignes du nord au sud ; scen[].g : codes de hauteur d'eau Uint8 sur la même grille.",
        "genere": time.strftime("%Y-%m-%d"),
        "scenarios": [{k: v for k, v in s.items() if k != "couches"} for s in SCENARIOS],
        "hauteurs": DEPTH_MID,
        "sites": [site(S) for S in SITES],
        "reseau": network_lines(),
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)} : {OUT.stat().st_size / 1e6:.1f} Mo")


if __name__ == "__main__":
    main()
