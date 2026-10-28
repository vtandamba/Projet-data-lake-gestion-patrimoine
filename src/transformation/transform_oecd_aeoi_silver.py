"""
Transformation — Relations d'échange automatique d'informations (OCDE)
======================================================================
Zone SILVER : nettoyage du fichier Bronze et restriction aux 23 pays du périmètre.

Entrée  : data/bronze/oecd_aeoi_relations_AAAAMMJJ.csv (le plus récent)
Sortie  : data/silver/oecd_aeoi_relations.csv — une ligne par relation d'échange
          active (pays émetteur, pays destinataire, accord), les deux pays étant
          du périmètre

Étapes :
  1. Lecture du Bronze (tout en texte).
  2. Normalisation des noms et conversion en ISO3 ; les variantes et fautes de
     frappe de l'OCDE sont corrigées (ex. « Siwtzerland », « Czech Republic »).
  3. Restriction au périmètre : on garde les relations dont l'émetteur ET le
     destinataire font partie des 23 pays.
  4. Suppression des doublons : une relation = un couple
     (émetteur, destinataire, accord).
  5. Contrôles : aucun doublon, aucune valeur manquante, codes ISO3 du périmètre.

Colonnes Silver :
  from_country      pays qui envoie les informations (où se trouve le compte),
                    en code ISO3 (ex. CHE)
  to_country        pays qui reçoit les informations (résidence du titulaire),
                    en code ISO3 (ex. FRA)
  legal_instrument  accord : crs_mcaa, cbc_mcaa, dpi_mcaa, carf_mcaa, gir_mcaa
                    (seul crs_mcaa concerne les comptes des particuliers)

Non repris en Silver : le texte libre « Legal instrument » (base légale et date
de prise d'effet, non utilisées par les besoins), les dates de mise à jour et
d'extraction (une ou deux valeurs pour tout le fichier). Tout reste disponible
dans le Bronze.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from referentiel_pays import PERIMETRE, noms_suspects, normaliser, vers_iso3

BRONZE = Path("data/bronze")
SILVER = Path("data/silver")
SORTIE = SILVER / "oecd_aeoi_relations.csv"
ACCORDS = ["crs_mcaa", "cbc_mcaa", "dpi_mcaa", "carf_mcaa", "gir_mcaa"]
COLONNES = ["from_country", "to_country", "legal_instrument"]


def dernier_bronze() -> Path:
    fichiers = sorted(BRONZE.glob("oecd_aeoi_relations_*.csv"))
    if not fichiers:
        raise SystemExit("[X] Aucun fichier oecd_aeoi_relations_*.csv dans data/bronze")
    return fichiers[-1]


def main():
    fichier = dernier_bronze()
    df = pd.read_csv(fichier, dtype=str, keep_default_na=False)
    print(f"Bronze lu : {fichier}  ({len(df)} lignes)")
    journal = [("Bronze", len(df))]

    # 2. Noms -> ISO3 (variantes et fautes de frappe corrigées par le référentiel)
    for cote in ("From", "To"):
        df[f"{cote} jurisdiction"] = df[f"{cote} jurisdiction"].map(normaliser)
    df["from_country"] = df["From jurisdiction"].map(vers_iso3)   # code ISO3
    df["to_country"] = df["To jurisdiction"].map(vers_iso3)       # code ISO3
    df["legal_instrument"] = df["Tableau"]
    noms = set(df["From jurisdiction"]) | set(df["To jurisdiction"])
    corriges = sorted(n for n in noms
                      if vers_iso3(n) and n != PERIMETRE[vers_iso3(n)][0])
    suspects = noms_suspects(noms)

    # 3. Périmètre : émetteur ET destinataire parmi les 23 pays
    df = df[df["from_country"].notna() & df["to_country"].notna()]
    journal.append(("Relations entre pays du périmètre", len(df)))

    # 4. Doublons
    avant = len(df)
    silver = (df[COLONNES].drop_duplicates()
              .sort_values(["legal_instrument", "from_country", "to_country"])
              .reset_index(drop=True))
    journal.append((f"Après suppression des doublons ({avant - len(silver)} supprimés)",
                    len(silver)))

    # 5. Contrôles
    erreurs = []
    if silver.duplicated().any():
        erreurs.append("doublons")
    if silver.isna().any().any() or (silver.astype(str) == "").any().any():
        erreurs.append("valeurs manquantes")
    if not set(silver["from_country"]) | set(silver["to_country"]) <= set(PERIMETRE):
        erreurs.append("pays hors périmètre")
    if not set(silver["legal_instrument"]) <= set(ACCORDS):
        erreurs.append("accord inconnu")
    if (silver["from_country"] == silver["to_country"]).any():
        erreurs.append("relation d'un pays vers lui-même")
    if erreurs:
        raise SystemExit(f"[X] Contrôles échoués : {', '.join(erreurs)}")

    SILVER.mkdir(parents=True, exist_ok=True)
    silver.to_csv(SORTIE, index=False, encoding="utf-8")

    print("\n=== Journal de transformation")
    for etape, n in journal:
        print(f"  {n:>6}  {etape}")
    print("\n=== Contrôles : aucun doublon, aucune valeur manquante, "
          "pays du périmètre uniquement  -> OK")
    if corriges:
        print(f"\nNoms corrigés vers le référentiel : {', '.join(corriges)}")
    if suspects:
        print("\n[!] Noms proches d'un pays du périmètre mais non reconnus (à vérifier) :")
        for nom, proche in suspects.items():
            print(f"    {nom!r} ressemble à {proche!r}")
    print("\n=== Relations par accord")
    print(silver["legal_instrument"].value_counts().to_string())
    n_pays = len(PERIMETRE)
    n_crs = int((silver["legal_instrument"] == "crs_mcaa").sum())
    print(f"\nCRS : {n_crs} relations sur {n_pays * (n_pays - 1)} paires possibles")
    print(f"\n[OK] Silver enregistré : {SORTIE}  ({len(silver)} lignes, "
          f"{silver.shape[1]} colonnes)")


if __name__ == "__main__":
    main()