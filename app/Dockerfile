# Image de l'application conseiller « Passerelle » (Streamlit) et du chargement PostgreSQL.
# Construite par docker compose (voir docker-compose.yml) : rien à lancer à la main.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /projet

COPY app/requirements-app.txt /tmp/requirements-app.txt
RUN pip install -r /tmp/requirements-app.txt

# code de l'application, requêtes SQL et thème ; les données sont montées en volume (non copiées)
COPY app/ app/
COPY sql/ sql/
COPY .streamlit/ .streamlit/
COPY src/gold/charger_postgres.py src/gold/charger_postgres.py

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
