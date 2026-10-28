"""
Source 4 - BIS Bilateral exchange rates (WS_XRU) : taux de change contre l'USD
Transformation bronze -> silver, selon le dictionnaire de données.

Entrée  : data/bronze/bis_S4/Bilateral exchange rates.csv
Sorties : data/silver/bis/bis_xru.csv          (mensuel : 1 ligne = 1 pays x 1 mois)
          data/silver/bis/bis_xru_daily.csv    (journalier : 1 ligne = 1 pays x 1 jour)
          data/silver/bis/dim_serie_xru.csv    (1 ligne = 1 pays)

Lancer depuis la racine du dépôt :
    python src/transformation/transform_bis_xru_silver.py
"""
import pandas as pd

from bis_commun import (DOSSIER_BRONZE_BIS, PERIMETRE_ISO2, ZONE_EURO,
                        ecrire_silver, separer_code_libelle)

FICHIER = "Bilateral exchange rates.csv"

# Colonnes gardées. Supprimées (dictionnaire) :
#   STRUCTURE, STRUCTURE_ID, ACTION, UNIT_MULT, AVAILABILITY, OBS_CONF -> une seule valeur
#   OBS_PRE_BREAK -> vide sur le périmètre ; OBS_STATUS -> redondant (M <=> valeur nulle)
#   TITLE, DECIMALS -> déplacées dans dim_serie
COLONNES_GARDEES = ["freq", "ref_area", "currency", "collection",
                    "time_period", "obs_value", "title", "decimals"]

DEBUT_PERIODE_COMMUNE = "2003-01"   # période commune avec CBPOL et CPI
FIN_PERIODE_COMMUNE = "2026-08"

# Date d'adoption de l'euro (pays du périmètre)
ADOPTION_EURO = {
    "AT": "1999-01-01", "BE": "1999-01-01", "DE": "1999-01-01", "ES": "1999-01-01",
    "FR": "1999-01-01", "IT": "1999-01-01", "NL": "1999-01-01", "PT": "1999-01-01",
    "EE": "2011-01-01", "LV": "2014-01-01", "LT": "2015-01-01", "HR": "2023-01-01",
    "BG": "2026-01-01", "XM": "1999-01-01",
}

# Début des données fiables (avant : lev bulgare non convertible, valeurs nulles)
DATE_DEBUT_FIABLE = {"BG": "1991-01-01"}

# Point suspect signalé dans le dictionnaire (conservé, mais marqué)
POINTS_SUSPECTS = {("GB", "1857-11")}


def lire_xru() -> pd.DataFrame:
    """Lecture par morceaux de 200 000 lignes, en ne gardant que le périmètre."""
    def nom_court(c):
        return c.split(":")[0].strip().lower()

    morceaux, total = [], 0
    lecteur = pd.read_csv(DOSSIER_BRONZE_BIS / FICHIER, dtype=str, encoding="utf-8",
                          usecols=lambda c: nom_court(c) in COLONNES_GARDEES,
                          chunksize=200_000)
    for morceau in lecteur:
        total += len(morceau)
        morceau.columns = [nom_court(c) for c in morceau.columns]
        morceau["ref_area"], morceau["nom_pays"] = separer_code_libelle(morceau["ref_area"])
        morceaux.append(morceau[morceau["ref_area"].isin(PERIMETRE_ISO2 | {ZONE_EURO})])
    print(f"Bronze lu : {total} lignes")
    return pd.concat(morceaux, ignore_index=True)[COLONNES_GARDEES + ["nom_pays"]]


def ajouter_colonnes_euro(df: pd.DataFrame) -> pd.DataFrame:
    adoption = pd.to_datetime(df["ref_area"].map(ADOPTION_EURO))
    df["zone_euro"] = adoption.notna()                 # pays (aujourd'hui) en zone euro
    df["date_adoption_euro"] = adoption
    df["en_euro_a_cette_date"] = df["date"] >= adoption   # False si hors zone euro
    return df


