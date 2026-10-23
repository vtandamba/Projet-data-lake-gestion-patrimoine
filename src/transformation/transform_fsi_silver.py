"""
Transformation BRONZE -> SILVER — Financial Secrecy Index (FSI 2026)
====================================================================
Objectif : nettoyer les données brutes du FSI et produire une table SILVER
propre, prête à être croisée avec les autres sources.

Transformations appliquées (= actions correctives à documenter) :
  0. Lecture robuste : le code "NA" (Namibie) n'est PAS pris pour un vide
  1. Conversion du code pays ISO 3166-1 alpha-2 -> alpha-3 (clé de jointure)
  2. Sélection des colonnes utiles (on jette les colonnes non exploitées)
  3. Renommage en noms clairs et cohérents
  4. Contrôle des types + arrondi du score à 2 décimales

Le script affiche un bilan AVANT / APRÈS et l'écrit dans un rapport
(reports/fsi_transformation.txt) pour l'analyse quantitative du barème.

Entrée : data/bronze/fsi_2026_raw.csv
Sortie : data/silver/fsi_2026_silver.csv
Rapport : reports/fsi_transformation.txt

À placer dans : src/transformation/transform_fsi_silver.py
Lancer depuis la racine du projet :
    python src/transformation/transform_fsi_silver.py

Dépendance : pycountry  (ajouter à requirements.txt : pycountry)
"""

from pathlib import Path
import pandas as pd
import pycountry

# ------------------------------------------------------------------
# Chemins
# ------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRONZE_FILE = PROJECT_ROOT / "data" / "bronze" / "fsi_2026_raw.csv"
SILVER_DIR = PROJECT_ROOT / "data" / "silver"
SILVER_FILE = SILVER_DIR / "fsi_2026_silver.csv"

# Un seul dossier reports/ à la racine, fichiers nommés <source>_<étape>.txt
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORT_FILE = REPORTS_DIR / "fsi_transformation.txt"

# ------------------------------------------------------------------
# Cas particuliers de codes pays non standard
# (le FSI inclut des juridictions que la norme ISO ne couvre pas)
# ------------------------------------------------------------------
OVERRIDES_ISO2_ISO3 = {
    "XK": "XKX",   # Kosovo : pas de code ISO officiel, XKX est la convention usuelle
    # Ajoute ici d'autres exceptions si le bilan en signale.
}

# On accumule les lignes pour les afficher ET les écrire dans le rapport.
_lignes_rapport = []


def sortie(texte=""):
    """Affiche à l'écran et mémorise la ligne pour le rapport."""
    print(texte)
    _lignes_rapport.append(texte)


def iso2_vers_iso3(code2: str) -> str | None:
    """Convertit un code ISO alpha-2 en alpha-3. Renvoie None si introuvable."""
    if not isinstance(code2, str):
        return None
    code2 = code2.strip().upper()

    # 1) cas particuliers connus
    if code2 in OVERRIDES_ISO2_ISO3:
        return OVERRIDES_ISO2_ISO3[code2]

    # 2) conversion standard via pycountry
    try:
        pays = pycountry.countries.get(alpha_2=code2)
        if pays is not None:
            return pays.alpha_3
    except Exception:
        pass

    return None  # non trouvé -> sera signalé dans le bilan


def main():
    sortie("=" * 60)
    sortie("TRANSFORMATION FSI 2026 — BRONZE -> SILVER")
    sortie("=" * 60)

    # --------------------------------------------------------------
    # Chargement
    # Transformation 0 : lecture robuste (sauve le code "NA" = Namibie)
    # --------------------------------------------------------------
    if not BRONZE_FILE.exists():
        raise FileNotFoundError(
            f"Fichier bronze introuvable : {BRONZE_FILE}\n"
            "Lance d'abord le script d'ingestion."
        )

    df = pd.read_csv(
        BRONZE_FILE,
        keep_default_na=False,
        na_values=["", "NaN", "null"],
    )
    nb_depart = len(df)
    sortie(f"\n[AVANT] {nb_depart} lignes, {df.shape[1]} colonnes")

    # --------------------------------------------------------------
    # Transformation 1 : conversion ISO2 -> ISO3
    # --------------------------------------------------------------
    df["iso3"] = df["jurisdiction_id"].apply(iso2_vers_iso3)

    non_convertis = df[df["iso3"].isna()]
    if len(non_convertis) > 0:
        sortie(f"\n[!] {len(non_convertis)} code(s) pays non converti(s) :")
        for _, row in non_convertis.iterrows():
            sortie(f"    {row['jurisdiction_id']} = {row.get('jurisdiction_name_en', '?')}")
        sortie("    -> ajoute-les dans OVERRIDES_ISO2_ISO3 si besoin.")
    else:
        sortie("\n[OK] Tous les codes pays convertis en ISO3.")

    # --------------------------------------------------------------
    # Transformation 2 + 3 : sélection + renommage
    # --------------------------------------------------------------
    colonnes_gardees = {
        "iso3": "iso3",
        "jurisdiction_name_fr": "jurisdiction_name_fr",
        "index_score": "fsi_2026_score",
        "rank": "fsi_2026_rank",
    }

    df_silver = df[list(colonnes_gardees.keys())].rename(columns=colonnes_gardees)

    # --------------------------------------------------------------
    # Transformation 4 : contrôle des types + arrondi du score
    # --------------------------------------------------------------
    df_silver["fsi_2026_score"] = pd.to_numeric(
        df_silver["fsi_2026_score"], errors="coerce"
    ).round(2)                                      # arrondi à 2 décimales
    df_silver["fsi_2026_rank"] = pd.to_numeric(
        df_silver["fsi_2026_rank"], errors="coerce"
    ).astype("Int64")   # entier qui accepte les valeurs manquantes

    # --------------------------------------------------------------
    # Bilan APRÈS
    # --------------------------------------------------------------
    sortie(f"\n[APRÈS] {len(df_silver)} lignes, {df_silver.shape[1]} colonnes")
    sortie("\nColonnes finales : " + ", ".join(df_silver.columns))
    sortie("\nValeurs manquantes par colonne :")
    for col, n in df_silver.isna().sum().items():
        sortie(f" - {col:22} {n}")

    sortie("\nAperçu :")
    sortie(df_silver.head(5).to_string(index=False))

    # --------------------------------------------------------------
    # Sauvegarde du fichier silver
    # --------------------------------------------------------------
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    df_silver.to_csv(SILVER_FILE, index=False, encoding="utf-8-sig")

    sortie("\n" + "=" * 60)
    sortie("[OK] Fichier silver enregistré :")
    sortie(f"     {SILVER_FILE}")
    sortie("=" * 60)

    # --------------------------------------------------------------
    # Écriture du rapport de transformation
    # --------------------------------------------------------------
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text("\n".join(_lignes_rapport), encoding="utf-8")
    print(f"\n[OK] Rapport enregistré : {REPORT_FILE}")


if __name__ == "__main__":
    main()