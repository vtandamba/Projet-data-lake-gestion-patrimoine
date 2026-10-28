"""
Fonctions communes à toutes les pages de l'application conseiller.
Les données viennent de la base PostgreSQL du data lake (schémas silver et gold) et les requêtes
de sql/analyses.sql : l'application, le notebook et le rapport utilisent exactement les mêmes.
"""
import os
import re
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

RACINE = Path(__file__).resolve().parents[1]
URL = os.environ.get("DATABASE_URL", "postgresql+psycopg2://data_lake:data_lake@localhost:5434/data_lake")
EN_TETE = re.compile(r"^-- @(\w+) \| (.+?) \| (.+?) \| (.+)$", re.MULTILINE)

# palette (ordre fixe) et couleurs d'état ; mêmes couleurs que le notebook
S1, S2, S3, S4 = "#1f7a4d", "#86bf3a", "#2f86c1", "#e0972a"   # vert, vert anis, bleu, ocre (validés daltonisme)
BON, ATTENTION, CRITIQUE = "#0ca30c", "#fab219", "#d03b3b"
ENCRE_2, GRILLE = "#52514e", "#e4e3df"

# fonds de case (teintes claires, texte noir lisible) : vert = fiable / favorable, jaune = moyen,
# orange = estimé, rouge = défavorable
FOND_VERT, FOND_JAUNE, FOND_ORANGE, FOND_ROUGE = "#d9f0d9", "#fcefc7", "#fbdcc8", "#f6d0d0"

FIABILITE = {   # début du libellé de gold.cout_transfert_france.fiabilite -> (libellé, fond, explication)
    "élevée": ("SEPA", FOND_VERT, "Zone euro : pas de change (règlement SEPA)."),
    "bonne": ("observé", FOND_VERT, "Marge de change observée sur des envois depuis la zone euro (RPW)."),
    "moyenne": ("observé (autre devise)", FOND_JAUNE, "Observé sur des envois depuis une autre devise (RPW)."),
    "faible": ("estimé", FOND_ORANGE, "Aucune donnée pour ce pays : estimation (médiane des corridors européens)."),
}
FOND_NIVEAU_RISQUE = {"Faible": FOND_VERT, "Moyen": FOND_JAUNE, "Élevé": FOND_ROUGE}
FOND_CONFORMITE = {"Conforme": FOND_VERT, "À vérifier": FOND_JAUNE}
FONDS_PAR_VALEUR = {lib: fond for lib, fond, _ in FIABILITE.values()} | FOND_NIVEAU_RISQUE | FOND_CONFORMITE


@st.cache_resource
def moteur():
    return create_engine(URL)


@st.cache_data
def requetes() -> dict:
    """Découpe sql/analyses.sql en requêtes (même format que executer_requetes.py)."""
    contenu = (RACINE / "sql" / "analyses.sql").read_text(encoding="utf-8")
    entetes = list(EN_TETE.finditer(contenu))
    res = {}
    for i, m in enumerate(entetes):
        fin = entetes[i + 1].start() if i + 1 < len(entetes) else len(contenu)
        res[m.group(1)] = {"question": m.group(2), "sql": re.split(r"\n-- =+\n", contenu[m.end():fin])[0].strip()}
    return res


@st.cache_data(ttl=600, show_spinner=False)
def executer_sql(sql: str) -> pd.DataFrame:
    with moteur().connect() as c:
        return pd.read_sql(text(sql), c)


@st.cache_data(ttl=600, show_spinner=False)
def _sql_parametre(sql: str, parametres: tuple) -> pd.DataFrame:
    with moteur().connect() as c:
        return pd.read_sql(text(sql), c, params=dict(parametres))


def requete(sql: str, **parametres) -> pd.DataFrame:
    """Requête SQL directe avec paramètres liés (:nom), pour les pages de détail."""
    return _sql_parametre(sql, tuple(sorted(parametres.items())))


