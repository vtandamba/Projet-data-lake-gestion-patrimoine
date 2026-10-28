"""
Inspection de la source 1 (RPW, feuille 1) : valeurs réelles des colonnes
à transformer. Script d'exploration, pas besoin de le pousser sur GitHub.

    python src/ingestion/profil_rpw.py > profil_rpw.txt
"""
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")   # évite les erreurs d'accents sous Windows

RACINE = Path(__file__).resolve().parents[2]
df = pd.read_csv(RACINE / "data" / "bronze" / "rpw_f1S1" / "Source1_f1.csv", dtype=str)

PERIMETRE = {"AUT", "BEL", "BGR", "HRV", "CZE", "EST", "FRA", "DEU", "HUN", "ITA", "LVA",
             "LTU", "NLD", "NOR", "POL", "PRT", "ROU", "ESP", "SWE", "CHE", "TUR", "UKR", "GBR"}
df = df[df["source_code"].isin(PERIMETRE)]
print(f"LIGNES (pays d'envoi dans le périmètre) : {len(df)}")
print(f"Périodes : {sorted(df['period'].unique())}")

for col in ["firm_type", "product", "sending location", "speed actual", "pick-up method",
            "coverage", "transparent", "cc1 lcu code", "cc2 lcu code",
            "cc1 denomination amount", "cc2 denomination amount"]:
    print(f"\n===== {col}  (nulls : {df[col].isna().sum()}) =====")
    print(df[col].value_counts(dropna=False).head(30).to_string())

for col in ["note1", "note2"]:
    print(f"\n===== {col}  (nulls : {df[col].isna().sum()}, valeurs distinctes : {df[col].nunique()}) =====")
    vc = df[col].value_counts().head(40)
    for valeur, n in vc.items():
        print(f"{n:>5}  {str(valeur)[:110]}")

print("\n===== Marges (cc1 / cc2) =====")
for c in ["cc1 fx margin", "cc2 fx margin"]:
    v = pd.to_numeric(df[c], errors="coerce")
    print(f"{c} : nulls={v.isna().sum()}  zéros={(v == 0).sum()}  négatives={(v < 0).sum()}")
v = pd.to_numeric(df["inter lcu bank fx"], errors="coerce")
print(f"inter lcu bank fx == 1 : {(v == 1).sum()}")
print(f"\nExemple de 3 lignes complètes :\n{df.head(3).T.to_string()}")
