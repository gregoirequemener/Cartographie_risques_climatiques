"""Test de fumée : ouvre la page construite dans Chromium et vérifie qu'elle fonctionne.

Contrôles : aucune erreur JavaScript, 90 réseaux chargés, 25 plans de réseau décodés,
fond de carte précis décodé, coûts financiers et voyageurs perturbés calculés pour chaque réseau,
bascule du panneau Portefeuille, version « Alpha V0.aa.mois.jour.n » affichée, polices de la charte chargées,
aucune requête réseau (page autonome), bascule chaleur / inondation (classes du jaune au rouge, puis en bleus),
tronçons exposés affichés sur Lyon.

Prérequis : pip install -r requirements-dev.txt && playwright install chromium
Usage     : python scripts/check_page.py [--page docs/index.html] [--chrome /chemin/vers/chrome]
La page est autonome : aucune connexion Internet n'est nécessaire.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent


async def run(page_path: Path, chrome: str | None, shot: Path | None) -> int:
    failures: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(**({"executable_path": chrome} if chrome else {}))
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        remote: list[str] = []  # la page doit tout contenir : aucune requête hors du fichier
        page.on("request", lambda r: remote.append(r.url) if r.url.startswith(("http:", "https:")) else None)
        await page.goto(page_path.resolve().as_uri())
        await page.wait_for_function("typeof NETL !== 'undefined' && NETL !== null", timeout=60_000)

        await page.wait_for_function("BASEMAP !== null", timeout=30_000)
        n_land = await page.evaluate("BASEMAP.nLand")
        if n_land < 1000:
            failures.append(f"fond de carte incomplet : {n_land} polygones de terre")
        version = await page.evaluate("document.getElementById('version').textContent.trim()")
        if not re.fullmatch(r"Alpha V0\.\d{2}\.(1[0-2]|[1-9])\.([1-9]|[12]\d|3[01])\.[1-9]\d*", version):
            failures.append(f"version mal formée : {version!r} (attendu « Alpha V0.aa.mois.jour.n »)")
        # Montserrat (titres) doit être chargée ; Carlito n'est utilisée qu'à défaut de Parisine Office et de Calibri
        fonts = await page.evaluate("document.fonts.ready.then(() => [...document.fonts].map(f => [f.family.replace(/\"/g, ''), f.status]))")
        if ["Montserrat", "loaded"] not in fonts:
            failures.append(f"police Montserrat non chargée : {fonts}")
        if not any(f == "Carlito" for f, _ in fonts):
            failures.append("police Carlito non intégrée à la page")
        n_networks = await page.evaluate("NETWORKS.length")
        n_lines = await page.evaluate("NETL.length")
        if n_networks != 90:
            failures.append(f"{n_networks} réseaux au lieu de 90")
        if n_lines != 25:
            failures.append(f"{n_lines} plans de réseau au lieu de 25")
        bad_fin = await page.evaluate("NETWORKS.filter((_, i) => !(FIN[i].b > 0 && Number.isFinite(M_HEAT.ssp585[2036][i].fin))).length")
        if bad_fin:
            failures.append(f"{bad_fin} réseau(x) sans coût financier calculable (chaleur)")
        bad_pax = await page.evaluate("NETWORKS.filter((_, i) => !(RID[i].v > 0 && Number.isFinite(M_HEAT.ssp585[2036][i].pax))).length")
        if bad_pax:
            failures.append(f"{bad_pax} réseau(x) sans voyageurs perturbés calculables (chaleur)")

        # Panneau Portefeuille : masqué puis réaffiché, la carte récupère la place libérée
        w0 = await page.evaluate("map.getSize().x")
        await page.click("#panel-toggle")
        hidden = await page.evaluate("getComputedStyle(document.getElementById('panel')).display === 'none'")
        w1 = await page.evaluate("map.getSize().x")
        await page.click("#panel-toggle")
        shown = await page.evaluate("getComputedStyle(document.getElementById('panel')).display !== 'none'")
        if not (hidden and shown and w1 > w0):
            failures.append(f"bascule du panneau : masqué={hidden}, réaffiché={shown}, largeur carte {w0} → {w1} px")

        heat_r5 = await page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--r5').trim()")
        await page.click('#hazards button[data-h="flood"]')
        await page.wait_for_timeout(1500)
        flood_r5 = await page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--r5').trim()")
        if heat_r5 == flood_r5:
            failures.append(f"les classes ne changent pas de couleur avec l'aléa (--r5 = {heat_r5})")
        bad_ff = await page.evaluate("NETWORKS.filter((_, i) => !Number.isFinite(M_FLOOD.ssp585[2036][i].fin) || !Number.isFinite(M_FLOOD.ssp585[2036][i].pax)).length")
        if bad_ff:
            failures.append(f"{bad_ff} réseau(x) sans coût ou voyageurs perturbés calculables (inondation)")
        await page.click('#hazards button[data-h="heat"]')
        await page.wait_for_timeout(1000)
        await page.evaluate("() => { const n = NETWORKS[74]; map.setView([n.la, n.lo], 12); }")  # Lyon
        await page.wait_for_timeout(1500)
        n_risk = await page.evaluate("linesRisk.getLayers().length")
        if n_risk == 0:
            failures.append("aucun tronçon exposé affiché sur Lyon (aléa chaleur)")
        if shot:
            await page.screenshot(path=str(shot))
        await browser.close()

    failures += [f"erreur JavaScript : {e}" for e in errors]
    failures += [f"requête réseau : {u}" for u in remote]
    print(f"{version} · réseaux : {n_networks} · plans de réseau : {n_lines} · tronçons exposés affichés (Lyon, chaleur) : {n_risk}")
    for f in failures:
        print("ÉCHEC :", f)
    print("OK" if not failures else f"{len(failures)} problème(s)")
    return 1 if failures else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--page", type=Path, default=ROOT / "docs/index.html")
    ap.add_argument("--chrome", help="exécutable Chrome/Chromium à utiliser (facultatif)")
    ap.add_argument("--screenshot", type=Path, help="enregistre une capture de la page")
    args = ap.parse_args()
    sys.exit(asyncio.run(run(args.page, args.chrome, args.screenshot)))


if __name__ == "__main__":
    main()
