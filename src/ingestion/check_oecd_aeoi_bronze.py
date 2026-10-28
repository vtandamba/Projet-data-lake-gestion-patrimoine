"""
Contrôle de complétude — Relations d'échange automatique (OCDE), zone BRONZE
============================================================================
Vérifie que le fichier produit par ingest_oecd_aeoi_bronze.py n'a perdu aucune ligne.

Trois contrôles par tableau (CRS, CbC, DPI, CARF, GIR) :
  1. Volume  : nombre de lignes du CSV comparé au nombre de pages du tableau
               (« / N ») multiplié par le nombre de lignes par page.
  2. Sondage : on tape un pays dans « Search jurisdiction » et on compare le
               nombre de lignes affichées par le site avec le CSV.
  3. Qualité : cellules vides, doublons, lignes d'en-tête, pays vers lui-même.

Usage (depuis la racine du projet, après l'ingestion) :
    py -3.14 check_oecd_aeoi_bronze.py
    py -3.14 check_oecd_aeoi_bronze.py --pays France Switzerland Portugal Türkiye
"""

import argparse
import re
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

BRONZE = Path("data/bronze")
TABLEAUX = {
    "crs_mcaa": "https://flo.uri.sh/visualisation/16162619/embed",
    "cbc_mcaa": "https://flo.uri.sh/visualisation/16185443/embed",
    "dpi_mcaa": "https://flo.uri.sh/visualisation/22341718/embed",
    "carf_mcaa": "https://flo.uri.sh/visualisation/26906787/embed",
    "gir_mcaa": "https://flo.uri.sh/visualisation/26906833/embed",
}
JS_ETAT = """() => {
    const t = document.body.innerText;
    const l = t.split('\\n').map(s => s.trim()).filter(Boolean);
    const m = t.match(/\\/\\s*(\\d+)\\s*(?:\\n|›|$)/) || [];
    return {lignes: l, total: m[1] ? +m[1] : null};
}"""


# Clic sur la flèche « › » en JavaScript : contourne la barre de pagination
# qui recouvre la flèche et intercepte les clics « souris » de Playwright.
JS_PAGE_SUIVANTE = """() => {
    const fleches = [...document.querySelectorAll('button, a, span, div')]
        .filter(e => e.textContent.trim() === '›' && e.children.length === 0);
    if (!fleches.length) return false;
    const cible = fleches[0].closest('button, a, [role=button]') || fleches[0];
    if (cible.disabled) return false;
    cible.click();
    return true;
}"""


def dernier_fichier() -> Path:
    fichiers = sorted(BRONZE.glob("oecd_aeoi_relations_*.csv"))
    if not fichiers:
        raise SystemExit("Aucun fichier oecd_aeoi_relations_*.csv : lancer d'abord l'ingestion.")
    return fichiers[-1]


def lignes_visibles(lignes: list[str]) -> list[list[str]]:
    try:
        debut = next(i for i, l in enumerate(lignes) if l.lower() == "legal instrument") + 1
    except StopIteration:
        return []
    corps = []
    for l in lignes[debut:]:
        if l in ("‹", "›") or re.fullmatch(r"\d+\s*/\s*\d+|/\s*\d+|\d+", l):
            break
        corps.append(l)
    return [corps[i:i + 3] for i in range(0, len(corps) - 2, 3)]


def compter_toutes_les_pages(page) -> int:
    n, vues = 0, set()
    total = page.evaluate(JS_ETAT)["total"] or 1
    for _ in range(total):
        etat = page.evaluate(JS_ETAT)
        cle = "|".join(etat["lignes"][:60])
        if cle in vues:
            break
        vues.add(cle)
        n += len(lignes_visibles(etat["lignes"]))
        if not page.evaluate(JS_PAGE_SUIVANTE):
            break
        page.wait_for_timeout(350)
    return n


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pays", nargs="+", default=["France", "Switzerland"])
    args = parser.parse_args()

    fichier = dernier_fichier()
    df = pd.read_csv(fichier, dtype=str, keep_default_na=False)
    print(f"Fichier contrôlé : {fichier}  ({len(df)} lignes)\n")

    # 3. Qualité
    cle = ["From jurisdiction", "To jurisdiction", "Tableau"]
    print("=== Qualité")
    vides = (df[["From jurisdiction", "To jurisdiction"]] == "").any(axis=1)
    print(f"  cellules vides          : {int(vides.sum())}")
    print(f"  doublons                : {int(df.duplicated(subset=cle).sum())}")
    print(f"  lignes d'en-tête        : {int(df['From jurisdiction'].str.contains('jurisdiction', case=False).sum())}")
    print(f"  pays vers lui-même      : {int((df['From jurisdiction'] == df['To jurisdiction']).sum())}")
    print(f"  juridictions distinctes : {len(set(df['From jurisdiction']) | set(df['To jurisdiction']))}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="en-US")
        for code, url in TABLEAUX.items():
            dans_csv = df[df["Tableau"] == code]
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(4000)
            etat = page.evaluate(JS_ETAT)
            par_page = len(lignes_visibles(etat["lignes"]))
            total = etat["total"] or 1

            # 1. Volume
            mini, maxi = (total - 1) * par_page + 1, total * par_page
            ok = mini <= len(dans_csv) <= maxi
            print(f"\n=== {code} : {total} pages x {par_page} lignes -> attendu entre "
                  f"{mini} et {maxi}, CSV = {len(dans_csv)}  {'OK' if ok else 'ECART'}")

            # 2. Sondage
            recherche = page.locator("#search-box")
            for pays in args.pays:
                attendu = int(((dans_csv["From jurisdiction"] == pays)
                               | (dans_csv["To jurisdiction"] == pays)).sum())
                if not recherche.count():
                    print(f"  {pays:<14} : recherche indisponible")
                    continue
                recherche.fill(pays)
                page.wait_for_timeout(1500)
                affiche = compter_toutes_les_pages(page)
                print(f"  {pays:<14} : site = {affiche:>4}, CSV = {attendu:>4}  "
                      f"{'OK' if affiche == attendu else 'ECART'}")
                recherche.fill("")
                page.wait_for_timeout(800)
        browser.close()

    print("\nUn ECART au sondage peut venir d'un nom qui contient le pays cherché "
          "(ex. 'Guinea' dans 'Papua New Guinea') : vérifier alors à la main.")


if __name__ == "__main__":
    main()