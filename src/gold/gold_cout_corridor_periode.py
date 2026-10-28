"""
Gold 4/9 - cout_corridor_periode : coûts agrégés par corridor, trimestre et type de prestataire
==============================================================================================
Une ligne par corridor x trimestre x devise de versement x type de prestataire.
Médianes (et non moyennes : quelques offres extrêmes ne doivent pas tirer le résultat),
calculées sur l'envoi d'environ 500 USD (colonnes cc2). Une ligne « tous » par corridor et
trimestre, plus une ligne par type de prestataire (banque, opérateur de transfert, autre).
Questions 1.1, 1.19, 2.8 (évolution du coût), 3.9 (banque contre plateforme), 3.13.

Entrée  : data/gold/offres_rpw.csv (produit par gold_offres_rpw.py)
Sortie  : data/gold/cout_corridor_periode.csv

Lancer depuis la racine du dépôt :
    python src/gold/gold_cout_corridor_periode.py
"""
import pandas as pd

from gold_commun import GOLD, Rapport, ecrire_gold

# la devise de versement fait partie de la clé : un versement en EUR n'a pas de change,
# un versement en devise locale en a un -> ne pas mélanger les deux dans une médiane
CLES = ["corridor", "source_code", "destination_code", "period", "period_std", "payout_currency"]


def agreger(df: pd.DataFrame, cles) -> pd.DataFrame:
    return (df.groupby(cles, dropna=False)
            .agg(nb_offres=("firm", "size"),
                 nb_prestataires=("firm", "nunique"),
                 devise_envoi=("send_currency", lambda s: s.mode().iloc[0] if len(s.dropna()) else None),
                 cout_total_median_pct=("cc2_total_cost_pct", "median"),
                 cout_total_min_pct=("cc2_total_cost_pct", "min"),
                 marge_change_mediane_pct=("cc2_fx_margin", "median"),
                 frais_median_pct=("frais_pct_cc2", "median"),
                 frais_median_devise_envoi=("cc2_lcu_fee", "median"),
                 part_transparente=("transparent", "mean"),
                 part_marges_imputees=("cc2_fx_margin_imputed", "mean"))
            .reset_index())


def main():
    r = Rapport("cout_corridor_periode")
    chemin = GOLD / "offres_rpw.csv"
    if not chemin.exists():
        raise SystemExit("[X] data/gold/offres_rpw.csv absent : lancer d'abord gold_offres_rpw.py")
    offres = pd.read_csv(chemin, low_memory=False)
    for c in ["transparent", "cc2_fx_margin_imputed"]:
        offres[c] = offres[c].astype(str).str.lower().eq("true")

    par_type = agreger(offres, CLES + ["type_prestataire"])
    tous = agreger(offres, CLES).assign(type_prestataire="tous")
    agg = pd.concat([tous, par_type], ignore_index=True)
    num = agg.select_dtypes("number").columns
    agg[num] = agg[num].round(3)
    agg = agg.sort_values(CLES + ["type_prestataire"]).reset_index(drop=True)

    r.log(f"{len(agg)} lignes : {agg['corridor'].nunique()} corridors x {agg['period'].nunique()} trimestres "
          f"x type de prestataire")
    der = agg[(agg["period"] == agg["period"].max()) & (agg["type_prestataire"] == "tous")]
    r.log(f"\nDernière période ({agg['period'].max()}), tous prestataires :")
    r.log(der[["corridor", "devise_envoi", "payout_currency", "nb_offres", "cout_total_median_pct",
               "marge_change_mediane_pct"]].sort_values(["corridor", "payout_currency"]).to_string(index=False))
    ecrire_gold(agg, "cout_corridor_periode", r)


if __name__ == "__main__":
    main()
