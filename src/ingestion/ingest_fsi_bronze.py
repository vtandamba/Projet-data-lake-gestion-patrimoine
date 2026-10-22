"""
Ingestion BRONZE — Financial Secrecy Index (FSI 2026)
Source : Tax Justice Network — https://fsi.taxjustice.net/full-list/
Licence : CC BY-NC-SA 4.0 (usage académique). >>> Citer le Tax Justice Network dans le rapport. <<<

POURQUOI CE SCRIPT :
Le classement FSI n'est pas un simple tableau HTML : la page est construite en
JavaScript et va chercher ses données via une API interne. Les méthodes classiques
(copier-coller, Google Sheets IMPORTHTML, pandas.read_html) tombent donc sur une
page vide. Le portail de téléchargement officiel, lui, limite l'accès gratuit à
10 lignes.

COMMENT ON CONTOURNE :
On ouvre la page avec un vrai navigateur (Playwright), on le laisse exécuter son
JavaScript, et on INTERCEPTE la réponse JSON de l'API que le site appelle
(fsi2026_jurisdictions). On récupère ainsi toutes les juridictions d'un coup.

PRINCIPE BRONZE :
On enregistre les données TELLES QUELLES, sans aucun nettoyage ni sélection de
colonnes. Le nettoyage (typage, harmonisation des noms de pays en ISO3, sélection
des colonnes utiles : score + rang) se fera plus tard, en zone SILVER.

SORTIE : data/bronze/fsi_2026_raw.csv
"""

import asyncio
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright


# ============================================================
# 1. CONFIGURATION
# ============================================================

URL = "https://fsi.taxjustice.net/full-list/#scoring_id=317"

# Le script se trouve dans src/ingestion/.
# parents[2] permet de retrouver la racine du projet.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Dossier Bronze existant à la racine du projet.
BRONZE_DIR = PROJECT_ROOT / "data" / "bronze"

# Fichier de sortie.
OUTPUT_FILE = BRONZE_DIR / "fsi_2026_raw.csv"


# ============================================================
# 2. RÉCUPÉRATION DES DONNÉES
# ============================================================

async def get_fsi_data():
    """Récupère les juridictions FSI via la réponse API du navigateur."""

    jurisdictions_data = []

    async with async_playwright() as p:
        print("🚀 Démarrage de Chromium...")

        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        async def handle_response(response):
            """Intercepte la réponse de l'API FSI 2026."""

            if "fsi2026_jurisdictions" not in response.url:
                return

            if not response.ok:
                print(
                    f"⚠️ Erreur API HTTP {response.status}"
                )
                return

            try:
                data = await response.json()

                if not isinstance(data, list):
                    print("⚠️ La réponse API n'est pas une liste JSON.")
                    return

                jurisdictions_data.extend(data)

                print(
                    f"✅ Réponse API récupérée : "
                    f"{len(data)} lignes"
                )

            except Exception as error:
                print(
                    "⚠️ Erreur lors de la lecture "
                    f"de la réponse API : {error}"
                )

        # Enregistrer l'écouteur avant de charger le site.
        page.on("response", handle_response)

        try:
            print("🌐 Chargement de la page FSI...")

            await page.goto(
                URL,
                wait_until="networkidle",
                timeout=120000
            )

            # Laisser le temps aux requêtes API de se terminer.
            print("⏳ Attente des données...")
            await page.wait_for_timeout(10000)

        finally:
            await browser.close()

    return jurisdictions_data


# ============================================================
# 3. PROGRAMME PRINCIPAL
# ============================================================

async def main():

    print("=" * 60)
    print("FSI 2026 — INGESTION BRONZE")
    print("=" * 60)

    # --------------------------------------------------------
    # Récupération
    # --------------------------------------------------------

    data = await get_fsi_data()

    if not data:
        raise RuntimeError(
            "Aucune donnée récupérée. "
            "Vérifie le chargement du site et les requêtes API."
        )

    # --------------------------------------------------------
    # Conversion en DataFrame
    # --------------------------------------------------------

    df = pd.DataFrame(data)

    print(f"\n✅ Juridictions récupérées : {len(df)}")
    print(f"✅ Colonnes récupérées : {len(df.columns)}")

    # --------------------------------------------------------
    # Contrôles de structure
    # --------------------------------------------------------

    required_columns = [
        "jurisdiction_name_en",
        "index_score",
        "rank"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            "Colonnes attendues absentes de la réponse API : "
            + ", ".join(missing_columns)
        )

    print("\n📋 Colonnes disponibles :")
    for column in df.columns:
        print(f" - {column}")

    # Aperçu uniquement : les données ne sont pas transformées.
    print("\n📊 Aperçu des données brutes :")
    print(df.head(5).to_string(index=False))

    # --------------------------------------------------------
    # Export dans data/bronze
    # --------------------------------------------------------

    # Le dossier existe déjà dans ton projet.
    # mkdir(exist_ok=True) évite une erreur s'il existe.
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n" + "=" * 60)
    print("✅ INGESTION TERMINÉE")
    print("=" * 60)
    print(f"📌 Nombre de lignes : {len(df)}")
    print(f"📌 Nombre de colonnes : {len(df.columns)}")
    print(f"💾 Fichier enregistré : {OUTPUT_FILE}")


# ============================================================
# 4. POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
