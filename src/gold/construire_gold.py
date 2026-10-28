"""
Construit toute la zone GOLD, dans l'ordre des dépendances.

    python src/gold/construire_gold.py
"""
import subprocess
import sys
import time
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent
ORDRE = [
    "gold_dim_pays.py",               # 1 table de référence (utilisée par toutes les autres)
    "gold_cout_transfert_france.py",  # 2
    "gold_offres_rpw.py",             # 3
    "gold_cout_corridor_periode.py",  # 4 (après 3)
    "gold_taux_change_jour.py",       # 5
    "gold_indicateurs_mensuels.py",   # 6
    "gold_indicateurs_annuels.py",    # 7
    "gold_fiscalite_conformite.py",   # 8
    "gold_risque_pays.py",            # 9 (après 5 et 7)
]

for script in ORDRE:
    debut = time.time()
    print(f"\n{'=' * 70}\n{script}\n{'=' * 70}")
    res = subprocess.run([sys.executable, str(DOSSIER / script)], cwd=DOSSIER.parents[1])
    if res.returncode != 0:
        sys.exit(f"[X] Échec de {script} : construction arrêtée")
    print(f"({time.time() - debut:.1f} s)")
print("\n[OK] Zone gold construite : data/gold/ ; rapports : reports/gold_*.txt")
