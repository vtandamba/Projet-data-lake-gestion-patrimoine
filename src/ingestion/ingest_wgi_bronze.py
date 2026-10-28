"""
Ingestion - Source 6 : Worldwide Governance Indicators (Banque mondiale, API v2)
================================================================================
Zone BRONZE : récupération brute des 6 dimensions de gouvernance (score "estimate",
d'environ -2,5 à +2,5) pour les 23 pays du périmètre.

  GOV_WGI_VA_EST  Voix et responsabilité        GOV_WGI_RQ_EST  Qualité réglementaire
  GOV_WGI_PV_EST  Stabilité politique           GOV_WGI_RL_EST  État de droit
  GOV_WGI_GE_EST  Efficacité du gouvernement    GOV_WGI_CC_EST  Contrôle de la corruption

Requêtes du projet : 2.7, 2.20, 2.21, 3.3

Source  : https://api.worldbank.org/v2/  (WGI, révision 2025, licence CC BY 4.0)
Sortie  : data/bronze/wgi_AAAAMMJJ.csv

Principe bronze : les champs de l'API sont enregistrés TELS QUELS (valeurs vides
comprises : le WGI n'est pas publié pour 1997, 1999 et 2001). Aucun nettoyage ici.

Lancer depuis la racine du dépôt :
    python src/ingestion/ingest_wgi_bronze.py
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
INDICATEURS = [f"GOV_WGI_{d}_EST" for d in ("VA", "PV", "GE", "RQ", "RL", "CC")]
ANNEES = "1996:2025"


def appeler_api(indicateur: str, source=None) -> list[dict]:
    """Toutes les pages de l'API pour un indicateur (les 23 pays en un appel)."""
    lignes, page, pages = [], 1, 1
    while page <= pages:
        params = {"format": "json", "date": ANNEES, "per_page": 1000, "page": page}
        if source:
            params["source"] = source
        url = URL.format(pays=";".join(PERIMETRE_ISO3), indicateur=indicateur)
        for essai in range(3):
            try:
                reponse = requests.get(url, params=params, timeout=60)
                reponse.raise_for_status()
                contenu = reponse.json()
                break
            except (requests.RequestException, ValueError) as erreur:
                if essai == 2:
                    raise SystemExit(f"[X] {indicateur} page {page} : {erreur}")
                time.sleep(3)
        if len(contenu) < 2 or contenu[1] is None:
            # indicateur introuvable dans la base par défaut (WDI) -> base WGI (source 3)
            if source is None:
                return appeler_api(indicateur, source=3)
            raise SystemExit(f"[X] {indicateur} : réponse inattendue de l'API : {contenu}")
        meta, enregistrements = contenu
        pages = int(meta["pages"])
        lignes.extend(enregistrements)
        page += 1
    return lignes


def aplatir(e: dict) -> dict:
    return {
        "indicator_id": e["indicator"]["id"],
        "indicator_name": e["indicator"]["value"],
        "country_id": e["country"]["id"],
        "country_name": e["country"]["value"],
        "countryiso3code": e["countryiso3code"],
        "date": e["date"],
        "value": e["value"],
        "unit": e["unit"],
        "obs_status": e["obs_status"],
        "decimal": e["decimal"],
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    toutes = []
    for indicateur in INDICATEURS:
        lignes = appeler_api(indicateur)
        print(f"  {indicateur:<16} {len(lignes):>5} lignes")
        toutes.extend(aplatir(e) for e in lignes)

    df = pd.DataFrame(toutes)
    sortie = OUTPUT_DIR / f"wgi_{datetime.now():%Y%m%d}.csv"
    df.to_csv(sortie, index=False, encoding="utf-8")

    remplies = df[df["value"].notna()]
    print(f"\n[OK] Bronze enregistré : {sortie}  ({len(df)} lignes, {df.shape[1]} colonnes)")
    print(f"     Pays reçus : {df['countryiso3code'].nunique()} / {len(PERIMETRE_ISO3)}")
    print(f"     Années avec des valeurs : {remplies['date'].min()} -> {remplies['date'].max()}")
    print(f"     Valeurs vides : {df['value'].isna().sum()} ({df['value'].isna().mean():.1%})")


if __name__ == "__main__":
    main()
