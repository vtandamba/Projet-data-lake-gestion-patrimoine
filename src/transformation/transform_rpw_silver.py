"""
Source 1 (feuille 1) - Remittance Prices Worldwide (RPW)
Transformation bronze -> silver : toutes les propositions correctives du dictionnaire.

Entrées : data/bronze/rpw_f1S1/Source1_f1.csv
          data/silver/bis/bis_xru.csv   (taux BIS, produit par transform_bis_xru_silver.py)
Sorties : data/silver/rpw/rpw.csv             (table de faits : 1 ligne = 1 offre)
          data/silver/rpw/dim_pays_rpw.csv    (attributs pays sortis de la table de faits)
          data/silver/rpw/dim_operateur.csv   (nom de référence unique par opérateur)

Lancer depuis la racine du dépôt (APRÈS transform_bis_xru_silver.py) :
    python src/transformation/transform_rpw_silver.py

Ordre des traitements :
  A. structure (noms, texte, périmètre, "..", dates, opérateurs)
  B. colonnes texte (product, sending_location, speed, coverage, pickup, notes, payout_currency)
  C. taux de référence BIS
  D. montants, frais, taux, marges, coût total
  E. clé d'offre, dimensions, écriture
"""
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

RACINE = Path(__file__).resolve().parents[2]
FICHIER_BRONZE = RACINE / "data" / "bronze" / "rpw_f1S1" / "Source1_f1.csv"
FICHIER_XRU = RACINE / "data" / "silver" / "bis" / "bis_xru.csv"
DOSSIER_SILVER = RACINE / "data" / "silver" / "rpw"

PERIMETRE_ISO3 = {
    "AUT", "BEL", "BGR", "HRV", "CZE", "EST", "FRA", "DEU", "HUN", "ITA", "LVA", "LTU",
    "NLD", "NOR", "POL", "PRT", "ROU", "ESP", "SWE", "CHE", "TUR", "UKR", "GBR",
}

# Devise nationale hors euro des pays du périmètre
DEVISE_NATIONALE = {
    "CZE": "CZK", "HUN": "HUF", "NOR": "NOK", "POL": "PLN", "ROU": "RON", "SWE": "SEK",
    "CHE": "CHF", "TUR": "TRY", "UKR": "UAH", "GBR": "GBP", "BGR": "BGN", "HRV": "HRK",
    "EST": "EEK", "LVA": "LVL", "LTU": "LTL",
    # zone franc CFA (arrimée à l'euro : 1 EUR = 655,957 XOF / XAF)
    "SEN": "XOF", "CIV": "XOF", "MLI": "XOF", "TGO": "XOF", "BEN": "XOF", "BFA": "XOF",
    "NER": "XOF", "GNB": "XOF", "CMR": "XAF", "CAF": "XAF", "TCD": "XAF", "COG": "XAF",
    "GNQ": "XAF", "GAB": "XAF",
}
ADOPTION_EURO = {
    "AUT": "1999-01-01", "BEL": "1999-01-01", "DEU": "1999-01-01", "ESP": "1999-01-01",
    "FRA": "1999-01-01", "ITA": "1999-01-01", "NLD": "1999-01-01", "PRT": "1999-01-01",
    "EST": "2011-01-01", "LVA": "2014-01-01", "LTU": "2015-01-01", "HRV": "2023-01-01",
    "BGR": "2026-01-01",
}
# Anciennes devises arrimées à l'euro (taux de conversion irrévocables) :
# la BIS a converti leur historique en euro, on les recalcule à partir de l'EUR.
PARITES_EURO = {"BGN": 1.95583, "HRK": 7.53450, "EEK": 15.6466, "LVL": 0.702804,
                "LTL": 3.45280, "XOF": 655.957, "XAF": 655.957}

# Seuil au-delà duquel le taux interbancaire RPW est jugé trop éloigné du taux BIS
SEUIL_ECART_BIS = 0.10   # 10 %

NON_RENSEIGNE = "Non renseigné"
rapport = []   # valeurs non reconnues, affichées à la fin


# =============================================================================
# A. STRUCTURE
# =============================================================================
def lire_bronze() -> pd.DataFrame:
    for encodage in ("utf-8", "latin-1"):
        try:
            return pd.read_csv(FICHIER_BRONZE, dtype=str, encoding=encodage)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Impossible de lire {FICHIER_BRONZE}")


def renommer_colonnes(df):
    """'cc2 total cost %' -> 'cc2_total_cost_pct' ; 'pick-up method' -> 'pickup_method'."""
    def snake(nom):
        nom = nom.strip().lower().replace("%", "pct").replace("-", "").replace(" ", "_")
        while "__" in nom:
            nom = nom.replace("__", "_")
        return nom
    return df.rename(columns=snake)


