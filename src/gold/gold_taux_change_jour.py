"""
Gold 5/9 - taux_change_jour : taux de change journaliers des devises hors euro du périmètre
==========================================================================================
Unités de devise pour 1 EUR (convention BCE) pour les 10 devises des destinations hors
euro : CZK, HUF, PLN, RON, SEK, NOK, CHF, TRY, GBP (BCE) et UAH (BIS, absente de la BCE).
En zone euro il n'y a pas de change : pas de ligne.

Indicateurs calculés par devise (fenêtre glissante de 252 jours de cotation ≈ 12 mois) :
  rendement_log           ln(taux du jour / taux de la veille de cotation)
  volatilite_12m_pct      écart-type des rendements x racine(252), en %
  moyenne_12m             moyenne du taux sur 12 mois
  ecart_moyenne_12m_pct   écart du taux du jour à sa moyenne 12 mois, en %
Un taux qui monte = la devise perd de la valeur face à l'euro (le client en reçoit plus).
Questions 1.4, 2.1 à 2.3, 2.9 à 2.11, 2.16, 2.24, 3.3, 3.11.

Entrées : data/gold/dim_pays.csv, data/silver/lucas/ecb_exchange_rates-silver.csv,
          data/silver/bis/bis_xru_daily.csv
Sortie  : data/gold/taux_change_jour.csv

Lancer depuis la racine du dépôt :
    python src/gold/gold_taux_change_jour.py
"""
import numpy as np

from gold_commun import Rapport, ecrire_gold, lire_dim_pays, taux_quotidiens_par_eur

FENETRE = 252   # jours de cotation par an


def main():
    r = Rapport("taux_change_jour")
    dim = lire_dim_pays()
    hors_euro = dim[~dim["zone_euro"]]
    devises = sorted(hors_euro["devise"])
    taux = taux_quotidiens_par_eur(devises)
    absentes = set(devises) - set(taux["devise"])
    if absentes:
        raise SystemExit(f"[X] Devises sans taux : {sorted(absentes)}")

    g = taux.groupby("devise")["taux_pour_1_eur"]
    taux["rendement_log"] = np.log(taux["taux_pour_1_eur"] / g.shift(1))
    taux["volatilite_12m_pct"] = (taux.groupby("devise")["rendement_log"]
                                  .transform(lambda s: s.rolling(FENETRE, min_periods=200).std())
                                  * np.sqrt(FENETRE) * 100)
    taux["moyenne_12m"] = g.transform(lambda s: s.rolling(FENETRE, min_periods=200).mean())
    taux["ecart_moyenne_12m_pct"] = (taux["taux_pour_1_eur"] / taux["moyenne_12m"] - 1) * 100
    pays = hors_euro.groupby("devise")["iso3"].first()
    taux["iso3"] = taux["devise"].map(pays)
    for c in ["rendement_log", "volatilite_12m_pct", "moyenne_12m", "ecart_moyenne_12m_pct"]:
        taux[c] = taux[c].round(6)
    taux = taux[["date", "devise", "iso3", "taux_pour_1_eur", "source", "rendement_log",
                 "volatilite_12m_pct", "moyenne_12m", "ecart_moyenne_12m_pct"]]

    der = taux.sort_values("date").groupby("devise").tail(1)
    r.log(f"{len(taux)} lignes, {taux['devise'].nunique()} devises, "
          f"{taux['date'].min():%Y-%m-%d} -> {taux['date'].max():%Y-%m-%d}")
    r.log("\nDernier taux connu par devise (du plus volatil au moins volatil) :")
    r.log(der.sort_values("volatilite_12m_pct", ascending=False)[
        ["devise", "date", "taux_pour_1_eur", "volatilite_12m_pct", "ecart_moyenne_12m_pct", "source"]]
        .to_string(index=False))
    taux["date"] = taux["date"].dt.strftime("%Y-%m-%d")
    ecrire_gold(taux, "taux_change_jour", r)


if __name__ == "__main__":
    main()
