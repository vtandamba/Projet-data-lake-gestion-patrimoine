# Image du pipeline reproductible SILVER -> GOLD -> PostgreSQL.
# Construite et lancée par docker compose : docker compose run --rm gold
# (construit data/gold depuis data/silver, puis charge silver et gold dans la base).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# dépendances des scripts src/gold/ (aucun ne lit ni n'écrit de parquet : pas de pyarrow)
RUN pip install "pandas>=2.0" "numpy" "sqlalchemy>=2.0" "psycopg2-binary>=2.9"

# code du pipeline ; data/silver, data/gold et reports sont montés en volume (non copiés)
COPY src/ src/
COPY sql/ sql/

CMD ["sh", "-c", "python src/gold/construire_gold.py && python src/gold/charger_postgres.py"]
