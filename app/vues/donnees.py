"""Page 3 - Données et qualité : architecture du data lake, sources, qualité et méthode d'estimation."""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from commun import (ANIS, ANIS_CLAIR, CONFIG_GRAPHIQUE, ENCRE_2, FIABILITE, GRILLE, RACINE, S1, S2, S3, S4,
                    VERT_FONCE, badge_fiabilite, case, colorier_cases, executer, mise_en_page, requetes, titre_carte, tuile,
                    verifier_connexion)

verifier_connexion()

# format d'origine et fichier bronze de chaque source (None : fichier fourni directement par l'équipe)
SOURCES = {
    "RPW (Banque mondiale)": ("Excel, 2 feuilles", "rpw_f1S1"),
    "BIS - taux de change": ("CSV SDMX", "bis_S4"),
    "BIS - taux directeurs": ("CSV SDMX", "bis_S4"),
    "BIS - prix": ("CSV SDMX", "bis_S4"),
    "BCE - taux de référence": ("CSV", "bronze_eurofxref-hist.csv"),
    "Banque mondiale + FMI (API)": ("API JSON", "wb_api_*.csv, imf_debt_*.csv"),
    "Banque mondiale - WGI": ("API JSON", "wgi_*.csv"),
    "GAFI": ("page web", "fatf_lists_*.csv"),
    "Tax Justice Network": ("API JSON", "fsi_2026_raw.csv"),
    "Union européenne": ("fourni par l'équipe", None),
    "OCDE": ("fourni par l'équipe", None),
    "Tax Foundation": ("fourni par l'équipe", None),
    "Référentiel pays": ("fourni par l'équipe", None),
}
FOND_FORMAT = {"Excel": "#e4f3c4", "CSV": "#dcebf7", "API": "#fbe7cc", "page": "#efe3f7", "fourni": "#eceeea"}
GROUPES = {"A": ("SEPA, pas de change", S1), "B": ("observé depuis la zone euro", S2),
           "C": ("observé depuis une autre devise", S3), "D": ("estimation", S4)}


@st.cache_data(ttl=600, show_spinner=False)
def inventaire_bronze() -> pd.DataFrame:
    """Fichiers bruts présents dans data/bronze (absents si l'application tourne sans les données locales)."""
    dossier = RACINE / "data" / "bronze"
    if not dossier.exists():
        return pd.DataFrame(columns=["element", "nb_fichiers", "taille_mo"])
    lignes = []
    for e in sorted(dossier.iterdir()):
        fichiers = [e] if e.is_file() else [f for f in e.rglob("*") if f.is_file()]
        lignes.append((e.name, len(fichiers), sum(f.stat().st_size for f in fichiers) / 1e6))
    return pd.DataFrame(lignes, columns=["element", "nb_fichiers", "taille_mo"])


def millier(v) -> str:
    return f"{int(v):,}".replace(",", " ")


# ------------------------------------------------------------------ données
with st.spinner("Comptage des lignes de chaque table…"):
    inventaire = executer("D1")
sources = executer("D2")
qualite = executer("P2")
profil = executer("P1")
methode = executer("D3")
bronze = inventaire_bronze()

silver = inventaire[inventaire["zone"] == "silver"]
gold = inventaire[inventaire["zone"] == "gold"]
ordre = list(SOURCES)
sources["ordre"] = sources["source"].map({s: i for i, s in enumerate(ordre)})
sources = sources.sort_values("ordre")

# ------------------------------------------------------------------ en-tête et tuiles
st.title("Données et qualité")
st.caption("Comment les chiffres de l'application sont produits : architecture du data lake, sources, contrôles "
           "de qualité et méthode d'estimation du coût depuis la France.")

t1, t2, t3, t4 = st.columns(4)
t1.markdown(tuile("Sources de données", f"{len(sources)}", "7 fournisseurs publics",
                  "Banque mondiale, BIS, BCE, FMI…", "globe", active=True), unsafe_allow_html=True)
t2.markdown(tuile("Lignes en zone silver", millier(silver["nb_lignes"].sum()), f"{len(silver)} tables nettoyées",
                  "CSV puis PostgreSQL (schéma silver)", "bouclier"), unsafe_allow_html=True)
t3.markdown(tuile("Lignes en zone gold", millier(gold["nb_lignes"].sum()), f"{len(gold)} tables métier",
                  "prêtes pour l'analyse (schéma gold)", "euro"), unsafe_allow_html=True)
