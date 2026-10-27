"""
Transformations bronze -> silver des sources 1 (feuille 2), 2 et 8.

    Source 1 (feuille 2) : data/bronze/lucas/Countries.csv
        Feuille « Countries » du classeur Remittance Prices Worldwide (Banque mondiale) :
        classification des pays (région, revenu, G8/G20).
        Complétée par data/bronze/lucas/worldbank_countries_api.json (API Banque mondiale v2,
        téléchargée automatiquement si absente) et src/transformation/reference/country_currency.csv
        (table pays -> devise construite à la main).
    Source 2 : data/bronze/lucas/eurofxref-hist.xml
        Historique des taux de change de référence de la BCE (1 EUR = x devise).
    Source 8 : data/bronze/lucas/2026 Capital Gains Tax Rates in Europe  Tax Foundation Europe.csv
        Taux marginal supérieur d'imposition des plus-values en Europe (Tax Foundation, 2026).

Usage (depuis la racine du dépôt) :
    python src/transformation/transform_lucas_silver.py           (utilise la copie locale de l'API)
    python src/transformation/transform_lucas_silver.py --refresh (re-télécharge l'API Banque mondiale)

Conventions silver (communes à toutes les tables) :
    - noms de colonnes en snake_case, en anglais ; booléens préfixés par is_ ;
    - pays identifiés par iso3, nom de pays = nom Banque mondiale (country_name) ;
    - devises identifiées par currency_code (ISO 4217) ;
    - dates au format ISO AAAA-MM-JJ ; taux et pourcentages en fraction (0.275 = 27,5 %) ;
    - valeurs manquantes = null (cellule vide en CSV) ;
    - aucune colonne constante ni dérivable d'une autre : les informations valables pour toute
      une table (source, date de chargement, année fiscale...) sont dans _metadata.json.

Sorties (data/silver/lucas/) : <table>-silver.csv (UTF-8),
_metadata.json et un rapport de contrôle qualité (quality_report.txt).
"""
import csv
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
SOURCES_DIR = ROOT / "data" / "bronze" / "lucas"
SILVER_DIR = ROOT / "data" / "silver" / "lucas"

COUNTRIES_FILE = SOURCES_DIR / "Countries.csv"
WB_API_FILE = SOURCES_DIR / "worldbank_countries_api.json"
CURRENCY_REF_FILE = Path(__file__).resolve().parent / "reference" / "country_currency.csv"
ECB_FILE = SOURCES_DIR / "eurofxref-hist.xml"
TAX_FILE = SOURCES_DIR / "2026 Capital Gains Tax Rates in Europe  Tax Foundation Europe.csv"

WB_API_URL = "https://api.worldbank.org/v2/country"
LOADED_AT = datetime.now().replace(microsecond=0)

# Valeur utilisée par la Banque mondiale pour « non applicable / non renseigné »
WB_MISSING = ".."

# Codes ISO3 obsolètes présents dans la feuille Countries (doublons d'un code actuel)
OBSOLETE_ISO3 = {
    "ZAR": "Ancien code du Zaïre, doublon de COD (Congo, Dem. Rep.)",
    "ANT": "Antilles néerlandaises, dissoutes en 2010 (remplacées par CUW et SXM), aucune donnée",
}

# Groupes de revenu Banque mondiale, du plus faible au plus élevé
INCOME_GROUPS = ["Low income", "Lower middle income", "Upper middle income", "High income"]

# Pays du G7 (la Russie, marquée G8 dans la source, en est exclue depuis 2014)
G7_ISO3 = {"CAN", "FRA", "DEU", "ITA", "JPN", "GBR", "USA"}

# Devises BCE qui ne sont plus publiées : passage à l'euro, redénomination ou suspension
ECB_DISCONTINUED = {
    "CYP": "Passage à l'euro (2008)",
    "MTL": "Passage à l'euro (2008)",
    "SIT": "Passage à l'euro (2007)",
    "SKK": "Passage à l'euro (2009)",
    "EEK": "Passage à l'euro (2011)",
    "LVL": "Passage à l'euro (2014)",
    "LTL": "Passage à l'euro (2015)",
    "HRK": "Passage à l'euro (2023)",
    "BGN": "Passage à l'euro (2026)",
    "TRL": "Redénomination en TRY (2005)",
    "ROL": "Redénomination en RON (2005)",
    "RUB": "Publication suspendue par la BCE (mars 2022)",
}

