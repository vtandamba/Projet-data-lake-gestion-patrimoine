"""
Ingestion - Source 1 : Remittance Prices Worldwide (Banque mondiale)
=====================================================================
Zone BRONZE : extraction des deux feuilles de données du classeur RPW en CSV,
TELLES QUELLES (tout en texte, aucune transformation).

Le classeur contient deux feuilles d'offres, séparées par un changement de
méthode de la Banque mondiale au 2e trimestre 2016 :
  'Dataset (up to Q1 2016)'  -> data/bronze/rpw_f1S1/rpw_q1_2011_2016.csv
  'Dataset (from Q2 2016)'   -> data/bronze/rpw_f1S1/rpw_q2_2016_2025.csv
(la feuille 'Countries' est traitée par la source 1, feuille 2)

Source  : https://datacatalogfiles.worldbank.org/ddh-published/0037898/DR0095523/
          rpw_dataset_2011_2025_q3.xlsx   (licence CC BY 4.0)
Entrée  : data/bronze/rpw_f1S1/rpw_dataset_2011_2025_q3.xlsx (à télécharger)

Lancer depuis la racine du dépôt (1 à 3 minutes : le classeur fait 48 Mo) :
    python src/ingestion/ingest_rpw_bronze.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

DOSSIER = Path("data/bronze/rpw_f1S1")
CLASSEUR = DOSSIER / "rpw_dataset_2011_2025_q3.xlsx"
FEUILLES = {
    "Dataset (up to Q1 2016)": DOSSIER / "rpw_q1_2011_2016.csv",
    "Dataset (from Q2 2016)": DOSSIER / "rpw_q2_2016_2025.csv",
}


def main():
    if not CLASSEUR.exists():
        raise SystemExit(f"[X] {CLASSEUR} introuvable : télécharger le classeur RPW "
                         "et le placer dans data/bronze/rpw_f1S1/")
    for feuille, sortie in FEUILLES.items():
        print(f"Lecture de la feuille '{feuille}'...")
        df = pd.read_excel(CLASSEUR, sheet_name=feuille, dtype=str)
        df.to_csv(sortie, index=False, encoding="utf-8")
        periodes = sorted(df["period"].dropna().unique())
        print(f"[OK] {sortie}  ({len(df)} lignes, {df.shape[1]} colonnes, "
              f"{periodes[0]} -> {periodes[-1]}, {len(periodes)} périodes)")


if __name__ == "__main__":
    main()
