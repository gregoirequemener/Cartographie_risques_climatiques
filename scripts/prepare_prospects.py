"""Ajoute les réseaux « prospects » (appels d'offres en cours) à la suite des réseaux exploités.

data/prospects.json (liste tenue à la main) → networks.json, climate_raw.json, flood.json, finance.json, ridership.json

Chaque prospect reçoit exactement les mêmes données que les réseaux exploités, extraites des mêmes sources avec la
même recette (vérifiable avec --verifier, qui recalcule des réseaux existants et les compare aux valeurs en place) :
  - climat : Banque mondiale CCKP, CMIP6 0,25°, médianes multi-modèles, maille la plus proche du point ;
  - inondation : WRI Aqueduct Floods v2, crue centennale, fenêtre de 0,5° autour du point. Fleuves : historique WATCH,
    puis médiane des 5 modèles climatiques ; côte : scénario avec affaissement des sols, percentile 50 ; hauteur × 25 sur 8 bits ;
  - relief : AWS Terrain Tiles, grille de 1/240° ;
  - budget et fréquentation : champs « budget » et « freq » de prospects.json, mêmes coûts unitaires que scripts/prepare_finance.py.

Les réseaux exploités (les premières entrées de chaque fichier) ne sont pas modifiés. Le script est relançable : il
remplace les prospects déjà présents. Pour ajouter un prospect, compléter data/prospects.json puis lancer, dans cet ordre :

    python scripts/prepare_prospects.py       # demande numpy, pillow, rasterio, h5py (requirements-dev.txt) et Internet
    python scripts/prepare_basemap.py         # fond de carte précis autour des nouveaux points
    python scripts/prepare_links.py           # liens utiles
    python build.py

Champs d'un prospect : ceux de networks.json (t, zone, pays, ci, cl, s, m, p, la, lo, kf), plus
  nom     : libellé court affiché sur la carte ;
  ao      : equipe, concurrents, etape, debut, sources [{l, u}] : état de l'appel d'offres, avec ses sources ;
  budget  : ["emp"|"veh"|"km"|"voy"|"hab"|"est", …] comme le tableau BASIS de prepare_finance.py, ou ["reel", M€, motif]
            pour un montant publié (pas d'indice pays) ;
  from    : année de mise en service, si le réseau n'existe pas encore ;
  freq    : ["pub", millions de voyages par an, libellé].
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_finance import COUNTRY, estimate, fr  # noqa: E402  (même dossier)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = Path(tempfile.gettempdir()) / "carto-risques-cckp"

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")

CCKP = "https://wbg-cckp.s3.amazonaws.com/data/cmip6-x0.25/{var}/ensemble-all-{scen}/climatology-{var}-annual-mean_cmip6-x0.25_ensemble-all-{scen}_climatology_{stat}_{period}.nc"
AQUEDUCT = "/vsicurl/https://aqueduct.wridata.org/AqueductFloods20/"
GCMS = ["0000GFDL-ESM2M", "0000HadGEM2-ES", "00IPSL-CM5A-LR", "MIROC-ESM-CHEM", "00000NorESM1-M"]
TERRAIN = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
TERRAIN_Z = 10
FS, DS = 60, 120  # taille des fenêtres : 60 cases de 1/120° (inondation), 120 cases de 1/240° (relief)


def read_json(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def write_json(name: str, obj, **kw) -> None:
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, **kw) + "\n", encoding="utf-8")


# ---------- Climat ----------
def cckp_grid(key: str):
    """Grille (valeurs, latitudes, longitudes) d'une clé « variable|scénario|statistique|période », mise en cache."""
    import h5py
    var, scen, stat, period = key.split("|")
    url = CCKP.format(var=var, scen=scen, stat=stat, period=period)
    CACHE.mkdir(exist_ok=True)
    path = CACHE / Path(url).name
    if not path.exists():
        urllib.request.urlretrieve(url, path)
    with h5py.File(path, "r") as f:
        names = [k for k in f if isinstance(f[k], h5py.Dataset) and f[k].ndim == 3]
        d = f[names[0]]
        grid = d[0].astype("f8")
        fill = d.attrs.get("_FillValue", d.attrs.get("missing_value"))
        if fill is not None:
            grid[grid == np.ravel(fill)[0]] = np.nan
        grid[np.abs(grid) > 1e15] = np.nan
        return grid, f["lat"][()], f["lon"][()]


def nearest(grid, lat, lon, la: float, lo: float) -> float:
    """Valeur de la maille renseignée la plus proche du point."""
    r, c = int(np.abs(lat - la).argmin()), int(np.abs(lon - lo).argmin())
    if np.isfinite(grid[r, c]):
        return float(grid[r, c])
    for k in range(1, 6):  # point sur une maille océanique : anneaux successifs
        sub = grid[max(0, r - k):r + k + 1, max(0, c - k):c + k + 1]
        if np.isfinite(sub).any():
            return float(np.nanmean(sub))
    return float("nan")