# Codes ISO 3166-1 alpha-2 (source 8) -> alpha-3 (clé de jointure de la source 1)
ISO2_TO_ISO3 = {
    "AT": "AUT", "BE": "BEL", "BG": "BGR", "HR": "HRV", "CY": "CYP", "CZ": "CZE",
    "DK": "DNK", "EE": "EST", "FI": "FIN", "FR": "FRA", "DE": "DEU", "GE": "GEO",
    "GR": "GRC", "HU": "HUN", "IS": "ISL", "IE": "IRL", "IT": "ITA", "LV": "LVA",
    "LT": "LTU", "LU": "LUX", "MT": "MLT", "MD": "MDA", "NL": "NLD", "NO": "NOR",
    "PL": "POL", "PT": "PRT", "RO": "ROU", "SK": "SVK", "SI": "SVN", "ES": "ESP",
    "SE": "SWE", "CH": "CHE", "TR": "TUR", "UA": "UKR", "GB": "GBR",
}

report_lines = []
metadata = {}


def log(message=""):
    print(message)
    report_lines.append(message)


def save(df, name, source_name, source_files, **table_constants):
    """Écrit la table et range ses informations constantes dans _metadata.json."""
    constant_cols = [c for c in df.columns if df[c].nunique(dropna=False) <= 1 and len(df) > 1]
    assert not constant_cols, f"{name} : colonnes constantes {constant_cols}"
    assert not df.duplicated().any(), f"{name} : lignes en double"

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(SILVER_DIR / f"{name}-silver.csv", index=False, encoding="utf-8", date_format="%Y-%m-%d")
    metadata[f"{name}-silver"] = {
        "source_name": source_name,
        "source_files": source_files,
        "loaded_at": LOADED_AT.isoformat(),
        "rows": len(df),
        "columns": list(df.columns),
        **table_constants,
    }
    log(f"  -> {name}-silver.csv : {len(df)} lignes x {df.shape[1]} colonnes")


def clean_silver_dir():
    """Supprime les sorties précédentes pour ne pas laisser de tables obsolètes."""
    if SILVER_DIR.exists():
        for f in SILVER_DIR.glob("*"):
            if f.suffix in {".csv", ".parquet", ".txt", ".json"}:
                try:
                    f.unlink()
                except PermissionError:
                    print(f"  ATTENTION : {f.name} est ouvert dans un autre programme, non supprimé")


# --------------------------------------------------------------------------
# Référentiels utilisés par la source 1
# --------------------------------------------------------------------------
def load_wb_countries(refresh=False):
    """Région et groupe de revenu selon l'API Banque mondiale v2 (classification en vigueur
    au moment du téléchargement), stockés en bronze pour la reproductibilité."""
    if refresh or not WB_API_FILE.exists():
        response = requests.get(WB_API_URL, params={"format": "json", "per_page": 500}, timeout=60)
        response.raise_for_status()
        WB_API_FILE.write_text(response.text, encoding="utf-8")
        log(f"  API Banque mondiale téléchargée -> {WB_API_FILE.name}")

    _, entries = json.loads(WB_API_FILE.read_text(encoding="utf-8"))
    # L'API renvoie certains libellés avec un espace final (« Sub-Saharan Africa  »)
    api = pd.DataFrame(
        [{"iso3": e["id"],
          "region_api": e["region"]["value"].strip(),
          "income_group_api": e["incomeLevel"]["value"].strip()}
         for e in entries if e["region"]["value"].strip() != "Aggregates"]
    )
    api["income_group_api"] = api["income_group_api"].replace("Not classified", pd.NA)
    return api


def load_currency_reference():
    ref = pd.read_csv(CURRENCY_REF_FILE, dtype=str, keep_default_na=False).replace("", pd.NA)
    ref["valid_from"] = pd.to_datetime(ref["valid_from"], format="%Y-%m-%d")
    ref["valid_to"] = pd.to_datetime(ref["valid_to"], format="%Y-%m-%d")
    assert ref["currency_code"].str.fullmatch(r"[A-Z]{3}").all(), "Code devise invalide"
    assert not ref.duplicated(["iso3", "currency_code"]).any(), "Doublon pays/devise"
    # Une seule devise courante (sans date de fin) par pays
    current = ref[ref["valid_to"].isna()]
    assert current["iso3"].is_unique, "Plusieurs devises courantes pour un même pays"
    return ref