def main():
    df = lire_xru()
    print(f"Périmètre : {len(df)} lignes, {df['ref_area'].nunique()} zones")
    print(f"Pays du périmètre absents du fichier : {sorted(PERIMETRE_ISO2 - set(df['ref_area']))}")

    # ---- FREQ / CURRENCY / COLLECTION : codes seuls ----
    for col in ("freq", "currency", "collection"):
        df[col], _ = separer_code_libelle(df[col])
    print(f"Fréquences : {df['freq'].value_counts().to_dict()}")
    print(f"Collections : {df['collection'].value_counts().to_dict()}")

    # ---- OBS_VALUE -> taux_change_lcu_usd (unités de devise locale pour 1 USD) ----
    df["obs_value"] = pd.to_numeric(df["obs_value"], errors="coerce")
    nulls = df["obs_value"].isna()
    print(f"Valeurs nulles : {nulls.sum()} ({nulls.mean():.2%}), "
          f"pays concernés : {sorted(df.loc[nulls, 'ref_area'].unique())}")
    # pas d'imputation : les lignes nulles ne portent aucune information
    df = df[~nulls]

    # ---- dim_serie : métadonnées par pays ----
    dim = (
        df.groupby("ref_area")
        .agg(nom_pays=("nom_pays", "first"), devise=("currency", "first"),
             titres=("title", lambda s: " | ".join(sorted(s.dropna().unique())[:4])),
             decimales_affichage=("decimals", "first"))
        .reset_index()
    )
    dim["source"] = "BIS:WS_XRU(1.0) - US dollar exchange rates"
    dim["sens_du_taux"] = "unités de devise locale pour 1 USD (inverse de la convention BCE)"
    dim["note"] = ("Zone euro : historique avant adoption converti rétroactivement "
                   "en équivalent euro (taux de conversion irrévocables)")
    dim["date_debut_fiable"] = pd.to_datetime(dim["ref_area"].map(DATE_DEBUT_FIABLE))

    resultats = {}

    # ---- MENSUEL : grain de référence ; A (moyenne) et E (fin de période) en 2 colonnes ----
    m = df[df["freq"] == "M"].copy()
    m["date"] = pd.to_datetime(m["time_period"], format="%Y-%m", errors="coerce")
    print(f"\n[bis_xru] {len(m)} lignes, dates non reconnues : {m['date'].isna().sum()}")
    m = m.dropna(subset=["date"])
    doublons = m.duplicated(["ref_area", "date", "collection"]).sum()
    if doublons:
        raise ValueError(f"{doublons} doublons (pays, mois, collection) dans le mensuel")
    m = (
        m.pivot(index=["ref_area", "currency", "date"], columns="collection", values="obs_value")
        .rename(columns={"A": "taux_change_lcu_usd", "E": "taux_change_lcu_usd_fin_periode"})
        .reset_index()
    )
    m.columns.name = None
    m["time_period"] = m["date"].dt.strftime("%Y-%m")
    resultats["bis_xru"] = m

    # ---- JOURNALIER : analyse fine ; seulement la moyenne (A) existe ----
    d = df[df["freq"] == "D"].copy()
    d["date"] = pd.to_datetime(d["time_period"], format="%Y-%m-%d", errors="coerce")
    print(f"[bis_xru_daily] {len(d)} lignes, dates non reconnues : {d['date'].isna().sum()}")
    d = d.dropna(subset=["date"])
    doublons = d.duplicated(["ref_area", "date"]).sum()
    if doublons:
        raise ValueError(f"{doublons} doublons (pays, jour) dans le journalier")
    d = d.rename(columns={"obs_value": "taux_change_lcu_usd"})
    d = d[["ref_area", "currency", "date", "taux_change_lcu_usd"]].copy()
    d["time_period"] = d["date"].dt.strftime("%Y-%m-%d")
    resultats["bis_xru_daily"] = d

    # Annuel (A) et trimestriel (Q) écartés : ils se déduisent du mensuel
    print(f"Lignes annuelles/trimestrielles écartées : {(~df['freq'].isin(['M', 'D'])).sum()}")

    # ---- Colonnes communes ----
    for nom, t in resultats.items():
        t = ajouter_colonnes_euro(t)
        debut_fiable = pd.to_datetime(t["ref_area"].map(DATE_DEBUT_FIABLE))
        t["fiable"] = debut_fiable.isna() | (t["date"] >= debut_fiable)
        t["point_suspect"] = [(a, p[:7]) in POINTS_SUSPECTS
                              for a, p in zip(t["ref_area"], t["time_period"])]
        t["periode_commune"] = t["date"].dt.strftime("%Y-%m").between(
            DEBUT_PERIODE_COMMUNE, FIN_PERIODE_COMMUNE)
        colonnes_taux = [c for c in t.columns if c.startswith("taux_change")]
        t = t[["ref_area", "currency", "time_period", "date", *colonnes_taux,
               "zone_euro", "date_adoption_euro", "en_euro_a_cette_date",
               "fiable", "point_suspect", "periode_commune"]]
        resultats[nom] = t.sort_values(["ref_area", "date"]).reset_index(drop=True)

    # ---- Contrôle : redondance des pays de la zone euro avec XM ----
    m = resultats["bis_xru"]
    xm = m[m["ref_area"] == "XM"].set_index("date")["taux_change_lcu_usd"]
    apres = m[m["en_euro_a_cette_date"] & (m["ref_area"] != "XM")]
    ecart = (apres["taux_change_lcu_usd"] - apres["date"].map(xm)).abs()
    print(f"Contrôle zone euro : {len(apres)} mois après adoption, "
          f"écart max avec XM = {ecart.max():.6f} (attendu ≈ 0 : séries identiques)")

    # couverture dans la dimension
    bornes = m.groupby("ref_area")["date"].agg(debut_mensuel="min", fin_mensuel="max")
    dim = dim.join(bornes, on="ref_area")

    print()
    for nom, table in resultats.items():
        ecrire_silver(table, f"{nom}.csv")
    ecrire_silver(dim, "dim_serie_xru.csv")

    print("\nCouverture des séries mensuelles :")
    print(dim[["ref_area", "devise", "debut_mensuel", "fin_mensuel"]].to_string(index=False))


if __name__ == "__main__":
    main()