t4.markdown(tuile("Données les plus récentes", str(sources.loc[sources["source"] == "BCE - taux de référence",
                                                                "fin"].iloc[0]),
                  "taux de change BCE", f"GAFI : plénière du {sources.loc[sources['source'] == 'GAFI', 'fin'].iloc[0]}",
                  "alerte"), unsafe_allow_html=True)
st.write("")

# ------------------------------------------------------------------ architecture
with st.container(border=True, key="carte_d1"):
    titre_carte("Architecture du data lake", "Architecture en médaillon : chaque zone a un rôle et un format")
    nb_bronze = int(bronze["nb_fichiers"].sum()) if len(bronze) else None
    taille_bronze = bronze["taille_mo"].sum() if len(bronze) else None
    etapes = [
        ("Bronze", "données brutes", [f"{nb_bronze} fichiers · {taille_bronze:,.0f} Mo".replace(",", " ")
                                      if nb_bronze else "fichiers bruts (non chargés ici)",
                                      "Excel, CSV SDMX, API JSON, pages web", "aucune modification"]),
        ("Silver", "données nettoyées", [f"{len(silver)} tables · {millier(silver['nb_lignes'].sum())} lignes",
                                         "types, dates, codes pays iso3", "doublons et erreurs corrigés"]),
        ("Gold", "tables métier", [f"{len(gold)} tables · {millier(gold['nb_lignes'].sum())} lignes",
                                   "coût, risque, conformité", "indicateurs consolidés"]),
        ("PostgreSQL", "base de restitution", ["schémas silver et gold", "Docker, port 5434", "chargement par COPY"]),
        ("Restitution", "usages", [f"{len(requetes())} requêtes SQL (sql/analyses.sql)",
                                   "notebook démonstrateur", f"application conseiller"]),
    ]
    fonds = ["#efe7dc", "#eceeea", "#eef8d6", "#dcebf7", VERT_FONCE]
    html = "<div style='display:flex;align-items:stretch;gap:6px;flex-wrap:wrap;margin-top:6px'>"
    for i, ((titre, role, lignes), fond) in enumerate(zip(etapes, fonds)):
        couleur_texte = "#ffffff" if fond == VERT_FONCE else VERT_FONCE
        html += (f"<div style='flex:1;min-width:150px;background:{fond};border-radius:14px;padding:12px 14px;"
                 f"color:{couleur_texte}'><div style='font-weight:700;font-size:1.05rem'>{titre}</div>"
                 f"<div style='font-size:0.78rem;opacity:0.75;margin-bottom:6px'>{role}</div>"
                 + "".join(f"<div style='font-size:0.82rem;line-height:1.45'>{l}</div>" for l in lignes)
                 + "</div>")
        if i < len(etapes) - 1:
            html += f"<div style='display:flex;align-items:center;color:{ENCRE_2};font-size:1.3rem'>→</div>"
    st.markdown(html + "</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ sources + volumes
with st.container(border=True, key="carte_d2"):
    titre_carte("Sources de données", "Format d'origine, période couverte et volume en zone silver")
    tableau = pd.DataFrame({
        "Source": sources["source"], "Contenu": sources["contenu"],
        "Format d'origine": sources["source"].map(lambda s: SOURCES.get(s, ("", None))[0]),
        "Période": [f"{str(d)[:4] if len(str(d)) == 10 else d} → {str(f)[:7] if len(str(f)) == 10 else f}"
                    if pd.notna(d) and d != f else (str(f) if pd.notna(f) else "-")
                    for d, f in zip(sources["debut"], sources["fin"])],
        "Lignes": sources["nb_lignes"].map(millier),
    })

    def fond_format(v):
        return next((f for cle, f in FOND_FORMAT.items() if str(v).startswith(cle)), "transparent")

    # tableau HTML : le texte passe à la ligne, aucune colonne n'est masquée sur un écran étroit
    entete = "".join(f"<th style='text-align:{a};padding:7px 8px;font-weight:600;color:{ENCRE_2};"
                     f"border-bottom:1px solid #e3e7e2'>{c}</th>"
                     for c, a in [("Source", "left"), ("Contenu", "left"), ("Format d'origine", "left"), ("Période", "left"),
                                  ("Lignes", "right")])
    corps = ""
    tableau = tableau.rename(columns={"Format d'origine": "format"})
    for _, r in tableau.iterrows():
        corps += (f"<tr style='border-bottom:1px solid #eef1ed'>"
                  f"<td style='padding:6px 8px'><b>{r['Source']}</b></td>"
                  f"<td style='padding:6px 8px;color:{ENCRE_2}'>{r['Contenu']}</td>"
                  f"<td style='padding:6px 8px'><span style='background:{fond_format(r['format'])};"
                  f"padding:2px 8px;border-radius:6px;white-space:nowrap'>{r['format']}</span></td>"
                  f"<td style='padding:6px 8px;white-space:nowrap'>{r['Période']}</td>"
                  f"<td style='padding:6px 8px;text-align:right;white-space:nowrap'>{r['Lignes']}</td></tr>")
    st.markdown(f"<table style='width:100%;border-collapse:collapse;font-size:0.86rem'><thead><tr>{entete}"
                f"</tr></thead><tbody>{corps}</tbody></table>", unsafe_allow_html=True)

# ------------------------------------------------------------------ qualité
c_qualite, c_profil = st.columns([3, 2])
HAUTEUR_QUALITE = 565
with c_qualite.container(border=True, key="carte_d4", height=HAUTEUR_QUALITE):
    titre_carte("Qualité : corrections appliquées à RPW", "Problèmes détectés au profilage et action corrective "
                                                         "(nombre de lignes concernées, échelle logarithmique)")
    q = qualite.sort_values("nb_lignes")
    fig = go.Figure(go.Bar(
        y=q["probleme"], x=q["nb_lignes"], orientation="h", marker=dict(color=S1),
        customdata=q[["action_corrective", "pct_lignes"]],
        text=[millier(n) for n in q["nb_lignes"]], textposition="outside", textfont=dict(size=11, color=ENCRE_2),
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:,.0f} lignes (%{customdata[1]:.2f} %)<br>"
                      "action : %{customdata[0]}<extra></extra>"))
    mise_en_page(fig, HAUTEUR_QUALITE - 115, margin=dict(l=10, r=60, t=10, b=10), xaxis=dict(type="log", gridcolor=GRILLE, range=[1, 6.1],
                 tickvals=[10, 1e3, 1e5], ticktext=["10", "1k", "100k"]),
                 yaxis=dict(tickfont=dict(size=11)), barcornerradius=4)
    st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)