def executer(code: str, **parametres) -> pd.DataFrame:
    """Exécute une requête du fichier SQL en remplaçant ses paramètres (CTE « parametres » / « hypotheses »)."""
    sql = requetes()[code]["sql"]
    for nom, val in parametres.items():
        if isinstance(val, bool):
            sql, n = re.subn(rf"(TRUE|FALSE)(\s+AS {nom}\b)", rf"{str(val).upper()}\2", sql)
        else:
            sql, n = re.subn(rf"[\d.]+::numeric AS {nom}\b", f"{float(val):.6f}::numeric AS {nom}", sql)
        if n != 1:
            raise ValueError(f"Paramètre {nom} introuvable dans la requête {code}")
    return executer_sql(sql)


@st.cache_data
def carte_europe() -> dict:
    """Contours des pays d'Europe (GeoJSON local, d'après Natural Earth via johan/world.geo.json) :
    la carte s'affiche sans accès Internet."""
    import json
    return json.loads((Path(__file__).resolve().parent / "assets" / "europe.geo.json").read_text(encoding="utf-8"))


def verifier_connexion():
    try:
        executer_sql("select 1")
    except Exception as e:
        st.error("Impossible de se connecter à la base PostgreSQL du data lake.\n\n"
                 "Vérifier que le conteneur tourne (`docker compose up -d`) et que les tables sont "
                 f"chargées (`python src/gold/charger_postgres.py`).\n\nDétail : {str(e).splitlines()[0]}")
        st.stop()


def badge_fiabilite(libelle: str) -> str:
    """Libellé court de la fiabilité du coût (SEPA, observé, estimé...)."""
    for cle, (lib, _, _) in FIABILITE.items():
        if str(libelle).startswith(cle):
            return lib
    return "inconnue"


def case(texte: str, fond: str | None = None) -> str:
    """Texte sur fond coloré (HTML) pour les cartes et les explications."""
    fond = fond or FONDS_PAR_VALEUR.get(str(texte), "#eeeeea")
    return (f'<span style="background:{fond};padding:1px 8px;border-radius:4px;'
            f'white-space:nowrap">{texte}</span>')


def colorier_cases(valeur) -> str:
    """Style pandas : colore la case selon sa valeur (fiabilité, niveau de risque, conformité)."""
    texte = str(valeur)
    for cle, fond in FONDS_PAR_VALEUR.items():
        if texte == cle or texte.startswith(cle + " ("):
            return f"background-color: {fond}"
    return ""


def euros(v, devise="€") -> str:
    if pd.isna(v):
        return "-"
    return f"{v:,.0f}\u00a0{devise}".replace(",", "\u202f")   # espaces insécables


# ------------------------------------------------------------------ identité visuelle du cabinet
NOM_CABINET = "Passerelle"                # nom du cabinet : le pont entre la France et le pays choisi
SOUS_TITRE_CABINET = "Conseil patrimonial"
VERT_FONCE, VERT_NUIT, ANIS, ANIS_CLAIR = "#0f2b1f", "#173d2c", "#b6e34f", "#eef8d6"
MARINE, OR, VIOLET = VERT_FONCE, ANIS, "#6250d6"   # noms gardés pour compatibilité
FOND_PAGE = "#f2f4f1"

# logo : deux points (France et pays de destination) reliés par une arche, sur un carré anis
_PICTO = """<rect x="2" y="2" width="60" height="60" rx="16" fill="{anis}"/>
  <path d="M15 42 Q32 10 49 42" fill="none" stroke="{fonce}" stroke-width="5" stroke-linecap="round"/>
  <circle cx="15" cy="44" r="6" fill="{fonce}"/><circle cx="49" cy="44" r="6" fill="{fonce}"/>"""

ICONES = {   # petites icônes des tuiles (traits simples)
    "globe": '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c3 3.2 3 13.8 0 17M12 3.5c-3 3.2-3 13.8 0 17"/>',
    "euro": '<path d="M17 6.5A7 7 0 1 0 17 17.5M4.5 10.5h9M4.5 13.5h9"/>',
    "bouclier": '<path d="M12 3l7.5 3v5.5c0 4.6-3.2 8-7.5 9.5-4.3-1.5-7.5-4.9-7.5-9.5V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "alerte": '<path d="M12 4l9 15.5H3z"/><path d="M12 10v4.5M12 17.2v.3"/>',
}


