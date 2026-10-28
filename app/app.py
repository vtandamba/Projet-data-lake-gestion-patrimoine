"""
Application conseiller - data lake « gestion patrimoniale internationale »
=========================================================================
Interface de simulation pour un conseiller patrimonial : où transférer le patrimoine d'un client
résidant en France, selon le coût, le risque, la conformité et la fiscalité.

Prérequis : base démarrée (docker compose up -d) et chargée (python src/gold/charger_postgres.py),
puis dans le venv : pip install streamlit plotly

Lancer depuis la racine du dépôt :
    streamlit run app/app.py
L'application s'ouvre dans le navigateur (http://localhost:8501).
"""
import streamlit as st

from commun import NOM_CABINET, appliquer_style

st.set_page_config(page_title=f"{NOM_CABINET} - simulateur", page_icon=":material/public:", layout="wide")
appliquer_style()

pages = [
    st.Page("vues/simulation.py", title="Simulation client", icon=":material/calculate:", default=True),
    st.Page("vues/fiche_pays.py", title="Fiche pays", icon=":material/public:"),
    st.Page("vues/prestataires.py", title="Prestataires", icon=":material/account_balance:"),
    st.Page("vues/donnees.py", title="Données et qualité", icon=":material/database:"),
]
st.navigation(pages).run()
