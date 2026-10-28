"""
Ingestion - Source 3 : Banque mondiale (World Development Indicators, API v2)
=============================================================================
Zone BRONZE : récupération brute, via l'API, des 3 indicateurs utilisés par les
requêtes du projet, pour les 23 pays du périmètre.

  FP.CPI.TOTL.ZG     Inflation, prix à la consommation (% annuel)      -> 2.5, 2.15, 2.17, 2.18, 3.3
  NY.GDP.MKTP.KD.ZG  Croissance du PIB (% annuel)                      -> 2.6
  GC.DOD.TOTL.GD.ZS  Dette de l'administration centrale (% du PIB)     -> 2.6

Source  : https://api.worldbank.org/v2/  (World Bank Open Data, licence CC BY 4.0)
Sortie  : data/bronze/wb_api_AAAAMMJJ.csv

Principe bronze : les champs de l'API sont enregistrés TELS QUELS (une ligne par
pays x indicateur x année, valeurs vides comprises). Aucun nettoyage ici.

Lancer depuis la racine du dépôt :
    python src/ingestion/ingest_wb_api_bronze.py
"""
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

URL = "https://api.worldbank.org/v2/country/{pays}/indicator/{indicateur}"
OUTPUT_DIR = Path("data/bronze")

PERIMETRE_ISO3 = [
    "AUT", "BEL", "BGR", "HRV", "CZE", "EST", "FRA", "DEU", "HUN", "ITA", "LVA", "LTU",
    "NLD", "NOR", "POL", "PRT", "ROU", "ESP", "SWE", "CHE", "TUR", "UKR", "GBR",
]
INDICATEURS = ["FP.CPI.TOTL.ZG", "NY.GDP.MKTP.KD.ZG", "GC.DOD.TOTL.GD.ZS"]
ANNEES = "2000:2025"


def appeler_api(indicateur: str) -> list[dict]:
    """Toutes les pages de l'API pour un indicateur (les 23 pays en un appel)."""
    lignes, page, pages = [], 1, 1
    while page <= pages:
        params = {"format": "json", "date": ANNEES, "per_page": 1000, "page": page}
        url = URL.format(pays=";".join(PERIMETRE_ISO3), indicateur=indicateur)
        for essai in range(3):                      # l'API coupe parfois : 3 essais
            try:
                reponse = requests.get(url, params=params, timeout=60)
                reponse.raise_for_status()
                contenu = reponse.json()
                break
            except (requests.RequestException, ValueError) as erreur:
                if essai == 2:
                    raise SystemExit(f"[X] {indicateur} page {page} : {erreur}")
                time.sleep(3)
        # réponse normale : [métadonnées, enregistrements] ; erreur : [{"message": ...}]
        if len(contenu) < 2 or contenu[1] is None:
            raise SystemExit(f"[X] {indicateur} : réponse inattendue de l'API : {contenu}")
        meta, enregistrements = contenu
        pages = int(meta["pages"])
        lignes.extend(enregistrements)
        page += 1
    return lignes


def aplatir(enregistrement: dict) -> dict:
    """Le JSON imbriqué de l'API -> une ligne de tableau (aucune valeur modifiée)."""
    return {
        "indicator_id": enregistrement["indicator"]["id"],
        "indicator_name": enregistrement["indicator"]["value"],
        "country_id": enregistrement["country"]["id"],
        "country_name": enregistrement["country"]["value"],
        "countryiso3code": enregistrement["countryiso3code"],
        "date": enregistrement["date"],
        "value": enregistrement["value"],
        "unit": enregistrement["unit"],
        "obs_status": enregistrement["obs_status"],
        "decimal": enregistrement["decimal"],
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    toutes = []
    for indicateur in INDICATEURS:
        lignes = appeler_api(indicateur)
        print(f"  {indicateur:<20} {len(lignes):>5} lignes")
        toutes.extend(aplatir(e) for e in lignes)

    df = pd.DataFrame(toutes)
    sortie = OUTPUT_DIR / f"wb_api_{datetime.now():%Y%m%d}.csv"
    df.to_csv(sortie, index=False, encoding="utf-8")

    print(f"\n[OK] Bronze enregistré : {sortie}  ({len(df)} lignes, {df.shape[1]} colonnes)")
    print(f"     Pays reçus : {df['countryiso3code'].nunique()} / {len(PERIMETRE_ISO3)}")
    print(f"     Années : {df['date'].min()} -> {df['date'].max()}")
    print(f"     Valeurs vides : {df['value'].isna().sum()} ({df['value'].isna().mean():.1%})")


if __name__ == "__main__":
    main()