def nettoyer_texte(df):
    for col in df.columns:
        df[col] = df[col].str.strip().str.replace(r"\s+", " ", regex=True).replace("", pd.NA)
    return df


def filtrer_perimetre(df):
    """Pays d'envoi dans le périmètre ; Antilles néerlandaises (ANT, dissoutes en 2010) exclues."""
    df = df[df["source_code"].isin(PERIMETRE_ISO3) & (df["destination_code"] != "ANT")].copy()
    df["destination_dans_perimetre"] = df["destination_code"].isin(PERIMETRE_ISO3)
    return df


def remplacer_points(df):
    for cote in ("source", "destination"):
        for suffixe in ("region", "lending"):
            df[f"{cote}_{suffixe}"] = df[f"{cote}_{suffixe}"].replace("..", "Non applicable")
        df[f"{cote}_g8g20"] = df[f"{cote}_g8g20"].replace("..", "Non membre")
    return df


def standardiser_dates(df):
    parties = df["period"].str.extract(r"^(\d{4})_(\d)Q$")
    df["period_std"] = parties[0] + "Q" + parties[1]
    df["semestre"] = parties[0] + "S" + parties[1].map({"1": "1", "2": "1", "3": "2", "4": "2"})
    df["date_releve"] = pd.to_datetime(df["date"], format="%d/%b/%Y", errors="coerce")
    df["mois"] = df["date_releve"].dt.to_period("M").dt.to_timestamp()
    if df["period_std"].isna().any():
        rapport.append(f"period non reconnues : {df.loc[df['period_std'].isna(), 'period'].unique()}")
    if df["date_releve"].isna().any():
        rapport.append(f"dates non reconnues : {df.loc[df['date_releve'].isna(), 'date'].unique()[:10]}")
    return df.drop(columns=["date"])


def normaliser_operateurs(df):
    df["firm_original"] = df["firm"]
    cle = df["firm"].str.lower()
    reference = df.groupby(cle)["firm"].agg(lambda s: s.value_counts().idxmax())
    df["firm"] = cle.map(reference)
    t = df["firm_type"].str.lower().fillna("")
    df["is_bank"] = t.str.contains("bank")
    df["is_mto"] = t.str.contains("money transfer operator")
    df["is_post_office"] = t.str.contains("post office")
    df["is_building_society"] = t.str.contains("building society")
    df["is_non_bank_fi"] = t.str.contains("non-bank fi")
    df["is_mobile_operator"] = t.str.contains("mobile operator")
    df["transparent"] = df["transparent"].str.lower().map({"yes": True, "no": False})
    return df


# =============================================================================
# B. COLONNES TEXTE
# =============================================================================
def contient(serie, *mots):
    s = serie.str.lower().fillna("")
    masque = pd.Series(False, index=serie.index)
    for mot in mots:
        masque |= s.str.contains(mot, regex=False)
    return masque


def valeur_meme_offre(df, col):
    """Valeur la plus fréquente de la même offre (opérateur + corridor) aux autres périodes."""
    def mode(s):
        s = s.dropna()
        return s.value_counts().idxmax() if len(s) else pd.NA
    return df.groupby(["firm", "corridor"])[col].transform(mode)


def traiter_product(df):
    p = df["product"]
    # devise de versement mélangée au produit ("USD service", "EUR service")
    df["payout_ccy_product"] = p.str.extract(r"\b(USD|EUR|GBP|LCU)\b\s*service", expand=False)
    # booléens par canal (les valeurs multiples d'une cellule sont toutes captées)
    df["produit_compte"] = contient(p, "account")
    df["produit_especes"] = contient(p, "cash")
    df["produit_carte"] = contient(p, "card")
    df["produit_en_ligne"] = contient(p, "online", "on-line", "internet")
    df["produit_mobile"] = contient(p, "mobile", "wallet")
    df["produit_domicile"] = contient(p, "door to door")
    # famille (le détail reste dans "product")
    famille = pd.Series("Autre", index=df.index)
    famille[df["produit_compte"]] = "Compte"
    famille[df["produit_especes"]] = "Espèces"
    famille[contient(p, "service")] = "Service en devise"
    famille[df["produit_en_ligne"]] = "En ligne"
    famille[df["produit_mobile"]] = "Mobile"
    famille[df["produit_carte"]] = "Carte"
    famille[df["produit_domicile"]] = "Livraison à domicile"
    famille[contient(p, "cash to cash")] = "Espèces vers espèces"
    famille[contient(p, "cash to account")] = "Espèces vers compte"
    famille[contient(p, "account to cash")] = "Compte vers espèces"
    famille[contient(p, "account to account")] = "Compte vers compte"
    famille[p.isna()] = pd.NA
    df["famille_produit"] = famille
    # nulls : même offre aux autres périodes
    df["product_impute"] = p.isna()
    df["product"] = p.fillna(valeur_meme_offre(df, "product"))
    autres = df.loc[df["famille_produit"] == "Autre", "product"].unique()
    if len(autres):
        rapport.append(f"product classés 'Autre' (à vérifier) : {list(autres)[:15]}")
    return df


