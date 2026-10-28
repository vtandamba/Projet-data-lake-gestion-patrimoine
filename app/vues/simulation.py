"""Page 1 - Simulation client : classement des destinations selon la situation et les priorités du client."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from commun import (ANIS, ATTENTION, BON, CRITIQUE, ENCRE_2, FIABILITE, GRILLE, MARINE, OR, S1, S2, S3, S4,
                    VIOLET, badge_fiabilite, carte_europe, case, colorier_cases, euros, executer, titre_carte, tuile,
                    verifier_connexion)

verifier_connexion()

PROFILS = {   # poids coût, risque, conformité (la fiscalité ne compte qu'en cas d'expatriation)
    "Équilibré": (35, 40, 25),
    "Prudent": (15, 60, 25),
    "Coût d'abord": (60, 25, 15),
    "Personnalisé": (35, 40, 25),
}
NIVEAU_COULEUR = {"Faible": "#2e9a5c", "Moyen": "#e3a63a", "Élevé": "#cf4b3c"}   # tons accordés au thème
CONFORMITE_COULEUR = {"Conforme": "#2e9a5c", "À vérifier": "#e3a63a"}
PFU_FRANCE = 30.0
CONFIG_GRAPHIQUE = {"displayModeBar": False}


def mise_en_page(fig, hauteur, **kw):
    fig.update_layout(height=hauteur, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="white",
                      plot_bgcolor="white", font=dict(family="Source Sans Pro, sans-serif", color="#0b0b0b"),
                      **kw)
    return fig


def anneau(valeurs: pd.Series, couleurs: dict, centre: str, legende_centre: str, hauteur: int = 200):
    """Anneau fin, fond transparent, total au centre (la légende détaillée est écrite à côté en HTML)."""
    ordre = [k for k in couleurs if k in valeurs.index]
    fig = go.Figure(go.Pie(labels=ordre, values=[valeurs[k] for k in ordre], hole=0.74, sort=False,
                           direction="clockwise", rotation=90,
                           marker=dict(colors=[couleurs[k] for k in ordre], line=dict(color="white", width=2)),
                           textinfo="none", hovertemplate="%{label} : %{value} destination(s)<extra></extra>"))
    fig.add_annotation(text=f"<b>{centre}</b>", showarrow=False, y=0.56, font=dict(size=30, color=MARINE))
    fig.add_annotation(text=legende_centre, showarrow=False, y=0.38, font=dict(size=12, color=ENCRE_2))
    fig.update_layout(height=hauteur, margin=dict(l=0, r=0, t=6, b=6), showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def legende_anneau(d: pd.DataFrame, colonne: str, couleurs: dict) -> str:
    """Légende en lignes : pastille, catégorie, nombre, part et pays concernés (sauf la catégorie majoritaire)."""
    total = len(d)
    comptes = d[colonne].value_counts()
    majoritaire = comptes.idxmax() if len(comptes) else None
    lignes = []
    for cat, coul in couleurs.items():
        n = int(comptes.get(cat, 0))
        pays = "" if cat == majoritaire or n == 0 else ", ".join(sorted(d.loc[d[colonne] == cat, "destination"]))
        lignes.append(
            f"<div style='display:flex;align-items:baseline;gap:8px;padding:5px 0;border-top:1px solid #eef1ed'>"
            f"<span style='width:10px;height:10px;border-radius:3px;background:{coul};flex:none;"
            f"transform:translateY(1px)'></span>"
            f"<span style='flex:1;color:#0b0b0b'>{cat}"
            + (f"<br><span style='font-size:0.78em;color:{ENCRE_2}'>{pays}</span>" if pays else "")
            + f"</span><b style='color:{MARINE}'>{n}</b>"
            f"<span style='width:38px;text-align:right;font-size:0.8em;color:{ENCRE_2}'>"
            f"{(100 * n / total if total else 0):.0f} %</span></div>")
    return "<div style='font-size:0.88rem;margin-top:2px'>" + "".join(lignes) + "</div>"


# ------------------------------------------------------------------ saisie (barre latérale)
with st.sidebar:
    st.header("Situation du client")
    montant = st.number_input("Montant à transférer (€)", min_value=1_000, max_value=50_000_000,
                              value=100_000, step=10_000, format="%d")
    horizon = st.radio("Conversion en devise", ["immédiate", "dans 3 mois"], horizontal=True,
                       help="Dans 3 mois : affiche la fourchette du montant reçu, d'après les variations "
                            "de change observées sur 5 ans.")
    expatriation = st.toggle("Le client s'installe dans le pays", value=False,
                             help="Résident fiscal français : ses plus-values sont imposées en France "
                                  f"({PFU_FRANCE:.0f} %) quel que soit le pays. La fiscalité locale ne compte "
                                  "que s'il change de résidence fiscale.")
    plus_value = st.slider("Plus-value attendue à la revente (%)", 0, 100, 20, 5, disabled=not expatriation)

    st.header("Priorités")
    profil = st.selectbox("Profil", list(PROFILS))
    p_cout, p_risque, p_conf = PROFILS[profil]
    perso = profil == "Personnalisé"
    poids_cout = st.slider("Coût du transfert", 0, 100, p_cout, 5, key=f"c_{profil}", disabled=not perso)
    poids_risque = st.slider("Risque du pays", 0, 100, p_risque, 5, key=f"r_{profil}", disabled=not perso)
    poids_conf = st.slider("Conformité", 0, 100, p_conf, 5, key=f"k_{profil}", disabled=not perso)
    poids_fisc = st.slider("Fiscalité locale", 0, 100, 40 if expatriation else 0, 5,
                           key=f"f_{profil}_{expatriation}", disabled=not expatriation)

    st.header("Destinations")
    zone = st.radio("Afficher", ["toutes", "zone euro", "hors zone euro"], horizontal=True)
    exclure = st.checkbox("Exclure les destinations « À vérifier »", value=False)
    st.write("")
    if st.button("＋  Nouvelle simulation", help="Remet tous les paramètres à leur valeur par défaut",
                 width="stretch"):
        st.session_state.clear()
        st.rerun()

if poids_cout + poids_risque + poids_conf + (poids_fisc if expatriation else 0) == 0:
    st.warning("Donner un poids non nul à au moins un critère.")
    st.stop()

# ------------------------------------------------------------------ calcul (requêtes Q14, Q01, Q08, Q12)
classement = executer("Q14", poids_cout=poids_cout, poids_risque=poids_risque, poids_fiscalite=poids_fisc,
                      poids_conformite=poids_conf, scenario_expatriation=expatriation,
                      exclure_a_verifier=exclure)
couts = executer("Q01")[["destination", "marge_change_pct", "methode_cout"]]
change = executer("Q08")
change["taux_pour_1_eur"] = change["recu_aujourdhui_devise_locale"] / 100_000
risque = executer("Q12")[["destination", "niveau_risque"]]

d = (classement.merge(couts, on="destination", how="left")
     .merge(risque, on="destination", how="left")
     .merge(change[["devise", "taux_pour_1_eur", "variation_p05_pct", "variation_mediane_pct",
                    "variation_p95_pct"]], on="devise", how="left"))
d["zone_euro"] = d["devise"].eq("EUR")
if zone == "zone euro":
    d = d[d["zone_euro"]]
elif zone == "hors zone euro":
    d = d[~d["zone_euro"]]
if d.empty:
    st.info("Aucune destination ne correspond aux filtres choisis.")
    st.stop()
d = d.sort_values("score_global", ascending=False).reset_index(drop=True)
d["rang"] = d["score_global"].rank(ascending=False, method="min").astype(int)

d["cout_change_eur"] = montant * d["marge_change_pct"] / 100
d["recu_eur"] = montant - d["cout_change_eur"]
d["taux_pour_1_eur"] = np.where(d["zone_euro"], 1.0, d["taux_pour_1_eur"])
d["recu_devise"] = d["recu_eur"] * d["taux_pour_1_eur"]
for q in ("p05", "p95"):
    d[f"recu_3m_{q}"] = np.where(d["zone_euro"], d["recu_devise"],
                                 d["recu_devise"] * (1 + d[f"variation_{q}_pct"] / 100))
d["impot_local_eur"] = montant * plus_value / 100 * d["taux_plus_value_pct"] / 100
impot_france = montant * plus_value / 100 * PFU_FRANCE / 100
d["badge"] = d["fiabilite_cout"].map(badge_fiabilite)

w = classement.iloc[0]
CRITERES = [("cout", S1, "coût"), ("risque", S2, "risque"), ("conformite", S4, "conformité"),
            ("fiscalite", S3, "fiscalité")]
poids_txt = " · ".join(f"{lib} {w[f'poids_{c}_effectif']:.0%}" for c, _, lib in CRITERES
                       if w[f"poids_{c}_effectif"] > 0)

# ------------------------------------------------------------------ en-tête et indicateurs
st.title("Tableau de bord · simulation client")
st.caption(f"Transfert de {euros(montant)} depuis la France · profil {profil.lower()} ({poids_txt}) · "
           + ("scénario expatriation" if expatriation else "le client reste résident fiscal français"))

meilleur = d.iloc[0]
nb = len(d)
nb_conformes = int((d["conformite"] == "Conforme").sum())
nb_eleve = int((d["niveau_risque"] == "Élevé").sum())
moins_cher_hors_euro = d[~d["zone_euro"]].nsmallest(1, "cout_change_eur")
t1, t2, t3, t4 = st.columns(4)
t1.markdown(tuile("Destination recommandée", meilleur["destination"],
                  f"score {meilleur['score_global']:.0f}/100", f"{meilleur['devise']} · {profil.lower()}",
                  "globe", active=True), unsafe_allow_html=True)
if moins_cher_hors_euro.empty:
    t2.markdown(tuile("Coût de change", "0 €", "SEPA", "zone euro : pas de change", "euro"),
                unsafe_allow_html=True)
else:
    r = moins_cher_hors_euro.iloc[0]
    t2.markdown(tuile("Coût de change hors zone euro", euros(r["cout_change_eur"]), f"au mieux : {r['destination']}",
                      "zone euro : 0 €", "euro"), unsafe_allow_html=True)
t3.markdown(tuile("Destinations conformes", f"{nb_conformes} / {nb}", f"{nb - nb_conformes} à vérifier",
                  "GAFI · liste UE · opacité", "bouclier"), unsafe_allow_html=True)
t4.markdown(tuile("Risque élevé", f"{nb_eleve} / {nb}",
                  ", ".join(d.loc[d["niveau_risque"] == "Élevé", "destination"]) or "aucune",
                  "change · inflation · gouvernance", "alerte"), unsafe_allow_html=True)
st.write("")

# ------------------------------------------------------------------ carte + anneaux
c_carte, c_risque, c_conf = st.columns([2, 1, 1])
HAUTEUR_LIGNE = 500   # même hauteur pour la carte et les deux anneaux (pas de vide)
with c_carte.container(border=True, key="carte_s1", height=HAUTEUR_LIGNE):
    titre_carte("Carte des destinations", "Survoler un pays pour le détail · France (en orange) = pays d'envoi")
    indicateur = st.radio("Colorer selon", ["score global", "coût de change", "risque"], horizontal=True,
                          label_visibility="collapsed")
    col, echelle, titre_echelle = {
        "score global": ("score_global", [[0, "#e4f3c4"], [0.5, "#86bf3a"], [1, "#0f2b1f"]], "score"),
        "coût de change": ("cout_change_eur", [[0, "#dcebf7"], [1, "#1d4f80"]], "€"),
        "risque": ("score_risque", [[0, "#dcebf7"], [1, "#1d4f80"]], "risque"),
    }[indicateur]
    geo = carte_europe()
    fig = go.Figure(go.Choroplethmap(      # fond : tous les pays d'Europe en gris
        geojson=geo, featureidkey="id", locations=[f["id"] for f in geo["features"]],
        z=[0] * len(geo["features"]), colorscale=[[0, "#e9ebef"], [1, "#e9ebef"]], showscale=False,
        marker_line_color="white", marker_line_width=0.6, hoverinfo="skip"))
    fig.add_trace(go.Choroplethmap(
        geojson=geo, featureidkey="id", locations=d["iso3"], z=d[col], colorscale=echelle, marker_line_color="white", marker_line_width=0.8,
        colorbar=dict(title=titre_echelle, thickness=10, len=0.75),
        customdata=np.stack([d["destination"], d["score_global"], d["cout_change_eur"], d["niveau_risque"],
                             d["conformite"], d["badge"]], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b><br>score %{customdata[1]:.0f}/100<br>coût de change "
                      "%{customdata[2]:,.0f} € (%{customdata[5]})<br>risque %{customdata[3]} · "
                      "%{customdata[4]}<extra></extra>"))
    fig.add_trace(go.Choroplethmap(geojson=geo, featureidkey="id", locations=["FRA"], z=[0], colorscale=[[0, "#e4572e"], [1, "#e4572e"]],
                                showscale=False, marker_line_color="white",
                                hovertemplate="<b>France</b> : pays d'envoi<extra></extra>"))
    # fond « white-bg » : aucune tuile à télécharger, la carte fonctionne hors connexion
    st.plotly_chart(mise_en_page(fig, 358, map=dict(style="white-bg", center=dict(lat=51, lon=17), zoom=2.15)),
                    width="stretch",
                    config=CONFIG_GRAPHIQUE)

with c_risque.container(border=True, key="carte_s2", height=HAUTEUR_LIGNE):
    titre_carte("Niveau de risque", "Change, inflation, taux, gouvernance")
    st.plotly_chart(anneau(d["niveau_risque"].value_counts(), NIVEAU_COULEUR,
                           f"{int((d['niveau_risque'] == 'Faible').sum())}/{nb}", "risque faible", hauteur=228), width="stretch", config=CONFIG_GRAPHIQUE)
    st.markdown(legende_anneau(d, "niveau_risque", NIVEAU_COULEUR), unsafe_allow_html=True)
with c_conf.container(border=True, key="carte_s3", height=HAUTEUR_LIGNE):
    titre_carte("Conformité", "GAFI, liste UE, échange d'informations")
    st.plotly_chart(anneau(d["conformite"].value_counts(), CONFORMITE_COULEUR, f"{nb_conformes}/{nb}",
                           "conformes", hauteur=268), width="stretch", config=CONFIG_GRAPHIQUE)
    st.markdown(legende_anneau(d, "conformite", CONFORMITE_COULEUR), unsafe_allow_html=True)

# ------------------------------------------------------------------ classement + 3 recommandations
c_classement, c_top = st.columns([2, 1])
with c_classement.container(border=True, key="carte_s4"):
    titre_carte("Classement des destinations", "Contribution de chaque critère au score (survoler une barre)")
    g = d.sort_values("score_global")
    fig = go.Figure()
    for crit, coul, lib in CRITERES:
        poids = w[f"poids_{crit}_effectif"]
        if poids == 0:
            continue
        fig.add_bar(y=g["destination"], x=g[f"note_{crit}"].fillna(0) * poids, orientation="h", name=lib,
                    marker=dict(color=coul, line=dict(color="white", width=1.5)),
                    customdata=np.stack([g[f"note_{crit}"].fillna(0)], axis=-1),
                    hovertemplate=f"%{{y}}<br>{lib} : note %{{customdata[0]:.0f}}/100, "
                                  f"contribution %{{x:.1f}} pts<extra></extra>")
    fig.add_scatter(y=g["destination"], x=g["score_global"], mode="text",
                    text=g["score_global"].round(0).astype(int), textposition="middle right",
                    textfont=dict(color=ENCRE_2, size=11), showlegend=False, hoverinfo="skip")
    mise_en_page(fig, max(320, 24 * len(g) + 70), barmode="stack", barcornerradius=5,
                 xaxis=dict(range=[0, 108], gridcolor=GRILLE, title=None),
                 legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, traceorder="normal"))
    st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)

with c_top.container(border=True, key="carte_s5"):
    titre_carte("Recommandations", "Les 3 meilleures destinations pour ce client")
    for _, r in d.head(3).iterrows():
        with st.container(border=True, key=f"carte_s6_{r['iso3']}"):
            st.markdown(f"**{r['rang']}. {r['destination']}** · {r['devise']} · "
                        f"<span style='background:{ANIS};color:{MARINE};font-weight:700;padding:1px 8px;border-radius:999px'>{r['score_global']:.0f}/100</span>",
                        unsafe_allow_html=True)
            lignes = [f"Coût de change : <b>{euros(r['cout_change_eur'])}</b> {case(r['badge'])}"]
            if r["zone_euro"]:
                lignes.append(f"Montant reçu : <b>{euros(r['recu_eur'])}</b>")
            else:
                lignes.append(f"Montant reçu : <b>{euros(r['recu_devise'], r['devise'])}</b>")
                if horizon == "dans 3 mois":
                    lignes.append(f"Dans 3 mois : {euros(r['recu_3m_p05'], r['devise'])} à "
                                  f"{euros(r['recu_3m_p95'], r['devise'])}")
            lignes.append(f"Risque : {case(r['niveau_risque'])} ({r['score_risque']:.0f}/100) · "
                          f"{case(r['conformite'])}")
            if expatriation:
                lignes.append(f"Impôt s'il s'installe : <b>{euros(r['impot_local_eur'])}</b> "
                              f"(en France : {euros(impot_france)})")
            if r["conformite"] != "Conforme":
                lignes.append(f"<span style='color:{ENCRE_2};font-size:0.85em'>À vérifier : {r['motifs']}</span>")
            st.markdown("<br>".join(lignes), unsafe_allow_html=True)
            if st.button("Voir la fiche pays →", key=f"fiche_{r['iso3']}", type="tertiary"):
                st.session_state["pays_fiche"] = r["destination"]
                st.switch_page("vues/fiche_pays.py")

# ------------------------------------------------------------------ détails
with st.container(border=True, key="carte_s7"):
    onglet_detail, onglet_change, onglet_nuage = st.tabs(["Détail chiffré", "Risque de change", "Coût et risque"])

    with onglet_detail:
        tableau = pd.DataFrame({
            "Rang": d["rang"], "Destination": d["destination"], "Devise": d["devise"],
            "Score": d["score_global"],
            "Coût de change (€)": d["cout_change_eur"],
            "Fiabilité du coût": d["badge"],
            "Montant reçu (devise)": d["recu_devise"],
            "Risque": d["niveau_risque"] + " (" + d["score_risque"].astype(int).astype(str) + ")",
            "Conformité": d["conformite"],
            "Motifs": d["motifs"].fillna(""),
            "Taux plus-value (%)": d["taux_plus_value_pct"],
        })
        if expatriation:
            tableau["Impôt si installé (€)"] = d["impot_local_eur"]
        entier = lambda v: "-" if pd.isna(v) else f"{v:,.0f}".replace(",", " ")
        formats = {"Score": "{:.1f}", "Taux plus-value (%)": "{:.1f}", "Coût de change (€)": entier,
                   "Montant reçu (devise)": entier, "Impôt si installé (€)": entier}
        style = (tableau.style
                 .map(colorier_cases, subset=["Fiabilité du coût", "Risque", "Conformité"])
                 .format({k: v for k, v in formats.items() if k in tableau.columns}))
        st.dataframe(style, hide_index=True, width="stretch")
        st.download_button("Télécharger la simulation (CSV)", tableau.to_csv(index=False).encode("utf-8"),
                           "simulation_client.csv", "text/csv")

    with onglet_change:
        hors_euro = d[~d["zone_euro"]].dropna(subset=["variation_p05_pct"]).sort_values("variation_p95_pct")
        if hors_euro.empty:
            st.info("Toutes les destinations affichées sont en zone euro : pas de risque de change.")
        else:
            st.markdown(f"Montant reçu si la conversion de **{euros(montant)}** a lieu dans 3 mois "
                        "(90 % des cas observés sur les 5 dernières années).")
            etiq = hors_euro["devise"] + " · " + hors_euro["destination"]
            fig = go.Figure()
            fig.add_bar(y=etiq, x=hors_euro["variation_p95_pct"] - hors_euro["variation_p05_pct"],
                        base=hors_euro["variation_p05_pct"], orientation="h", marker_color="rgba(42,120,214,0.35)",
                        name="fourchette (5 % - 95 %)",
                        customdata=np.stack([hors_euro["recu_3m_p05"], hors_euro["recu_3m_p95"],
                                             hors_euro["devise"]], axis=-1),
                        hovertemplate="%{y}<br>de %{customdata[0]:,.0f} à %{customdata[1]:,.0f} "
                                      "%{customdata[2]}<extra></extra>")
            fig.add_scatter(y=etiq, x=hors_euro["variation_mediane_pct"], mode="markers", name="médiane",
                            marker=dict(color=S1, size=10, line=dict(color="white", width=2)),
                            hovertemplate="%{y}<br>médiane %{x:+.1f} %<extra></extra>")
            fig.add_vline(x=0, line_color=ENCRE_2, line_width=1)
            mise_en_page(fig, max(260, 40 * len(hors_euro) + 80),
                         xaxis=dict(title="Variation du montant reçu en devise (%)", gridcolor=GRILLE,
                                    zeroline=False),
                         legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)
            st.caption("Pour la livre turque (TRY) et la hryvnia (UAH), recevoir plus de devises vient surtout de "
                       "leur dépréciation et d'une forte inflation locale : ce n'est pas un gain réel.")

    with onglet_nuage:
        fig = go.Figure()
        for niveau, coul in NIVEAU_COULEUR.items():
            e = d[d["niveau_risque"] == niveau]
            fig.add_scatter(x=e["cout_change_eur"], y=e["score_risque"], mode="markers+text",
                            name=f"risque {niveau.lower()}",
                            text=np.where(e["zone_euro"], "", e["destination"]), textposition="top center",
                            textfont=dict(size=10, color=ENCRE_2), hovertext=e["destination"],
                            marker=dict(color=coul, size=12, line=dict(color="white", width=2),
                                        symbol=np.where(e["conformite"] == "Conforme", "circle", "diamond")),
                            customdata=np.stack([e["conformite"], e["badge"]], axis=-1),
                            hovertemplate="%{hovertext}<br>coût %{x:,.0f} € (%{customdata[1]})<br>risque "
                                          "%{y:.0f}/100<br>%{customdata[0]}<extra></extra>")
        mise_en_page(fig, 460, xaxis=dict(title=f"Coût de change pour {euros(montant)} (€)", gridcolor=GRILLE),
                     yaxis=dict(title="Score de risque (0 = sûr, 100 = risqué)", gridcolor=GRILLE),
                     legend=dict(orientation="h", y=-0.18))
        st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)
        st.caption("Les pays de la zone euro (coût de change nul) sont regroupés à gauche : survoler un point pour "
                   "voir son nom. Losange = destination « À vérifier ». En bas à gauche : bon marché et peu risqué.")

with st.expander("Comment ces résultats sont calculés"):
    st.markdown(
        "- **Score** : chaque critère est ramené entre 0 (le plus défavorable des 22 pays) et 100 (le plus "
        "favorable), puis pondéré selon les priorités choisies (requête Q14).\n"
        "- **Coût de change** : marge de change appliquée au montant (requête Q01). Le RPW ne contient aucun "
        "envoi au départ de la France vers ces pays ; la fiabilité de chaque chiffre est indiquée :\n"
        + "\n".join(f"    - {case(lib, fond)} : {t}" for lib, fond, t in FIABILITE.values()) + "\n"
        "- **Risque** : volatilité du change, inflation, écart de taux directeur avec la BCE et gouvernance "
        "(table gold `risque_pays`).\n"
        "- **Conformité** : listes GAFI et UE, échange automatique d'informations avec la France, indice "
        "d'opacité financière (table gold `fiscalite_conformite`).\n"
        f"- **Fiscalité** : un résident fiscal français paie {PFU_FRANCE:.0f} % sur ses plus-values, quel que soit "
        "le pays ; le taux local (Tax Foundation, taux général) ne s'applique que s'il s'installe dans le pays.\n"
        "- **Change à 3 mois** : variations observées entre chaque jour et 63 jours ouvrés plus tard, sur 5 ans "
        "(requête Q08). Les frais fixes des prestataires, négligeables pour de gros montants, ne sont pas inclus.",
        unsafe_allow_html=True)
