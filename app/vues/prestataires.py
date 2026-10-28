"""Page 4 - Prestataires : banques, opérateurs de transfert et autres, comparés sur les envois depuis la zone euro."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from commun import (ANIS_CLAIR, CONFIG_GRAPHIQUE, ENCRE_2, GRILLE, S1, S2, S3, S4, VERT_FONCE, case,
                    mise_en_page, requete, titre_carte, tuile, verifier_connexion)

verifier_connexion()

TYPES = {"operateur_transfert": ("opérateurs de transfert", S1), "banque": ("banques", S2),
         "autre": ("autres (poste, agents…)", S3)}
DELAIS = {1: "< 1 heure", 2: "même jour", 3: "lendemain", 4: "2 jours", 5: "3-5 jours", 6: "6 jours +"}
MIN_OFFRES = 15     # un prestataire n'est classé qu'avec assez de relevés


@st.cache_data(ttl=600, show_spinner=False)
def offres_zone_euro() -> pd.DataFrame:
    """Offres RPW envoyées depuis un pays de la zone euro (situation la plus proche d'un client français)."""
    return requete("""
        select o.period_std, left(o.period_std, 4)::int as annee, o.corridor, o.source_code, o.destination_code,
               p.nom_fr as destination, o.payout_currency, o.firm, o.type_prestataire, o.cc2_total_cost_pct,
               o.cc2_fx_margin, o.frais_pct_cc2, o.speed_rang, o.transparent
        from gold.offres_rpw o
        join gold.dim_pays e on e.iso3 = o.source_code and e.zone_euro
        join gold.dim_pays p on p.iso3 = o.destination_code
        where o.cc2_total_cost_pct is not null and o.payout_currency is not null
          and o.payout_currency <> 'USD'""")


toutes = offres_zone_euro()
destinations = sorted(toutes["destination"].unique())

# ------------------------------------------------------------------ filtres
with st.sidebar:
    st.header("Envois analysés")
    destination = st.selectbox("Destination", ["toutes"] + destinations)
    versement = st.radio("Versement", ["en devise locale", "en euros"], horizontal=True,
                         help="En devise locale, le prestataire applique une marge de change ; en euros, non.")
    debut = st.slider("Depuis l'année", int(toutes["annee"].min()), int(toutes["annee"].max()), 2023)
    st.caption("Envois d'environ 500 USD mesurés par la Banque mondiale (RPW), depuis l'Allemagne, l'Autriche, "
               "la Belgique, l'Espagne, l'Italie et les Pays-Bas.")

base = toutes if destination == "toutes" else toutes[toutes["destination"] == destination]
base = base[base["payout_currency"].eq("EUR") == (versement == "en euros")]
d = base[base["annee"] >= debut]

st.title("Prestataires de transfert")
st.caption(f"Qui propose les envois les moins chers et les plus rapides ? · destination : {destination} · "
           f"versement {versement} · depuis {debut}")
if d.empty:
    st.info("Aucune offre observée pour ces filtres : élargir la période ou choisir une autre destination.")
    st.stop()

# ------------------------------------------------------------------ tuiles
med = d.groupby("type_prestataire")["cc2_total_cost_pct"].median()
classement = (d.groupby("firm")
              .agg(type_prestataire=("type_prestataire", lambda s: s.mode().iloc[0]),
                   nb_offres=("firm", "size"), nb_corridors=("corridor", "nunique"),
                   cout_median=("cc2_total_cost_pct", "median"), marge_mediane=("cc2_fx_margin", "median"),
                   frais_median=("frais_pct_cc2", "median"), delai=("speed_rang", "mean"))
              .query("nb_offres >= @MIN_OFFRES").sort_values(["cout_median", "delai"]).reset_index())
t1, t2, t3, t4 = st.columns(4)
t1.markdown(tuile("Offres analysées", f"{len(d):,}".replace(",", " "), f"{d['firm'].nunique()} prestataires",
                  f"{d['corridor'].nunique()} corridors", "globe", active=True), unsafe_allow_html=True)
def pct(v) -> str:
    return "-" if pd.isna(v) else f"{v:.2f} %"


t2.markdown(tuile("Coût médian · opérateurs", pct(med.get("operateur_transfert")),
                  "du montant envoyé", "Wise, Remitly, Western Union…", "euro"), unsafe_allow_html=True)
t3.markdown(tuile("Coût médian · banques", pct(med.get("banque")),
                  f"{(d['type_prestataire'] == 'banque').sum()} offres", "banques de détail", "bouclier"),
            unsafe_allow_html=True)
if len(classement):
    m = classement.iloc[0]
    t4.markdown(tuile("Le moins cher", m["firm"], f"{m['cout_median']:.2f} % en médiane",
                      f"{DELAIS.get(round(m['delai']), '')} · {m['nb_offres']} offres", "alerte"),
                unsafe_allow_html=True)
else:
    t4.markdown(tuile("Le moins cher", "-", f"moins de {MIN_OFFRES} offres", "par prestataire", "alerte"),
                unsafe_allow_html=True)
st.write("")

# ------------------------------------------------------------------ évolution + répartition
HAUTEUR_1 = 430
c_evol, c_part = st.columns([2, 1])
with c_evol.container(border=True, key="carte_p1", height=HAUTEUR_1):
    titre_carte("Évolution du coût médian, 2011-2025", "Coût total en % du montant, par type de prestataire "
                                                       "(toutes années, mêmes filtres)")
    evol = base.groupby(["annee", "type_prestataire"]).agg(cout=("cc2_total_cost_pct", "median"),
                                                           n=("firm", "size")).reset_index()
    fig = go.Figure()
    for t, (lib, coul) in TYPES.items():
        e = evol[(evol["type_prestataire"] == t) & (evol["n"] >= 5)]     # au moins 5 offres par point
        fig.add_scatter(x=e["annee"], y=e["cout"], name=lib, mode="lines+markers", line=dict(color=coul, width=2.4),
                        marker=dict(size=6), customdata=e["n"], hovertemplate="%{y:.2f} % (%{customdata} offres)")
    fig.add_vrect(x0=debut - 0.5, x1=evol["annee"].max() + 0.5, fillcolor=ANIS_CLAIR, opacity=0.6, line_width=0,
                  layer="below")
    mise_en_page(fig, HAUTEUR_1 - 145, hovermode="x unified", legend=dict(orientation="h", y=1.1, x=0),
                 yaxis=dict(ticksuffix=" %", rangemode="tozero", gridcolor=GRILLE), xaxis=dict(gridcolor=GRILLE))
    st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)
    st.caption("Zone verte : période retenue pour les autres graphiques. Points calculés sur au moins 5 offres.")

