"""
Gold 7/9 - indicateurs_annuels : situation économique et institutionnelle, par pays et par année
==============================================================================================
Une ligne par pays (23) et par année (2000 -> dernière année disponible).
  inflation_pct, croissance_pib_pct            Banque mondiale (WDI)
  dette_publique_pct_pib                       FMI (WEO), administrations publiques
  wgi_va ... wgi_cc                            6 indicateurs de gouvernance (WGI, -2,5 à +2,5)
  taux_directeur_moyen_pct                     moyenne annuelle du taux applicable (BCE en zone euro)
  devise_annee                                 devise du pays cette année-là (EUR après adoption)
  variation_change_annuelle_pct                variation du taux moyen pour 1 EUR vs l'année
                                               précédente (> 0 : la devise perd de la valeur)
  volatilite_change_annuelle_pct               écart-type des rendements journaliers x racine(252)
En zone euro (après adoption) : variation et volatilité de change = 0.
Questions 2.5 à 2.7, 2.15, 2.17, 2.18, 2.20, 2.21.

Entrées : data/gold/dim_pays.csv, data/silver/wb_api.csv, data/silver/wgi.csv,
          data/silver/bis/bis_cbpol.csv, taux BCE / BIS
Sortie  : data/gold/indicateurs_annuels.csv

Lancer depuis la racine du dépôt :
    python src/gold/gold_indicateurs_annuels.py
"""
import numpy as np
import pandas as pd

from gold_commun import (DEVISE_AVANT_EURO, Rapport, ecrire_gold, lire_dim_pays, lire_silver,
                         taux_directeur_applicable_mensuel, taux_quotidiens_par_eur)

ANNEE_DEBUT = 2000
INDICATEURS_WB = {"FP.CPI.TOTL.ZG": "inflation_pct", "NY.GDP.MKTP.KD.ZG": "croissance_pib_pct",
                  "GGXWDG_NGDP": "dette_publique_pct_pib"}


def main():
    r = Rapport("indicateurs_annuels")
    dim = lire_dim_pays()

    # ---- Banque mondiale / FMI ----
    wb = lire_silver("wb_api.csv")
    wb = wb[wb["indicator_id"].isin(INDICATEURS_WB)]
    macro = (wb.pivot_table(index=["countryiso3code", "date"], columns="indicator_id", values="value")
             .rename(columns=INDICATEURS_WB).reset_index()
             .rename(columns={"countryiso3code": "iso3", "date": "annee"}))

    # ---- WGI ----
    wgi = lire_silver("wgi.csv")
    gouv = (wgi.pivot_table(index=["economy_code", "year"], columns="governance_dimension",
                            values="governance_score")
            .add_prefix("wgi_").reset_index().rename(columns={"economy_code": "iso3", "year": "annee"}))

    # ---- taux directeur moyen ----
    td = taux_directeur_applicable_mensuel(dim)
    td["annee"] = td["date"].dt.year
    td = td.groupby(["iso3", "annee"])["taux_directeur_pct"].mean().rename("taux_directeur_moyen_pct")

    # ---- change : devise de chaque pays chaque année ----
    annees = range(ANNEE_DEBUT, int(max(macro["annee"].max(), gouv["annee"].max())) + 1)
    grille = pd.MultiIndex.from_product([dim["iso3"], annees], names=["iso3", "annee"]).to_frame(index=False)
    adoption = grille["iso3"].map(dim.set_index("iso3")["date_adoption_euro"].dt.year)
    en_euro = grille["annee"] >= adoption
    devise_actuelle = grille["iso3"].map(dim.set_index("iso3")["devise"])
    avant = grille["iso3"].map(DEVISE_AVANT_EURO)
    grille["devise_annee"] = np.where(en_euro, "EUR", avant.fillna(devise_actuelle))
    grille.loc[~en_euro & devise_actuelle.eq("EUR") & avant.isna(), "devise_annee"] = None  # euro avant 2000 : n/a

    devises = sorted(set(grille["devise_annee"].dropna()) - {"EUR"})
    taux = taux_quotidiens_par_eur(devises)
    taux["annee"] = taux["date"].dt.year
    taux["rendement_log"] = np.log(taux["taux_pour_1_eur"]
                                   / taux.groupby("devise")["taux_pour_1_eur"].shift(1))
    fx = taux.groupby(["devise", "annee"]).agg(taux_moyen=("taux_pour_1_eur", "mean"),
                                                vol=("rendement_log", "std"),
                                                nb_jours=("rendement_log", "count")).reset_index()
    fx["variation_change_annuelle_pct"] = (fx["taux_moyen"]
                                           / fx.groupby("devise")["taux_moyen"].shift(1) - 1) * 100
    fx["volatilite_change_annuelle_pct"] = np.where(fx["nb_jours"] >= 150, fx["vol"] * np.sqrt(252) * 100,
                                                    np.nan)
    grille = grille.merge(fx[["devise", "annee", "variation_change_annuelle_pct",
                              "volatilite_change_annuelle_pct"]],
                          left_on=["devise_annee", "annee"], right_on=["devise", "annee"], how="left"
                          ).drop(columns="devise")
    grille.loc[grille["devise_annee"].eq("EUR"),
               ["variation_change_annuelle_pct", "volatilite_change_annuelle_pct"]] = 0.0

    df = (grille.merge(macro, on=["iso3", "annee"], how="left")
          .merge(gouv, on=["iso3", "annee"], how="left")
          .merge(td, on=["iso3", "annee"], how="left"))
    colonnes = ["iso3", "annee", "devise_annee", "inflation_pct", "croissance_pib_pct",
                "dette_publique_pct_pib", "taux_directeur_moyen_pct", "variation_change_annuelle_pct",
                "volatilite_change_annuelle_pct", "wgi_va", "wgi_pv", "wgi_ge", "wgi_rq", "wgi_rl", "wgi_cc"]
    df = df[colonnes].sort_values(["iso3", "annee"]).reset_index(drop=True)
    num = df.select_dtypes("number").columns.drop("annee")
    df[num] = df[num].round(4)

    r.log(f"{len(df)} lignes : {df['iso3'].nunique()} pays x {df['annee'].nunique()} années "
          f"({df['annee'].min()} -> {df['annee'].max()})")
    r.log("\nTaux de remplissage par colonne :")
    r.log((df[colonnes[3:]].notna().mean() * 100).round(1).to_string())
    derniere = df["annee"].max()
    r.log(f"\nAperçu {derniere - 1} (destinations hors euro) :")
    apercu = df[(df["annee"] == derniere - 1) & (df["devise_annee"] != "EUR")]
    r.log(apercu[["iso3", "inflation_pct", "croissance_pib_pct", "dette_publique_pct_pib",
                  "taux_directeur_moyen_pct", "volatilite_change_annuelle_pct", "wgi_pv"]].to_string(index=False))
    ecrire_gold(df, "indicateurs_annuels", r)


if __name__ == "__main__":
    main()
