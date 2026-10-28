"""
Transformation - Source 3 : indicateurs macroéconomiques (Banque mondiale + FMI)
================================================================================
Zone SILVER : nettoyage des fichiers Bronze les plus récents.

Entrées : data/bronze/wb_api_AAAAMMJJ.csv    (Banque mondiale : inflation, croissance du PIB)
          data/bronze/imf_debt_AAAAMMJJ.csv  (FMI WEO : dette publique)
Sortie  : data/silver/wb_api.csv            - une ligne par pays x indicateur x année
Rapport : reports/transform_wb_api.txt

Étapes :
  1. Lecture des Bronze (tout en texte, aucune conversion implicite).
  2. Restriction aux 23 pays du périmètre.
  3. Dette publique : l'indicateur Banque mondiale GC.DOD.TOTL.GD.ZS (administration
     centrale) est absent pour 18 pays sur 23 -> remplacé par la dette des
     administrations publiques du FMI (GGXWDG_NGDP), disponible pour les 23 pays.
  4. Prévisions du FMI (années >= année en cours) écartées : on ne garde que l'observé.
  5. Typage : date -> année entière, value -> décimal.
  6. Valeurs vides supprimées, SANS imputation (couverture documentée dans le rapport).
  7. Ajout de iso2 (jointure avec les sources BIS), du libellé français, de la source
     et d'un indicateur de valeur extrême (valeur conservée).
  8. Contrôles : doublons, indicateurs attendus, années reconnues.

Colonnes Silver (noms utilisés par les requêtes SQL du projet) :
  indicator_id, indicateur, source, countryiso3code, iso2, country_name, date, value,
  valeur_extreme

Requête 2.6 : remplacer 'GC.DOD.TOTL.GD.ZS' par 'GGXWDG_NGDP'.

Lancer depuis la racine du dépôt :
    python src/transformation/transform_wb_api_silver.py
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")   # accents sous Windows

BRONZE = Path("data/bronze")
SILVER = Path("data/silver")
REPORTS = Path("reports")
SORTIE = SILVER / "wb_api.csv"
RAPPORT = REPORTS / "transform_wb_api.txt"

PERIMETRE = {  # ISO3 -> ISO2
    "AUT": "AT", "BEL": "BE", "BGR": "BG", "HRV": "HR", "CZE": "CZ", "EST": "EE",
    "FRA": "FR", "DEU": "DE", "HUN": "HU", "ITA": "IT", "LVA": "LV", "LTU": "LT",
    "NLD": "NL", "NOR": "NO", "POL": "PL", "PRT": "PT", "ROU": "RO", "ESP": "ES",
    "SWE": "SE", "CHE": "CH", "TUR": "TR", "UKR": "UA", "GBR": "GB",
}
INDICATEURS = {  # indicator_id -> (libellé, source, bornes au-delà desquelles valeur_extreme)
    "FP.CPI.TOTL.ZG": ("Inflation, prix à la consommation (% annuel)",
                       "Banque mondiale WDI", (-5, 30)),
    "NY.GDP.MKTP.KD.ZG": ("Croissance du PIB (% annuel)", "Banque mondiale WDI", (-10, 15)),
    "GGXWDG_NGDP": ("Dette brute des administrations publiques (% du PIB)",
                    "FMI World Economic Outlook", (0, 150)),
}
ANNEE_EN_COURS = datetime.now().year


def dernier_bronze(prefixe: str, script: str) -> Path:
    fichiers = sorted(BRONZE.glob(f"{prefixe}_*.csv"))
    if not fichiers:
        raise SystemExit(f"[X] Aucun fichier {prefixe}_*.csv dans data/bronze : "
                         f"lancer d'abord src/ingestion/{script}")
    return fichiers[-1]


def main():
    lignes_rapport = []

    def log(texte=""):
        print(texte)
        lignes_rapport.append(texte)

    # ---- 1. lecture ----
    f_wb = dernier_bronze("wb_api", "ingest_wb_api_bronze.py")
    f_fmi = dernier_bronze("imf_debt", "ingest_imf_debt_bronze.py")
    wb = pd.read_csv(f_wb, dtype=str, encoding="utf-8")
    fmi = pd.read_csv(f_fmi, dtype=str, encoding="utf-8")
    log(f"Bronze lu : {f_wb}  ({len(wb)} lignes)")
    log(f"Bronze lu : {f_fmi}  ({len(fmi)} lignes)")
    journal = [("Bronze Banque mondiale", len(wb)), ("Bronze FMI", len(fmi))]

    # ---- 3. dette : GC.DOD.TOTL.GD.ZS écarté, remplacé par le FMI ----
    gc_dod = wb["indicator_id"] == "GC.DOD.TOTL.GD.ZS"
    log(f"\nGC.DOD.TOTL.GD.ZS écarté (couverture insuffisante) : {gc_dod.sum()} lignes, "
        f"dont {wb.loc[gc_dod, 'value'].isna().sum()} vides")
    wb = wb[~gc_dod]

    noms = wb.drop_duplicates("countryiso3code").set_index("countryiso3code")["country_name"]
    fmi = fmi.rename(columns={"country_iso3": "countryiso3code", "year": "date"})
    fmi["country_name"] = fmi["countryiso3code"].map(noms)

    # ---- 4. prévisions FMI écartées ----
    annee = pd.to_numeric(fmi["date"], errors="coerce")
    previsions = annee >= ANNEE_EN_COURS
    log(f"Prévisions FMI écartées (années >= {ANNEE_EN_COURS}) : {previsions.sum()} lignes")
    # même fenêtre que la Banque mondiale (2000 -> dernière année observée)
    avant_2000 = annee < 2000
    log(f"Années FMI avant 2000 écartées (fenêtre commune avec la Banque mondiale) : "
        f"{avant_2000.sum()} lignes")
    fmi = fmi[~previsions & ~avant_2000]

    colonnes = ["indicator_id", "countryiso3code", "country_name", "date", "value"]
    df = pd.concat([wb[colonnes], fmi[colonnes]], ignore_index=True)

    # ---- 2. périmètre ----
    df = df[df["countryiso3code"].isin(PERIMETRE) & df["indicator_id"].isin(INDICATEURS)].copy()
    journal.append(("Périmètre, 3 indicateurs, sans prévisions", len(df)))

    # ---- 5. typage ----
    df["date"] = pd.to_numeric(df["date"], errors="coerce").astype("Int64")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    # ---- 6. valeurs vides : supprimées sans imputation ----
    vides = df["value"].isna()
    log("\nValeurs vides par indicateur (supprimées, sans imputation) :")
    for ind in INDICATEURS:
        log(f"  {ind:<20} {(vides & (df['indicator_id'] == ind)).sum():>4}")
    df = df[~vides].copy()
    journal.append(("Après suppression des valeurs vides", len(df)))

    # ---- 7. enrichissement ----
    df["iso2"] = df["countryiso3code"].map(PERIMETRE)
    df["indicateur"] = df["indicator_id"].map(lambda i: INDICATEURS[i][0])
    df["source"] = df["indicator_id"].map(lambda i: INDICATEURS[i][1])
    bas = df["indicator_id"].map(lambda i: INDICATEURS[i][2][0])
    haut = df["indicator_id"].map(lambda i: INDICATEURS[i][2][1])
    df["valeur_extreme"] = (df["value"] < bas) | (df["value"] > haut)

    silver = (df[["indicator_id", "indicateur", "source", "countryiso3code", "iso2",
                  "country_name", "date", "value", "valeur_extreme"]]
              .sort_values(["indicator_id", "countryiso3code", "date"])
              .reset_index(drop=True))

    # ---- 8. contrôles ----
    erreurs = []
    if silver.duplicated(["indicator_id", "countryiso3code", "date"]).any():
        erreurs.append("doublons (indicateur, pays, année)")
    if set(silver["indicator_id"]) != set(INDICATEURS):
        erreurs.append(f"indicateurs manquants : {set(INDICATEURS) - set(silver['indicator_id'])}")
    if silver["date"].isna().any():
        erreurs.append("années non reconnues")
    if silver["country_name"].isna().any():
        erreurs.append("pays sans nom")
    if erreurs:
        raise SystemExit("[X] Contrôles en échec : " + " ; ".join(erreurs))

    # couverture
    couverture = (silver.groupby(["countryiso3code", "indicator_id"])["date"]
                  .agg(["max", "count"]).unstack("indicator_id"))
    log("\nDernière année disponible (nombre d'années entre parenthèses) :")
    log(f"  {'pays':<5} " + " ".join(f"{i:>20}" for i in INDICATEURS))
    for pays in sorted(PERIMETRE):
        cellules = []
        for ind in INDICATEURS:
            if pays in couverture.index and pd.notna(couverture.loc[pays, ("max", ind)]):
                cellules.append(f"{int(couverture.loc[pays, ('max', ind)])} "
                                f"({int(couverture.loc[pays, ('count', ind)])})")
            else:
                cellules.append("ABSENT")
        log(f"  {pays:<5} " + " ".join(f"{c:>20}" for c in cellules))

    extremes = silver[silver["valeur_extreme"]]
    log(f"\nValeurs extrêmes conservées : {len(extremes)}")
    if len(extremes):
        log(extremes[["indicator_id", "countryiso3code", "date", "value"]]
            .head(40).to_string(index=False))

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
