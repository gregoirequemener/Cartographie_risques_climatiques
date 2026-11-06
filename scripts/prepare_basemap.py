"""Fond de carte précis autour des réseaux : terres, mer, cours d'eau et lacs → data/basemap.json.gz

Le fond mondial (Natural Earth 1:50 M) a plusieurs kilomètres d'erreur sur les côtes : à l'échelle
d'une agglomération, les tracés GTFS tombaient « dans la mer ». Ce script remplace le fond grossier,
dans une zone autour de chaque réseau, par des données précises :

  - France : communes de la BD TOPO (IGN, précision métrique), dont le contour suit le trait de côte,
    et surfaces hydrographiques permanentes de la BD TOPO (fleuves, rivières larges, lacs, étangs) ;
  - ailleurs : terres et petites îles Natural Earth 1:10 M (environ 5 fois plus fines que le fond mondial).

Zone d'un réseau : emprise de ses tracés + 4 km pour les réseaux français cartographiés ; ± 15 km autour
du point pour les autres réseaux français ; ± 20 km hors de France. Hors de ces zones, le fond mondial
est conservé. Le contour des terres sert au fond de carte et au masque de la mer (calques températures
et relief) ; les cours d'eau et lacs précis remplacent ceux de Natural Earth dans les zones françaises.

Sources téléchargées (mises en cache dans le dossier temporaire du système) :
  - Géoplateforme IGN, service WFS : BDTOPO_V3:commune, BDTOPO_V3:surface_hydrographique (Licence Ouverte)
  - Natural Earth 10m : land, minor_islands, admin_0_countries (domaine public)

Prérequis : Python 3.10+, shapely >= 2 et geopandas (lecture des fichiers Natural Earth).
Usage     : python scripts/prepare_basemap.py && python build.py
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
from shapely import force_2d, make_valid
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon, box, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = Path(tempfile.gettempdir()) / "carto-risques-basemap-cache"
UA = {"User-Agent": "carto-risques-climatiques/1.0 (prepare_basemap.py)"}
WFS = "https://data.geopf.fr/wfs/ows"
NE = "https://naciscdn.org/naturalearth/10m/{}.zip"

MARGIN_LINES_KM = 4      # marge autour de l'emprise des tracés
HALF_FR_KM = 15          # demi-côté de la zone, réseaux français sans tracés
HALF_WORLD_KM = 20       # demi-côté de la zone, hors de France
SIMPLIFY_FINE = 0.00003  # ~3 m : tolérance de simplification des contours IGN
SIMPLIFY_NE = 0.0003     # ~30 m : Natural Earth 10m (détail ~100 m)
SIMPLIFY_WATER = 0.000045  # ~5 m : surfaces en eau IGN (moins d'un pixel et demi au zoom maximal de la carte)
MIN_WATER_HA = 1         # surfaces en eau plus petites ignorées
Q = 1e5                  # quantification des coordonnées (1e-5° ≈ 1 m)


# ---------- téléchargements ----------
def fetch(url: str, params: dict | None = None) -> bytes:
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / hashlib.sha1(full.encode()).hexdigest()
    if f.exists():
        return f.read_bytes()
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(full, headers=UA), timeout=180) as r:
                data = r.read()
            f.write_bytes(data)
            return data
        except Exception as e:  # réseau capricieux : on réessaie avec un délai croissant
            if attempt == 4:
                raise
            print(f"    nouvel essai ({e})")
            time.sleep(2 ** attempt)
    raise RuntimeError("inaccessible")


def wfs(layer: str, bounds: tuple[float, float, float, float], props: tuple[str, ...] = ()) -> list[dict]:
    """Objets d'une couche WFS de la Géoplateforme dans une emprise (w, s, e, n), avec pagination."""
    w, s, e, n = bounds
    out, start, page = [], 0, 5000
    while True:
        raw = fetch(WFS, {
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": layer,
            "SRSNAME": "EPSG:4326", "OUTPUTFORMAT": "application/json", "COUNT": page, "STARTINDEX": start,
            "BBOX": f"{s},{w},{n},{e},urn:ogc:def:crs:EPSG::4326",
            **({"PROPERTYNAME": ",".join(("geometrie",) + props)} if props else {}),
        })
        feats = json.loads(raw).get("features", [])
        out += feats
        if len(feats) < page:
            return out
        start += page


def natural_earth(name: str):
    path = CACHE / f"ne_10m_{name.split('/')[-1]}.zip"
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fetch(NE.format(name)))
    return gpd.read_file(path)


# ---------- TopoJSON → shapely ----------
def topo_arcs(topo: dict) -> list[list[tuple[float, float]]]:
    sx, sy = topo["transform"]["scale"]; tx, ty = topo["transform"]["translate"]
    arcs = []
    for a in topo["arcs"]:
        x = y = 0; pts = []
        for p in a:
            x += p[0]; y += p[1]; pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    return arcs


def topo_line(arcs, idxs):
    pts = []
    for i in idxs:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts += a if not pts else a[1:]
    return pts