def _ecrire_logos() -> tuple[str, str]:
    """Génère le logo et son icône à partir de NOM_CABINET (fichiers SVG dans app/assets)."""
    dossier = Path(__file__).resolve().parent / "assets"
    dossier.mkdir(exist_ok=True)
    picto = _PICTO.format(anis=ANIS, fonce=VERT_FONCE)
    logo = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 250 64" width="250" height="64">{picto}'
            f'<text x="76" y="33" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="25" '
            f'font-weight="700" fill="#ffffff">{NOM_CABINET}</text>'
            f'<text x="77" y="52" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="12.5" '
            f'fill="{ANIS}">{SOUS_TITRE_CABINET}</text></svg>')
    icone = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">{picto}</svg>'
    (dossier / "logo.svg").write_text(logo, encoding="utf-8")
    (dossier / "icone.svg").write_text(icone, encoding="utf-8")
    return str(dossier / "logo.svg"), str(dossier / "icone.svg")


CSS = f"""
<style>
.stApp {{ background: {FOND_PAGE}; }}
.block-container {{ padding-top: 2rem; max-width: 1400px; }}
h1 {{ color: {VERT_FONCE}; font-size: 1.9rem !important; }}
/* barre latérale vert nuit */
[data-testid="stSidebar"] {{ background: {VERT_FONCE}; }}
[data-testid="stSidebar"] * {{ color: #e8efe9; }}
[data-testid="stSidebar"] h2 {{ color: #9db3a5 !important; font-size: 0.72rem; text-transform: uppercase;
    letter-spacing: 0.1em; font-weight: 600; margin-top: 0.8rem; }}
[data-testid="stSidebar"] input, [data-testid="stSidebar"] [data-baseweb="select"] *,
[data-testid="stSidebar"] [data-testid="stNumberInput"] button,
[data-testid="stSidebar"] [data-testid="stNumberInput"] button * {{ color: #0b0b0b !important; }}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] {{ border-radius: 10px; }}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {{ background: {VERT_NUIT}; }}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] span {{ color: {ANIS} !important; }}
[data-testid="stSidebar"] [data-testid="stTooltipIcon"] svg {{ stroke: #e8efe9; }}
[data-testid="stSidebar"] [data-baseweb="slider"] [role="slider"] {{ background: {ANIS}; }}
[data-testid="stSidebar"] .stButton, [data-testid="stSidebar"] .stButton > div {{ width: 100%; }}
[data-testid="stSidebar"] .stButton button {{ background: transparent; border: 1.5px dashed #4c6b5a;
    border-radius: 12px; width: 100%; padding: 14px 0; }}
[data-testid="stSidebar"] .stButton button:hover {{ border-color: {ANIS}; }}
/* cartes blanches : conteneurs st.container(border=True, key="carte_...") */
/* cartes à hauteur fixe : le contenu est réparti sur toute la hauteur (pas de vide en bas) */
div.st-key-carte_s1, div.st-key-carte_s2, div.st-key-carte_s3, div.st-key-carte_d2, div.st-key-carte_d3,
div.st-key-carte_d4, div.st-key-carte_d5, div.st-key-carte_d6, div.st-key-carte_d7,
div.st-key-carte_p1, div.st-key-carte_p2, div.st-key-carte_p3, div.st-key-carte_p4, div.st-key-carte_p5,
div.st-key-carte_p6 {{ justify-content: space-between; overflow: hidden !important; }}
div[class*="st-key-carte_"] {{ background: #ffffff; border-radius: 16px !important;
    border: 1px solid #e3e7e2 !important; box-shadow: 0 1px 2px rgba(15, 43, 31, 0.05); }}
[data-testid="stVerticalBlockBorderWrapper"] {{ background: #ffffff; border-radius: 16px;
    border: 1px solid #e3e7e2 !important; box-shadow: 0 1px 2px rgba(15, 43, 31, 0.05); }}
.titre-carte {{ font-weight: 700; font-size: 1.05rem; color: {VERT_FONCE}; }}
.sous-titre-carte {{ font-size: 0.78rem; color: #7b857f; margin-bottom: 0.3rem; }}
/* onglets en pastilles */
[data-baseweb="tab-list"] {{ gap: 6px; background: #f2f4f1; padding: 4px; border-radius: 999px; width: fit-content; }}
[data-baseweb="tab"] {{ border-radius: 999px !important; padding: 6px 16px !important; height: auto !important; }}
[data-baseweb="tab"][aria-selected="true"] {{ background: {VERT_FONCE}; }}
[data-baseweb="tab"][aria-selected="true"] p {{ color: #ffffff !important; }}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {{ display: none; }}
/* tuiles d'indicateurs */
.tuile {{ background: #ffffff; border: 1px solid #e3e7e2; border-radius: 16px; overflow: hidden;
    box-shadow: 0 1px 2px rgba(15, 43, 31, 0.05); }}
.tuile .corps {{ padding: 14px 16px 10px 16px; position: relative; min-height: 96px; }}
.tuile .libelle {{ font-size: 0.8rem; color: #7b857f; }}
.tuile .valeur {{ font-size: 1.65rem; font-weight: 700; color: {VERT_FONCE}; margin-top: 2px; line-height: 1.25; }}
.tuile .pastille {{ display: inline-block; background: {ANIS_CLAIR}; color: {VERT_FONCE}; font-size: 0.72rem;
    font-weight: 600; padding: 2px 9px; border-radius: 999px; margin-top: 6px; }}
.tuile .icone {{ position: absolute; top: 12px; right: 12px; width: 32px; height: 32px; border-radius: 9px;
    border: 1px solid #e3e7e2; display: flex; align-items: center; justify-content: center; }}
.tuile .icone svg {{ width: 18px; height: 18px; fill: none; stroke: {VERT_FONCE}; stroke-width: 1.8;
    stroke-linecap: round; stroke-linejoin: round; }}
.tuile .pied {{ border-top: 1px solid #eef1ed; padding: 8px 16px; font-size: 0.78rem; color: {VERT_FONCE};
    display: flex; justify-content: space-between; }}
.tuile.active .icone {{ background: {VERT_FONCE}; border-color: {VERT_FONCE}; }}
.tuile.active .icone svg {{ stroke: {ANIS}; }}
.tuile.active .pied {{ background: {VERT_FONCE}; color: #ffffff; }}
</style>
"""


