"""
Transformation BRONZE -> SILVER — BCE / historique des taux de change
=====================================================================
Source : Banque centrale européenne — taux de change de référence de l'euro
(eurofxref-hist.csv), format "large" : une colonne Date + une colonne par devise.

Objectif : produire une table SILVER propre, au format "long", prête pour
l'analyse de séries temporelles (volatilité, tendances) et les jointures.

Transformations appliquées (= actions correctives à documenter) :
  1. Retrait de la colonne vide finale ("Unnamed: 42", due à la virgule finale)
  2. Conversion de la colonne Date en vrai type date
  3. Tri CHRONOLOGIQUE (le fichier source est trié du + récent au + ancien)
  4. Passage format LARGE -> LONG : une ligne = (date, devise, taux)
  5. Suppression des lignes sans taux (devise non cotée ce jour-là / morte)
  6. Typage du taux en décimal

Entrée : data/bronze/bronze_eurofxref-hist.csv
Sortie : data/silver/bce_hist_silver.csv
Rapport : reports/transform_bce_hist.txt

À placer dans : src/transformation/transform_bce_hist_silver.py
Lancer depuis la racine :  python src/transformation/transform_bce_hist_silver.py
"""

from pathlib import Path
import pandas as pd

# ------------------------------------------------------------------
# Chemins
# ------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRONZE_FILE = PROJECT_ROOT / "data" / "bronze" / "bronze_eurofxref-hist.csv"
SILVER_DIR = PROJECT_ROOT / "data" / "silver"
SILVER_FILE = SILVER_DIR / "bce_hist_silver.csv"

REPORTS_DIR = PROJECT_ROOT / "reports"
REPORT_FILE = REPORTS_DIR / "transform_bce_hist.txt"

_lignes_rapport = []


def sortie(texte=""):
    print(texte)
    _lignes_rapport.append(texte)


def main():
    sortie("=" * 60)
    sortie("TRANSFORMATION BCE — BRONZE -> SILVER")
    sortie("=" * 60)

    if not BRONZE_FILE.exists():
        raise FileNotFoundError(f"Fichier bronze introuvable : {BRONZE_FILE}")

    # --------------------------------------------------------------
    # Chargement (la BCE écrit "N/A" -> lu comme manquant par défaut)
    # --------------------------------------------------------------
    df = pd.read_csv(BRONZE_FILE)
    sortie(f"\n[AVANT] {df.shape[0]} lignes (jours), {df.shape[1]} colonnes")

    # --------------------------------------------------------------
    # Transformation 1 : retrait des colonnes vides ("Unnamed: X")
    # --------------------------------------------------------------
    colonnes_vides = [c for c in df.columns if str(c).startswith("Unnamed")]
    if colonnes_vides:
        df = df.drop(columns=colonnes_vides)
        sortie(f"[T1] Colonne(s) vide(s) retirée(s) : {colonnes_vides}")

    # --------------------------------------------------------------
    # Transformation 2 : Date en vrai type date
    # --------------------------------------------------------------
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    sortie("[T2] Colonne Date convertie en type date")

    # --------------------------------------------------------------
    # Transformation 3 : tri chronologique (source en ordre décroissant)
    # --------------------------------------------------------------
    df = df.sort_values("Date").reset_index(drop=True)
    sortie("[T3] Données triées par date croissante")
    sortie(f"     de {df['Date'].min().date()} à {df['Date'].max().date()}")

    # --------------------------------------------------------------
    # Transformation 4 : format LARGE -> LONG (melt)
    #   une ligne par couple (date, devise)
    # --------------------------------------------------------------
    df_long = df.melt(
        id_vars="Date",
        var_name="devise",
        value_name="taux",
    )
    df_long = df_long.rename(columns={"Date": "date"})
    nb_avant_drop = len(df_long)
    sortie(f"[T4] Passage en format long : {nb_avant_drop} lignes (date x devise)")

    # --------------------------------------------------------------
    # Transformation 5 : suppression des lignes sans taux
    #   (devise non cotée ce jour-là, ou devise morte après sa disparition)
    # --------------------------------------------------------------
    df_long["taux"] = pd.to_numeric(df_long["taux"], errors="coerce")
    df_long = df_long.dropna(subset=["taux"]).reset_index(drop=True)
    nb_supprimees = nb_avant_drop - len(df_long)
    sortie(f"[T5] Lignes sans taux supprimées : {nb_supprimees}")

    # --------------------------------------------------------------
    # Bilan APRÈS
    # --------------------------------------------------------------
    sortie(f"\n[APRÈS] {len(df_long)} lignes, {df_long.shape[1]} colonnes")
    sortie("Colonnes finales : " + ", ".join(df_long.columns))
    sortie(f"Nombre de devises présentes : {df_long['devise'].nunique()}")

    sortie("\nValeurs manquantes par colonne :")
    for col, n in df_long.isna().sum().items():
        sortie(f" - {col:10} {n}")

    sortie("\nAperçu (5 premières lignes) :")
    sortie(df_long.head(5).to_string(index=False))

    # --------------------------------------------------------------
    # Sauvegarde
    # --------------------------------------------------------------
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    df_long.to_csv(SILVER_FILE, index=False, encoding="utf-8-sig")

    sortie("\n" + "=" * 60)
    sortie("[OK] Fichier silver enregistré :")
    sortie(f"     {SILVER_FILE}")
    sortie("=" * 60)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text("\n".join(_lignes_rapport), encoding="utf-8")
    print(f"\n[OK] Rapport enregistré : {REPORT_FILE}")


if __name__ == "__main__":
    main()