def traiter_sending_location(df):
    s = df["sending_location"].copy()
    manquant = s.isna() | contient(s, "not available")
    df["sending_location_original"] = df["sending_location"]
    # 1. déduire du produit (Online service -> On-line)
    s[manquant & df["produit_en_ligne"]] = "On-line"
    # 2. même offre aux autres périodes
    df["sending_location"] = s.where(~(manquant & ~df["produit_en_ligne"]))
    meme = valeur_meme_offre(df, "sending_location")
    reste = df["sending_location"].isna()
    df.loc[reste, "sending_location"] = meme[reste]
    # 3. sinon "Non renseigné"
    df["sending_location"] = df["sending_location"].fillna(NON_RENSEIGNE)
    # booléens par canal
    s = df["sending_location"]
    df["envoi_agence"] = contient(s, "branch", "agent", "agency", "office")
    df["envoi_centre_appels"] = contient(s, "call", "phone", "telephone")
    df["envoi_en_ligne"] = contient(s, "on-line", "online", "internet", "web", "mobile")
    inconnus = s[~(df["envoi_agence"] | df["envoi_centre_appels"] | df["envoi_en_ligne"])
                 & (s != NON_RENSEIGNE)].unique()
    if len(inconnus):
        rapport.append(f"sending_location sans canal reconnu : {list(inconnus)}")
    return df


def traiter_speed(df):
    s = df["speed_actual"].str.lower()
    rang = pd.Series(np.nan, index=df.index)
    for motif, valeur in [(r"less than (?:one|1) hour|< ?1 ?h", 1), (r"same day", 2),
                          (r"next day", 3), (r"^2 days", 4), (r"3.?-.?5 days", 5),
                          (r"6 days|more than", 6)]:
        rang[s.str.contains(motif, regex=True, na=False) & rang.isna()] = valeur
    df["speed_rang"] = rang
    # null : valeur de la même offre aux périodes voisines
    df["speed_impute"] = df["speed_actual"].isna()
    df["speed_actual"] = df["speed_actual"].fillna(valeur_meme_offre(df, "speed_actual"))
    df["speed_rang"] = df["speed_rang"].fillna(valeur_meme_offre(df, "speed_rang"))
    inconnus = df.loc[df["speed_rang"].isna() & df["speed_actual"].notna(), "speed_actual"].unique()
    if len(inconnus):
        rapport.append(f"speed_actual non classées : {list(inconnus)}")
    ordre = (df.dropna(subset=["speed_rang"]).sort_values("speed_rang")["speed_actual"]
             .drop_duplicates().tolist())
    ordre += [v for v in df["speed_actual"].dropna().unique() if v not in ordre]
    df["speed_actual"] = pd.Categorical(df["speed_actual"], categories=ordre, ordered=True)
    return df


def traiter_coverage(df):
    mode_operateur = df.groupby("firm")["coverage"].transform(
        lambda s: s.dropna().value_counts().idxmax() if s.notna().any() else pd.NA)
    df["coverage"] = df["coverage"].fillna(mode_operateur)
    return df


def traiter_pickup(df):
    p = (df["pickup_method"].str.lower().str.replace("acciunt", "account", regex=False))
    df["pickup_method_original"] = df["pickup_method"]
    df["retrait_compte"] = contient(p, "account")
    df["retrait_especes"] = contient(p, "cash")
    df["retrait_carte"] = contient(p, "card")
    df["retrait_atm"] = contient(p, "atm")
    df["retrait_mobile"] = contient(p, "mobile", "wallet")
    df["retrait_domicile"] = contient(p, "home", "door")
    noms = {"retrait_compte": "Bank Account", "retrait_especes": "Cash", "retrait_carte": "Card",
            "retrait_atm": "ATM", "retrait_mobile": "Mobile", "retrait_domicile": "Home delivery"}
    methode = df[list(noms)].apply(
        lambda ligne: "; ".join(n for c, n in noms.items() if ligne[c]) or pd.NA, axis=1)
    inconnus = df.loc[methode.isna() & p.notna(), "pickup_method"].unique()
    if len(inconnus):
        rapport.append(f"pickup_method non reconnues : {list(inconnus)}")
    # nulls : 1. déduire du produit
    manque = methode.isna()
    methode[manque & contient(df["product"], "cash to cash", "account to cash")] = "Cash"
    methode[manque & contient(df["product"], "account to account", "cash to account")] = "Bank Account"
    df["pickup_method"] = methode
    # 2. même offre aux autres périodes ; 3. "Non renseigné"
    reste = df["pickup_method"].isna()
    df.loc[reste, "pickup_method"] = valeur_meme_offre(df, "pickup_method")[reste]
    df["pickup_method"] = df["pickup_method"].fillna(NON_RENSEIGNE)
    # les booléens suivent la valeur finale
    for c, n in noms.items():
        df[c] = df["pickup_method"].str.contains(n, regex=False)
    return df


