"""Construit les « liens utiles » de chaque fiche réseau : data/networks.json → data/links.json

Sources systématiques :
  - France : plans de prévention (API Géorisques, base GASPAR), document d'information sur les risques de la commune
    (Géorisques), plan climat de l'intercommunalité (ADEME, Territoires & Climat) ;
  - États-Unis : carte réglementaire des zones inondables (FEMA, National Flood Hazard Layer) ;
  - hors de France : fiche ThinkHazard! du territoire (Banque mondiale, GFDRR).
S'y ajoutent les plans d'adaptation repérés à la main (tableau CURATED).

Chaque lien est testé : une adresse qui ne répond pas n'est pas retenue, et le script le signale.
Usage : python scripts/prepare_links.py && python build.py      (bibliothèque standard, accès Internet requis)
"""
from __future__ import annotations

import csv
import io
import json
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept": "*/*"}
ADEME = "https://www.territoires-climat.ademe.fr/"
NFHL = "https://hazards-fema.maps.arcgis.com/apps/webappviewer/index.html?id=8b0adb51996444d4879338b5529aa9cd&center={lo},{la}&level=12"

# Requête ThinkHazard! : nom anglais du territoire (id réseau → (requête, pays attendu))
THINK = {
    34: ("Copenhagen", "Denmark"), 35: ("Melbourne", "Australia"), 36: ("Sydney", "Australia"), 52: ("Geneve", "Switzerland"),
    75: ("Hong Kong", "China"), 76: ("Riyad", "Saudi Arabia"), 77: ("Saudi Arabia", "Saudi Arabia"), 78: ("Johannesburg", "South Africa"),
    79: ("Singapore", "Singapore"), 80: ("Cairo", "Egypt"), 81: ("Casablanca", "Morocco"), 82: ("Firenze", "Italy"), 83: ("Arezzo", "Italy"),
    84: ("Lazio", "Italy"), 85: ("Toscana", "Italy"), 86: ("Doha", "Qatar"), 87: ("Manila", "Philippines"), 88: ("Quebec", "Canada"),
    89: ("Belgrade", "Serbia"), 91: ("Melbourne", "Australia"), 92: ("Dublin", "Ireland"),
}
COMMUNE = {48: "Monnetier-Mornex"}  # point au sommet, hors de toute commune trouvée par coordonnées

# Plans d'adaptation et cartes d'aléa propres à un réseau : id → [(type, libellé, adresse)]
SYDNEY = [("plan", "Adapting for climate change, City of Sydney", "https://www.cityofsydney.nsw.gov.au/strategies-action-plans/adapting-for-climate-change"),
          ("plan", "Stratégie de résilience, City of Sydney", "https://www.cityofsydney.nsw.gov.au/strategies-action-plans/resilience-strategy")]
MELBOURNE = [("carte", "Cartographie des inondations, City of Melbourne", "https://participate.melbourne.vic.gov.au/flood-mapping/project-overview"),
             ("carte", "Nouvelles cartes d'inondation, Melbourne Water", "https://www.melbournewater.com.au/node/10641")]
IDROGEO = ("carte", "Cartes d'aléas inondation et mouvements de terrain (ISPRA IdroGEO)", "https://idrogeo.isprambiente.it/app/")
CURATED = {
    74: [("plan", "PCAET 2026-2031, synthèse (Métropole de Lyon)", "https://mutu.grandlyon.com/jeparticipe/PCAET_MDL%205.%20Synth%C3%A8se.pdf"),
         ("plan", "Bilan du PCAET 2019-2025 (Métropole de Lyon)", "https://plan-climat.grandlyon.com/app/uploads/2026/05/Metropole_de_Lyon_Bilan_final_PCAET_2019_2025.pdf"),
         ("ppri", "Stratégie de gestion du risque inondation (Métropole de Lyon)", "https://developpementdurable.grandlyon.com/app/uploads/2024/06/Cycle2-strategieinondation-nov2023-WEB.pdf")],
    41: [("plan", "Plan d'adaptation au changement climatique (Angers Loire Métropole)", "https://presse.angers.fr/private/uploads/piecesjointes/1-pacc.pdf")],
    39: [("plan", "PCAET Caen Normandie Métropole : avis de l'Autorité environnementale", "https://www.mrae.developpement-durable.gouv.fr/IMG/pdf/a_2022-4678_pcaet_caen-normandie-metropole_delibere.pdf")],
    35: MELBOURNE, 91: MELBOURNE,
    36: SYDNEY,
    90: [("plan", "Climate Ready Boston (Ville de Boston)", "https://www.boston.gov/departments/environment/climate-ready-boston"),
         ("carte", "Comprendre les zones inondables (Ville de Boston)", "https://boston.gov/node/4496")],
    92: [("plan", "Plan d'action climat de Dublin 2024-2029", "https://www.dublincity.ie/environment-and-climate-action/acting-against-climate-change/climate-change-action-plan"),
         ("carte", "Cartes d'inondation floodinfo.ie (OPW, Irlande)", "https://www.floodinfo.ie/")],
    75: [("plan", "Hong Kong's Climate Action Plan 2050", "https://www.eeb.gov.hk/sites/default/files/pdf/cap_2050_en.pdf")],
    78: [("plan", "Révision du Climate Action Plan (Ville de Johannesbourg, 2026)", "https://joburg.org.za/media_/Newsroom/Pages/2026-News-Articles/Joburg-undertakes-comprehensive-review-of-Climate-Action-Plan.aspx")],
    34: [("plan", "Plan de gestion des pluies torrentielles de Copenhague (Eurocities)", "https://eurocities.eu/stories/preventing-flooding-with-urban-spaces/")],
    82: [("ppri", "Plan de gestion du risque d'inondation, bassin de l'Arno (Appennino Settentrionale)", "https://www.appenninosettentrionale.it/itc/"), IDROGEO],
    83: [("ppri", "Plan de gestion du risque d'inondation (Appennino Settentrionale)", "https://www.appenninosettentrionale.it/itc/"), IDROGEO],
    85: [("ppri", "Plan de gestion du risque d'inondation (Appennino Settentrionale)", "https://www.appenninosettentrionale.it/itc/"), IDROGEO],
    84: [IDROGEO],
    52: [("plan", "Politique climatique du canton de Genève", "https://www.geneve.ch/themes/durabilite/climat/gouverner/politique-climatique-canton"),
         ("carte", "Zones indicatives de dangers d'inondation (SITG)", "https://ckan.opendata.swiss/dataset/zones-indicatives-de-dangers1")],
    88: [("plan", "Plan climat de la Ville de Québec", "https://www.ville.quebec.qc.ca/apropos/planification-orientations/environnement/plan-climat/index.aspx")],
    0: [("plan", "Stratégie face à la montée des eaux à Charleston (NOAA, U.S. Climate Resilience Toolkit)", "https://toolkit.climate.gov/PG_Resource_Charleston")],
    10: [("plan", "Community Climate Action Plan (Raleigh)", "https://cityofraleigh0drupal.blob.core.usgovcloudapi.net/drupal-prod/COR27/RaleighCCAP.pdf")],
    13: [("plan", "Governor's Council on Climate Change (Connecticut)", "https://portal.ct.gov/DEEP/Climate-Change/GC3/Governors-Council-on-Climate-Change"),
         ("plan", "Building a More Resilient Connecticut : rapport GC3", "https://portal.ct.gov/-/media/DEEP/climatechange/GC3/GC3_Phase1_Report_011521.pdf")],
    12: [("plan", "Climate Action Plan (comté de Prince George)", "https://www.epa.gov/system/files/documents/2023-12/prince-georges-county-climate-action-plan.pdf")],
    86: [("plan", "Qatar National Climate Change Action Plan 2030 (fiche PNUE)", "https://leap.unep.org/en/countries/qa/national-legislation/qatar-national-climate-change-action-plan-2030")],
    89: [("plan", "Plan d'adaptation de Belgrade (fiche Climate-ADAPT)", "https://climate-adapt.eea.europa.eu/en/metadata/guidances/climate-change-adaptation-action-plan-and-vulnerability-assessment")],
}
PPR_INONDATION = ("-I", "Multi", "Litt", "-L")      # modèles de procédure des PPR liés à l'eau
PPR_MOTS = ("PPRI", "PPRN-I", "INOND", "PPRL", "SUBMERSION", "LITTORA")
FICHIERS_PCAET = ("Programme d'actions", "Rapport", "Document PCAET définitif (Dépôt)", "Diagnostic")


def fetch(url: str, timeout: int = 40) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def get_json(url: str):
    """Services publics parfois instables : jusqu'à 7 essais espacés."""
    for k in range(7):
        try:
            return json.loads(fetch(url).decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            if k == 6:
                raise
            time.sleep(2.0 + k)


CHECKED: dict[str, str] = {}


def check(url: str, retry: int = 0) -> str:
    """« ok », ou la raison de l'échec. Une seule requête par adresse, lue partiellement."""
    if url in CHECKED:
        return CHECKED[url]
    try:
        req = urllib.request.Request(url, headers={**UA, "Range": "bytes=0-2047"})
        with urllib.request.urlopen(req, timeout=40) as r:
            r.read(2048)
        res = "ok"
    except urllib.error.HTTPError as e:
        res = f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001  (délai, TLS, DNS : le lien n'est simplement pas retenu)
        res = type(e).__name__
    if res != "ok" and retry < 5 and (res.startswith("HTTP 50") or "thinkhazard.org" in url):  # erreurs passagères
        time.sleep(2.0 + retry)
        return check(url, retry + 1)
    CHECKED[url] = res
    time.sleep(.08)
    return res


def load_pcaet():
    """Démarches PCAET de l'ADEME par SIREN, avec leurs documents."""
    files = defaultdict(list)
    txt = fetch(ADEME + "opendata/Correspondance_demarche_fichiers.csv").decode("utf-8-sig")
    for x in csv.DictReader(io.StringIO(txt), delimiter=";"):
        files[x["demarche_id"]].append(x)
    by_siren = defaultdict(list)
    for v in ("V2", "V1"):  # V2 d'abord : démarches les plus récentes
        txt = fetch(ADEME + f"opendata/Demarches_PCAET_{v}_entete.csv").decode("utf-8-sig")
        for x in csv.DictReader(io.StringIO(txt), delimiter=";"):
            for sir in x["SIREN collectivites_coporteuses"].replace(",", " ").replace("|", " ").split():
                by_siren[sir].append((x, files.get(x["Id"], [])))
    return by_siren


def pcaet_link(by_siren, siren: str, epci: str):
    for x, docs in by_siren.get(siren, []):
        order = sorted(docs, key=lambda d: (FICHIERS_PCAET.index(d["type_fichier"]) if d["type_fichier"] in FICHIERS_PCAET else 9,
                                            0 if any(w in d["display_name"].lower() for w in ("strat", "action", "synth")) else 1))
        for d in order[:4]:
            if d["type_fichier"] not in FICHIERS_PCAET:
                continue
            url = ADEME + urllib.parse.quote(d["lien_fichier"])
            if check(url) == "ok":
                etat = "" if x["Demarche_etat"] == "Mise en oeuvre" else " (en cours d'élaboration)"
                return ("plan", f"Plan climat (PCAET) · {epci}{etat}", url)
    return None


def france(n: dict, by_siren):
    i = n["id"]
    if i in COMMUNE:
        c = get_json(f"https://geo.api.gouv.fr/communes?nom={urllib.parse.quote(COMMUNE[i])}&fields=nom,code,codeEpci,epci,departement&limit=1")[0]
    else:
        c = get_json(f"https://geo.api.gouv.fr/communes?lat={n['la']}&lon={n['lo']}&fields=nom,code,codeEpci,epci,departement&format=json")[0]
    insee, commune = c["code"], c["nom"]
    res = get_json(f"https://www.georisques.gouv.fr/api/v1/gaspar/pprn?codeInsee={insee}&page_size=40").get("content", [])
    links, ppr, seen = [], 0, set()
    for p in res:
        name, model = p["libPpr"].strip(), p.get("modeleProcedure") or ""
        if (any(k in model for k in PPR_INONDATION) or any(k in name.upper() for k in PPR_MOTS)) and not any(k in name.upper() for k in ("ARGILE", "CAVIT", "PPRMT", "MVT")):
            if name in seen:
                continue
            seen.add(name)
            url = f"https://www.georisques.gouv.fr/donnee-risques/PPR/Fiche-ppr/pprn/{p['idGaspar']}"
            if check(url) == "ok":
                ppr += 1
                if ppr <= 3:  # au-delà, la fiche de risques de la commune suffit
                    links.append(("ppri", f"{name} (Géorisques)", url))
    lk = pcaet_link(by_siren, c.get("codeEpci"), (c.get("epci") or {}).get("nom", ""))
    if lk:
        links.append(lk)
    url = f"https://www.georisques.gouv.fr/DICRIM/{insee}"
    if check(url) == "ok":
        de = "d’" if commune[0] in "AEIOUYÉÈÎÔ" else "de "
        links.append(("ppri", f"Risques majeurs {de}{commune} (Géorisques)", url))
    dep = unicodedata.normalize("NFD", (c.get("departement") or {}).get("nom", "")).encode("ascii", "ignore").decode()
    return commune, ppr, links, dep


def state_county(la: float, lo: float):
    d = get_json(f"https://geocoding.geo.census.gov/geocoder/geographies/coordinates?x={lo}&y={la}&benchmark=Public_AR_Current&vintage=Current_Current&format=json&layers=Counties,States")
    g = d["result"]["geographies"]
    return g["States"][0]["NAME"], g["Counties"][0]["BASENAME"]


def thinkhazard(query: str, country: str, admin1: str | None = None, admin2: str | None = None):
    time.sleep(.8)  # service sensible aux rafales
    rows = get_json("https://thinkhazard.org/en/administrativedivision?q=" + urllib.parse.quote(query))["data"]
    rows = [r for r in rows if r.get("admin0") == country or country in str(r.get("admin0"))]
    if admin1:
        rows = [r for r in rows if r.get("admin1") == admin1]
    if admin2:
        rows = [r for r in rows if r.get("admin2") == admin2]
    rows.sort(key=lambda r: 0 if r.get("admin2") else 1)  # le niveau le plus fin d'abord
    return rows[0] if rows else None


def main() -> None:
    nets = json.loads((DATA / "networks.json").read_text(encoding="utf-8"))
    by_siren = load_pcaet()
    out, failed = [], []
    for n in nets:
        i, pays, ppr, links, commune = n["id"], n["pays"], 0, [], None
        try:
            if pays == "France":
                commune, ppr, links, dep = france(n, by_siren)
                if not links:  # ni PCAET publié ni document communal : à défaut, la fiche du département
                    t = thinkhazard(dep, "France")
                    if t:
                        links.append(("risque", f"Aléas naturels : {t.get('admin2') or t.get('admin1')} (ThinkHazard!)", t["url"]))
            elif pays == "États-Unis":
                state, county = state_county(n["la"], n["lo"])
                links.append(("carte", "Zones inondables réglementaires (FEMA)", NFHL.format(la=n["la"], lo=n["lo"])))
                t = thinkhazard(county, "United States", state, county)
                if t:
                    links.append(("risque", f"Aléas naturels : comté de {county} (ThinkHazard!)", t["url"]))
            elif i in THINK:
                q, c = THINK[i]
                t = thinkhazard(q, c)
                if t:
                    links.append(("risque", f"Aléas naturels : {t.get('admin2') or t.get('admin1') or t.get('admin0')} (ThinkHazard!)", t["url"]))
        except Exception as e:  # noqa: BLE001
            failed.append((i, n["ci"], "service", repr(e)[:90]))
        links = links + CURATED.get(i, [])
        kept = []
        for k, label, url in links:
            r = "ok" if url.startswith(NFHL[:40]) else check(url)
            if r == "ok":
                kept.append({"k": k, "l": label, "u": url})
            else:
                failed.append((i, n["ci"], r, url))
        order = {"plan": 0, "ppri": 1, "carte": 2, "risque": 3}
        kept.sort(key=lambda x: order[x["k"]])
        out.append({"np": ppr, "commune": commune, "l": kept})
        print(f"{i:3d} {n['ci'][:26]:26s} {len(kept)} lien(s) · PPR {ppr}", flush=True)
    doc = {"_doc": "Liens utiles par réseau, dans l'ordre de networks.json. Généré par scripts/prepare_links.py ; toutes les adresses ont été testées. "
                   "np : nombre de plans de prévention liés à l'eau sur la commune principale (Géorisques) ; l : k (plan|ppri|carte|risque), l (libellé), u (adresse).",
           "networks": out}
    (DATA / "links.json").write_text(json.dumps(doc, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"\n{sum(len(x['l']) for x in out)} liens retenus · {sum(1 for x in out if x['np'])} réseaux avec PPR · {sum(1 for x in out if not x['l'])} réseaux sans lien")
    for f in failed:
        print("NON RETENU", f)


if __name__ == "__main__":
    main()
