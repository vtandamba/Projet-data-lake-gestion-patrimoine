"""
Zone GOLD - éléments communs à toutes les tables gold.

Les tables gold sont construites à partir des CSV silver et écrites en CSV dans
data/gold/ (elles seront chargées ensuite dans PostgreSQL). Toutes les jointures se
font sur le code pays ISO3.
"""
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

RACINE = Path(__file__).resolve().parents[2]
SILVER = RACINE / "data" / "silver"
GOLD = RACINE / "data" / "gold"
REPORTS = RACINE / "reports"

PAYS_ENVOI = "FRA"   # le client du cabinet réside en France

# Périmètre : ISO3 -> (ISO2, nom français)
PERIMETRE = {
    "AUT": ("AT", "Autriche"), "BEL": ("BE", "Belgique"), "BGR": ("BG", "Bulgarie"),
    "HRV": ("HR", "Croatie"), "CZE": ("CZ", "Tchéquie"), "EST": ("EE", "Estonie"),
    "FRA": ("FR", "France"), "DEU": ("DE", "Allemagne"), "HUN": ("HU", "Hongrie"),
    "ITA": ("IT", "Italie"), "LVA": ("LV", "Lettonie"), "LTU": ("LT", "Lituanie"),
    "NLD": ("NL", "Pays-Bas"), "NOR": ("NO", "Norvège"), "POL": ("PL", "Pologne"),
    "PRT": ("PT", "Portugal"), "ROU": ("RO", "Roumanie"), "ESP": ("ES", "Espagne"),
    "SWE": ("SE", "Suède"), "CHE": ("CH", "Suisse"), "TUR": ("TR", "Türkiye"),
    "UKR": ("UA", "Ukraine"), "GBR": ("GB", "Royaume-Uni"),
}

ADOPTION_EURO = {
    "AUT": "1999-01-01", "BEL": "1999-01-01", "DEU": "1999-01-01", "ESP": "1999-01-01",
    "FRA": "1999-01-01", "ITA": "1999-01-01", "NLD": "1999-01-01", "PRT": "1999-01-01",
    "EST": "2011-01-01", "LVA": "2014-01-01", "LTU": "2015-01-01", "HRV": "2023-01-01",
    "BGR": "2026-01-01",
}
# Membres de l'Union européenne dans le périmètre (hors NOR, CHE, TUR, UKR, GBR)
MEMBRES_UE = {"AUT", "BEL", "BGR", "HRV", "CZE", "EST", "FRA", "DEU", "HUN", "ITA", "LVA",
              "LTU", "NLD", "POL", "PRT", "ROU", "ESP", "SWE"}
# Zone SEPA : UE + Norvège, Suisse, Royaume-Uni (pas la Türkiye ni l'Ukraine)
ZONE_SEPA = MEMBRES_UE | {"NOR", "CHE", "GBR"}

# Méthode d'estimation du coût d'un transfert depuis la France (note de cadrage v2, § 7)
GROUPES_COUT = {
    "A": ("sepa", "Zone euro : virement SEPA au prix d'un virement national, sans change"),
    "B": ("rpw_zone_euro", "Hors euro : médiane des offres RPW envoyées en EUR depuis la zone euro"),
    "C": ("rpw_autre_devise", "Hors euro : marge de change RPW observée depuis une autre devise"),
    "D": ("estimation", "Hors euro, non observé : marge médiane des envois en EUR vers d'autres "
                        "devises européennes"),
}
GROUPE_PAR_PAYS = {
    **{p: "A" for p in ADOPTION_EURO if p != PAYS_ENVOI},
    "HUN": "B", "ROU": "B", "TUR": "B", "UKR": "B",
    "POL": "C",
    "GBR": "D", "CHE": "D", "NOR": "D", "SWE": "D", "CZE": "D",
}


def lire_silver(chemin_relatif: str, **kwargs) -> pd.DataFrame:
    chemin = SILVER / chemin_relatif
    if not chemin.exists():
        raise SystemExit(f"[X] Table silver absente : {chemin}")
    return pd.read_csv(chemin, low_memory=False, **kwargs)


class Rapport:
    """Affiche et enregistre le rapport d'une table gold dans reports/gold_<nom>.txt."""

    def __init__(self, nom: str):
        self.nom, self.lignes = nom, []

    def log(self, texte=""):
        print(texte)
        self.lignes.append(str(texte))

    def ecrire(self):
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / f"gold_{self.nom}.txt").write_text("\n".join(self.lignes), encoding="utf-8")