# ---------- Inondation ----------
def read_window(name: str, r0: int, c0: int) -> np.ndarray:
    import rasterio
    from rasterio.windows import Window
    with rasterio.open(AQUEDUCT + name) as ds:
        res = ds.res[0]
        col, row = int(round((-180 + c0 / 120 - ds.bounds.left) / res)), int(round((ds.bounds.top - (90 - r0 / 120)) / res))
        d = ds.read(1, window=Window(col, row, FS, FS), boundless=True, fill_value=0).astype("f4")
    d[d < 0] = 0
    return d


def flood_files(key: str) -> list[str]:
    parts = key.split("|")
    if parts[0] == "river":
        if parts[1] == "hist":
            return ["inunriver_historical_000000000WATCH_1980_rp00100.tif"]
        return [f"inunriver_{parts[1]}_{g}_{parts[2]}_rp00100.tif" for g in GCMS]
    if parts[1] == "hist":
        return ["inuncoast_historical_wtsub_hist_rp0100_0.tif"]
    return [f"inuncoast_{parts[1]}_wtsub_{parts[2]}_rp0100_0_perc_50.tif"]


def flood_window(key: str, r0: int, c0: int) -> np.ndarray:
    arrs = [read_window(f, r0, c0) for f in flood_files(key)]
    d = arrs[0] if len(arrs) == 1 else np.median(np.stack(arrs), axis=0)
    return np.clip(np.rint(d * 25), 0, 255).astype("u1")


# ---------- Relief ----------
TILES: dict[tuple[int, int], np.ndarray] = {}


def tile(x: int, y: int) -> np.ndarray:
    from PIL import Image
    if (x, y) not in TILES:
        with urllib.request.urlopen(TERRAIN.format(z=TERRAIN_Z, x=x, y=y), timeout=60) as r:
            a = np.array(Image.open(io.BytesIO(r.read())).convert("RGB"), dtype="f8")
        TILES[(x, y)] = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
    return TILES[(x, y)]


def elevation(lat: float, lon: float) -> float:
    n = 2 ** TERRAIN_Z * 256
    fx = (lon + 180) / 360 * n - .5
    fy = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n - .5
    x0, y0 = int(math.floor(fx)), int(math.floor(fy))
    dx, dy = fx - x0, fy - y0
    px = lambda ix, iy: tile(ix // 256, iy // 256)[iy % 256, ix % 256]  # noqa: E731
    return float(px(x0, y0) * (1 - dx) * (1 - dy) + px(x0 + 1, y0) * dx * (1 - dy) + px(x0, y0 + 1) * (1 - dx) * dy + px(x0 + 1, y0 + 1) * dx * dy)


def dem_window(r0: int, c0: int) -> tuple[np.ndarray, float, float]:
    g = np.array([[elevation(90 - (2 * r0 + a + .5) / 240, -180 + (2 * c0 + b + .5) / 240) for b in range(DS)] for a in range(DS)])
    mn = math.floor(g.min())
    step = max(1, math.ceil((g.max() - mn) / 254))
    return np.clip(np.rint((g - mn) / step), 0, 255).astype("u1"), float(mn), float(step)


# ---------- Mosaïques PNG ----------
def decode(uri: str) -> np.ndarray:
    from PIL import Image
    a = np.array(Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))))
    return a[..., 0] if a.ndim == 3 else a


def encode(a: np.ndarray) -> str:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(a, "L").save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def extended(a: np.ndarray, count: int, size: int, per_row: int) -> np.ndarray:
    """Mosaïque limitée aux `count` fenêtres existantes, agrandie de lignes vides si besoin."""
    return a[:math.ceil(count / per_row) * size].copy()


