"""
Transformation — Liste UE des juridictions non coopératives
===========================================================
Zone SILVER : nettoyage du fichier Bronze et restriction aux 23 pays du périmètre.

Entrée  : data/bronze/eu_noncoop_list_AAAAMMJJ.csv (le plus récent)
Sortie  : data/silver/eu_noncoop_list.csv  — une ligne par pays du périmètre (23 lignes)

Étapes :
  1. Lecture du Bronze (tout en texte, aucune conversion implicite).
  2. Normalisation des noms de pays et conversion en code ISO3.
  3. Encodage de la section en code numérique + libellé descriptif.
  4. Suppression des doublons (un pays = une ligne ; s'il apparaissait dans deux
     sections, on garde la plus sévère).
  5. Restriction au périmètre + ajout des pays absents de la liste
     (pays de l'UE, Royaume-Uni, Ukraine) avec le statut « non évalué ».
  6. Contrôles : aucun doublon, aucune valeur manquante, 23 pays exactement.

Colonnes Silver :
  country                    pays, en code ISO 3166-1 alpha-3 (ex. TUR) ; clé de jointure
  state_cooperation_with_eu  0 = non coopératif (annexe I)
                             1 = coopératif avec engagements en cours (annexe II)
                             2 = coopératif sans engagement en cours
                             3 = non évalué par l'UE (absent de la liste)
  classification             libellé du code : non_cooperative (0), pending_commitments (1),
                             cooperative (2), not_evaluated (3)

Non repris en Silver (une seule valeur pour tout le fichier) : la date de révision de
la liste (affichée à l'exécution) et la date d'extraction (dans le nom du fichier Bronze).
Le nom du pays et l'appartenance à l'UE sont dans la dimension pays commune.
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from referentiel_pays import PERIMETRE, noms_suspects, normaliser, vers_iso3

BRONZE = Path("data/bronze")
SILVER = Path("data/silver")
SORTIE = SILVER / "eu_noncoop_list.csv"

# Section de la page -> (code, libellé)
SECTIONS = [
    (re.compile(r"do not cooperate", re.I), 0, "non_cooperative"),
    (re.compile(r"have pending commitments", re.I), 1, "pending_commitments"),
    (re.compile(r"have no pending commitments", re.I), 2, "cooperative"),
]
NON_EVALUE = (3, "not_evaluated")
COLONNES = ["country", "state_cooperation_with_eu", "classification"]


def dernier_bronze() -> Path:
    fichiers = sorted(BRONZE.glob("eu_noncoop_list_*.csv"))
    if not fichiers:
        raise SystemExit("[X] Aucun fichier eu_noncoop_list_*.csv dans data/bronze")
    return fichiers[-1]


def coder_section(texte: str):
    for motif, code, libelle in SECTIONS:
        if motif.search(texte):
            return code, libelle
    return None, None


def main():
    fichier = dernier_bronze()
    df = pd.read_csv(fichier, dtype=str, keep_default_na=False)
    print(f"Bronze lu : {fichier}  ({len(df)} lignes)")
    print(f"Révision de la liste : {df['Revision'].iloc[0]}")
    journal = [("Bronze", len(df))]

    # 2. Noms -> ISO3
    df["Country"] = df["Country"].map(normaliser)
    df["iso3"] = df["Country"].map(vers_iso3)

    # 3. Encodage de la section
    codes = df["Section"].map(coder_section)
    df["state_cooperation_with_eu"] = codes.str[0]
    df["classification"] = codes.str[1]
    inconnues = df[df["state_cooperation_with_eu"].isna()]["Section"].unique()
    if len(inconnues):
        raise SystemExit(f"[X] Section non reconnue : {list(inconnues)}")

    # 4. Doublons : un pays = une ligne (on garde le statut le plus sévère)
    avant = len(df)
    df = df.sort_values("state_cooperation_with_eu").drop_duplicates("Country", keep="first")
    journal.append(("Après suppression des doublons", len(df)))
    if avant != len(df):
        print(f"[!] {avant - len(df)} pays en double supprimés")

    # 5. Périmètre
    suspects = noms_suspects(df["Country"])
    dans_perimetre = df[df["iso3"].notna()]
    journal.append(("Pays du périmètre présents dans la liste", len(dans_perimetre)))

    lignes = []
    for iso3 in PERIMETRE:
        ligne = dans_perimetre[dans_perimetre["iso3"] == iso3]
        code, libelle = ((int(ligne["state_cooperation_with_eu"].iloc[0]),
                          ligne["classification"].iloc[0]) if len(ligne) else NON_EVALUE)
        lignes.append({"country": iso3, "state_cooperation_with_eu": code,
                       "classification": libelle})
    silver = pd.DataFrame(lignes, columns=COLONNES).sort_values("country").reset_index(drop=True)
    journal.append(("Silver (23 pays du périmètre)", len(silver)))

    # 6. Contrôles
    erreurs = []
    if silver.duplicated("country").any():
        erreurs.append("doublons sur country")
    if silver.isna().any().any() or (silver.astype(str) == "").any().any():
        erreurs.append("valeurs manquantes")
    if len(silver) != len(PERIMETRE):
        erreurs.append(f"{len(silver)} lignes au lieu de {len(PERIMETRE)}")
    if erreurs:
        raise SystemExit(f"[X] Contrôles échoués : {', '.join(erreurs)}")

    SILVER.mkdir(parents=True, exist_ok=True)
    silver.to_csv(SORTIE, index=False, encoding="utf-8")

    print("\n=== Journal de transformation")
    for etape, n in journal:
        print(f"  {n:>4}  {etape}")
    print("\n=== Contrôles : aucun doublon, aucune valeur manquante, 23 pays  -> OK")
    if suspects:
        print("\n[!] Noms proches d'un pays du périmètre mais non reconnus (à vérifier) :")
        for nom, proche in suspects.items():
            print(f"    {nom!r} ressemble à {proche!r}")
    print("\n=== Répartition dans le périmètre")
    print(silver.groupby(["state_cooperation_with_eu", "classification"])
          .size().to_string())
    print(f"\n[OK] Silver enregistré : {SORTIE}  ({len(silver)} lignes, "
          f"{silver.shape[1]} colonnes)")


if __name__ == "__main__":
    main()