def extraire_devise_versement(texte):
    """'sends EUR and pays out USD' -> USD ; 'send and payout in EUR' -> EUR ;
    'USD service' -> USD ; 'not allowed to pay out ... in any currency' -> LCU."""
    devise = texte.str.extract(r"pay(?:s)?\s?out(?:\s+in)?\s+([A-Z]{3})\b", expand=False)
    service = texte.str.extract(r"\b(USD|EUR|GBP|LCU) service", expand=False)
    devise = devise.fillna(service)
    devise[contient(texte, "not allowed to pay out")] = "LCU"
    return devise


def traiter_notes(df):
    n = df["note1"]
    # texte normalisé (casse "USD Service", espaces) ; l'original reste en bronze
    df["standard_note"] = (n.str.replace("’", "'", regex=False)
                           .str.replace(r"\s+", " ", regex=True).str.strip())
    df["payout_ccy_note"] = extraire_devise_versement(n)
    # devise de versement de tout le corridor, donnée dans note2 (repli)
    df["payout_ccy_note2"] = extraire_devise_versement(df["note2"])
    df["fx_cost_hidden"] = contient(n, "additional cost", "not shown here", "may be converted")
    df["note_promo"] = contient(n, "promotion", "special offer")
    df["note_parallele"] = contient(n, "parallel", "grey")
    df["promo_or_parallel_fx"] = df["note_promo"] | df["note_parallele"]
    df["avertissement_transparence"] = contient(n, "not transparent")
    df["fx_info_non_fiable"] = contient(n, "did not seem to be reliable",
                                        "did not seem to be comparable")
    # note2 : information du corridor -> attribut du corridor, puis colonne supprimée
    df["note_corridor"] = df.groupby(["corridor", "period"])["note2"].transform(
        lambda s: s.dropna().iloc[0] if s.notna().any() else pd.NA)
    return df.drop(columns=["note1", "note2", "note_promo"])


# =============================================================================
# C. TAUX DE RÉFÉRENCE BIS (XRU)
# =============================================================================
def charger_taux_bis():
    """Table (devise, mois) -> unités de devise pour 1 USD."""
    if not FICHIER_XRU.exists():
        rapport.append("bis_xru.csv absent : lancer transform_bis_xru_silver.py d'abord. "
                       "Contrôles BIS ignorés.")
        return None
    xru = pd.read_csv(FICHIER_XRU, parse_dates=["date"])
    eur = xru[xru["ref_area"] == "XM"][["date", "taux_change_lcu_usd"]].assign(currency="EUR")
    autres = (xru[(xru["currency"] != "EUR")]
              .groupby(["currency", "date"], as_index=False)["taux_change_lcu_usd"].first())
    taux = pd.concat([eur, autres], ignore_index=True)
    for devise, parite in PARITES_EURO.items():
        taux = pd.concat([taux, eur.assign(currency=devise,
                                           taux_change_lcu_usd=eur["taux_change_lcu_usd"] * parite)])
    usd = eur.assign(currency="USD", taux_change_lcu_usd=1.0)
    return pd.concat([taux, usd], ignore_index=True).drop_duplicates(["currency", "date"])


def taux_croise(taux, devise_envoi, devise_versement, mois):
    """Unités de devise de versement pour 1 unité de devise d'envoi, d'après la BIS."""
    cle = taux.set_index(["currency", "date"])["taux_change_lcu_usd"]
    v = pd.MultiIndex.from_arrays([devise_versement, mois])
    e = pd.MultiIndex.from_arrays([devise_envoi, mois])
    return pd.Series(cle.reindex(v).to_numpy() / cle.reindex(e).to_numpy(), index=devise_envoi.index)


def devise_locale_destination(df):
    adoption = pd.to_datetime(df["destination_code"].map(ADOPTION_EURO))
    locale = df["destination_code"].map(DEVISE_NATIONALE)
    return locale.where(~(df["date_releve"] >= adoption), "EUR").where(
        adoption.notna() | locale.notna(), pd.NA)