with c_profil.container(border=True, key="carte_d5", height=HAUTEUR_QUALITE):
    titre_carte("Profilage de RPW après nettoyage", "Les deux feuilles du classeur Excel, harmonisées")
    for _, r in profil.iterrows():
        st.markdown(
            f"<div style='border:1px solid #e3e7e2;border-radius:12px;padding:10px 14px;margin-bottom:10px'>"
            f"<div style='font-weight:700;color:{VERT_FONCE}'>Feuille {r['feuille']} "
            f"<span style='font-weight:400;color:{ENCRE_2};font-size:0.85em'>· {r['premiere_periode']} → "
            f"{r['derniere_periode']}</span></div>"
            f"<div style='display:flex;gap:18px;margin:6px 0 8px 0;font-size:0.9rem'>"
            f"<span><b>{millier(r['nb_offres'])}</b> offres</span><span><b>{r['nb_corridors']}</b> corridors</span>"
            f"<span><b>{r['nb_prestataires']}</b> prestataires</span></div>"
            + "".join(f"{case(f'{lib} : {100 - r[col]:.1f} %', '#d9f0d9' if r[col] < 1 else '#fcefc7')} "
                      for lib, col in [("coût renseigné", "pct_cout_500usd_manquant"),
                                       ("devise connue", "pct_devise_versement_manquante"),
                                       ("délai connu", "pct_delai_manquant")])
            + "</div>", unsafe_allow_html=True)
    st.caption("Limite majeure révélée par le profilage : le RPW ne contient aucun envoi au départ de la France "
               "vers les destinations étudiées. D'où la méthode d'estimation ci-dessous.")

