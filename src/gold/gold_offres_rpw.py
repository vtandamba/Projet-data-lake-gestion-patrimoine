"""
Gold 3/9 - offres_rpw : offres de transfert entre pays du périmètre (2011-2025)
==============================================================================
Une ligne par offre observée (prestataire x corridor x trimestre) dont le pays d'envoi ET
le pays de destination sont dans le périmètre. Colonnes utiles aux questions du besoin 1
(1.1 à 1.3, 1.6, 1.10 à 1.12, 1.15 à 1.17, 1.20 à 1.24) et 2.8.

Entrées : data/silver/rpw/rpw.csv, data/gold/dim_pays.csv
Sortie  : data/gold/offres_rpw.csv

Lancer depuis la racine du dépôt :
    python src/gold/gold_offres_rpw.py
"""
from gold_commun import Rapport, ecrire_gold, lire_dim_pays, lire_silver

COLONNES = [
    "offre_key", "feuille", "period", "period_std", "date_releve", "corridor", "source_code",
    "destination_code", "send_currency", "payout_currency", "firm", "firm_type", "is_bank", "is_mto",
    "product", "payment_instrument", "famille_produit", "sending_location", "speed_actual",
    "speed_rang", "pickup_method", "pickup_location", "transparent",
    "cc1_lcu_amount", "cc1_lcu_fee", "cc1_fx_margin", "cc1_total_cost_pct",
    "cc2_lcu_amount", "cc2_lcu_fee", "cc2_lcu_fx_rate", "inter_lcu_bank_fx", "cc2_fx_margin",
    "cc2_total_cost_pct", "cc2_cout_ajuste_pct", "cout_complet", "cc2_fx_margin_imputed",
    "promo", "marche_parallele", "standard_note", "note_corridor", "suivi_continu",
]


def type_prestataire(firm_type):
    """Banque / opérateur de transfert / autre (bureaux de poste, types mixtes)."""
    t = str(firm_type).lower()
    if "bank" in t and "money transfer" not in t and "post" not in t:
        return "banque"
    if "money transfer operator" in t and "bank" not in t and "post" not in t:
        return "operateur_transfert"
    return "autre"


def main():
    r = Rapport("offres_rpw")
    dim = lire_dim_pays()
    rpw = lire_silver("rpw/rpw.csv", usecols=lambda c: c in COLONNES + ["destination_dans_perimetre"])
    offres = rpw[rpw["destination_dans_perimetre"] & rpw["source_code"].isin(dim["iso3"])].copy()
    offres = offres[[c for c in COLONNES if c in offres.columns]]

    offres["type_prestataire"] = offres["firm_type"].map(type_prestataire)
    offres["frais_pct_cc2"] = (offres["cc2_lcu_fee"] / offres["cc2_lcu_amount"] * 100).round(4)
    euro = dim.set_index("iso3")["zone_euro"]
    offres["envoi_depuis_zone_euro"] = offres["source_code"].map(euro) & (offres["send_currency"] == "EUR")
    offres["groupe_cout_destination"] = offres["destination_code"].map(dim.set_index("iso3")["groupe_cout"])
    offres = offres.sort_values(["corridor", "period", "firm"]).reset_index(drop=True)

    r.log(f"Offres entre pays du périmètre : {len(offres)} ({offres['corridor'].nunique()} corridors, "
          f"{offres['period'].nunique()} trimestres, {offres['period'].min()} -> {offres['period'].max()})")
    r.log(f"Envoyées en EUR depuis la zone euro : {offres['envoi_depuis_zone_euro'].sum()}")
    r.log("\nOffres par type de prestataire :")
    r.log(offres["type_prestataire"].value_counts().to_string())
    r.log("\nCorridors (offres sur la dernière période) :")
    der = offres[offres["period"] == offres["period"].max()]
    r.log(der.groupby("corridor").size().sort_values(ascending=False).to_string())
    ecrire_gold(offres, "offres_rpw", r)


if __name__ == "__main__":
    main()