def determiner_payout_currency(df, taux):
    """Devise de versement : produit, puis note1, puis comparaison du taux interbancaire
    avec les taux BIS (devise d'envoi -> USD, -> EUR ou -> devise locale)."""
    locale = devise_locale_destination(df)
    payout = (df["payout_ccy_product"].fillna(df["payout_ccy_note"])
              .fillna(df["payout_ccy_note2"]))
    df["payout_source"] = np.select(
        [df["payout_ccy_product"].notna(), df["payout_ccy_note"].notna(),
         df["payout_ccy_note2"].notna()], ["product", "note1", "note2"], default=None)
    df["devise_taux_interbancaire"] = pd.NA
    if taux is not None:
        inter = df["inter_lcu_bank_fx"]
        candidats = {"USD": pd.Series("USD", index=df.index),
                     "EUR": pd.Series("EUR", index=df.index), "LCU": locale}
        ecarts = {}
        for nom, devise in candidats.items():
            ref = taux_croise(taux, df["send_currency"], devise, df["mois"])
            ecarts[nom] = (inter / ref - 1).abs()
        ecarts = pd.DataFrame(ecarts).fillna(np.inf)
        meilleur = ecarts.idxmin(axis=1)
        proche = ecarts.min(axis=1) < SEUIL_ECART_BIS
        deduit = meilleur.where(proche)
        # devise dans laquelle le taux interbancaire est réellement exprimé
        df["devise_taux_interbancaire"] = deduit.where(deduit != "LCU", locale)
        reste = payout.isna() & deduit.notna()
        payout[reste] = deduit[reste]
        df.loc[reste, "payout_source"] = "taux BIS"
        # ni USD ni EUR (les deux taux BIS sont connus et loin) -> devise locale
        # (seulement si la devise locale est inconnue : pays hors périmètre)
        ni_usd_ni_eur = (ecarts["USD"].lt(np.inf) & ecarts["EUR"].lt(np.inf) & locale.isna()
                         & (ecarts["USD"] >= SEUIL_ECART_BIS) & (ecarts["EUR"] >= SEUIL_ECART_BIS))
        elimination = payout.isna() & ni_usd_ni_eur & df["inter_lcu_bank_fx"].notna()
        payout[elimination] = "LCU"
        df.loc[elimination, "payout_source"] = "taux BIS (élimination)"
    # LCU -> code de la devise locale quand on le connaît
    payout = payout.where(payout != "LCU", locale.fillna("LCU"))
    df["payout_currency"] = payout
    return df.drop(columns=["payout_ccy_product", "payout_ccy_note", "payout_ccy_note2"])


def controler_taux_interbancaire(df, taux):
    """inter_lcu_bank_fx comparé au taux croisé BIS du même mois.
    - s'il correspond à une autre devise que payout_currency (ex. franc CFA alors que la note
      dit EUR) : on le garde et on le signale (devise_note_differente) ;
    - s'il ne correspond à aucune devise connue (marché parallèle, taux peu fiable) :
      remplacé par le taux BIS, l'original est gardé."""
    df["inter_lcu_bank_fx_original"] = df["inter_lcu_bank_fx"]
    df["taux_bis_croise"] = np.nan
    df["inter_fx_remplace"] = False
    devise_taux = df["devise_taux_interbancaire"]
    df["devise_note_differente"] = devise_taux.notna() & (devise_taux != df["payout_currency"])
    if taux is None:
        return df
    devise_ref = devise_taux.fillna(df["payout_currency"])
    ref = taux_croise(taux, df["send_currency"], devise_ref, df["mois"])
    df["taux_bis_croise"] = ref
    trop_loin = ((df["inter_lcu_bank_fx"] / ref - 1).abs() > SEUIL_ECART_BIS) & devise_taux.isna()
    df.loc[trop_loin, "inter_lcu_bank_fx"] = ref[trop_loin]
    df["inter_fx_remplace"] = trop_loin
    return df


# =============================================================================
# D. MONTANTS, FRAIS, TAUX, MARGES, COÛT TOTAL
# =============================================================================
NUMERIQUES = ["cc1_lcu_amount", "cc1_denomination_amount", "cc1_lcu_fee", "cc1_lcu_fx_rate",
              "cc1_fx_margin", "cc1_total_cost_pct", "cc2_lcu_amount", "cc2_denomination_amount",
              "cc2_lcu_fee", "cc2_lcu_fx_rate", "cc2_fx_margin", "cc2_total_cost_pct",
              "inter_lcu_bank_fx"]