def unwrap_ring(pts):
    """Anneau qui saute de +180 à −180 : on le prolonge au-delà de 180° pour qu'il reste valide."""
    out = [pts[0]]
    for x, y in pts[1:]:
        px = out[-1][0]
        while x - px > 180: x -= 360
        while x - px < -180: x += 360
        out.append((x, y))
    return out


def topo_geoms(topo: dict, obj: str):
    arcs = topo_arcs(topo)
    for g in topo["objects"][obj]["geometries"]:
        t, a, props = g["type"], g.get("arcs"), g.get("properties") or {}
        if t == "Polygon":
            yield props, [[unwrap_ring(topo_line(arcs, r)) for r in a]]
        elif t == "MultiPolygon":
            yield props, [[unwrap_ring(topo_line(arcs, r)) for r in p] for p in a]
        elif t == "LineString":
            yield props, [topo_line(arcs, a)]
        elif t == "MultiLineString":
            yield props, [topo_line(arcs, l) for l in a]


def polys(g) -> list[Polygon]:
    if g.is_empty: return []
    if isinstance(g, Polygon): return [g]
    if isinstance(g, MultiPolygon): return list(g.geoms)
    return [p for part in getattr(g, "geoms", []) for p in polys(part)]


def lines(g) -> list[LineString]:
    if g.is_empty: return []
    if isinstance(g, LineString): return [g]
    if isinstance(g, MultiLineString): return list(g.geoms)
    return [l for part in getattr(g, "geoms", []) for l in lines(part)]


# ---------- zones à affiner ----------
def km_box(lat: float, lon: float, half_km: float):
    dy = half_km / 111.2; dx = half_km / (111.2 * math.cos(math.radians(lat)))
    return box(lon - dx, lat - dy, lon + dx, lat + dy)


def zones(networks: list[dict]) -> list[Polygon]:
    raw = json.loads(gzip.decompress((DATA / "lines.json.gz").read_bytes()))
    ext = {}
    for net in raw["nets"]:
        la, lo = [], []
        for r in net["r"]:
            for s in r["s"]:
                a = b = 0
                for j in range(0, len(s), 2):
                    a += s[j]; b += s[j + 1]; la.append(a / Q); lo.append(b / Q)
        ext[net["i"]] = (min(lo), min(la), max(lo), max(la))
    boxes = []
    for n in networks:
        if n["id"] in ext:
            w, s, e, nn = ext[n["id"]]
            dy = MARGIN_LINES_KM / 111.2; dx = MARGIN_LINES_KM / (111.2 * math.cos(math.radians(n["la"])))
            boxes.append(box(w - dx, s - dy, e + dx, nn + dy))
        else:
            boxes.append(km_box(n["la"], n["lo"], HALF_FR_KM if n["pays"] == "France" else HALF_WORLD_KM))
    return polys(unary_union(boxes))


# ---------- terres et eaux précises d'une zone ----------
def ign_land(R, france_inner) -> object:
    """Terres françaises de la zone selon les communes BD TOPO (zone intérieure : la zone entière)."""
    if R.within(france_inner):
        return R
    feats = wfs("BDTOPO_V3:commune", R.bounds, ("code_insee",))
    geoms = [make_valid(force_2d(shape(f["geometry"]))) for f in feats if f.get("geometry")]
    return unary_union(geoms).intersection(R) if geoms else Polygon()


def ign_water(R, land):
    """Surfaces en eau permanentes de la BD TOPO. Les objets sont gardés entiers, même au-delà de la zone
    (le Léman est un seul polygone) ; seules leurs parties en mer dans la zone (bassins portuaires) sont retirées."""
    feats = wfs("BDTOPO_V3:surface_hydrographique", R.bounds, ("nature", "persistance", "position_par_rapport_au_sol"))
    keep = [make_valid(force_2d(shape(f["geometry"]))) for f in feats if f.get("geometry")
            and (f["properties"].get("persistance") or "Permanent") == "Permanent"
            and (f["properties"].get("position_par_rapport_au_sol") or "0") in ("0", "Au sol")]
    if not keep:
        return []
    lat = R.centroid.y
    min_area = MIN_WATER_HA * 1e4 / (111_200 ** 2 * math.cos(math.radians(lat)))
    u = unary_union(keep).difference(R.difference(land))
    return [p for p in polys(u) if p.area >= min_area]


def fine_land(R, ign, foreign_land, ne_ocean):
    """Terres de la zone : communes françaises + terres étrangères Natural Earth, puis comblement des
    « fausses mers » (interstices le long des frontières, lacs) : une poche sans terre n'est gardée en mer
    que si elle recoupe la mer Natural Earth."""
    land = unary_union([ign, foreign_land.intersection(R)])
    gaps = polys(R.difference(land))
    fill = [g for g in gaps if g.intersection(ne_ocean).area < max(0.3 * g.area, 1e-7)]
    if fill:
        land = unary_union([land] + fill)
    return land


# ---------- encodage ----------
def enc(coords) -> list[int]:
    out, px, py = [], 0, 0
    for c in coords:
        qx, qy = round(c[0] * Q), round(c[1] * Q)
        if out and qx == px and qy == py:
            continue
        out += [qx - px, qy - py]; px, py = qx, qy
    return out


