"""
Ingestion - Source 9 : listes du GAFI (FATF)
============================================
Zone BRONZE : listes publiques du GAFI à l'issue de sa dernière plénière.

  grey_list  : « Jurisdictions under Increased Monitoring »
  black_list : « High-Risk Jurisdictions subject to a Call for Action »

Le GAFI ne propose PAS d'API : ses listes sont publiées en page web / PDF à chaque
plénière (février, juin, octobre), à une adresse différente à chaque fois. Un
extracteur automatique serait fragile. On procède donc comme pour un fichier de
référence : la liste est transcrite ci-dessous depuis la publication officielle,
avec la date de la plénière et la source, et ce script écrit le Bronze daté.

MISE À JOUR après chaque plénière (prochaine : fin octobre 2026, décision attendue
le 30/10/2026 - sortie de la Bulgarie annoncée par la presse, non confirmée) :
  1. modifier PLENIERE et les listes GREY_LIST / BLACK_LIST ci-dessous ;
  2. relancer ce script, puis src/transformation/transform_fatf_silver.py.

Source  : https://www.fatf-gafi.org/en/countries/black-and-grey-lists.html
Sortie  : data/bronze/fatf_lists_AAAAMMJJ.csv

Lancer depuis la racine du dépôt :
    python src/ingestion/ingest_fatf_bronze.py
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

OUTPUT_DIR = Path("data/bronze")
SOURCE_URL = "https://www.fatf-gafi.org/en/countries/black-and-grey-lists.html"
PLENIERE = "2026-06-19"   # plénière du GAFI des 17-19 juin 2026

# Noms tels qu'ils figurent dans la publication du GAFI (aucune normalisation ici)
GREY_LIST = [
    "Angola", "Bolivia", "Bosnia and Herzegovina", "Bulgaria", "Cameroon",
    "Côte d'Ivoire", "Democratic Republic of the Congo", "Haiti", "Iraq", "Kenya",
    "Kuwait", "Lao PDR", "Lebanon", "Monaco", "Nepal", "Papua New Guinea",
    "South Sudan", "Syria", "Venezuela", "Vietnam", "Virgin Islands (UK)", "Yemen",
]
BLACK_LIST = [
    # Myanmar figure dans la même publication, avec une mesure de vigilance renforcée
    "Democratic People's Republic of Korea (DPRK)", "Iran", "Myanmar",
]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    lignes = ([{"country_name": p, "fatf_status": "grey_list"} for p in GREY_LIST]
              + [{"country_name": p, "fatf_status": "black_list"} for p in BLACK_LIST])
    df = pd.DataFrame(lignes)
    df["plenary_date"] = PLENIERE
    df["source_url"] = SOURCE_URL

    if df["country_name"].duplicated().any():
        raise SystemExit("[X] Un pays apparaît deux fois dans les listes")

    sortie = OUTPUT_DIR / f"fatf_lists_{datetime.now():%Y%m%d}.csv"
    df.to_csv(sortie, index=False, encoding="utf-8")
    print(f"[OK] Bronze enregistré : {sortie}  ({len(df)} lignes)")
    print(f"     Plénière : {PLENIERE} - liste grise : {len(GREY_LIST)}, "
          f"liste noire : {len(BLACK_LIST)}")


if __name__ == "__main__":
    main()
