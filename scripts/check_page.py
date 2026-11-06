"""Test de fumée : ouvre la page construite dans Chromium et vérifie qu'elle fonctionne.

Contrôles : aucune erreur JavaScript, 90 réseaux chargés, 25 plans de réseau décodés,
coûts financiers calculés pour chaque réseau, bascule chaleur / inondation, tronçons exposés affichés sur Lyon.

Prérequis : pip install -r requirements-dev.txt && playwright install chromium
Usage     : python scripts/check_page.py [--page docs/index.html] [--chrome /chemin/vers/chrome]
La page charge Leaflet depuis le CDN jsDelivr : une connexion Internet est nécessaire.
"""
from __future__ import annotations

import argparse
import asyncio
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
        await page.goto(page_path.resolve().as_uri())
        await page.wait_for_function("typeof NETL !== 'undefined' && NETL !== null", timeout=60_000)

        n_networks = await page.evaluate("NETWORKS.length")
        n_lines = await page.evaluate("NETL.length")
        if n_networks != 90:
            failures.append(f"{n_networks} réseaux au lieu de 90")
        if n_lines != 25:
            failures.append(f"{n_lines} plans de réseau au lieu de 25")
        bad_fin = await page.evaluate("NETWORKS.filter((_, i) => !(FIN[i].b > 0 && Number.isFinite(M_HEAT.ssp585[2036][i].fin))).length")
        if bad_fin:
            failures.append(f"{bad_fin} réseau(x) sans coût financier calculable (chaleur)")

        await page.click('#hazards button[data-h="flood"]')
        await page.wait_for_timeout(1500)
        bad_ff = await page.evaluate("NETWORKS.filter((_, i) => !Number.isFinite(M_FLOOD.ssp585[2036][i].fin)).length")
        if bad_ff:
            failures.append(f"{bad_ff} réseau(x) sans coût financier calculable (inondation)")
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
    print(f"réseaux : {n_networks} · plans de réseau : {n_lines} · tronçons exposés affichés (Lyon, chaleur) : {n_risk}")
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
