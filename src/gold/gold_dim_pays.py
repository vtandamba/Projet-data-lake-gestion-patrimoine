"""
Gold 1/9 - dim_pays : table de référence des 23 pays du périmètre
==================================================================
Joue le rôle de la table « perimetre » des requêtes de l'Excel. Toutes les tables
gold s'y joignent par iso3.

Entrée  : data/silver/lucas/countries-silver.csv (nom, région, revenu, devise, G20/G7)
Sortie  : data/gold/dim_pays.csv - une ligne par pays (23 lignes)

Colonnes :
  iso3, iso2, nom_pays, nom_fr, devise, zone_euro, date_adoption_euro, membre_ue,
  zone_sepa, region, income_group, is_g20, is_g7, est_pays_envoi,
  groupe_cout, methode_cout, description_methode_cout

Lancer depuis la racine du dépôt :
    python src/gold/gold_dim_pays.py
"""
import pandas as pd

from gold_commun import (ADOPTION_EURO, GROUPE_PAR_PAYS, GROUPES_COUT, MEMBRES_UE, PAYS_ENVOI,
                         PERIMETRE, ZONE_SEPA, Rapport, ecrire_gold, lire_silver)


def main():
    r = Rapport("dim_pays")
    pays = lire_silver("lucas/countries-silver.csv")
    pays = pays[pays["iso3"].isin(PERIMETRE)].copy()
    r.log(f"Pays du périmètre trouvés dans countries-silver : {len(pays)} / {len(PERIMETRE)}")
    manquants = set(PERIMETRE) - set(pays["iso3"])
    if manquants:
        raise SystemExit(f"[X] Pays absents de countries-silver : {sorted(manquants)}")

    dim = pays.rename(columns={"country_name": "nom_pays", "currency_code": "devise"})
    dim["iso2"] = dim["iso3"].map(lambda c: PERIMETRE[c][0])
    dim["nom_fr"] = dim["iso3"].map(lambda c: PERIMETRE[c][1])
    dim["date_adoption_euro"] = pd.to_datetime(dim["iso3"].map(ADOPTION_EURO))
    dim["zone_euro"] = dim["date_adoption_euro"].notna()
    dim["membre_ue"] = dim["iso3"].isin(MEMBRES_UE)
    dim["zone_sepa"] = dim["iso3"].isin(ZONE_SEPA)
    dim["est_pays_envoi"] = dim["iso3"] == PAYS_ENVOI
    dim["groupe_cout"] = dim["iso3"].map(GROUPE_PAR_PAYS)            # vide pour la France
    dim["methode_cout"] = dim["groupe_cout"].map(lambda g: GROUPES_COUT[g][0] if pd.notna(g) else None)
    dim["description_methode_cout"] = dim["groupe_cout"].map(
        lambda g: GROUPES_COUT[g][1] if pd.notna(g) else "Pays d'envoi")

    # contrôle de cohérence : la devise actuelle doit être l'EUR pour la zone euro, et seulement là
    incoherents = dim[(dim["devise"] == "EUR") != dim["zone_euro"]]
    if len(incoherents):
        raise SystemExit(f"[X] Devise et zone euro incohérentes : {incoherents[['iso3', 'devise']].values.tolist()}")

    dim = dim[["iso3", "iso2", "nom_pays", "nom_fr", "devise", "zone_euro", "date_adoption_euro",
               "membre_ue", "zone_sepa", "region", "income_group", "is_g20", "is_g7",
               "est_pays_envoi", "groupe_cout", "methode_cout", "description_methode_cout"]]
    dim = dim.sort_values("nom_fr").reset_index(drop=True)
    dim["date_adoption_euro"] = dim["date_adoption_euro"].dt.strftime("%Y-%m-%d")

    r.log(f"\nZone euro : {dim['zone_euro'].sum()} pays ; UE : {dim['membre_ue'].sum()} ; "
          f"SEPA : {dim['zone_sepa'].sum()}")
    r.log("\nDestinations par groupe d'estimation du coût :")
    for g, (methode, _) in GROUPES_COUT.items():
        noms = dim.loc[dim["groupe_cout"] == g, "nom_fr"].tolist()
        r.log(f"  {g} ({methode}, {len(noms)}) : {', '.join(noms)}")
    ecrire_gold(dim, "dim_pays", r)


if __name__ == "__main__":
    main()
