"""
Exécute les requêtes d'analyse de sql/analyses.sql sur PostgreSQL
=================================================================
Chaque requête du fichier commence par une ligne d'en-tête :
    -- @<code> | <question> | <visuel> | <catégorie>
Le script affiche, pour chaque requête, la question, le résultat et le temps d'exécution,
et enregistre le résultat dans reports/analyses/<code>.csv (réutilisable dans le rapport
et le notebook).

Prérequis : base démarrée (docker compose up -d) et chargée (python src/gold/charger_postgres.py).

Lancer depuis la racine du dépôt :
    python src/analyse/executer_requetes.py            # toutes les requêtes
    python src/analyse/executer_requetes.py Q08 Q14    # seulement celles-ci
"""
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

sys.stdout.reconfigure(encoding="utf-8")

RACINE = Path(__file__).resolve().parents[2]
FICHIER_SQL = RACINE / "sql" / "analyses.sql"
SORTIE = RACINE / "reports" / "analyses"
URL = os.environ.get("DATABASE_URL", "postgresql+psycopg2://data_lake:data_lake@localhost:5434/data_lake")
EN_TETE = re.compile(r"^-- @(\w+) \| (.+?) \| (.+?) \| (.+)$", re.MULTILINE)


def lire_requetes() -> list[dict]:
    """Découpe le fichier SQL en requêtes à partir des lignes d'en-tête « -- @code | ... »."""
    contenu = FICHIER_SQL.read_text(encoding="utf-8")
    entetes = list(EN_TETE.finditer(contenu))
    requetes = []
    for i, m in enumerate(entetes):
        fin = entetes[i + 1].start() if i + 1 < len(entetes) else len(contenu)
        sql = contenu[m.end():fin]
        # on retire le bandeau de la partie suivante (lignes « -- ===== » et titres)
        sql = re.split(r"\n-- =+\n", sql)[0].strip()
        requetes.append({"code": m.group(1), "question": m.group(2), "visuel": m.group(3),
                         "categorie": m.group(4), "sql": sql})
    return requetes


def main():
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.max_colwidth", 45)

    choix = {c.upper() for c in sys.argv[1:]}
    requetes = [r for r in lire_requetes() if not choix or r["code"] in choix]
    if not requetes:
        raise SystemExit(f"[X] Aucune requête trouvée pour {sorted(choix)}")

    SORTIE.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL)
    bilan = []
    for r in requetes:
        print(f"\n{'=' * 100}\n{r['code']} - {r['question']}\n"
              f"    catégorie : {r['categorie']}   |   visuel : {r['visuel']}\n{'=' * 100}")
        debut = time.time()
        try:
            with engine.connect() as c:
                df = pd.read_sql(text(r["sql"]), c)
        except Exception as e:                      # on continue avec les requêtes suivantes
            print(f"[X] ERREUR : {str(e).splitlines()[0]}")
            bilan.append((r["code"], "ERREUR", 0))
            continue
        duree = time.time() - debut
        print(df.head(30).to_string(index=False))
        if len(df) > 30:
            print(f"... ({len(df) - 30} lignes de plus dans le CSV)")
        df.to_csv(SORTIE / f"{r['code']}.csv", index=False, encoding="utf-8")
        print(f"-> {len(df)} lignes, {duree:.2f} s, reports/analyses/{r['code']}.csv")
        bilan.append((r["code"], "OK", len(df)))

    print(f"\n{'=' * 100}\nBilan")
    for code, statut, n in bilan:
        print(f"  {code:<4} {statut:<7} {n:>5} lignes")
    erreurs = sum(1 for b in bilan if b[1] != "OK")
    print(f"{'[X]' if erreurs else '[OK]'} {len(bilan) - erreurs}/{len(bilan)} requêtes exécutées")


if __name__ == "__main__":
    main()
