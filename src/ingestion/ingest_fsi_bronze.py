"""
Ingestion — Financial Secrecy Index (Tax Justice Network)
=========================================================
Zone BRONZE : récupération brute du classement complet (Full List).

Le tableau de la page est construit en JavaScript : les outils qui lisent
le HTML brut (Google Sheets IMPORTHTML, pandas.read_html seul) voient une
page vide. Playwright ouvre un vrai navigateur, laisse le JS s'exécuter,
puis on récupère le HTML déjà rendu.

Source  : https://fsi.taxjustice.net/full-list/
Licence : CC BY-NC-SA 4.0 — usage académique non commercial.
          >>> Citer le Tax Justice Network comme source dans le rapport. <<<

Principe bronze : on enregistre les données TELLES QUELLES, sans nettoyage.
Le nettoyage (types, noms de pays, valeurs manquantes) se fera en zone SILVER.
"""

from pathlib import Path
from datetime import datetime
import pandas as pd
from playwright.sync_api import sync_playwright

URL = "https://fsi.taxjustice.net/full-list/"
OUTPUT_DIR = Path("data/bronze")


def recuperer_html_rendu() -> str:
    """Ouvre la page dans un navigateur, attend le rendu JS, renvoie le HTML."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)   # headless=False pour voir le navigateur
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60_000)

        # 1) Attendre que le tableau soit réellement présent dans la page
        page.wait_for_selector("table", timeout=30_000)

        # 2) Faire défiler jusqu'en bas pour déclencher un éventuel
        #    chargement progressif (lazy-load) de toutes les lignes
        hauteur_precedente = 0
        for _ in range(30):
            page.mouse.wheel(0, 20_000)
            page.wait_for_timeout(500)
            hauteur = page.evaluate("document.body.scrollHeight")
            if hauteur == hauteur_precedente:
                break
            hauteur_precedente = hauteur

        html = page.content()
        browser.close()
        return html


def apercu_tableaux(html: str) -> list[pd.DataFrame]:
    """Liste tous les tableaux trouvés pour repérer le bon."""
    tables = pd.read_html(html)
    print(f"\n{len(tables)} tableau(x) détecté(s) :")
    for i, t in enumerate(tables):
        colonnes = list(t.columns)[:6]
        print(f"  [{i}] {t.shape[0]} lignes x {t.shape[1]} col.  ->  {colonnes}")
    return tables


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    html = recuperer_html_rendu()
    tables = apercu_tableaux(html)

    # --- A AJUSTER APRES LE PREMIER LANCEMENT -----------------------------
    # Regarde l'aperçu ci-dessus et choisis l'index du tableau qui contient
    # la colonne "Secrecy Score". Souvent 0, parfois 1.
    index_tableau = 0
    # ----------------------------------------------------------------------

    df = tables[index_tableau]

    horodatage = datetime.now().strftime("%Y%m%d")
    sortie = OUTPUT_DIR / f"fsi_full_list_{horodatage}.csv"
    df.to_csv(sortie, index=False)

    print(f"\n[OK] Bronze enregistré : {sortie}")
    print(f"     {df.shape[0]} lignes, {df.shape[1]} colonnes")
    print(f"     Colonnes : {list(df.columns)}")
    print("\nVérifie qu'une colonne 'Secrecy Score' (valeurs 0-100) est bien présente.")


if __name__ == "__main__":
    main()