def ecrire_gold(df: pd.DataFrame, nom: str, rapport: Rapport) -> Path:
    GOLD.mkdir(parents=True, exist_ok=True)
    chemin = GOLD / f"{nom}.csv"
    df.to_csv(chemin, index=False, encoding="utf-8")
    rapport.log(f"\n[OK] Gold enregistré : data/gold/{nom}.csv  ({len(df)} lignes, {df.shape[1]} colonnes)")
    rapport.ecrire()
    return chemin


# ---------------------------------------------------------------------------
# Fonctions partagées par plusieurs tables gold
# ---------------------------------------------------------------------------
# Anciennes devises des pays passés à l'euro (pour les années avant adoption)
DEVISE_AVANT_EURO = {"HRV": "HRK", "BGR": "BGN", "LTU": "LTL", "LVA": "LVL", "EST": "EEK"}


def lire_dim_pays() -> pd.DataFrame:
    chemin = GOLD / "dim_pays.csv"
    if not chemin.exists():
        raise SystemExit("[X] data/gold/dim_pays.csv absent : lancer d'abord src/gold/gold_dim_pays.py")
    return pd.read_csv(chemin, parse_dates=["date_adoption_euro"])


def taux_quotidiens_par_eur(devises) -> pd.DataFrame:
    """Taux journaliers en unités de devise pour 1 EUR : BCE (Lucas), et hryvnia (UAH)
    reconstituée à partir de la BIS (UAH/USD divisé par EUR/USD), absente de la BCE.
    Colonnes : date, devise, taux_pour_1_eur, source."""
    bce = lire_silver("lucas/ecb_exchange_rates-silver.csv", parse_dates=["date"])
    bce = bce[bce["currency_code"].isin(devises)].rename(
        columns={"currency_code": "devise", "rate_per_eur": "taux_pour_1_eur"})
    bce["source"] = "BCE"
    morceaux = [bce[["date", "devise", "taux_pour_1_eur", "source"]]]
    if "UAH" in devises:
        bis = lire_silver("bis/bis_xru_daily.csv", usecols=["iso3", "date", "taux_change_lcu_usd"],
                          parse_dates=["date"])
        ua = bis[bis["iso3"] == "UKR"].set_index("date")["taux_change_lcu_usd"]
        eu = bis[bis["iso3"] == "EMU"].set_index("date")["taux_change_lcu_usd"]
        uah = (ua / eu).dropna().rename("taux_pour_1_eur").reset_index()
        uah = uah[uah["date"] >= "1999-01-01"]
        uah["devise"], uah["source"] = "UAH", "BIS (UAH/USD ÷ EUR/USD)"
        morceaux.append(uah[["date", "devise", "taux_pour_1_eur", "source"]])
    return pd.concat(morceaux, ignore_index=True).sort_values(["devise", "date"]).reset_index(drop=True)


def taux_directeur_applicable_mensuel(dim: pd.DataFrame) -> pd.DataFrame:
    """Taux directeur applicable par pays et par mois (BIS CBPOL mensuel) :
    - pays en zone euro à cette date : taux de la BCE (série EMU) ;
    - sinon : taux de la banque centrale nationale, s'il existe.
    Colonnes : iso3, date, taux_directeur_pct, taux_bce_pct, source_taux_directeur."""
    cb = lire_silver("bis/bis_cbpol.csv", usecols=["iso3", "date", "taux_directeur_pct"],
                     parse_dates=["date"])
    bce = cb[cb["iso3"] == "EMU"].set_index("date")["taux_directeur_pct"]
    mois = pd.date_range("2003-01-01", cb["date"].max(), freq="MS")
    grille = pd.MultiIndex.from_product([dim["iso3"], mois], names=["iso3", "date"]).to_frame(index=False)
    grille = grille.merge(cb, on=["iso3", "date"], how="left")
    adoption = grille["iso3"].map(dim.set_index("iso3")["date_adoption_euro"])
    en_euro = grille["date"] >= adoption
    grille["taux_bce_pct"] = grille["date"].map(bce)
    grille["source_taux_directeur"] = "banque centrale nationale"
    grille.loc[en_euro, "taux_directeur_pct"] = grille.loc[en_euro, "taux_bce_pct"]
    grille.loc[en_euro, "source_taux_directeur"] = "BCE (zone euro)"
    grille.loc[grille["taux_directeur_pct"].isna(), "source_taux_directeur"] = "absent"
    return grille