# --------------------------------------------------------------------------
# Source 1 (feuille 2) : classification des pays (Banque mondiale)
# --------------------------------------------------------------------------
def transform_countries(refresh_api=False):
    log("== Source 1 (feuille 2) : Countries.csv ==")

    # Ligne 1 = titre fusionné, qui contient la date de mise à jour (« updated Q3 2025 »)
    with open(COUNTRIES_FILE, encoding="cp1252") as f:
        title = f.readline() + f.readline()
    match = re.search(r"updated\s+Q([1-4])\s+(\d{4})", title)
    assert match, "Date de classification introuvable dans la ligne de titre"
    classification_quarter = f"{match.group(2)}-Q{match.group(1)}"
    log(f"  Classification Banque mondiale : {classification_quarter}")

    # Export Excel en Windows-1252, séparateur « ; », en-têtes en ligne 2.
    # Le titre étant sur 2 lignes physiques (retour à la ligne dans la cellule), on laisse
    # le parseur CSV gérer les guillemets et on saute le premier enregistrement.
    raw = pd.read_csv(COUNTRIES_FILE, sep=";", skiprows=1, encoding="cp1252", dtype=str)
    log(f"  Lu : {raw.shape[0]} lignes x {raw.shape[1]} colonnes")

    # Les 3 dernières colonnes (« ;;; » en fin de ligne) sont entièrement vides
    empty_cols = [c for c in raw.columns if raw[c].isna().all()]
    df = raw.drop(columns=empty_cols)
    log(f"  Colonnes vides supprimées : {empty_cols}")

    df = df.rename(columns={
        "ISO 3166-1 alpha-3 country code": "iso3",
        "Country name": "country_name",
        "Region": "region",
        "Income Group": "income_group",
        "Lending category": "lending_category",
        "G8/G20": "g8_g20",
    })
    for col in df.columns:
        df[col] = df[col].str.strip()
    df = df.replace(WB_MISSING, pd.NA)

    # Codes obsolètes / doublons
    df = df[~df["iso3"].isin(OBSOLETE_ISO3)].copy()
    for code, reason in OBSOLETE_ISO3.items():
        log(f"  Ligne supprimée {code} : {reason}")

    # Confrontation avec l'API Banque mondiale. Règle : une valeur manquante de la feuille RPW
    # n'est complétée par l'API que si les deux sources concordent sur toutes les valeurs
    # renseignées ; sinon elles ne décrivent pas la même chose et on ne les mélange pas.
    api = load_wb_countries(refresh_api)
    df = df.merge(api, on="iso3", how="left")

    # Région : aucune divergence -> les 75 régions absentes de la feuille RPW sont complétées
    region_diff = df[df["region"].notna() & df["region_api"].notna() & (df["region"] != df["region_api"])]
    assert region_diff.empty, f"Régions incohérentes RPW/API : {region_diff['iso3'].tolist()}"
    filled = df["region"].isna() & df["region_api"].notna()
    df.loc[filled, "region"] = df.loc[filled, "region_api"]
    log(f"  Régions complétées via l'API Banque mondiale : {int(filled.sum())}")

    # Groupe de revenu : la feuille RPW donne la classification de son trimestre, l'API celle
    # en vigueur aujourd'hui (révisée chaque 1er juillet). Si elles divergent, ce sont deux
    # millésimes différents : on garde la feuille RPW, cohérente avec la période des données
    # RPW, et on ne complète pas ses valeurs manquantes avec un autre millésime.
    income_diff = df[df["income_group"].notna() & df["income_group_api"].notna()
                     & (df["income_group"] != df["income_group_api"])]
    for _, r in income_diff.iterrows():
        log(f"  Groupe de revenu {r.iso3} : « {r.income_group} » ({classification_quarter}) / "
            f"« {r.income_group_api} » (API, classification actuelle)")
    not_filled = df[df["income_group"].isna()]
    if income_diff.empty:
        df.loc[not_filled.index, "income_group"] = not_filled["income_group_api"]
        log(f"  Groupes de revenu complétés via l'API : {int(not_filled['income_group_api'].notna().sum())}")
    else:
        log(f"  -> {len(income_diff)} pays ont changé de groupe : millésimes différents, "
            f"income_group conservé tel que publié en {classification_quarter}")
        for _, r in not_filled.iterrows():
            log(f"  Groupe de revenu {r.iso3} non classé en {classification_quarter} "
                f"(API actuelle : {r.income_group_api if pd.notna(r.income_group_api) else 'non classé'}) "
                f"-> laissé vide")
    df = df.drop(columns=["region_api", "income_group_api"])

    # G8/G20 -> booléens ; G8 remplacé par G7 (Russie exclue depuis 2014)
    df["is_g20"] = df["g8_g20"].isin(["G20", "G8/G20"])
    df["is_g7"] = df["iso3"].isin(G7_ISO3)
    df = df.drop(columns="g8_g20")

    # Groupe de revenu : uniquement les 4 libellés Banque mondiale (l'ordre Low < ... < High
    # se redonne au chargement, voir la documentation ; pas de colonne de rang en double)
    unknown = set(df["income_group"].dropna()) - set(INCOME_GROUPS)
    assert not unknown, f"Groupe de revenu inattendu : {unknown}"

    # Devise courante du pays (lien avec les taux BCE) et date depuis laquelle elle est en
    # vigueur, si elle a changé depuis 2011 (null = inchangée sur toute la période)
    currencies = load_currency_reference()
    current = currencies.loc[currencies["valid_to"].isna(), ["iso3", "currency_code", "valid_from"]]
    df = df.merge(current.rename(columns={"valid_from": "currency_since"}), on="iso3", how="left")
    missing_currency = df.loc[df["currency_code"].isna(), "iso3"].tolist()
    assert not missing_currency, f"Pays sans devise : {missing_currency}"

    # lending_category (IDA/IBRD/Blend) : sans lien avec l'objet du projet, non conservée
    df = df[["iso3", "country_name", "region", "income_group", "currency_code", "currency_since",
             "is_g20", "is_g7"]]

    assert df["iso3"].str.fullmatch(r"[A-Z]{3}").all(), "Code ISO3 invalide"
    assert df["iso3"].is_unique, "Code ISO3 en double"
    assert df["country_name"].is_unique, "Nom de pays en double"

    nulls = df.isna().sum()
    log(f"  Valeurs manquantes après nettoyage : {nulls[nulls > 0].to_dict() or 'aucune'}")
    save(df, "countries",
         source_name="World Bank - Remittance Prices Worldwide (feuille Countries) + API v2 (régions)",
         source_files=[COUNTRIES_FILE.name, WB_API_FILE.name, CURRENCY_REF_FILE.name],
         classification_quarter=classification_quarter)

    # Anciennes devises uniquement (la devise actuelle est déjà dans countries) :
    # nécessaire pour joindre les taux BCE à une date passée (passages à l'euro, redénominations)
    history = (
        currencies[currencies["valid_to"].notna() & currencies["iso3"].isin(df["iso3"])]
        [["iso3", "currency_code", "valid_from", "valid_to"]]
        .sort_values(["iso3", "valid_to"]).reset_index(drop=True)
    )
    save(history, "currency_history",
         source_name="Référentiel construit manuellement (ISO 4217), changements depuis 2011",
         source_files=[CURRENCY_REF_FILE.name])
    return df