def convertir_numeriques(df):
    for col in NUMERIQUES:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def traiter_montants_et_devise(df):
    # montant envoyé : identique pour un même (corridor, période) -> valeur la plus fréquente
    for k in ("cc1", "cc2"):
        mode = df.groupby(["corridor", "period"])[f"{k}_lcu_amount"].transform(
            lambda s: s.dropna().mode().iloc[0] if s.notna().any() else np.nan)
        df[f"{k}_lcu_amount"] = df[f"{k}_lcu_amount"].fillna(mode)
    # montant de référence USD : 201/202 -> 200, 501/502 -> 500, 6,0 -> 200 ; colonne variante
    d1, d2 = df["cc1_denomination_amount"], df["cc2_denomination_amount"]
    v1 = (d1 - 200).where(d1.isin([201, 202]), 0)
    v2 = (d2 - 500).where(d2.isin([501, 502]), 0)
    df["variante"] = np.maximum(v1, v2).astype(int)
    df["cc1_denomination_amount"] = np.where(d1.isin([201, 202, 6]), 200, d1)
    df["cc2_denomination_amount"] = np.where(d2.isin([501, 502]), 500, d2)
    # devise d'envoi : fusion cc1 / cc2, sinon déduite du pays d'envoi
    send = df["cc1_lcu_code"].fillna(df["cc2_lcu_code"])
    devise_pays = df.groupby("source_code")["cc1_lcu_code"].agg(
        lambda s: s.dropna().value_counts().idxmax() if s.notna().any() else pd.NA)
    df["send_currency"] = send.fillna(df["source_code"].map(devise_pays))
    return df.drop(columns=["cc1_lcu_code", "cc2_lcu_code"])


def traiter_frais(df):
    """Frais nuls recalculés : frais = (coût total - marge) x montant / 100 (valeurs publiées)."""
    for k in ("cc1", "cc2"):
        recalcul = ((df[f"{k}_total_cost_pct"] - df[f"{k}_fx_margin"])
                    * df[f"{k}_lcu_amount"] / 100)
        manque = df[f"{k}_lcu_fee"].isna()
        df[f"{k}_fee_recalcule"] = manque & recalcul.notna()
        df[f"{k}_lcu_fee"] = df[f"{k}_lcu_fee"].fillna(recalcul)
    return df


def traiter_marges(df, taux):
    # les marges RPW sont définies par rapport au taux interbancaire publié par le RPW
    inter_rpw = df["inter_lcu_bank_fx_original"]
    sans_conversion = (df["send_currency"] == df["payout_currency"]) | (inter_rpw == 1)
    df["promo"] = False
    df["marche_parallele"] = False
    for k in ("cc1", "cc2"):
        m = f"{k}_fx_margin"
        df[f"{m}_original"] = df[m]
        # nulls : marge = (1 - taux appliqué / taux interbancaire) x 100
        recalcul = (1 - df[f"{k}_lcu_fx_rate"] / inter_rpw) * 100
        df[f"{m}_recalculee"] = df[m].isna() & recalcul.notna()
        df[m] = df[m].fillna(recalcul)
        # zéros masquant une valeur manquante : offres non transparentes, ou
        # marge 0 alors qu'il y a conversion (GBP, CZK, EUR sans note)
        suspect = (df[f"{m}_original"] == 0) & (~df["transparent"].fillna(False) | ~sans_conversion)
        # marges négatives : marché parallèle (recalcul avec le taux BIS) ou promotion
        negative = df[m] < 0
        parallele = negative & (df["note_parallele"]
                                | ((df["destination_code"] == "TUR") & ~df["promo_or_parallel_fx"]))
        df["marche_parallele"] |= parallele
        df["promo"] |= negative & ~parallele
        if taux is not None:
            # recalcul avec le taux BIS, gardé seulement s'il est plausible (|marge| <= 20 %)
            nouvelle = (1 - df[f"{k}_lcu_fx_rate"] / df["taux_bis_croise"]) * 100
            ok = parallele & nouvelle.notna() & (nouvelle.abs() <= 20)
            df.loc[ok, m] = nouvelle[ok]
        # imputation : médiane des offres transparentes saines du même corridor,
        # même période, même type d'opérateur (repli : corridor + période)
        saines = df[m].where(df["transparent"].fillna(False) & ~suspect & (df[m] >= 0))
        med = saines.groupby([df["corridor"], df["period"], df["firm_type"]]).transform("median")
        med = med.fillna(saines.groupby([df["corridor"], df["period"]]).transform("median"))
        df[f"{k}_fx_margin_imputed"] = suspect & med.notna()
        df.loc[df[f"{k}_fx_margin_imputed"], m] = med
    return df


def traiter_taux_appliques(df):
    """Taux 1,0 alors que les devises diffèrent -> suspect, recalculé ;
    cc2 nul -> taux cc1 de la même offre, sinon recalculé."""
    for k in ("cc1", "cc2"):
        r = f"{k}_lcu_fx_rate"
        recalcul = df["inter_lcu_bank_fx_original"] * (1 - df[f"{k}_fx_margin"] / 100)
        suspect = (df[r] == 1) & (df["send_currency"] != df["payout_currency"]) \
            & df["payout_currency"].notna()
        df[f"{r}_suspect"] = suspect
        df.loc[suspect, r] = recalcul[suspect]
        if k == "cc2":
            df[r] = df[r].fillna(df["cc1_lcu_fx_rate"])
        df[r] = df[r].fillna(recalcul)
    return df


