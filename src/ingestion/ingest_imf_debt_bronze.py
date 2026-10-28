"""
Ingestion - Source 3 (complément) : dette publique, FMI World Economic Outlook
==============================================================================
Zone BRONZE : récupération brute, via l'API DataMapper du FMI, de la dette brute
des administrations publiques en % du PIB, pour les 23 pays du périmètre.

  GGXWDG_NGDP   General government gross debt (% of GDP)          -> requête 2.6

Pourquoi ce complément : l'indicateur Banque mondiale GC.DOD.TOTL.GD.ZS (dette de
l'administration CENTRALE) est absent pour 18 des 23 pays. Le FMI couvre les 23 pays
avec la définition de référence en Europe (administrations publiques).

Source  : https://www.imf.org/external/datamapper/api/v1/  (FMI, World Economic Outlook)
Sortie  : data/bronze/imf_debt_AAAAMMJJ.csv

Principe bronze : toutes les années renvoyées sont gardées TELLES QUELLES, y compris
les PRÉVISIONS du FMI (années futures). Elles seront écartées en zone Silver.

Lancer depuis la racine du dépôt :
    python src/ingestion/ingest_imf_debt_bronze.py
"""
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

INDICATEUR = "GGXWDG_NGDP"
URL = "https://www.imf.org/external/datamapper/api/v1/{indicateur}/{pays}"
OUTPUT_DIR = Path("data/bronze")

PERIMETRE_ISO3 = [
    "AUT", "BEL", "BGR", "HRV", "CZE", "EST", "FRA", "DEU", "HUN", "ITA", "LVA", "LTU",
    "NLD", "NOR", "POL", "PRT", "ROU", "ESP", "SWE", "CHE", "TUR", "UKR", "GBR",
]


NAVIGATEUR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


def appeler_api_requests(url: str) -> dict:
    """1er essai : requête simple avec des en-têtes de navigateur."""
    reponse = requests.get(url, headers=NAVIGATEUR, timeout=60)
    reponse.raise_for_status()
    return reponse.json()


def appeler_api_playwright(url: str) -> dict:
    """2e essai : le site du FMI bloque les robots (403) -> vrai navigateur Chromium,
    comme pour l'ingestion du FSI."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        navigateur = p.chromium.launch(headless=True)
        page = navigateur.new_page()
        reponse = page.goto(url, wait_until="networkidle", timeout=90_000)
        if reponse is None or not reponse.ok:
            statut = None if reponse is None else reponse.status
            navigateur.close()
            raise SystemExit(f"[X] API FMI inaccessible, même avec un navigateur (HTTP {statut})")
        contenu = reponse.json()
        navigateur.close()
        return contenu


def appeler_api() -> dict:
    # toutes les années disponibles (1980 -> prévisions) ; le filtre se fait en Silver
    url = URL.format(indicateur=INDICATEUR, pays="/".join(PERIMETRE_ISO3))
    try:
        return appeler_api_requests(url)
    except (requests.RequestException, ValueError) as erreur:
        print(f"  Requête simple refusée ({erreur.__class__.__name__}) -> navigateur Playwright")
        time.sleep(2)
        return appeler_api_playwright(url)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    contenu = appeler_api()
    # structure : {"values": {"GGXWDG_NGDP": {"FRA": {"2024": 113.1, ...}, ...}}, "api": {...}}
    par_pays = contenu.get("values", {}).get(INDICATEUR)
    if not par_pays:
        raise SystemExit(f"[X] Réponse inattendue de l'API FMI : {str(contenu)[:300]}")

    lignes = [
        {"indicator_id": INDICATEUR, "country_iso3": pays, "year": annee, "value": valeur}
        for pays, serie in par_pays.items()
        for annee, valeur in serie.items()
    ]
    df = pd.DataFrame(lignes)
    sortie = OUTPUT_DIR / f"imf_debt_{datetime.now():%Y%m%d}.csv"
    df.to_csv(sortie, index=False, encoding="utf-8")

    print(f"[OK] Bronze enregistré : {sortie}  ({len(df)} lignes, {df.shape[1]} colonnes)")
    print(f"     Pays reçus : {df['country_iso3'].nunique()} / {len(PERIMETRE_ISO3)}"
          f"  - absents : {sorted(set(PERIMETRE_ISO3) - set(df['country_iso3']))}")
    print(f"     Années : {df['year'].min()} -> {df['year'].max()} (prévisions FMI comprises)")


if __name__ == "__main__":
    main()