# ------------------------------------------------------------------ méthode d'estimation
c_anneau, c_methode = st.columns([1, 2])
HAUTEUR_METHODE = 390
with c_anneau.container(border=True, key="carte_d6", height=HAUTEUR_METHODE):
    titre_carte("Origine du coût par pays", "22 destinations, 4 méthodes")
    fig = go.Figure(go.Pie(
        labels=[GROUPES[g][0] for g in methode["groupe_cout"]], values=methode["nb_pays"], hole=0.72, sort=False,
        direction="clockwise", rotation=90, textinfo="none",
        marker=dict(colors=[GROUPES[g][1] for g in methode["groupe_cout"]], line=dict(color="white", width=2)),
        hovertemplate="%{label} : %{value} pays<extra></extra>"))
    observes = int(methode.loc[methode["groupe_cout"].isin(["A", "B", "C"]), "nb_pays"].sum())
    fig.add_annotation(text=f"<b>{observes}/22</b>", showarrow=False, y=0.56, font=dict(size=28, color=VERT_FONCE))
    fig.add_annotation(text="sans estimation", showarrow=False, y=0.38, font=dict(size=12, color=ENCRE_2))
    fig.update_layout(height=HAUTEUR_METHODE - 90, margin=dict(l=0, r=0, t=4, b=4), showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)

with c_methode.container(border=True, key="carte_d7", height=HAUTEUR_METHODE):
    titre_carte("Méthode d'estimation du coût depuis la France",
                "Chaque coût affiché dans l'application porte sa méthode et sa fiabilité")
    lignes = ""
    for _, r in methode.iterrows():
        lib, coul = GROUPES[r["groupe_cout"]]
        badge = badge_fiabilite(r["fiabilite"])
        lignes += (f"<div style='display:flex;gap:12px;align-items:flex-start;padding:8px 0;"
                   f"border-top:1px solid #eef1ed'>"
                   f"<span style='flex:none;width:26px;height:26px;border-radius:8px;background:{coul};color:white;"
                   f"font-weight:700;display:flex;align-items:center;justify-content:center'>{r['groupe_cout']}</span>"
                   f"<div style='flex:1'><b>{lib}</b> · {r['nb_pays']} pays · {case(badge)}"
                   f"<div style='font-size:0.8rem;color:{ENCRE_2}'>{r['pays']}</div></div>"
                   f"<div style='flex:none;text-align:right;font-size:0.85rem'>marge moyenne<br>"
                   f"<b>{r['marge_moyenne_pct']:.2f} %</b></div></div>")
    st.markdown(lignes, unsafe_allow_html=True)

# ------------------------------------------------------------------ volumes
with st.container(border=True, key="carte_d3"):
    titre_carte("Volume par table", "Nombre de lignes (échelle logarithmique) · vert foncé = gold")
    v = inventaire[inventaire["nb_lignes"] >= 1000].sort_values("nb_lignes")
    fig = go.Figure(go.Bar(
        y=v["zone"] + "." + v["nom_table"], x=v["nb_lignes"], orientation="h",
        marker=dict(color=[S1 if z == "gold" else S2 for z in v["zone"]], line=dict(color="white", width=1)),
        hovertemplate="%{y} : %{x:,.0f} lignes<extra></extra>"))
    mise_en_page(fig, 380, xaxis=dict(type="log", gridcolor=GRILLE,
                 tickvals=[1e3, 1e4, 1e5], ticktext=["1 000", "10 000", "100 000"]),
                 yaxis=dict(tickfont=dict(size=11)), barcornerradius=4)
    st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)
    st.caption(f"Tables de plus de 1 000 lignes. Les {len(inventaire) - len(v)} autres sont des référentiels "
               "(pays, listes, séries).")

with st.expander("Le détail des groupes"):
    st.markdown(
        "- **A, SEPA** : la destination utilise l'euro ; un virement SEPA depuis la France n'a pas de change.\n"
        "- **B, observé depuis la zone euro** : le RPW mesure des envois vers ce pays depuis un autre pays de la "
        "zone euro (Allemagne, Autriche, Belgique, Espagne, Italie, Pays-Bas) ; leur marge de change sert de "
        "substitut pour la France.\n"
        "- **C, observé depuis une autre devise** : seuls des envois depuis une autre devise (GBP, NOK) existent ; "
        "la marge de change est reprise, les frais ne sont pas comparables.\n"
        "- **D, estimation** : aucun envoi observé vers ce pays ; on applique la médiane des marges observées sur "
        "les corridors européens.\n\n"
        "Pour 100 000 €, seule la marge de change est extrapolée : les frais fixes des prestataires, mesurés sur "
        "des envois d'environ 500 USD, deviennent négligeables.")
