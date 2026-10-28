"""
Inspection de la feuille RPW 'Dataset (from Q2 2016)' (bronze) : couverture du
périmètre et valeurs réelles des colonnes. Script d'exploration, à ne pas pousser.

    python src/ingestion/profil_rpw_q2.py > profil_rpw_q2.txt
"""
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 200)

df = pd.read_csv(Path("data/bronze/rpw_f1S1/rpw_q2_2016_2025.csv"), dtype=str)
PERIMETRE = {"AUT", "BEL", "BGR", "HRV", "CZE", "EST", "FRA", "DEU", "HUN", "ITA", "LVA",
             "LTU", "NLD", "NOR", "POL", "PRT", "ROU", "ESP", "SWE", "CHE", "TUR", "UKR", "GBR"}

print(f"LIGNES : {len(df)} ; COLONNES ({df.shape[1]}) :\n{list(df.columns)}")
print(f"\nPériodes : {sorted(df['period'].unique())}")

# ---- couverture du périmètre ----
envoi = df[df["source_code"].isin(PERIMETRE)]
interne = envoi[envoi["destination_code"].isin(PERIMETRE)]
print(f"\nOffres envoyées depuis le périmètre : {len(envoi)} ; vers le périmètre : {len(interne)}")
print("\nCorridors internes au périmètre (offres en 2025_3Q / nb de périodes) :")
tab = interne.groupby("corridor").agg(
    periodes=("period", "nunique"),
    offres_2025_3Q=("period", lambda s: (s == "2025_3Q").sum()))
print(tab.sort_values("offres_2025_3Q", ascending=False).to_string())
fra = df[df["source_code"] == "FRA"]
print(f"\nDepuis la France : {len(fra)} offres, destinations : "
      f"{sorted(fra['destination_code'].unique())}")
print(f"Pays du périmètre qui reçoivent des offres : "
      f"{sorted(interne['destination_code'].unique())}")
print(f"Pays d'envoi du périmètre présents : {sorted(envoi['source_code'].unique())}")

# ---- valeurs des colonnes (sur les envois depuis le périmètre) ----
for col in ["firm_type", "payment instrument", "access point", "speed actual",
            "pickup method", "pickup location", "receiving network coverage", "transparent",
            "cc1 lcu code", "cc2 lcu code", "cc1 denomination amount",
            "cc2 denomination amount"]:
    if col in envoi.columns:
        print(f"\n===== {col}  (nulls : {envoi[col].isna().sum()}) =====")
        print(envoi[col].value_counts(dropna=False).head(25).to_string())

for col in ["Standard Note", "note2"]:
    if col in envoi.columns:
        print(f"\n===== {col}  (nulls : {envoi[col].isna().sum()}, "
              f"distinctes : {envoi[col].nunique()}) =====")
        for valeur, n in envoi[col].value_counts().head(30).items():
            print(f"{n:>6}  {str(valeur)[:120]}")

print("\n===== Marges et taux (envois depuis le périmètre) =====")
for c in ["cc1 fx margin", "cc2 fx margin", "cc1 total cost %", "cc2 total cost %"]:
    v = pd.to_numeric(envoi[c], errors="coerce")
    print(f"{c} : nulls={v.isna().sum()} zéros={(v == 0).sum()} négatives={(v < 0).sum()}")
print(f"\nExemples de dates : {envoi['date'].dropna().unique()[:5]}")
print(f"\n2 lignes d'exemple :\n{envoi.head(2).T.to_string()}")
