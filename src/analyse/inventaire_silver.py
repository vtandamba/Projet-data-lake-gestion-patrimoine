"""
Inventaire de la zone SILVER : pour chaque table, nombre de lignes, colonnes
et 2 lignes d'exemple. Sert à concevoir la zone GOLD.

    python src/analyse/inventaire_silver.py > inventaire_silver.txt
"""
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_colwidth", 30)

for fichier in sorted(Path("data/silver").rglob("*.csv")):
    try:
        df = pd.read_csv(fichier, low_memory=False)
    except Exception as erreur:          # fichier illisible : on le signale et on continue
        print(f"\n##### {fichier} : ILLISIBLE ({erreur})")
        continue
    print(f"\n##### {fichier}  ({len(df)} lignes, {df.shape[1]} colonnes)")
    print(", ".join(f"{c} [{t}]" for c, t in df.dtypes.astype(str).items()))
    print(df.head(2).to_string(index=False))

for fichier in sorted(Path("data/silver").rglob("*")):
    if fichier.is_file() and fichier.suffix not in (".csv", ""):
        print(f"\n(autre fichier : {fichier})")