with c_part.container(border=True, key="carte_p2", height=HAUTEUR_1):
    titre_carte("Qui propose les offres ?", f"Répartition des {len(d)} offres depuis {debut}")
    part = d["type_prestataire"].value_counts()
    ordre = [t for t in TYPES if t in part.index]
    fig = go.Figure(go.Pie(labels=[TYPES[t][0] for t in ordre], values=[part[t] for t in ordre], hole=0.72,
                           sort=False, direction="clockwise", rotation=90, textinfo="none",
                           marker=dict(colors=[TYPES[t][1] for t in ordre], line=dict(color="white", width=2)),
                           hovertemplate="%{label} : %{value} offres (%{percent})<extra></extra>"))
    principal = part.idxmax()
    fig.add_annotation(text=f"<b>{100 * part.max() / part.sum():.0f} %</b>", showarrow=False, y=0.56,
                       font=dict(size=28, color=VERT_FONCE))
    fig.add_annotation(text=TYPES[principal][0], showarrow=False, y=0.38, font=dict(size=12, color=ENCRE_2))
    fig.update_layout(height=180, margin=dict(l=0, r=0, t=4, b=4), showlegend=False, paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)
    lignes = ""
    for t in ordre:
        lib, coul = TYPES[t]
        lignes += (f"<div style='display:flex;align-items:center;gap:8px;padding:5px 0;border-top:1px solid #eef1ed'>"
                   f"<span style='width:10px;height:10px;border-radius:3px;background:{coul}'></span>"
                   f"<span style='flex:1'>{lib}</span><b>{part[t]}</b>"
                   f"<span style='width:60px;text-align:right;font-size:0.8em;color:{ENCRE_2}'>"
                   f"{pct(med.get(t))}</span></div>")
    st.markdown(f"<div style='font-size:0.88rem'><div style='text-align:right;font-size:0.75em;color:{ENCRE_2}'>"
                f"offres · coût médian</div>{lignes}</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ classement + nuage
HAUTEUR_2 = 520
c_table, c_nuage = st.columns([3, 2])
with c_table.container(border=True, key="carte_p3", height=HAUTEUR_2):
    titre_carte("Classement des prestataires", f"Du moins cher au plus cher · au moins {MIN_OFFRES} offres "
                                               f"depuis {debut}")
    if classement.empty:
        st.info("Pas assez d'offres par prestataire pour établir un classement.")
    else:
        maxi = classement["cout_median"].max()
        corps = ""
        for i, r in classement.head(8).iterrows():
            lib, coul = TYPES.get(r["type_prestataire"], (r["type_prestataire"], ENCRE_2))
            largeur = 100 * r["cout_median"] / maxi if maxi else 0
            corps += (
                f"<tr style='border-top:1px solid #eef1ed'><td style='padding:6px 6px;color:{ENCRE_2}'>{i + 1}</td>"
                f"<td style='padding:6px 6px'><span style='color:{coul}'>●</span> <b>{r['firm']}</b></td>"
                f"<td style='padding:6px 6px;width:34%'><div style='display:flex;align-items:center;gap:8px'>"
                f"<div style='flex:1;background:#f2f4f1;border-radius:999px;height:8px'>"
                f"<div style='width:{largeur:.0f}%;background:{coul};height:8px;border-radius:999px'></div></div>"
                f"<b style='width:52px;text-align:right'>{r['cout_median']:.2f} %</b></div></td>"
                f"<td style='padding:6px 6px;white-space:nowrap'>{case(DELAIS.get(round(r['delai']), '-'), '#eef8d6' if r['delai'] < 2.5 else '#fcefc7')}</td>"
                f"<td style='padding:6px 6px;text-align:right;color:{ENCRE_2}'>{r['nb_offres']}</td></tr>")
        entete = "".join(f"<th style='text-align:{a};padding:4px 6px;font-weight:600;color:{ENCRE_2};"
                         f"font-size:0.8em'>{c}</th>" for c, a in
                         [("#", "left"), ("Prestataire", "left"), ("Coût médian", "left"), ("Délai moyen", "left"),
                          ("Offres", "right")])
        st.markdown(f"<table style='width:100%;border-collapse:collapse;font-size:0.86rem'><thead><tr>{entete}"
                    f"</tr></thead><tbody>{corps}</tbody></table>", unsafe_allow_html=True)
        legende = " ".join(f"<span style='color:{c}'>●</span> {l}" for l, c in TYPES.values())
        reste = f" · et {len(classement) - 8} autres prestataires" if len(classement) > 8 else ""
        st.markdown(f"<div style='font-size:0.8rem;color:{ENCRE_2}'>{legende}{reste}</div>", unsafe_allow_html=True)

with c_nuage.container(border=True, key="carte_p4", height=HAUTEUR_2):
    titre_carte("Coût et rapidité", "Chaque point est un prestataire · en haut à gauche : rapide et peu cher")
    fig = go.Figure()
    for t, (lib, coul) in TYPES.items():
        e = classement[classement["type_prestataire"] == t]
        fig.add_scatter(x=e["cout_median"], y=e["delai"], mode="markers", name=lib, text=e["firm"],
                        marker=dict(color=coul, size=np.clip(8 + np.sqrt(e["nb_offres"]) * 1.6, 8, 34),
                                    line=dict(color="white", width=1.5), opacity=0.9),
                        customdata=e["nb_offres"],
                        hovertemplate="<b>%{text}</b><br>coût %{x:.2f} %<br>délai %{y:.1f}<br>%{customdata} offres"
                                      "<extra></extra>")
    meilleurs = classement.head(4)
    for _, r in meilleurs.iterrows():
        fig.add_annotation(x=r["cout_median"], y=r["delai"], text=r["firm"], showarrow=False, yshift=14,
                           font=dict(size=10, color=ENCRE_2))
    mise_en_page(fig, HAUTEUR_2 - 120, hovermode="closest", legend=dict(orientation="h", y=-0.18, x=0),
                 xaxis=dict(title="coût médian (%)", gridcolor=GRILLE, rangemode="tozero"),
                 yaxis=dict(autorange="reversed", tickvals=list(DELAIS), ticktext=list(DELAIS.values()),
                            gridcolor=GRILLE, range=[6.3, 0.7]))
    st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)

