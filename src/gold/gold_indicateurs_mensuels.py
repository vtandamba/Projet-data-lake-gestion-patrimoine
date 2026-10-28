"""
Gold 6/9 - indicateurs_mensuels : inflation et politique monétaire, par pays et par mois
=======================================================================================
Une ligne par pays (23) et par mois, de 2003-01 au dernier mois disponible.
  inflation_ga_pct / cpi_indice_2010   BIS (prix à la consommation) ; Ukraine absente
  taux_directeur_pct                   taux applicable : BCE pour un pays de la zone euro à
                                       cette date, sinon banque centrale nationale
  taux_bce_pct, ecart_vs_bce_pts       écart avec la BCE (0 en zone euro)
  source_taux_directeur                BCE (zone euro) / banque centrale nationale / absent
Questions 2.4, 2.12, 2.13, 2.19.

Entrées : data/gold/dim_pays.csv, data/silver/bis/bis_cpi.csv, data/silver/bis/bis_cbpol.csv
Sortie  : data/gold/indicateurs_mensuels.csv

Lancer depuis la racine du dépôt :
    python src/gold/gold_indicateurs_mensuels.py
"""
from gold_commun import (Rapport, ecrire_gold, lire_dim_pays, lire_silver,
                         taux_directeur_applicable_mensuel)


def main():
    r = Rapport("indicateurs_mensuels")
    dim = lire_dim_pays()
    grille = taux_directeur_applicable_mensuel(dim)
    cpi = lire_silver("bis/bis_cpi.csv", usecols=["iso3", "date", "cpi_indice_2010", "inflation_ga_pct"],
                      parse_dates=["date"])
    df = grille.merge(cpi, on=["iso3", "date"], how="left")
    df["ecart_vs_bce_pts"] = (df["taux_directeur_pct"] - df["taux_bce_pct"]).round(4)
    df["zone_euro_a_cette_date"] = df["source_taux_directeur"].eq("BCE (zone euro)")
    df["mois"] = df["date"].dt.strftime("%Y-%m")
    df = df[["iso3", "mois", "inflation_ga_pct", "cpi_indice_2010", "taux_directeur_pct", "taux_bce_pct",
             "ecart_vs_bce_pts", "source_taux_directeur", "zone_euro_a_cette_date"]]
    # on s'arrête au dernier mois où au moins une des deux mesures existe
    remplis = df.dropna(subset=["inflation_ga_pct", "taux_directeur_pct"], how="all")
    df = df[df["mois"] <= remplis["mois"].max()].sort_values(["iso3", "mois"]).reset_index(drop=True)

    der = df[df["mois"] == df.loc[df["taux_directeur_pct"].notna(), "mois"].max()]
    r.log(f"{len(df)} lignes : {df['iso3'].nunique()} pays x {df['mois'].nunique()} mois "
          f"({df['mois'].min()} -> {df['mois'].max()})")
    r.log(f"\nTaux directeurs au {der['mois'].iloc[0]} :")
    r.log(der[["iso3", "taux_directeur_pct", "ecart_vs_bce_pts", "source_taux_directeur"]]
          .sort_values("taux_directeur_pct", ascending=False).to_string(index=False))
    sans_inflation = sorted(set(df["iso3"]) - set(df.loc[df["inflation_ga_pct"].notna(), "iso3"]))
    r.log(f"\nPays sans inflation mensuelle BIS : {sans_inflation} (inflation annuelle : table annuelle)")
    ecrire_gold(df, "indicateurs_mensuels", r)


if __name__ == "__main__":
    main()