def traiter_cout_total(df):
    """Coût total recalculé à partir des composantes corrigées (original gardé en contrôle)."""
    for k in ("cc1", "cc2"):
        t = f"{k}_total_cost_pct"
        df[f"{t}_original"] = df[t]
        df[t] = df[f"{k}_lcu_fee"] / df[f"{k}_lcu_amount"] * 100 + df[f"{k}_fx_margin"]
    df["cc2_disponible"] = df["cc2_total_cost_pct"].notna()
    df["ecart_cout_cc1"] = (df["cc1_total_cost_pct"] - df["cc1_total_cost_pct_original"]).abs()

    # envois en EUR vers un pays hors zone euro, versés sans conversion locale :
    # la conversion à l'arrivée n'est pas mesurée -> coût incomplet
    locale = devise_locale_destination(df)
    incomplet = ((df["send_currency"] == "EUR") & locale.notna() & (locale != "EUR")
                 & df["payout_currency"].notna() & (df["payout_currency"] != locale))
    df["cout_complet"] = ~incomplet
    marge_lcu = df["cc2_fx_margin"].where(df["payout_currency"] == locale)
    med = marge_lcu.groupby([df["corridor"], df["period"]]).transform("median")
    # sans offre en devise locale de référence dans le corridor (ex. zone CFA où tout est
    # versé en EUR) : pas d'ajustement possible -> coût publié, signalé par cout_complet
    df["cc2_cout_ajuste_pct"] = np.where(incomplet & med.notna(), df["cc2_total_cost_pct"] + med,
                                         df["cc2_total_cost_pct"])
    df["cout_ajuste_applique"] = incomplet & med.notna()
    return df


# =============================================================================
# E. CLÉ, CORRIDORS, DIMENSIONS
# =============================================================================
def supprimer_doublons_stricts(df):
    """Lignes identiques sur la clé d'offre ET sur les frais / marges / taux : vrais doublons."""
    cols = ["period", "corridor", "firm", "product", "payout_currency", "speed_actual",
            "sending_location", "pickup_method", "cc1_lcu_fee", "cc1_fx_margin_original",
            "cc2_lcu_fee", "cc2_fx_margin_original", "cc1_lcu_fx_rate", "inter_lcu_bank_fx_original"]
    doublons = df.astype({c: object for c in cols}).duplicated(cols)
    print(f"Doublons stricts supprimés : {doublons.sum()}")
    return df[~doublons].copy()


def creer_cle_offre(df):
    cols = ["period", "corridor", "firm", "product", "payout_currency", "speed_actual",
            "sending_location", "pickup_method", "coverage", "variante", "send_currency"]
    texte = df[cols].astype(object).fillna("").astype(str).agg("|".join, axis=1)
    cle = texte.map(lambda t: hashlib.md5(t.encode("utf-8")).hexdigest())
    # offres identiques sur tous ces attributs mais avec des frais différents :
    # numéro d'ordre pour garder une clé unique
    df["rang_doublon"] = cle.groupby(cle).cumcount() + 1
    df["offre_key"] = cle.where(df["rang_doublon"] == 1, cle + "-" + df["rang_doublon"].astype(str))
    return df


def marquer_suivi_continu(df):
    df["suivi_continu"] = df.groupby("corridor")["period"].transform("nunique") > 2
    return df


def extraire_dimensions(df):
    colonnes_pays = ["name", "region", "income", "lending", "g8g20"]
    morceaux = []
    for cote in ("source", "destination"):
        d = df[[f"{cote}_code"] + [f"{cote}_{c}" for c in colonnes_pays]].copy()
        d.columns = ["iso3"] + colonnes_pays
        morceaux.append(d)
    dim_pays = (pd.concat(morceaux).dropna(subset=["iso3"])
                .groupby("iso3").agg(lambda s: s.dropna().value_counts().idxmax()
                                     if s.notna().any() else pd.NA).reset_index()
                .rename(columns={"name": "nom_pays"}))
    dim_pays["dans_perimetre"] = dim_pays["iso3"].isin(PERIMETRE_ISO3)

    dim_op = (df.groupby("firm").agg(
        firm_type=("firm_type", lambda s: s.value_counts().idxmax()),
        variantes_nom=("firm_original", lambda s: " | ".join(sorted(s.dropna().unique()))),
        nb_offres=("firm", "size")).reset_index())

    a_retirer = [f"{c}_{x}" for c in ("source", "destination") for x in colonnes_pays]
    return df.drop(columns=a_retirer), dim_pays, dim_op


