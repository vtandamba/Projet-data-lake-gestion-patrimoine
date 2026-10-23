"""
La page OCDE intègre 5 tableaux Flourish (iframes flo.uri.sh), un par accord :
CRS, CbC, DPI, CARF, GIR. Chaque tableau a 3 colonnes (From jurisdiction,
To jurisdiction, Legal instrument) et il est paginé. Playwright ouvre chaque
tableau, puis on lit toutes les lignes :
  1. dans les données que Flourish charge dans la page (rapide et complet) ;
  2. sinon en parcourant les pages du tableau avec le bouton « › ».

Source  : https://www.oecd.org/en/topics/sub-issues/international-standards-on-tax-transparency/automatic-exchange-of-information-exchange-relationships.html
Licence : conditions d'utilisation de l'OCDE, réutilisation autorisée avec mention de la source.
          >>> Citer l'OCDE comme source dans le rapport. <<<

Colonnes : From jurisdiction, To jurisdiction, Legal instrument (texte d'origine),
           Tableau (accord du tableau : crs_mcaa, cbc_mcaa, dpi_mcaa, carf_mcaa, gir_mcaa),
           Last updated (date de mise à jour affichée sur le tableau).

Sortie : data/bronze/oecd_aeoi_relations_AAAAMMJJ.csv
"""

import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

URL = ("https://www.oecd.org/en/topics/sub-issues/international-standards-on-tax-"
       "transparency/automatic-exchange-of-information-exchange-relationships.html")
OUTPUT_DIR = Path("data/bronze")
COLONNES = ["From jurisdiction", "To jurisdiction", "Legal instrument"]

# Ordre des tableaux sur la page (même ordre que les titres de la page)
TABLEAUX = ["crs_mcaa", "cbc_mcaa", "dpi_mcaa", "carf_mcaa", "gir_mcaa"]
# Adresses relevées le 22/10/2026, utilisées si la détection automatique échoue
ADRESSES_CONNUES = {
    "crs_mcaa": "https://flo.uri.sh/visualisation/16162619/embed",
    "cbc_mcaa": "https://flo.uri.sh/visualisation/16185443/embed",
    "dpi_mcaa": "https://flo.uri.sh/visualisation/22341718/embed",
    "carf_mcaa": "https://flo.uri.sh/visualisation/26906787/embed",
    "gir_mcaa": "https://flo.uri.sh/visualisation/26906833/embed",
}

# Lit les lignes que Flourish a chargées dans la page (window._Flourish_data)
JS_DONNEES_FLOURISH = """() => {
    const d = window._Flourish_data;
    if (!d) return null;
    let meilleure = [];
    const parcourir = o => {
        if (Array.isArray(o)) {
            if (o.length > meilleure.length && o.length && typeof o[0] === 'object') meilleure = o;
            o.forEach(parcourir);
        } else if (o && typeof o === 'object') Object.values(o).forEach(parcourir);
    };
    parcourir(d);
    return meilleure.map(r => {
        if (Array.isArray(r)) return r.map(String);
        if (Array.isArray(r.columns)) return r.columns.map(String);
        return Object.values(r).filter(v => typeof v !== 'object').map(String);
    });
}"""

# Texte visible du tableau + date « Last updated » + nombre de pages (« / N »)
JS_PAGE_COURANTE = """() => {
    const texte = document.body.innerText;
    const lignes = texte.split('\\n').map(s => s.trim()).filter(Boolean);
    const total = (texte.match(/\\/\\s*(\\d+)\\s*(?:\\n|›|$)/) || [])[1];
    const maj = (texte.match(/Last updated:\\s*([^\\n]+)/) || [])[1] || '';
    return {lignes, total: total ? +total : null, maj: maj.trim()};
}"""


def espaces(texte) -> str:
    """Retire seulement les espaces en trop (pas de nettoyage métier)."""
    return re.sub(r"\s+", " ", str(texte or "")).strip()


def lignes_visibles(lignes: list[str]) -> list[list[str]]:
    """Regroupe le texte affiché en triplets (from, to, legal instrument)."""
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


def lire_tableau(page, url: str) -> tuple[list[list[str]], str]:
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(4000)
    etat = page.evaluate(JS_PAGE_COURANTE)

    # 1. Données chargées par Flourish
    try:
        brutes = page.evaluate(JS_DONNEES_FLOURISH)
    except Exception:
        brutes = None
    if brutes and len(brutes) > 10:
        lignes = [[espaces(c) for c in r[:3]] for r in brutes if len(r) >= 3]
        lignes = [l for l in lignes if "jurisdiction" not in " ".join(l).lower()]
        if lignes:
            print(f"    {len(lignes)} lignes lues dans les données Flourish", flush=True)
            return lignes, etat["maj"]

    # 2. Repli : page par page
    print("    données Flourish non trouvées, lecture page par page…", flush=True)
    toutes, vues = [], set()
    total = etat["total"] or 2000
    for n in range(1, total + 1):
        etat = page.evaluate(JS_PAGE_COURANTE)
        cle = "|".join(etat["lignes"][:60])
        if cle in vues:            # la page n'a pas changé : dernière page atteinte
            break
        vues.add(cle)
        toutes.extend(lignes_visibles(etat["lignes"]))
        suivant = page.get_by_text("›", exact=True)
        if not suivant.count():
            break
        suivant.first.click()
        page.wait_for_timeout(400)
        if n % 50 == 0:
            print(f"    page {n}/{total}", flush=True)
    return toutes, etat["maj"]


def adresses_des_tableaux(page) -> dict:
    """Repère les 5 iframes Flourish sur la page OCDE, dans l'ordre des titres."""
    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(5000)
        srcs = page.evaluate("""() => [...document.querySelectorAll('iframe')]
                                 .map(f => f.src).filter(s => s.includes('flo.uri.sh'))""")
    except Exception as exc:
        print(f"[!] Page OCDE inaccessible ({exc}), adresses connues utilisées")
        return dict(ADRESSES_CONNUES)
    if len(srcs) != len(TABLEAUX):
        print(f"[!] {len(srcs)} tableaux trouvés au lieu de 5, adresses connues utilisées")
        return dict(ADRESSES_CONNUES)
    return {code: src.split("?")[0] for code, src in zip(TABLEAUX, srcs)}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    morceaux = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)   # headless=False pour voir le navigateur
        page = browser.new_page(locale="en-US")
        print("Recherche des tableaux sur la page OCDE…", flush=True)
        for code, url in adresses_des_tableaux(page).items():
            print(f"  {code} : {url}", flush=True)
            lignes, maj = lire_tableau(page, url)
            df = pd.DataFrame(lignes, columns=COLONNES)
            df["Tableau"] = code
            df["Last updated"] = maj
            morceaux.append(df)
            print(f"    -> {len(df)} lignes (Last updated : {maj or '?'})", flush=True)
        browser.close()

    df = pd.concat(morceaux, ignore_index=True)
    if df.empty:
        raise SystemExit("[X] Aucune ligne extraite.")

    horodatage = datetime.now().strftime("%Y%m%d")
    sortie = OUTPUT_DIR / f"oecd_aeoi_relations_{horodatage}.csv"
    df.to_csv(sortie, index=False)       # Bronze : on garde tout, doublons compris

    print(f"\n[OK] Bronze enregistré : {sortie}")
    print(f"     {df.shape[0]} lignes, {df.shape[1]} colonnes")
    print(f"     Colonnes : {list(df.columns)}")
    print("\nLignes par tableau :")
    for code, n in df.groupby("Tableau", sort=False).size().items():
        print(f"  {code:<10} {n}")


if __name__ == "__main__":
    main()