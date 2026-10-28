"""
Gold 9/9 - risque_pays : score de risque de chaque destination (requête 3.3 de l'Excel)
======================================================================================
Quatre composantes, ramenées entre 0 et 1 (min-max sur les 22 destinations), poids égaux :
  volatilite_change_pct   volatilité annualisée de la devise contre l'EUR sur 12 mois
                          (0 en zone euro)                                  -> risque si élevée
  inflation_moy_5ans_pct  inflation moyenne des 5 dernières années (Banque mondiale)
  ecart_taux_bce_pts      |taux directeur - taux BCE| du dernier mois (0 en zone euro)
  gouvernance_moy         moyenne des scores WGI pv, rl, rq de la dernière année
                                                                            -> risque si faible
score_risque = 100 x (0,25 vol + 0,25 infl + 0,25 écart + 0,25 (1 - gouv)), arrondi.
Donnée manquante = risque maximal (choix prudent de l'Excel) : composante normalisée = 1.
Niveau : < 33 Faible, < 66 Moyen, sinon Élevé. Poids et seuils : hypothèses à calibrer.

Entrées : dim_pays, taux_change_jour, indicateurs_annuels (gold) ; bis_cbpol (silver)
Sortie  : data/gold/risque_pays.csv - une ligne par destination (22)

Lancer depuis la racine du dépôt (après les tables 5 et 7) :
    python src/gold/gold_risque_pays.py
"""
import pandas as pd

from gold_commun import (GOLD, PAYS_ENVOI, Rapport, ecrire_gold, lire_dim_pays,
                         taux_directeur_applicable_mensuel)

POIDS = {"vol": 0.25, "infl": 0.25, "ecart": 0.25, "gouv": 0.25}


def lire_gold(nom):
    chemin = GOLD / f"{nom}.csv"
    if not chemin.exists():
        raise SystemExit(f"[X] data/gold/{nom}.csv absent : construire cette table d'abord")
    return pd.read_csv(chemin, low_memory=False)


def normaliser(s: pd.Series) -> pd.Series:
    etendue = s.max() - s.min()
    return (s - s.min()) / etendue if etendue else s * 0


def main():
    r = Rapport("risque_pays")
    dim = lire_dim_pays()
    dest = dim.loc[dim["iso3"] != PAYS_ENVOI, ["iso3", "nom_fr", "devise", "zone_euro"]].copy()

    # volatilité de change sur 12 mois (dernière valeur)
    fx = lire_gold("taux_change_jour")
    vol = fx.dropna(subset=["volatilite_12m_pct"]).sort_values("date").groupby("devise").tail(1)
    dest["volatilite_change_pct"] = dest["devise"].map(vol.set_index("devise")["volatilite_12m_pct"])
    dest.loc[dest["zone_euro"], "volatilite_change_pct"] = 0.0

    # inflation moyenne et gouvernance (indicateurs annuels)
    an = lire_gold("indicateurs_annuels")
    der_infl = int(an.loc[an["inflation_pct"].notna(), "annee"].max())
    infl = an[an["annee"].between(der_infl - 4, der_infl)].groupby("iso3")["inflation_pct"].mean()
    dest["inflation_moy_5ans_pct"] = dest["iso3"].map(infl)
    der_wgi = int(an.loc[an["wgi_pv"].notna(), "annee"].max())
    gouv = an[an["annee"] == der_wgi].set_index("iso3")[["wgi_pv", "wgi_rl", "wgi_rq"]].mean(axis=1)
    dest["gouvernance_moy"] = dest["iso3"].map(gouv)

    # écart de taux directeur avec la BCE (dernier mois disponible)
    td = taux_directeur_applicable_mensuel(dim)
    dernier_mois = td.loc[td["taux_bce_pct"].notna(), "date"].max()
    td = td[td["date"] == dernier_mois].set_index("iso3")
    dest["ecart_taux_bce_pts"] = dest["iso3"].map((td["taux_directeur_pct"] - td["taux_bce_pct"]).abs())

    # normalisation et score (donnée manquante = risque maximal)
    n_vol = normaliser(dest["volatilite_change_pct"]).fillna(1)
    n_infl = normaliser(dest["inflation_moy_5ans_pct"]).fillna(1)
    n_ecart = normaliser(dest["ecart_taux_bce_pts"]).fillna(1)
    n_gouv = normaliser(dest["gouvernance_moy"]).fillna(0)
    dest["score_risque"] = (100 * (POIDS["vol"] * n_vol + POIDS["infl"] * n_infl
                                   + POIDS["ecart"] * n_ecart + POIDS["gouv"] * (1 - n_gouv))).round(0)
    dest["niveau_risque"] = pd.cut(dest["score_risque"], [-1, 32.999, 65.999, 101],
                                   labels=["Faible", "Moyen", "Élevé"]).astype(str)
    composantes = {"volatilite_change_pct": "volatilité", "inflation_moy_5ans_pct": "inflation",
                   "ecart_taux_bce_pts": "taux directeur", "gouvernance_moy": "gouvernance"}
    dest["donnees_manquantes"] = dest.apply(
        lambda p: ", ".join(v for c, v in composantes.items() if pd.isna(p[c])), axis=1)
    dest["periode_reference"] = (f"change {vol['date'].max()} ; inflation {der_infl - 4}-{der_infl} ; "
                                 f"WGI {der_wgi} ; taux directeurs {dernier_mois:%Y-%m}")
    for c in composantes:
        dest[c] = dest[c].round(3)
    dest = dest.sort_values("score_risque").reset_index(drop=True)

    r.log(f"Période de référence : {dest['periode_reference'].iloc[0]}")
    r.log(dest[["nom_fr", "volatilite_change_pct", "inflation_moy_5ans_pct", "ecart_taux_bce_pts",
                "gouvernance_moy", "score_risque", "niveau_risque", "donnees_manquantes"]].to_string(index=False))
    r.log("\n" + dest["niveau_risque"].value_counts().to_string())
    ecrire_gold(dest, "risque_pays", r)


if __name__ == "__main__":
    main()
