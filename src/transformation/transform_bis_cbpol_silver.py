"""
Source 4 - BIS Central bank policy rates (WS_CBPOL)
Transformation bronze -> silver, selon le dictionnaire de données.

Entrée  : data/bronze/bis_S4/Central bank policy rates.csv
Sorties : data/silver/bis/bis_cbpol.csv          (mensuel : 1 ligne = 1 pays x 1 mois)
          data/silver/bis/bis_cbpol_daily.csv    (journalier : 1 ligne = 1 pays x 1 jour)
          data/silver/bis/dim_serie_cbpol.csv    (1 ligne = 1 série pays x fréquence)

Lancer depuis la racine du dépôt :
    python src/transformation/transform_bis_cbpol_silver.py
"""
import pandas as pd

from bis_commun import (PERIMETRE_ISO2, ZONE_EURO, ecrire_silver,
                        lire_csv_bis, separer_code_libelle)

FICHIER = "Central bank policy rates.csv"

# Colonnes gardées. Supprimées (dictionnaire) :
#   STRUCTURE, STRUCTURE_ID, ACTION, UNIT_MEASURE, UNIT_MULT, DECIMALS, OBS_CONF -> une seule valeur
#   TIME_FORMAT, OBS_PRE_BREAK -> 100 % vides
#   OBS_STATUS -> redondant, remplacé par is_imputed
#   COMPILATION, SOURCE_REF, SUPP_INFO_BREAKS, TITLE -> déplacées dans dim_serie
COLONNES_GARDEES = ["freq", "ref_area", "time_period", "obs_value",
                    "compilation", "source_ref", "supp_info_breaks", "title"]

DEBUT_PERIODE_COMMUNE = "2003-01"
FIN_PERIODE_COMMUNE = "2026-08"


def completer_et_imputer(df: pd.DataFrame, pas: str) -> pd.DataFrame:
    """
    Pour chaque pays :
      1. supprime les nulls en début et en fin de série ;
      2. reconstruit le calendrier complet (jours ou mois sans publication) ;
      3. remplit les trous par forward-fill : un taux directeur reste en vigueur
         jusqu'à la décision suivante ; is_imputed = True sur ces lignes.
    pas = "D" (journalier) ou "MS" (mensuel, 1er du mois)
    """
    morceaux = []
    for pays, serie in df.groupby("ref_area"):
        serie = serie.set_index("date").sort_index()
        valides = serie["taux_directeur_pct"].dropna()
        if valides.empty:
            continue
        # 1. nulls de début et de fin
        serie = serie.loc[valides.index.min():valides.index.max()]
        # 2. calendrier complet
        calendrier = pd.date_range(serie.index.min(), serie.index.max(), freq=pas)
        serie = serie.reindex(calendrier)
        serie.index.name = "date"
        # 3. forward-fill tracé
        serie["is_imputed"] = serie["taux_directeur_pct"].isna()
        serie["taux_directeur_pct"] = serie["taux_directeur_pct"].ffill()
        serie["ref_area"] = pays
        morceaux.append(serie.reset_index())
    return pd.concat(morceaux, ignore_index=True)


def main():
    df = lire_csv_bis(FICHIER, COLONNES_GARDEES)
    print(f"Bronze lu : {len(df)} lignes")

    # ---- REF_AREA : code ISO seul + filtre périmètre ----
    df["ref_area"], df["nom_pays"] = separer_code_libelle(df["ref_area"])
    df = df[df["ref_area"].isin(PERIMETRE_ISO2 | {ZONE_EURO})].copy()
    print(f"Périmètre : {len(df)} lignes, {df['ref_area'].nunique()} zones")
    print(f"Pays du périmètre absents du fichier : {sorted(PERIMETRE_ISO2 - set(df['ref_area']))}")

    # ---- FREQ : code seul ----
    df["freq"], _ = separer_code_libelle(df["freq"])
    print(f"Répartition des fréquences : {df['freq'].value_counts().to_dict()}")

    # ---- OBS_VALUE -> taux_directeur_pct (% annuel), décimal ----
    df["taux_directeur_pct"] = pd.to_numeric(df["obs_value"], errors="coerce")
    print(f"Valeurs nulles avant traitement : {df['taux_directeur_pct'].isna().mean():.2%}")

    # ---- dim_serie : métadonnées constantes par série ----
    dim = (
        df.groupby(["ref_area", "freq"])
        .agg(nom_pays=("nom_pays", "first"), titre=("title", "first"),
             compilation=("compilation", "first"), source_ref=("source_ref", "first"),
             supp_info_breaks=("supp_info_breaks", "first"))
        .reset_index()
    )
    dim["source"] = "BIS:WS_CBPOL(1.0) - Central bank policy rates"
    dim["unite"] = "% par an"

    # ---- FREQ : deux tables séparées (on ne mélange jamais les grains) ----
    resultats = {}
    for freq, pas, format_date, nom in [("M", "MS", "%Y-%m", "bis_cbpol"),
                                        ("D", "D", "%Y-%m-%d", "bis_cbpol_daily")]:
        sous = df[df["freq"] == freq].copy()
        sous["date"] = pd.to_datetime(sous["time_period"], format=format_date, errors="coerce")
        print(f"\n[{nom}] {len(sous)} lignes, dates non reconnues : {sous['date'].isna().sum()}")
        sous = sous.dropna(subset=["date"])

        doublons = sous.duplicated(["ref_area", "date"]).sum()
        if doublons:
            raise ValueError(f"{doublons} doublons (pays, date) dans {nom}")

        sous = completer_et_imputer(sous[["ref_area", "date", "taux_directeur_pct"]], pas)
        sous["time_period"] = sous["date"].dt.strftime(format_date)
        sous["periode_commune"] = sous["date"].dt.strftime("%Y-%m").between(
            DEBUT_PERIODE_COMMUNE, FIN_PERIODE_COMMUNE)
        sous = sous[["ref_area", "time_period", "date", "taux_directeur_pct",
                     "is_imputed", "periode_commune"]].sort_values(["ref_area", "date"])

        print(f"[{nom}] après calendrier complet + forward-fill : {len(sous)} lignes, "
              f"dont {sous['is_imputed'].sum()} imputées ({sous['is_imputed'].mean():.2%})")
        resultats[nom] = sous

    # dates de couverture dans la dimension
    for freq, nom in [("M", "bis_cbpol"), ("D", "bis_cbpol_daily")]:
        bornes = resultats[nom].groupby("ref_area")["date"].agg(date_debut="min", date_fin="max")
        masque = dim["freq"] == freq
        dim.loc[masque, "date_debut"] = dim.loc[masque, "ref_area"].map(bornes["date_debut"])
        dim.loc[masque, "date_fin"] = dim.loc[masque, "ref_area"].map(bornes["date_fin"])

    print()
    for nom, table in resultats.items():
        ecrire_silver(table, f"{nom}.csv")
    ecrire_silver(dim, "dim_serie_cbpol.csv")

    print("\nCouverture des séries mensuelles :")
    print(dim[dim["freq"] == "M"][["ref_area", "date_debut", "date_fin"]].to_string(index=False))


if __name__ == "__main__":
    main()
