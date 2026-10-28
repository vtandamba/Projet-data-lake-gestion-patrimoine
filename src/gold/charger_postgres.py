"""
Chargement des zones SILVER et GOLD dans PostgreSQL
===================================================
Crée deux schémas dans la base data_lake et y charge tous les CSV :
  data/silver/**/*.csv  ->  schéma silver   (ex. data/silver/bis/bis_cpi.csv -> silver.bis_cpi)
  data/gold/*.csv       ->  schéma gold     (ex. data/gold/dim_pays.csv      -> gold.dim_pays)
Chaque table est recréée à chaque lancement (rechargement complet). Le chargement passe par
COPY (rapide, même pour les tables de plusieurs centaines de milliers de lignes).

Base : conteneur Docker du projet (docker compose up -d), port 5434. Pour une autre base,
définir la variable d'environnement DATABASE_URL.

Prérequis (une fois, dans le venv) :
    pip install sqlalchemy psycopg2-binary

Lancer depuis la racine du dépôt :
    python src/gold/charger_postgres.py            # silver + gold
    python src/gold/charger_postgres.py gold       # gold seulement
"""
import io
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

sys.stdout.reconfigure(encoding="utf-8")

RACINE = Path(__file__).resolve().parents[2]
URL = os.environ.get("DATABASE_URL", "postgresql+psycopg2://data_lake:data_lake@localhost:5434/data_lake")
ZONES = {"silver": RACINE / "data" / "silver", "gold": RACINE / "data" / "gold"}
COLONNES_DATE = re.compile(r"^(date|date_.*|.*_date)$")


def nom_table(fichier: Path) -> str:
    """'capital_gains_tax_europe-silver.csv' -> 'capital_gains_tax_europe_silver'."""
    nom = re.sub(r"[^0-9a-zA-Z_]", "_", fichier.stem).lower()
    return re.sub(r"_+", "_", nom).strip("_")


def preparer(df: pd.DataFrame) -> pd.DataFrame:
    """Dates en vrai type date ; booléens écrits True/False -> booléens PostgreSQL."""
    for col in df.columns:
        texte = df[col].dtype == object or pd.api.types.is_string_dtype(df[col])  # pandas 2 et 3
        if COLONNES_DATE.match(col) and texte:
            conv = pd.to_datetime(df[col], errors="coerce", format="mixed")
            if conv.notna().sum() >= 0.9 * df[col].notna().sum():   # vraie colonne de dates
                df[col] = conv
        if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
            valeurs = set(df[col].dropna().astype(str).unique())
            if valeurs and valeurs <= {"True", "False"}:
                df[col] = df[col].map({"True": True, "False": False})
    return df


def charger(engine, schema: str, table: str, df: pd.DataFrame):
    df.head(0).to_sql(table, engine, schema=schema, if_exists="replace", index=False)  # structure
    tampon = io.StringIO()
    df.to_csv(tampon, index=False, header=False)
    tampon.seek(0)
    colonnes = ", ".join(f'"{c}"' for c in df.columns)
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            cur.copy_expert(f'COPY {schema}."{table}" ({colonnes}) FROM STDIN WITH (FORMAT csv)', tampon)
        conn.commit()
    finally:
        conn.close()


def main():
    zones = sys.argv[1:] or list(ZONES)
    engine = create_engine(URL)
    with engine.begin() as c:
        version = c.execute(text("select version()")).scalar()
    print(f"Connecté : {version.split(',')[0]}")

    bilan = []
    for zone in zones:
        dossier = ZONES[zone]
        with engine.begin() as c:
            c.execute(text(f"create schema if not exists {zone}"))
        fichiers = sorted(dossier.rglob("*.csv"))
        noms = [nom_table(f) for f in fichiers]
        doublons = {n for n in noms if noms.count(n) > 1}
        if doublons:
            raise SystemExit(f"[X] Plusieurs fichiers donneraient la même table : {doublons}")
        print(f"\n=== schéma {zone} : {len(fichiers)} fichiers ===")
        for fichier, table in zip(fichiers, noms):
            debut = time.time()
            df = preparer(pd.read_csv(fichier, low_memory=False))
            charger(engine, zone, table, df)
            with engine.begin() as c:
                n = c.execute(text(f'select count(*) from {zone}."{table}"')).scalar()
            statut = "OK" if n == len(df) else f"ÉCART ({len(df)} lignes dans le CSV)"
            print(f"  {zone}.{table:<40} {n:>8} lignes  {df.shape[1]:>3} col.  "
                  f"{time.time() - debut:5.1f} s  {statut}")
            bilan.append((zone, table, n, statut))

    erreurs = [b for b in bilan if b[3] != "OK"]
    print(f"\n{'[X]' if erreurs else '[OK]'} {len(bilan)} tables chargées"
          + (f", {len(erreurs)} en écart" if erreurs else "") + f" dans {URL.split('@')[-1]}")


if __name__ == "__main__":
    main()
