"""
Fonctions communes aux 3 fichiers BIS de la source 4
(Consumer prices, Central bank policy rates, Bilateral exchange rates).
"""
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parents[2]
DOSSIER_BRONZE_BIS = RACINE / "data" / "bronze" / "bis_S4"
DOSSIER_SILVER_BIS = RACINE / "data" / "silver" / "bis"

# Périmètre du projet en codes ISO2 (codes utilisés par la BIS) + XM = zone euro
PERIMETRE_ISO2 = {
    "AT", "BE", "BG", "HR", "CZ", "EE", "FR", "DE", "HU", "IT", "LV", "LT",
    "NL", "NO", "PL", "PT", "RO", "ES", "SE", "CH", "TR", "UA", "GB",
}
ZONE_EURO = "XM"


def lire_csv_bis(nom_fichier: str, colonnes=None) -> pd.DataFrame:
    """Lit un CSV BIS en texte. Les en-têtes 'FREQ:Frequency' deviennent 'freq'."""
    chemin = DOSSIER_BRONZE_BIS / nom_fichier
    df = pd.read_csv(chemin, dtype=str, encoding="utf-8", low_memory=False)
    df.columns = [c.split(":")[0].strip().lower() for c in df.columns]
    if colonnes is not None:
        df = df[colonnes]
    return df


def separer_code_libelle(serie: pd.Series) -> tuple[pd.Series, pd.Series]:
    """'AT: Austria' -> ('AT', 'Austria'). Si pas de ':', le libellé est vide."""
    parties = serie.str.split(":", n=1, expand=True)
    code = parties[0].str.strip()
    libelle = parties[1].str.strip() if parties.shape[1] > 1 else pd.Series(pd.NA, index=serie.index)
    return code, libelle


def ecrire_silver(df: pd.DataFrame, nom_fichier: str) -> Path:
    DOSSIER_SILVER_BIS.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER_SILVER_BIS / nom_fichier
    df.to_parquet(chemin, index=False)
    print(f"Écrit : {chemin}  ({len(df)} lignes, {df.shape[1]} colonnes)")
    return chemin