# =============================================================================
def main():
    df = lire_bronze()
    print(f"Bronze lu : {len(df)} lignes, {df.shape[1]} colonnes")

    # A. structure
    df = renommer_colonnes(df)
    df = nettoyer_texte(df)
    df = filtrer_perimetre(df)
    print(f"Après périmètre : {len(df)} lignes")
    df = remplacer_points(df)
    df = standardiser_dates(df)
    df = normaliser_operateurs(df)
    df = convertir_numeriques(df)

    # B. texte
    df = traiter_product(df)
    df = traiter_sending_location(df)
    df = traiter_speed(df)
    df = traiter_coverage(df)
    df = traiter_pickup(df)
    df = traiter_notes(df)

    # C + D. devises, taux, montants
    df = traiter_montants_et_devise(df)
    taux = charger_taux_bis()
    df = determiner_payout_currency(df, taux)
    df = controler_taux_interbancaire(df, taux)
    df = traiter_frais(df)            # avant la correction des marges (valeurs publiées)
    df = traiter_marges(df, taux)
    df = traiter_taux_appliques(df)
    df = traiter_cout_total(df)

    # E. clé et dimensions
    df = supprimer_doublons_stricts(df)
    df = creer_cle_offre(df)
    df = marquer_suivi_continu(df)
    df, dim_pays, dim_op = extraire_dimensions(df)
    df = df.drop(columns=["mois"])

    # ---------------- rapport ----------------
    print("\n===== CONTRÔLES =====")
    print(f"Opérateurs : {df['firm_original'].nunique()} noms -> {df['firm'].nunique()}")
    print(f"payout_currency trouvée : {df['payout_currency'].notna().mean():.1%} "
          f"(par source : {df['payout_source'].value_counts(dropna=False).to_dict()})")
    print(f"Taux interbancaires remplacés par la BIS : {df['inter_fx_remplace'].sum()} | "
          f"taux exprimés dans une autre devise que la note (gardés) : "
          f"{df['devise_note_differente'].sum()}")
    for k in ("cc1", "cc2"):
        print(f"[{k}] frais recalculés : {df[f'{k}_fee_recalcule'].sum()} | "
              f"marges imputées : {df[f'{k}_fx_margin_imputed'].sum()} | "
              f"taux 1,0 suspects : {df[f'{k}_lcu_fx_rate_suspect'].sum()} | "
              f"coûts nuls restants : {df[f'{k}_total_cost_pct'].isna().sum()}")
    print(f"Promotions : {df['promo'].sum()} | marché parallèle : {df['marche_parallele'].sum()}")
    print(f"cc2 non disponible : {(~df['cc2_disponible']).sum()} | "
          f"coût incomplet (EUR hors zone euro) : {(~df['cout_complet']).sum()}, "
          f"dont ajusté avec la marge médiane locale : {df['cout_ajuste_applique'].sum()}")
    non_imputees = ~df["cc1_fx_margin_imputed"] & ~df["marche_parallele"] & ~df["inter_fx_remplace"]
    incoherent = non_imputees & (df["ecart_cout_cc1"] > 1)
    print(f"Écart > 1 point coût cc1 recalculé / publié (lignes non imputées) : {incoherent.sum()}")
    if incoherent.any():
        print(df.loc[incoherent, ["corridor", "period", "firm", "ecart_cout_cc1"]]
              .sort_values("ecart_cout_cc1", ascending=False).head(5).to_string(index=False))
    remplaces = df[df["inter_fx_remplace"]]
    if len(remplaces):
        print("Taux interbancaires remplacés, par corridor et source de la devise (top 10) :")
        print(remplaces.groupby(["corridor", "payout_currency", "payout_source"]).size()
              .sort_values(ascending=False).head(10).to_string())
    print(f"Offres en plusieurs exemplaires (frais différents), numérotées : "
          f"{(df['rang_doublon'] > 1).sum()}")
    print(f"Doublons de offre_key : {df['offre_key'].duplicated().sum()}")
    print(f"Corridors non continus : {sorted(df.loc[~df['suivi_continu'], 'corridor'].unique())}")
    print("\n===== VALEURS NON RECONNUES (à me renvoyer) =====")
    print("\n".join(rapport) if rapport else "Aucune")

    DOSSIER_SILVER.mkdir(parents=True, exist_ok=True)
    df.to_csv(DOSSIER_SILVER / "rpw.csv", index=False, encoding="utf-8")
    dim_pays.to_csv(DOSSIER_SILVER / "dim_pays_rpw.csv", index=False, encoding="utf-8")
    dim_op.to_csv(DOSSIER_SILVER / "dim_operateur.csv", index=False, encoding="utf-8")
    print(f"\nÉcrit : rpw.csv ({len(df)} lignes, {df.shape[1]} colonnes), "
          f"dim_pays_rpw.csv ({len(dim_pays)}), dim_operateur.csv ({len(dim_op)})")


if __name__ == "__main__":
    main()