# ------------------------------------------------------------------ distribution + décomposition
HAUTEUR_3 = 400
c_boite, c_decomp = st.columns(2)
with c_boite.container(border=True, key="carte_p5", height=HAUTEUR_3):
    titre_carte("Dispersion des coûts", "Chaque boîte : de 25 % à 75 % des offres, trait = médiane")
    fig = go.Figure()
    for t, (lib, coul) in TYPES.items():
        e = d[d["type_prestataire"] == t]
        if len(e):
            fig.add_box(x=e["cc2_total_cost_pct"].clip(upper=20), name=lib, marker_color=coul, boxpoints=False,
                        line=dict(width=1.6), fillcolor=coul, opacity=0.75, orientation="h",
                        hovertemplate="%{x:.2f} %<extra>" + lib + "</extra>")
    mise_en_page(fig, HAUTEUR_3 - 120, showlegend=False, hovermode="closest",
                 xaxis=dict(title="coût total (%), plafonné à 20 %", gridcolor=GRILLE))
    st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)

with c_decomp.container(border=True, key="carte_p6", height=HAUTEUR_3):
    titre_carte("Frais ou marge de change ?", "Composition du coût médian par type de prestataire")
    comp = d.groupby("type_prestataire")[["frais_pct_cc2", "cc2_fx_margin"]].median()
    ordre = [t for t in TYPES if t in comp.index]
    fig = go.Figure()
    fig.add_bar(y=[TYPES[t][0] for t in ordre], x=comp.loc[ordre, "frais_pct_cc2"], name="frais", orientation="h",
                marker=dict(color=VERT_FONCE), hovertemplate="frais : %{x:.2f} %<extra></extra>")
    fig.add_bar(y=[TYPES[t][0] for t in ordre], x=comp.loc[ordre, "cc2_fx_margin"], name="marge de change",
                orientation="h", marker=dict(color=S4), hovertemplate="marge de change : %{x:.2f} %<extra></extra>")
    mise_en_page(fig, HAUTEUR_3 - 155, barmode="stack", barcornerradius=5, hovermode="y unified",
                 legend=dict(orientation="h", y=1.15, x=0), xaxis=dict(ticksuffix=" %", gridcolor=GRILLE))
    st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)
    st.caption("Pour un gros montant, les frais fixes deviennent négligeables : c'est la marge de change qui compte.")