def paste(a: np.ndarray, i: int, size: int, per_row: int, win: np.ndarray) -> np.ndarray:
    rows = i // per_row + 1
    if a.shape[0] < rows * size:
        a = np.vstack([a, np.zeros((rows * size - a.shape[0], a.shape[1]), "u1")])
    ox, oy = (i % per_row) * size, (i // per_row) * size
    a[oy:oy + size, ox:ox + size] = win
    return a


def window_of(la: float, lo: float) -> tuple[int, int]:
    return math.floor((90 - la) * 120) - FS // 2, math.floor((lo + 180) * 120) - FS // 2


def verify() -> None:
    """Recalcule quelques réseaux existants : la recette doit redonner les valeurs en place."""
    nets = read_json("networks.json"); clim = read_json("climate_raw.json"); fl = read_json("flood.json")
    sample = [74, 37, 0, 87]
    keys = [k for k in clim if not k.startswith("_")]
    errs = []
    for k in keys:
        grid, lat, lon = cckp_grid(k)
        vals = clim[k].split(",")
        for i in sample:
            errs.append(abs(nearest(grid, lat, lon, nets[i]["la"], nets[i]["lo"]) - float(vals[i])))
    print(f"climat   : {len(errs)} valeurs, écart maximal {max(errs):.3f}, moyen {np.mean(errs):.4f}")
    for k in fl["fields"]:
        a = decode(fl["fields"][k]); ok = n = 0
        for i in sample:
            ox, oy = (i % fl["perRow"]) * FS, (i // fl["perRow"]) * FS
            ref = a[oy:oy + FS, ox:ox + FS]; e = flood_window(k, *fl["win"][i]); m = (ref > 0) | (e > 0)
            ok += int((ref[m] == e[m]).sum()); n += int(m.sum())
        print(f"inondation {k:20s} : {100 * ok / max(1, n):5.1f} % de cases identiques ({n} cases > 0)", flush=True)
    d = decode(fl["dem"]["uri"])
    for i in sample[:2]:
        ox, oy = (i % fl["dem"]["perRow"]) * DS, (i // fl["dem"]["perRow"]) * DS
        ref = d[oy:oy + DS, ox:ox + DS] * fl["dem"]["step"][i] + fl["dem"]["min"][i]
        q, mn, st = dem_window(*fl["win"][i])
        print(f"relief   : réseau {i} écart moyen {np.mean(np.abs(q * st + mn - ref)):.2f} m (pas {fl['dem']['step'][i]} m) · altitude du point {elevation(nets[i]['la'], nets[i]['lo']):.1f} m (en place {fl['pelev'][i]})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verifier", action="store_true", help="contrôle la recette sur des réseaux existants, sans rien écrire")
    if ap.parse_args().verifier:
        return verify()

    prospects = read_json("prospects.json")
    nets = [n for n in read_json("networks.json") if n.get("st") != "prospect"]
    base = len(nets)
    clim = read_json("climate_raw.json"); fl = read_json("flood.json"); fin = read_json("finance.json"); rid = read_json("ridership.json")
    keys = [k for k in clim if not k.startswith("_")]
    grids = {k: cckp_grid(k) for k in keys}
    for k in keys:
        clim[k] = ",".join(clim[k].split(",")[:base])
    fl["win"], fl["pelev"] = fl["win"][:base], fl["pelev"][:base]
    fl["dem"]["min"], fl["dem"]["step"] = fl["dem"]["min"][:base], fl["dem"]["step"][:base]
    mos = {k: extended(decode(u), base, FS, fl["perRow"]) for k, u in fl["fields"].items()}
    dem = extended(decode(fl["dem"]["uri"]), base, DS, fl["dem"]["perRow"])
    fin["networks"], rid["networks"] = fin["networks"][:base], rid["networks"][:base]
    COUNTRY.setdefault("Irlande", 1.2)

    for j, p in enumerate(prospects):
        i = base + j
        n = {"id": i, "st": "prospect", "pg": None, **{k: v for k, v in p.items() if k not in ("budget", "freq", "from")}}
        print(f"{i} · {p['nom']}", flush=True)
        for k in keys:
            v = nearest(*grids[k], p["la"], p["lo"])
            clim[k] += "," + f"{round(v, 1):g}"
        r0, c0 = window_of(p["la"], p["lo"])
        fl["win"].append([r0, c0])
        for k in mos:
            mos[k] = paste(mos[k], i, FS, fl["perRow"], flood_window(k, r0, c0))
        q, mn, st = dem_window(r0, c0)
        dem = paste(dem, i, DS, fl["dem"]["perRow"], q)
        fl["dem"]["min"].append(mn); fl["dem"]["step"].append(st)
        fl["pelev"].append(round(elevation(p["la"], p["lo"]), 1))

        kind = p["budget"][0]
        if kind == "reel":
            row = {"b": float(p["budget"][1]), "base": p["budget"][2]}
        else:
            b0, label = estimate(n, tuple(p["budget"]))
            k = COUNTRY[p["pays"]]
            row = {"b": round(b0 * k, 2), "base": label + (f" × indice pays {fr(k, 2)}" if k != 1 else "")}
        if p.get("from"):
            row["from"] = p["from"]
        fin["networks"].append(row)
        rid["networks"].append({"v": p["freq"][1], "base": p["freq"][2]})
        nets.append(n)

    for k, a in mos.items():
        fl["fields"][k] = encode(a)
    fl["mh"] = next(iter(mos.values())).shape[0]
    fl["dem"]["uri"] = encode(dem); fl["dem"]["mh"] = dem.shape[0]

    (DATA / "networks.json").write_text(json.dumps(nets, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    write_json("climate_raw.json", clim, indent=0)
    (DATA / "flood.json").write_text(json.dumps(fl, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    write_json("finance.json", fin, indent=1)
    write_json("ridership.json", rid, indent=1)
    print(f"{base} réseaux exploités + {len(prospects)} prospects")


if __name__ == "__main__":
    main()
