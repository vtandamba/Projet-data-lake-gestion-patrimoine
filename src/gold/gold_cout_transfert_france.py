"""
Gold 2/9 - cout_transfert_france : coût d'un transfert depuis la France, par destination
=========================================================================================
Le RPW ne contient aucune offre depuis la France vers le périmètre. Le coût est donc
reconstruit selon 4 méthodes (note de cadrage v2, § 7), indiquées sur chaque ligne :

  A  sepa              zone euro : virement SEPA au prix d'un virement national, marge 0 %
  B  rpw_zone_euro     hors euro : médiane des offres envoyées en EUR depuis la zone euro,
                       versées en devise locale (substitut d'un envoi depuis la France)
  C  rpw_autre_devise  hors euro : offres versées en devise locale depuis une autre devise
                       (seule la marge de change est reprise)
  D  estimation        hors euro, non observé : médiane des envois en EUR vers les autres
                       devises européennes hors euro observées

Coûts mesurés sur l'envoi d'environ 500 USD du RPW (colonnes cc2). Pour un montant
patrimonial, seule la marge de change (%) est extrapolée ; les frais RPW sont donnés à titre
indicatif.

Entrées : data/gold/dim_pays.csv, data/silver/rpw/rpw.csv
Sortie  : data/gold/cout_transfert_france.csv - une ligne par destination (22 lignes)

Lancer depuis la racine du dépôt :
    python src/gold/gold_cout_transfert_france.py
"""
import numpy as np
import pandas as pd

from gold_commun import GROUPES_COUT, PAYS_ENVOI, Rapport, ecrire_gold, lire_dim_pays, lire_silver

MONTANT_REFERENCE_EUR = 100_000
FIABILITE = {"A": "élevée (règle SEPA)", "B": "bonne (observé, substitut zone euro)",
             "C": "moyenne (observé depuis une autre devise)", "D": "faible (estimation)"}
COLONNES_RPW = ["period", "source_code", "destination_code", "corridor", "firm", "send_currency",
                "payout_currency", "cc2_lcu_amount", "cc2_lcu_fee", "cc2_fx_margin",
                "cc2_total_cost_pct"]


def resumer(offres: pd.DataFrame) -> dict:
    """Médianes d'un ensemble d'offres (déjà restreint à une période)."""
    return {
        "nb_offres": len(offres),
        "nb_prestataires": offres["firm"].nunique(),
        "corridors_sources": ", ".join(sorted(offres["corridor"].unique())),
        "marge_change_pct": offres["cc2_fx_margin"].median(),
        "frais_pct_500usd": (offres["cc2_lcu_fee"] / offres["cc2_lcu_amount"] * 100).median(),
        "cout_total_pct_500usd": offres["cc2_total_cost_pct"].median(),
    }


def derniere_periode(offres: pd.DataFrame):
    if offres.empty:
        return None, offres
    p = offres["period"].max()
    return p, offres[offres["period"] == p]


