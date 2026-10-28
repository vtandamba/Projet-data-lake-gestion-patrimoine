"""
Gold 8/9 - fiscalite_conformite : fiscalité future et conformité, par destination
=================================================================================
Une ligne par destination (22). Règle de conformité de la requête 3.4 de l'Excel :
  Exclu       liste noire du GAFI, ou annexe I de la liste UE (state_cooperation_with_eu = 0)
  À vérifier  liste grise du GAFI, ou annexe II de la liste UE (= 1), ou pays hors UE sans
              échange automatique CRS vers la France, ou score FSI >= SEUIL_FSI
  Conforme    sinon
La fiscalité (taux d'imposition des plus-values) est un indicateur DISTINCT du coût du
transfert : elle s'applique à la vente d'actifs par un résident du pays.
Questions 1.7, 1.8, 1.14, 2.22, 2.23, 3.4, 3.17.

Entrées : dim_pays (gold) ; silver : lucas/capital_gains_tax_europe, fatf, eu_noncoop_list,
          oecd_aeoi_relations, fsi_2026
Sortie  : data/gold/fiscalite_conformite.csv

Lancer depuis la racine du dépôt :
    python src/gold/gold_fiscalite_conformite.py
"""
import pandas as pd

from gold_commun import PAYS_ENVOI, Rapport, ecrire_gold, lire_dim_pays, lire_silver

SEUIL_FSI = 60   # paramètre :seuil_fsi de l'Excel (opacité financière élevée)
LIBELLES_UE = {0: "annexe I (non coopératif)", 1: "annexe II (engagements en cours)",
               2: "coopératif", 3: "non évalué"}


def main():
    r = Rapport("fiscalite_conformite")
    dim = lire_dim_pays()
    df = dim.loc[dim["iso3"] != PAYS_ENVOI, ["iso3", "nom_fr", "membre_ue", "zone_euro"]].copy()

    cgt = lire_silver("lucas/capital_gains_tax_europe-silver.csv")
    cgt["taux_plus_value_pct"] = (cgt["capital_gains_tax_rate"] * 100).round(3)
    df = df.merge(cgt[["iso3", "taux_plus_value_pct", "comments"]].rename(
        columns={"comments": "commentaires_fiscalite"}), on="iso3", how="left")

    fatf = lire_silver("fatf.csv")[["iso3", "fatf_status", "plenary_date"]]
    df = df.merge(fatf.rename(columns={"plenary_date": "gafi_date_pleniere"}), on="iso3", how="left")

    ue = lire_silver("eu_noncoop_list.csv").rename(columns={"country": "iso3"})
    df = df.merge(ue[["iso3", "state_cooperation_with_eu"]], on="iso3", how="left")
    df["liste_ue"] = df["state_cooperation_with_eu"].map(LIBELLES_UE).fillna("non évalué")

    oecd = lire_silver("oecd_aeoi_relations.csv")
    vers_fr = oecd[oecd["to_country"] == PAYS_ENVOI]
    df["echange_crs_avec_france"] = df["iso3"].isin(
        vers_fr.loc[vers_fr["legal_instrument"] == "crs_mcaa", "from_country"])
    df["instruments_avec_france"] = df["iso3"].map(
        vers_fr.groupby("from_country")["legal_instrument"].agg(lambda s: ", ".join(sorted(s.unique()))))

    fsi = lire_silver("fsi_2026_silver.csv")[["iso3", "fsi_2026_score", "fsi_2026_rank"]]
    df = df.merge(fsi, on="iso3", how="left")

    # ---- règle de conformité (requête 3.4) ----
    motifs, statuts = [], []
    for _, p in df.iterrows():
        m = []
        if p["fatf_status"] == "black_list":
            m.append("liste noire GAFI")
        if p["state_cooperation_with_eu"] == 0:
            m.append("annexe I UE")
        exclu = bool(m)
        if p["fatf_status"] == "grey_list":
            m.append("liste grise GAFI")
        if p["state_cooperation_with_eu"] == 1:
            m.append("annexe II UE")
        if not p["membre_ue"] and not p["echange_crs_avec_france"]:
            m.append("pas d'échange CRS avec la France")
        if pd.notna(p["fsi_2026_score"]) and p["fsi_2026_score"] >= SEUIL_FSI:
            m.append(f"opacité financière élevée (FSI {p['fsi_2026_score']:.1f})")
        statuts.append("Exclu" if exclu else ("À vérifier" if m else "Conforme"))
        motifs.append(", ".join(m))
    df["conformite"], df["motifs"] = statuts, motifs
    df["seuil_fsi"] = SEUIL_FSI

    df = df[["iso3", "nom_fr", "membre_ue", "zone_euro", "taux_plus_value_pct", "commentaires_fiscalite",
             "fatf_status", "gafi_date_pleniere", "state_cooperation_with_eu", "liste_ue",
             "echange_crs_avec_france", "instruments_avec_france", "fsi_2026_score", "fsi_2026_rank",
             "seuil_fsi", "conformite", "motifs"]].sort_values("nom_fr").reset_index(drop=True)

    manquants = df[df["taux_plus_value_pct"].isna()]["iso3"].tolist()
    r.log(f"Destinations : {len(df)} ; sans taux de plus-value : {manquants or 'aucune'}")
    r.log("\nConformité :")
    r.log(df["conformite"].value_counts().to_string())
    r.log("\nDestinations à signaler :")
    r.log(df.loc[df["conformite"] != "Conforme", ["nom_fr", "conformite", "motifs"]].to_string(index=False))
    r.log("\nTaux d'imposition des plus-values (%) :")
    r.log(df.sort_values("taux_plus_value_pct")[["nom_fr", "taux_plus_value_pct"]].to_string(index=False))
    ecrire_gold(df, "fiscalite_conformite", r)


if __name__ == "__main__":
    main()