# --------------------------------------------------------------------------
# Source 2 : taux de change de référence BCE
# --------------------------------------------------------------------------
def transform_ecb():
    log("\n== Source 2 : eurofxref-hist.xml ==")
    ns = {"e": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
    root = ET.parse(ECB_FILE).getroot()

    # Structure : <Cube time="AAAA-MM-JJ"><Cube currency="USD" rate="1.12"/>...</Cube>
    rows = [
        (day.get("time"), fx.get("currency"), fx.get("rate"))
        for day in root.iterfind(".//e:Cube[@time]", ns)
        for fx in day
    ]
    df = pd.DataFrame(rows, columns=["date", "currency_code", "rate_per_eur"])
    log(f"  Lu : {len(df)} cotations, {df['date'].nunique()} jours, {df['currency_code'].nunique()} devises")

    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    df["rate_per_eur"] = pd.to_numeric(df["rate_per_eur"], errors="raise")

    assert not df.duplicated(["date", "currency_code"]).any(), "Cotation en double"
    assert (df["rate_per_eur"] > 0).all(), "Taux négatif ou nul"

    # Trous de cotation anormaux (> 10 jours calendaires, hors week-ends/jours fériés)
    df = df.sort_values(["currency_code", "date"])
    gaps = df.groupby("currency_code")["date"].diff().dt.days
    for _, g in df.loc[gaps > 10].assign(gap_days=gaps[gaps > 10]).iterrows():
        log(f"  Trou de cotation {g.currency_code} : {int(g.gap_days)} jours avant le {g.date.date()}")

    coverage = df.groupby("currency_code")["date"].agg(["min", "max"])
    for code, reason in ECB_DISCONTINUED.items():
        log(f"  Devise discontinue {code} ({coverage.loc[code, 'min'].date()} -> "
            f"{coverage.loc[code, 'max'].date()}) : {reason}")

    # Pas de lignes EUR (taux = 1 constant), pas de taux inverse (1 / rate_per_eur) ni d'indicateur
    # de devise discontinue (la dernière date de cotation suffit) : ce serait de l'information
    # répétée sur chaque ligne. EUR = 1 est géré au moment de la jointure.
    df = df.reset_index(drop=True)
    save(df, "ecb_exchange_rates",
         source_name="European Central Bank - euro foreign exchange reference rates",
         source_files=[ECB_FILE.name],
         rate_definition="rate_per_eur = unités de devise pour 1 EUR ; EUR non listé (taux = 1)",
         discontinued_currencies=ECB_DISCONTINUED)
    return df


# --------------------------------------------------------------------------
# Source 8 : taux d'imposition des plus-values en Europe (Tax Foundation)
# --------------------------------------------------------------------------
def transform_capital_gains_tax(countries):
    log("\n== Source 8 : Capital Gains Tax Rates in Europe (Tax Foundation) ==")

    # Fichier mal échappé : chaque ligne est entièrement entourée de guillemets et les
    # guillemets internes sont doublés ("Austria (AT),""27.5%"",""-""").
    # On retire l'enveloppe, on dé-double les guillemets, puis on lit un CSV standard.
    lines = TAX_FILE.read_text(encoding="utf-8-sig").splitlines()
    fixed = [l[1:-1].replace('""', '"') if l.startswith('"') and l.endswith('"') else l for l in lines if l.strip()]
    df = pd.read_csv(io.StringIO("\n".join(fixed)), dtype=str, quoting=csv.QUOTE_MINIMAL)
    log(f"  Lu : {df.shape[0]} lignes x {df.shape[1]} colonnes")

    df = df.rename(columns={
        "Country": "country_raw",
        "Top Marginal Capital Gains Tax Rate": "rate_raw",
        "Additional Comments": "comments",
    })

    # « Austria (AT) » -> code ISO2 -> ISO3 (le nom Tax Foundation est remplacé par le nom BM)
    parts = df["country_raw"].str.extract(r"^\s*(?P<country_name_tf>.+?)\s*\((?P<iso2>[A-Z]{2})\)\s*$")
    assert parts.notna().all().all(), "Format de pays inattendu"
    df = pd.concat([parts, df.drop(columns="country_raw")], axis=1)
    df["iso3"] = df["iso2"].map(ISO2_TO_ISO3)
    assert df["iso3"].notna().all(), f"ISO2 sans correspondance : {df.loc[df['iso3'].isna(), 'iso2'].tolist()}"

    # « 27.5% » -> 0.275 (fraction, comme les autres taux du silver)
    rate_pct = df["rate_raw"].str.strip().str.rstrip("%").astype(float)
    assert rate_pct.between(0, 100).all()
    df["capital_gains_tax_rate"] = (rate_pct / 100).round(4)

    # « - » = pas de commentaire
    df["comments"] = df["comments"].str.strip().replace({"-": pd.NA, "": pd.NA})

    df = df.merge(countries[["iso3", "country_name"]], on="iso3", how="left")
    missing = df.loc[df["country_name"].isna(), "iso3"].tolist()
    assert not missing, f"Pays absents de la source 1 : {missing}"
    for _, r in df[df["country_name_tf"] != df["country_name"]].iterrows():
        log(f"  Nom harmonisé : « {r.country_name_tf} » (Tax Foundation) -> « {r.country_name} » (BM)")

    df = df[["iso3", "country_name", "capital_gains_tax_rate", "comments"]]
    assert df["iso3"].is_unique
    save(df, "capital_gains_tax_europe",
         source_name="Tax Foundation Europe - 2026 Capital Gains Tax Rates",
         source_files=[TAX_FILE.name],
         tax_year=2026,
         rate_definition="taux marginal supérieur d'imposition des plus-values, en fraction")
    return df


if __name__ == "__main__":
    clean_silver_dir()
    log(f"Transformation lancée le {LOADED_AT:%Y-%m-%d %H:%M:%S}\n")
    countries = transform_countries(refresh_api="--refresh" in sys.argv)
    transform_ecb()
    transform_capital_gains_tax(countries)
    (SILVER_DIR / "_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (SILVER_DIR / "quality_report.txt").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print("\nRapport : data/silver/lucas/quality_report.txt")
