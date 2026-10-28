"""
Transformation - Source 6 : Worldwide Governance Indicators (WGI)
=================================================================
Zone SILVER : nettoyage du fichier Bronze le plus récent.

Entrée  : data/bronze/wgi_AAAAMMJJ.csv (le plus récent)
Sortie  : data/silver/wgi.csv           - une ligne par pays x dimension x année
Rapport : reports/transform_wgi.txt

Étapes :
  1. Lecture du Bronze (tout en texte).
  2. Restriction aux 23 pays du périmètre.
  3. Code indicateur -> dimension courte attendue par les requêtes
     (GOV_WGI_PV_EST -> 'pv', etc.) + libellé français.
  4. Typage : année entière, score décimal.
  5. Années non publiées (1997, 1999, 2001 : WGI bisannuel au début) supprimées,
     SANS imputation (une interpolation inventerait une mesure qui n'existe pas).
  6. Contrôles : doublons, 6 dimensions, bornes du score (environ -2,5 à +2,5).

Colonnes Silver (noms utilisés par les requêtes SQL 2.7, 2.20, 2.21, 3.3) :
  economy_code, iso2, country_name, year, governance_dimension, dimension,
  governance_score

Non repris en Silver : indicator_id et indicator_name (remplacés par
governance_dimension et dimension), unit, obs_status, decimal (vides ou présentation).

Lancer depuis la racine du dépôt :
    python src/transformation/transform_wgi_silver.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

BRONZE = Path("data/bronze")
SILVER = Path("data/silver")
REPORTS = Path("reports")
SORTIE = SILVER / "wgi.csv"
RAPPORT = REPORTS / "transform_wgi.txt"

PERIMETRE = {  # ISO3 -> ISO2
    "AUT": "AT", "BEL": "BE", "BGR": "BG", "HRV": "HR", "CZE": "CZ", "EST": "EE",
    "FRA": "FR", "DEU": "DE", "HUN": "HU", "ITA": "IT", "LVA": "LV", "LTU": "LT",
    "NLD": "NL", "NOR": "NO", "POL": "PL", "PRT": "PT", "ROU": "RO", "ESP": "ES",
    "SWE": "SE", "CHE": "CH", "TUR": "TR", "UKR": "UA", "GBR": "GB",
}
DIMENSIONS = {  # code indicateur -> (code court, libellé)
    "GOV_WGI_VA_EST": ("va", "Voix et responsabilité"),
    "GOV_WGI_PV_EST": ("pv", "Stabilité politique et absence de violence"),
    "GOV_WGI_GE_EST": ("ge", "Efficacité du gouvernement"),
    "GOV_WGI_RQ_EST": ("rq", "Qualité réglementaire"),
    "GOV_WGI_RL_EST": ("rl", "État de droit"),
    "GOV_WGI_CC_EST": ("cc", "Contrôle de la corruption"),
}
BORNE = 2.5   # le score est construit sur environ -2,5 / +2,5 (quelques pays dépassent)


def dernier_bronze() -> Path:
    fichiers = sorted(BRONZE.glob("wgi_*.csv"))
    if not fichiers:
        raise SystemExit("[X] Aucun fichier wgi_*.csv dans data/bronze : "
                         "lancer d'abord src/ingestion/ingest_wgi_bronze.py")
    return fichiers[-1]


def main():
    lignes_rapport = []

    def log(texte=""):
        print(texte)
        lignes_rapport.append(texte)

    fichier = dernier_bronze()
    df = pd.read_csv(fichier, dtype=str, encoding="utf-8")
    log(f"Bronze lu : {fichier}  ({len(df)} lignes)")
    journal = [("Bronze", len(df))]

    # 2. périmètre
    df = df[df["countryiso3code"].isin(PERIMETRE) & df["indicator_id"].isin(DIMENSIONS)].copy()
    journal.append(("Périmètre (23 pays, 6 dimensions)", len(df)))

    # 3 + 4. dimension courte, typage
    df["governance_dimension"] = df["indicator_id"].map(lambda i: DIMENSIONS[i][0])
    df["dimension"] = df["indicator_id"].map(lambda i: DIMENSIONS[i][1])
    df["year"] = pd.to_numeric(df["date"], errors="coerce").astype("Int64")
    df["governance_score"] = pd.to_numeric(df["value"], errors="coerce")

    # 5. années non publiées
    vides = df["governance_score"].isna()
    annees_vides = sorted(df.loc[vides, "year"].dropna().unique().tolist())
    log(f"\nScores vides supprimés (sans imputation) : {vides.sum()} - années : {annees_vides}")
    df = df[~vides].copy()
    journal.append(("Après suppression des années non publiées", len(df)))

    df["economy_code"] = df["countryiso3code"]
    df["iso2"] = df["economy_code"].map(PERIMETRE)
    silver = (df[["economy_code", "iso2", "country_name", "year", "governance_dimension",
                  "dimension", "governance_score"]]
              .sort_values(["economy_code", "governance_dimension", "year"])
              .reset_index(drop=True))

    # 6. contrôles
    erreurs = []
    if silver.duplicated(["economy_code", "governance_dimension", "year"]).any():
        erreurs.append("doublons (pays, dimension, année)")
    if silver["governance_dimension"].nunique() != 6:
        erreurs.append("les 6 dimensions ne sont pas toutes présentes")
    if silver["economy_code"].nunique() != len(PERIMETRE):
        erreurs.append(f"pays manquants : {set(PERIMETRE) - set(silver['economy_code'])}")
    if erreurs:
        raise SystemExit("[X] Contrôles en échec : " + " ; ".join(erreurs))

    hors_bornes = silver[silver["governance_score"].abs() > BORNE]
    log(f"Scores au-delà de ±{BORNE} (conservés) : {len(hors_bornes)}")
    if len(hors_bornes):
        log(hors_bornes[["economy_code", "governance_dimension", "year", "governance_score"]]
            .to_string(index=False))

    derniere = int(silver["year"].max())
    log(f"\nAnnées : {int(silver['year'].min())} -> {derniere}")
    log(f"\nScores {derniere} par pays (du plus stable politiquement au moins stable) :")
    tableau = (silver[silver["year"] == derniere]
               .pivot(index="economy_code", columns="governance_dimension",
                      values="governance_score")
               [["va", "pv", "ge", "rq", "rl", "cc"]]
               .sort_values("pv", ascending=False).round(2))
    log(tableau.to_string())

    log("\nJournal :")
    for etape, n in journal + [("Silver", len(silver))]:
        log(f"  {etape:<45} {n:>6}")

    SILVER.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    silver.to_csv(SORTIE, index=False, encoding="utf-8")
    log(f"\n[OK] Silver enregistré : {SORTIE}  ({len(silver)} lignes, {silver.shape[1]} colonnes)")
    RAPPORT.write_text("\n".join(lignes_rapport), encoding="utf-8")
    print(f"[OK] Rapport : {RAPPORT}")


if __name__ == "__main__":
    main()