def enc_poly(p: Polygon) -> list[list[int]]:
    return [enc(p.exterior.coords)] + [enc(r.coords) for r in p.interiors]


def main() -> None:
    networks = json.loads((DATA / "networks.json").read_text(encoding="utf-8"))
    world = json.loads((DATA / "geo/world-countries-50m.json").read_text(encoding="utf-8"))
    water = json.loads((DATA / "water.json").read_text(encoding="utf-8"))

    print("Natural Earth 10m…")
    ne_land = unary_union(list(natural_earth("physical/ne_10m_land").geometry) + list(natural_earth("physical/ne_10m_minor_islands").geometry))
    admin = natural_earth("cultural/ne_10m_admin_0_countries")
    france = unary_union(list(admin[admin["ADMIN"] == "France"].geometry))
    france_inner = france.buffer(-0.12)  # au-delà de ~10 km des côtes et frontières

    Z = zones(networks)
    zone_u = unary_union(Z)
    print(f"{len(Z)} zones à affiner")

    land_parts, fr_zones, fine_water = [], [], []
    for k, R in enumerate(Z):
        near_fr = R.intersects(france.buffer(0.05))
        ign = ign_land(R, france_inner) if near_fr else Polygon()
        foreign = ne_land.difference(france) if near_fr else ne_land
        ne_ocean = R.difference(ne_land)
        land = fine_land(R, ign, foreign.intersection(R) if not foreign.is_empty else Polygon(), ne_ocean)
        tol = SIMPLIFY_FINE if near_fr else SIMPLIFY_NE
        land = land.simplify(tol, preserve_topology=True)
        land_parts.append(land)
        if near_fr:
            fr_zones.append(R)
            fine_water += ign_water(R, land)
        w, s, e, n = R.bounds
        print(f"  zone {k + 1:>2}/{len(Z)}  {s:7.2f} {w:7.2f}  {'IGN' if near_fr else 'NE10m'}  "
              f"terres {sum(len(p.exterior.coords) for p in polys(land)):>6} sommets")

    # Fond mondial : terres Natural Earth 1:50 M (hors Antarctique), remplacées dans les zones
    coarse = [Polygon(p[0], p[1:]) for props, ps in topo_geoms(world, "countries")
              if props.get("name") != "Antarctica" for p in ps]
    coarse = unary_union([make_valid(p) for p in coarse])
    land = unary_union([coarse.difference(zone_u)] + land_parts)
    land_out = [enc_poly(p) for p in polys(land)]

    # Cours d'eau et lacs : Natural Earth hors des zones françaises + surfaces IGN dans ces zones
    fr_u = unary_union(fr_zones) if fr_zones else Polygon()
    rivers_out, lakes_out = [], []
    fine_u = unary_union(fine_water) if fine_water else Polygon()
    for props, ls in topo_geoms(water["rivers"], "rivers"):
        g = MultiLineString(ls).difference(fr_u).difference(fine_u)  # ni dans les zones françaises, ni à travers les lacs IGN
        segs = [enc(l.coords) for l in lines(g) if len(l.coords) > 1]
        if segs:
            rivers_out.append([props.get("sr", 9), segs])
    for props, ps in topo_geoms(water["lakes"], "lakes"):
        for p in ps:
            g = make_valid(Polygon(p[0], p[1:]))
            if g.intersects(fr_u):
                if g.intersection(fine_u).area > 0.5 * g.area:
                    continue  # lac déjà décrit, en entier, par la BD TOPO
                g = g.difference(fr_u)
            for q in polys(g):
                lakes_out.append([props.get("sr", 9), enc_poly(q)])
    fine_water = [q.simplify(SIMPLIFY_WATER, preserve_topology=True) for q in polys(fine_u)]
    for q in fine_water:
        lakes_out.append([0, enc_poly(q)])

    doc = {
        "_doc": "Fond de carte : terres (Natural Earth 1:50 M, précisées autour des réseaux par la BD TOPO IGN "
                "en France et Natural Earth 1:10 M ailleurs), cours d'eau et lacs. Coordonnées [lon, lat] × 1e5 "
                "encodées en écarts. Généré par scripts/prepare_basemap.py.",
        "q": Q,
        "zones": [[round(c, 4) for c in R.bounds] for R in Z],
        "land": land_out,
        "rivers": rivers_out,
        "lakes": lakes_out,
    }
    raw = json.dumps(doc, separators=(",", ":")).encode()
    (DATA / "basemap.json.gz").write_bytes(gzip.compress(raw, 9, mtime=0))
    n_land = sum(len(r) // 2 for p in land_out for r in p)
    print(f"data/basemap.json.gz : {len(gzip.compress(raw, 9)) / 1e6:.2f} Mo "
          f"({len(raw) / 1e6:.1f} Mo décompressé) · {len(land_out)} polygones de terre, {n_land} sommets · "
          f"{len(fine_water)} surfaces en eau IGN")


if __name__ == "__main__":
    main()
