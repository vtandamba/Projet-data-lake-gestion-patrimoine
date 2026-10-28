"""
Transformation - Source 9 : listes du GAFI (FATF)
=================================================
Zone SILVER : statut GAFI de chacun des 23 pays du périmètre.

Entrée  : data/bronze/fatf_lists_AAAAMMJJ.csv (le plus récent)
Sortie  : data/silver/fatf.csv              - une ligne par pays du périmètre (23 lignes)
Rapport : reports/transform_fatf.txt

Étapes :
  1. Lecture du Bronze (tout en texte).
  2. Nom GAFI -> code ISO3 (table de correspondance ci-dessous). Un nom inconnu
     arrête le script : après une plénière, un nouveau pays doit y être ajouté.
     (Excel du projet : « fatf (9) n'a que des noms de pays : ajouter une colonne
     iso3 en zone Silver pour fiabiliser les jointures ».)
  3. Une ligne par pays du périmètre : statut 'grey_list', 'black_list' ou
     'none' (pays absent des deux listes - c'est une information, pas un manquant).
  4. Contrôles : 23 lignes, pas de doublon, statuts autorisés.

Colonnes Silver :
  iso3, iso2, country_name, fatf_status, sous_surveillance_gafi, plenary_date

Lancer depuis la racine du dépôt :
    python src/transformation/transform_fatf_silver.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

BRONZE = Path("data/bronze")
SILVER = Path("data/silver")
REPORTS = Path("reports")
SORTIE = SILVER / "fatf.csv"
RAPPORT = REPORTS / "transform_fatf.txt"

PERIMETRE = {  # ISO3 -> (ISO2, nom)
    "AUT": ("AT", "Austria"), "BEL": ("BE", "Belgium"), "BGR": ("BG", "Bulgaria"),
    "HRV": ("HR", "Croatia"), "CZE": ("CZ", "Czechia"), "EST": ("EE", "Estonia"),
    "FRA": ("FR", "France"), "DEU": ("DE", "Germany"), "HUN": ("HU", "Hungary"),
    "ITA": ("IT", "Italy"), "LVA": ("LV", "Latvia"), "LTU": ("LT", "Lithuania"),
    "NLD": ("NL", "Netherlands"), "NOR": ("NO", "Norway"), "POL": ("PL", "Poland"),
    "PRT": ("PT", "Portugal"), "ROU": ("RO", "Romania"), "ESP": ("ES", "Spain"),
    "SWE": ("SE", "Sweden"), "CHE": ("CH", "Switzerland"), "TUR": ("TR", "Türkiye"),
    "UKR": ("UA", "Ukraine"), "GBR": ("GB", "United Kingdom"),
}

# Noms utilisés par le GAFI -> ISO3 (pays listés et pays du périmètre)
NOM_GAFI_VERS_ISO3 = {
    "Angola": "AGO", "Bolivia": "BOL", "Bosnia and Herzegovina": "BIH", "Bulgaria": "BGR",
    "Cameroon": "CMR", "Côte d'Ivoire": "CIV", "Democratic Republic of the Congo": "COD",
    "Haiti": "HTI", "Iraq": "IRQ", "Kenya": "KEN", "Kuwait": "KWT", "Lao PDR": "LAO",
    "Lebanon": "LBN", "Monaco": "MCO", "Nepal": "NPL", "Papua New Guinea": "PNG",
    "South Sudan": "SSD", "Syria": "SYR", "Venezuela": "VEN", "Vietnam": "VNM",
    "Virgin Islands (UK)": "VGB", "Yemen": "YEM",
    "Democratic People's Republic of Korea (DPRK)": "PRK", "Iran": "IRN", "Myanmar": "MMR",
    # pays du périmètre (au cas où ils entreraient dans une liste)
    **{nom: iso3 for iso3, (_, nom) in PERIMETRE.items()},
    "Turkey": "TUR", "Czech Republic": "CZE",
}
STATUTS = {"grey_list", "black_list", "none"}


def dernier_bronze() -> Path:
    fichiers = sorted(BRONZE.glob("fatf_lists_*.csv"))
    if not fichiers:
        raise SystemExit("[X] Aucun fichier fatf_lists_*.csv dans data/bronze : "
                         "lancer d'abord src/ingestion/ingest_fatf_bronze.py")
    return fichiers[-1]


def main():
    lignes_rapport = []

    def log(texte=""):
        print(texte)
        lignes_rapport.append(texte)

    fichier = dernier_bronze()
    df = pd.read_csv(fichier, dtype=str, encoding="utf-8")
    df["country_name"] = df["country_name"].str.strip().str.replace("’", "'", regex=False)
    log(f"Bronze lu : {fichier}  ({len(df)} lignes, plénière du {df['plenary_date'].iloc[0]})")

    # 2. noms -> ISO3
    df["iso3"] = df["country_name"].map(NOM_GAFI_VERS_ISO3)
    inconnus = df.loc[df["iso3"].isna(), "country_name"].tolist()
    if inconnus:
        raise SystemExit(f"[X] Noms GAFI sans code ISO3 : {inconnus} -> "
                         "les ajouter à NOM_GAFI_VERS_ISO3")
    statut_par_pays = df.set_index("iso3")["fatf_status"]

    # 3. une ligne par pays du périmètre
    silver = pd.DataFrame(
        [{"iso3": iso3, "iso2": iso2, "country_name": nom} for iso3, (iso2, nom) in PERIMETRE.items()]
    )
    silver["fatf_status"] = silver["iso3"].map(statut_par_pays).fillna("none")
    silver["sous_surveillance_gafi"] = silver["fatf_status"] != "none"
    silver["plenary_date"] = df["plenary_date"].iloc[0]
    silver = silver.sort_values("country_name").reset_index(drop=True)

    # 4. contrôles
    erreurs = []
    if len(silver) != len(PERIMETRE):
        erreurs.append(f"{len(silver)} lignes au lieu de {len(PERIMETRE)}")
    if silver["iso3"].duplicated().any():
        erreurs.append("doublons")
    if not set(silver["fatf_status"]) <= STATUTS:
        erreurs.append(f"statuts inattendus : {set(silver['fatf_status']) - STATUTS}")
    if erreurs:
        raise SystemExit("[X] Contrôles en échec : " + " ; ".join(erreurs))

    log(f"\nPays listés par le GAFI : {len(df)} (dont "
        f"{df['iso3'].isin(PERIMETRE).sum()} dans le périmètre)")
    log("\nStatut des 23 pays du périmètre :")
    log(silver["fatf_status"].value_counts().to_string())
    surveilles = silver[silver["sous_surveillance_gafi"]]
    log("\nPays du périmètre sous surveillance :")
    log(surveilles[["iso3", "country_name", "fatf_status"]].to_string(index=False)
        if len(surveilles) else "  aucun")

    SILVER.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    silver.to_csv(SORTIE, index=False, encoding="utf-8")
    log(f"\n[OK] Silver enregistré : {SORTIE}  ({len(silver)} lignes, {silver.shape[1]} colonnes)")
    RAPPORT.write_text("\n".join(lignes_rapport), encoding="utf-8")
    print(f"[OK] Rapport : {RAPPORT}")


if __name__ == "__main__":
    main()
