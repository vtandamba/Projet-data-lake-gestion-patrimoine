"""
Source 4 - BIS Consumer prices (WS_LONG_CPI)
Transformation bronze -> silver, selon le dictionnaire de données.

Entrée  : data/bronze/bis_S4/Consumer prices.csv
Sorties : data/silver/bis/bis_cpi.csv        (table de faits, 1 ligne = 1 pays x 1 mois)
          data/silver/bis/dim_serie_cpi.csv  (1 ligne = 1 pays)

Lancer depuis la racine du dépôt :
    python src/transformation/transform_bis_cpi_silver.py
"""
import pandas as pd

from bis_commun import (PERIMETRE_ISO2, ZONE_EURO, ecrire_silver,
                        lire_csv_bis, separer_code_libelle)

FICHIER = "Consumer prices.csv"

# Seules colonnes utiles. Toutes les autres sont supprimées (dictionnaire) :
#   STRUCTURE, STRUCTURE_ID, ACTION, UNIT_MULT, OBS_CONF -> une seule valeur
#   TIME_FORMAT, BREAKS, COVERAGE, DECIMALS, TITLE_TS, OBS_PRE_BREAK -> 100 % vides
#   OBS_STATUS -> redondant (M <=> OBS_VALUE null)
COLONNES_GARDEES = ["freq", "ref_area", "unit_measure", "time_period", "obs_value"]

# Fenêtre commune avec CBPOL et XRU (dictionnaire)
DEBUT_PERIODE_COMMUNE = "2003-01"
FIN_PERIODE_COMMUNE = "2026-07"   # HR et NL s'arrêtent en 2026-07


def type_de_mesure(unite: pd.Series) -> pd.Series:
    """Classe UNIT_MEASURE en 'indice' (2010 = 100) ou 'variation' (sur un an, %)."""
    u = unite.str.lower()
    est_indice = u.str.contains("index", na=False)
    est_variation = u.str.contains("year", na=False) | u.str.contains("change", na=False)
    mesure = pd.Series(pd.NA, index=unite.index, dtype="object")
    mesure[est_indice] = "indice"
    mesure[est_variation] = "variation"   # prioritaire si les deux mots apparaissent
    return mesure


def main():
    df = lire_csv_bis(FICHIER, COLONNES_GARDEES)
    print(f"Bronze lu : {len(df)} lignes")

    # ---- FREQ : on garde le mensuel (l'annuel se déduit du mensuel) ----
    df["freq"], _ = separer_code_libelle(df["freq"])
    df = df[df["freq"] == "M"]
    print(f"Mensuel seulement : {len(df)} lignes")

    # ---- REF_AREA : code ISO seul, filtre 22 pays + XM ----
    df["ref_area"], df["nom_pays"] = separer_code_libelle(df["ref_area"])
    df = df[df["ref_area"].isin(PERIMETRE_ISO2 | {ZONE_EURO})].copy()
    print(f"Périmètre : {len(df)} lignes, {df['ref_area'].nunique()} zones")
    absents = sorted(PERIMETRE_ISO2 - set(df["ref_area"]))
    print(f"Pays du périmètre absents du fichier : {absents}  (attendu : ['UA'])")

    # ---- UNIT_MEASURE : indice ou variation ----
    df["mesure"] = type_de_mesure(df["unit_measure"])
    inconnues = df.loc[df["mesure"].isna(), "unit_measure"].unique()
    if len(inconnues):
        raise ValueError(f"Unités non reconnues : {inconnues}")

    # ---- TIME_PERIOD : texte 'AAAA-MM' -> vraie date (1er du mois) ----
    df["date"] = pd.to_datetime(df["time_period"], format="%Y-%m", errors="coerce")
    print(f"Dates non reconnues : {df['date'].isna().sum()}")

    # ---- OBS_VALUE : décimal, pas d'imputation, valeurs extrêmes conservées ----
    df["obs_value"] = pd.to_numeric(df["obs_value"], errors="coerce")

    # ---- Doublon de grain caché : pivot -> 2 colonnes au lieu de 2 lignes ----
    doublons = df.duplicated(["ref_area", "date", "mesure"]).sum()
    if doublons:
        raise ValueError(f"{doublons} doublons (pays, mois, mesure) : vérifier le fichier")

    cpi = (
        df.pivot(index=["ref_area", "date"], columns="mesure", values="obs_value")
        .rename(columns={"indice": "cpi_indice_2010", "variation": "inflation_ga_pct"})
        .reset_index()
    )
    cpi.columns.name = None

    # Lignes où les deux mesures sont nulles (BE 1940-46, SE 1918-54...) : aucune info
    vides = cpi["cpi_indice_2010"].isna() & cpi["inflation_ga_pct"].isna()
    cpi = cpi[~vides]
    print(f"Lignes sans aucune valeur supprimées : {vides.sum()}")

    # ---- Colonnes pratiques ----
    cpi["time_period"] = cpi["date"].dt.strftime("%Y-%m")   # format utilisé par le SQL
    cpi["periode_commune"] = cpi["time_period"].between(DEBUT_PERIODE_COMMUNE, FIN_PERIODE_COMMUNE)

    # ---- Contrôle qualité : la variation doit se déduire de l'indice ----
    # Décalage de 12 mois PAR DATE (jamais par position de ligne)
    il_y_a_un_an = cpi[["ref_area", "date", "cpi_indice_2010"]].copy()
    il_y_a_un_an["date"] = il_y_a_un_an["date"] + pd.DateOffset(years=1)
    controle = cpi.merge(il_y_a_un_an, on=["ref_area", "date"], suffixes=("", "_n_1"))
    recalcul = (controle["cpi_indice_2010"] / controle["cpi_indice_2010_n_1"] - 1) * 100
    ecart_max = (recalcul - controle["inflation_ga_pct"]).abs().max()
    print(f"Contrôle indice/variation : écart max = {ecart_max:.4f} point (attendu ≈ 0,011)")

    cpi = cpi[["ref_area", "time_period", "date", "cpi_indice_2010",
               "inflation_ga_pct", "periode_commune"]].sort_values(["ref_area", "date"])

    # ---- dim_serie : une ligne par pays (remplace TITLE_TS, vide) ----
    dim = (
        df.groupby("ref_area")
        .agg(nom_pays=("nom_pays", "first"),
             unites=("unit_measure", lambda s: " | ".join(sorted(s.unique()))))
        .join(cpi.groupby("ref_area")["date"].agg(date_debut="min", date_fin="max"))
        .reset_index()
    )
    dim["source"] = "BIS:WS_LONG_CPI(1.0) - Consumer prices"
    dim["base_indice"] = "2010 = 100"

    ecrire_silver(cpi, "bis_cpi.csv")
    ecrire_silver(dim, "dim_serie_cpi.csv")
    print("\nFin de série par pays :")
    print(dim[["ref_area", "date_debut", "date_fin"]].to_string(index=False))


if __name__ == "__main__":
    main()
