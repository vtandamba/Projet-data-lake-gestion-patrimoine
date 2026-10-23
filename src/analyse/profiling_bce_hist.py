"""
Profiling BRONZE — BCE / Taux de change de référence de l'euro
==============================================================
Source : Banque centrale européenne (eurofxref-hist.csv), format "large" :
une colonne Date + une colonne par devise (1 EUR = X unités de la devise).

Objectif : ANALYSER les données brutes AVANT transformation. On ne modifie
rien, on observe. Cette source est une SÉRIE TEMPORELLE, donc le profiling
regarde des choses particulières :
- la plage de dates couverte ;
- les valeurs manquantes par devise ;
- les devises "mortes" (colonnes quasi vides : monnaies disparues,
  remplacées par l'euro, ou cotation suspendue comme le rouble) ;
- les doublons de date.

Entrée : data/bronze/bronze_eurofxref-hist.csv
Sortie : affichage console + rapport dans reports/profiling_bce_hist.txt

À placer dans : src/analyse/profiling_bce_hist.py
Lancer depuis la racine du projet :  python src/analyse/profiling_bce_hist.py
"""

from pathlib import Path
import pandas as pd

# ------------------------------------------------------------------
# Chemins
# ------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRONZE_FILE = PROJECT_ROOT / "data" / "bronze" / "bronze_eurofxref-hist.csv"

REPORTS_DIR = PROJECT_ROOT / "reports"
REPORT_FILE = REPORTS_DIR / "profiling_bce_hist.txt"

_lignes_rapport = []


def sortie(texte=""):
    print(texte)
    _lignes_rapport.append(texte)


def titre(t):
    sortie("\n" + "=" * 60)
    sortie(t)
    sortie("=" * 60)


def main():
    titre("PROFILING BRONZE — BCE (taux de change de l'euro)")

    # --------------------------------------------------------------
    # Chargement
    #   La BCE écrit "N/A" pour une devise non cotée ce jour-là :
    #   pandas le lit comme valeur manquante (comportement par défaut, OK ici).
    # --------------------------------------------------------------
    if not BRONZE_FILE.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {BRONZE_FILE}\n"
            "Vérifie le nom/emplacement du fichier bronze."
        )

    df = pd.read_csv(BRONZE_FILE)

    # Le fichier BCE a souvent une colonne vide en fin de ligne (virgule
    # finale) -> pandas la nomme "Unnamed: X". On retire ces colonnes vides.
    colonnes_vides = [c for c in df.columns if str(c).startswith("Unnamed")]
    if colonnes_vides:
        df = df.drop(columns=colonnes_vides)
        sortie(f"[info] Colonne(s) vide(s) retirée(s) : {colonnes_vides}")

    # --------------------------------------------------------------
    # 1. Dimensions
    # --------------------------------------------------------------
    titre("1. DIMENSIONS")
    sortie(f"Nombre de lignes (jours)   : {df.shape[0]}")
    sortie(f"Nombre de colonnes         : {df.shape[1]}")
    devises = [c for c in df.columns if c != "Date"]
    sortie(f"Nombre de devises          : {len(devises)}")

    # --------------------------------------------------------------
    # 2. Plage de dates
    # --------------------------------------------------------------
    titre("2. PLAGE DE DATES")
    if "Date" in df.columns:
        dates = pd.to_datetime(df["Date"], errors="coerce")
        sortie(f"Date la plus ancienne : {dates.min().date()}")
        sortie(f"Date la plus récente  : {dates.max().date()}")
        sortie(f"Nombre de dates       : {dates.nunique()}")
        nb_dates_invalides = dates.isna().sum()
        if nb_dates_invalides:
            sortie(f"[!] Dates non reconnues : {nb_dates_invalides}")
    else:
        sortie("[!] Pas de colonne 'Date' trouvée — à vérifier.")

    # --------------------------------------------------------------
    # 3. Doublons de date
    # --------------------------------------------------------------
    titre("3. DOUBLONS")
    sortie(f"Lignes entièrement dupliquées : {df.duplicated().sum()}")
    if "Date" in df.columns:
        sortie(f"Doublons sur la Date          : {df['Date'].duplicated().sum()}")

    # --------------------------------------------------------------
    # 4. Valeurs manquantes par devise (triées : les plus vides en haut)
    # --------------------------------------------------------------
    titre("4. VALEURS MANQUANTES PAR DEVISE")
    manquantes = df[devises].isna().sum().sort_values(ascending=False)
    for devise, n in manquantes.items():
        pct = 100 * n / len(df)
        sortie(f" - {devise:6} {n:6} manquantes ({pct:5.1f} %)")

    # --------------------------------------------------------------
    # 5. Devises "mortes" vs actives
    #    (morte = pas de valeur sur la dernière ligne disponible)
    # --------------------------------------------------------------
    titre("5. DEVISES ACTIVES / MORTES")
       
    idx_recent = pd.to_datetime(df["Date"], errors="coerce").idxmax()
    derniere_ligne = df.loc[idx_recent, devises]
    actives = [d for d in devises if pd.notna(derniere_ligne[d])]
    mortes = [d for d in devises if pd.isna(derniere_ligne[d])]
    sortie(f"Devises actives aujourd'hui ({len(actives)}) :")
    sortie("   " + ", ".join(actives))
    sortie(f"\nDevises mortes / suspendues ({len(mortes)}) :")
    sortie("   " + ", ".join(mortes) if mortes else "   (aucune)")

    # --------------------------------------------------------------
    # 6. Aperçu (début et fin du fichier)
    # --------------------------------------------------------------
    titre("6. APERÇU")
    colonnes_apercu = ["Date"] + devises[:5]   # Date + 5 premières devises
    sortie("Premières lignes :")
    sortie(df[colonnes_apercu].head(3).to_string(index=False))
    sortie("\nDernières lignes :")
    sortie(df[colonnes_apercu].tail(3).to_string(index=False))

    titre("FIN DU PROFILING")

    # --------------------------------------------------------------
    # Écriture du rapport
    # --------------------------------------------------------------
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text("\n".join(_lignes_rapport), encoding="utf-8")
    print(f"\n[OK] Rapport enregistré : {REPORT_FILE}")


if __name__ == "__main__":
    main()