def appliquer_style():
    logo, icone = _ecrire_logos()
    st.logo(logo, size="large", icon_image=icone)
    st.markdown(CSS, unsafe_allow_html=True)


def tuile(libelle: str, valeur: str, pastille: str, pied: str, icone: str = "globe", active: bool = False) -> str:
    """Tuile d'indicateur : libellé, valeur, pastille anis, pied de carte (foncé si active)."""
    return (f'<div class="tuile{" active" if active else ""}"><div class="corps">'
            f'<div class="icone"><svg viewBox="0 0 24 24">{ICONES[icone]}</svg></div>'
            f'<div class="libelle">{libelle}</div><div class="valeur">{valeur}</div>'
            f'<span class="pastille">{pastille}</span></div>'
            f'<div class="pied"><span>{pied}</span><span>→</span></div></div>')


def titre_carte(titre: str, sous_titre: str = ""):
    st.markdown(f'<div class="titre-carte">{titre}</div>'
                + (f'<div class="sous-titre-carte">{sous_titre}</div>' if sous_titre else ""),
                unsafe_allow_html=True)


# ------------------------------------------------------------------ graphiques
CONFIG_GRAPHIQUE = {"displayModeBar": False}


def mise_en_page(fig, hauteur, **kw):
    """Mise en forme commune des graphiques plotly (fond blanc, marges serrées)."""
    reglages = dict(height=hauteur, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="white",
                    plot_bgcolor="white", font=dict(family="Source Sans Pro, sans-serif", color="#0b0b0b"))
    fig.update_layout(**(reglages | kw))
    return fig