def main():
    r = Rapport("cout_transfert_france")
    dim = lire_dim_pays()
    rpw = lire_silver("rpw/rpw.csv", usecols=COLONNES_RPW)
    derniere = rpw["period"].max()
    r.log(f"RPW silver : {len(rpw)} offres, dernière période {derniere}")

    euro_envoi = set(dim.loc[dim["zone_euro"], "iso3"])          # pays d'envoi de la zone euro
    en_eur = rpw[(rpw["send_currency"] == "EUR") & rpw["source_code"].isin(euro_envoi)]
    devises_hors_euro = set(dim.loc[~dim["zone_euro"], "devise"]) | {"BGN"}

    lignes = []
    for _, pays in dim[dim["iso3"] != PAYS_ENVOI].iterrows():
        iso3, devise, groupe = pays["iso3"], pays["devise"], pays["groupe_cout"]
        ligne = {"iso3": iso3, "nom_fr": pays["nom_fr"], "devise": devise, "groupe_cout": groupe,
                 "methode_cout": GROUPES_COUT[groupe][0], "fiabilite": FIABILITE[groupe]}

        if groupe == "A":
            ligne.update({"periode_reference": None, "nb_offres": 0, "nb_prestataires": 0,
                          "corridors_sources": "", "marge_change_pct": 0.0,
                          "frais_pct_500usd": np.nan, "cout_total_pct_500usd": np.nan,
                          "commentaire": "Virement SEPA : frais d'un virement national, aucun change "
                                         "(règlement (UE) 2021/1230)."})
        elif groupe == "B":
            sel = en_eur[(en_eur["destination_code"] == iso3) & (en_eur["payout_currency"] == devise)]
            p, sel = derniere_periode(sel)
            ligne.update({"periode_reference": p, **resumer(sel),
                          "commentaire": "Offres en EUR depuis la zone euro, versées en " + devise + "."})
        elif groupe == "C":
            sel = rpw[(rpw["destination_code"] == iso3) & (rpw["payout_currency"] == devise)]
            p, sel = derniere_periode(sel)
            ligne.update({"periode_reference": p, **resumer(sel),
                          "commentaire": "Aucun envoi en EUR observé : marge de change des envois en "
                                         + ", ".join(sorted(sel["send_currency"].unique()))
                                         + " ; frais non comparables."})
            ligne["frais_pct_500usd"], ligne["cout_total_pct_500usd"] = np.nan, np.nan
        else:  # D
            # versement dans la devise locale de la destination (BGN pour la Bulgarie avant 2026)
            devise_locale = {**dim.loc[~dim["zone_euro"]].set_index("iso3")["devise"].to_dict(),
                             "BGR": "BGN"}
            sel = en_eur[(en_eur["period"] == derniere)
                         & en_eur["payout_currency"].isin(devises_hors_euro)
                         & (en_eur["payout_currency"] == en_eur["destination_code"].map(devise_locale))]
            ligne.update({"periode_reference": derniere, **resumer(sel),
                          "commentaire": "Estimation : aucune offre observée vers " + devise
                                         + " ; médiane des envois en EUR vers "
                                         + ", ".join(sorted(sel["payout_currency"].unique())) + "."})
        lignes.append(ligne)

    df = pd.DataFrame(lignes)
    df["cout_change_eur_pour_100k"] = (df["marge_change_pct"] / 100 * MONTANT_REFERENCE_EUR).round(0)
    df["montant_recu_avant_frais_eur_pour_100k"] = MONTANT_REFERENCE_EUR - df["cout_change_eur_pour_100k"]
    for c in ["marge_change_pct", "frais_pct_500usd", "cout_total_pct_500usd"]:
        df[c] = df[c].round(3)
    df = df[["iso3", "nom_fr", "devise", "groupe_cout", "methode_cout", "fiabilite", "periode_reference",
             "nb_offres", "nb_prestataires", "corridors_sources", "marge_change_pct", "frais_pct_500usd",
             "cout_total_pct_500usd", "cout_change_eur_pour_100k",
             "montant_recu_avant_frais_eur_pour_100k", "commentaire"]]
    df = df.sort_values(["marge_change_pct", "nom_fr"]).reset_index(drop=True)

    if df["marge_change_pct"].isna().any():
        raise SystemExit(f"[X] Marge introuvable pour : {df.loc[df['marge_change_pct'].isna(), 'iso3'].tolist()}")

    r.log(f"\nCoût du change pour {MONTANT_REFERENCE_EUR:,} € envoyés depuis la France :".replace(",", " "))
    r.log(df[["nom_fr", "groupe_cout", "periode_reference", "nb_offres", "marge_change_pct",
              "cout_change_eur_pour_100k"]].to_string(index=False))
    ecrire_gold(df, "cout_transfert_france", r)


if __name__ == "__main__":
    main()
