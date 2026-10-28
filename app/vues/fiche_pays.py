"""Page 2 - Fiche pays : tout ce que le data lake sait d'une destination."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from commun import (CONFIG_GRAPHIQUE, ENCRE_2, FIABILITE, FOND_CONFORMITE, FOND_JAUNE, FOND_NIVEAU_RISQUE,
                    FOND_ROUGE, FOND_VERT, GRILLE, S1, S2, S3, VERT_FONCE, badge_fiabilite, case, euros,
                    executer, mise_en_page, requete, titre_carte, tuile, verifier_connexion)

verifier_connexion()

GRIS = "#9aa39d"
WGI = {"wgi_va": "Voix et<br>responsabilité", "wgi_pv": "Stabilité<br>politique",
       "wgi_ge": "Efficacité<br>du gouvernement", "wgi_rq": "Qualité de la<br>réglementation",
       "wgi_rl": "État de<br>droit", "wgi_cc": "Contrôle de<br>la corruption"}

# ------------------------------------------------------------------ données de référence (gold)
pays = requete("""
    select d.iso3, d.nom_fr, d.devise, d.zone_euro, d.date_adoption_euro, d.membre_ue, d.zone_sepa,
           d.income_group, c.groupe_cout, c.methode_cout, c.fiabilite, c.marge_change_pct,
           c.cout_change_eur_pour_100k, c.corridors_sources, c.periode_reference, c.nb_offres, c.commentaire,
           r.score_risque, r.niveau_risque, r.volatilite_change_pct, r.inflation_moy_5ans_pct,
           r.ecart_taux_bce_pts, r.gouvernance_moy, r.donnees_manquantes, r.periode_reference as periode_risque,
           f.taux_plus_value_pct, f.commentaires_fiscalite, f.fatf_status, f.gafi_date_pleniere,
           f.liste_ue, f.state_cooperation_with_eu, f.echange_crs_avec_france, f.instruments_avec_france,
           f.fsi_2026_score, f.fsi_2026_rank, f.seuil_fsi, f.conformite, f.motifs
    from gold.dim_pays d
    join gold.cout_transfert_france c using (iso3)
    join gold.risque_pays r using (iso3)
    join gold.fiscalite_conformite f using (iso3)
    order by d.nom_fr""")

# ------------------------------------------------------------------ choix du pays
st.title("Fiche pays")
noms = pays["nom_fr"].tolist()
defaut = st.session_state.get("pays_fiche", "Pologne")
choix = st.selectbox("Destination", noms, index=noms.index(defaut) if defaut in noms else 0,
                     label_visibility="collapsed")
st.session_state["pays_fiche"] = choix
p = pays[pays["nom_fr"] == choix].iloc[0]
iso3 = p["iso3"]

statut = [f"devise : {p['devise']}"]
if p["zone_euro"]:
    statut.append(f"zone euro depuis {pd.Timestamp(p['date_adoption_euro']).year}")
statut.append("membre de l'UE" if p["membre_ue"] else "hors UE")
if p["zone_sepa"]:
    statut.append("espace SEPA")
st.caption(" · ".join(statut))

# ------------------------------------------------------------------ indicateurs
rang_risque = int((pays["score_risque"] < p["score_risque"]).sum()) + 1
t1, t2, t3, t4 = st.columns(4)
t1.markdown(tuile("Coût de change pour 100 000 €", euros(p["cout_change_eur_pour_100k"]),
                  badge_fiabilite(p["fiabilite"]), f"marge {p['marge_change_pct']:.2f} %", "euro", active=True),
            unsafe_allow_html=True)
t2.markdown(tuile("Score de risque", f"{p['score_risque']:.0f} / 100", f"risque {p['niveau_risque'].lower()}",
                  f"{rang_risque}e plus sûr sur 22", "alerte"), unsafe_allow_html=True)
t3.markdown(tuile("Conformité", p["conformite"], "aucun signal" if p["conformite"] == "Conforme"
                  else f"{len(str(p['motifs']).split(','))} signal(aux)",
                  "GAFI · liste UE · échange · FSI", "bouclier"), unsafe_allow_html=True)
t4.markdown(tuile("Impôt sur les plus-values", f"{p['taux_plus_value_pct']:.1f} %",
                  "taux local", "seulement si le client s'y installe", "globe"), unsafe_allow_html=True)
st.write("")

# ------------------------------------------------------------------ change + gouvernance
c1, c2 = st.columns([3, 2])
with c1.container(border=True, key="carte_f1"):
    if p["zone_euro"]:
        titre_carte("Devise", "Pays de la zone euro")
        st.markdown(f"**{choix}** utilise l'euro depuis **{pd.Timestamp(p['date_adoption_euro']).year}** : un "
                    "transfert depuis la France ne comporte **aucun change** et suit les règles du virement SEPA "
                    "(mêmes frais qu'un virement national).")
        st.markdown(case("SEPA", FOND_VERT) + "&nbsp; pas de risque de change", unsafe_allow_html=True)
    else:
        titre_carte(f"Évolution de {p['devise']} face à l'euro",
                    "Unités de devise pour 1 € · une hausse signifie que la devise perd de la valeur")
        duree = st.radio("Période", ["1 an", "5 ans", "10 ans", "tout"], index=1, horizontal=True,
                         label_visibility="collapsed")
        fx = requete("select date, taux_pour_1_eur, volatilite_12m_pct from gold.taux_change_jour "
                     "where devise = :devise order by date", devise=p["devise"])
        fx["date"] = pd.to_datetime(fx["date"])
        if duree != "tout":
            fx = fx[fx["date"] >= fx["date"].max() - pd.DateOffset(years=int(duree.split()[0]))]
        variation = 100 * (fx["taux_pour_1_eur"].iloc[-1] / fx["taux_pour_1_eur"].iloc[0] - 1)
        fig = go.Figure(go.Scatter(x=fx["date"], y=fx["taux_pour_1_eur"], mode="lines",
                                   line=dict(color=S1, width=2), fill="tozeroy", fillcolor="rgba(31,122,77,0.07)",
                                   hovertemplate="%{x|%d/%m/%Y} : %{y:.4f} " + p["devise"] + "<extra></extra>"))
        bas = fx["taux_pour_1_eur"].min()
        mise_en_page(fig, 260, xaxis=dict(gridcolor=GRILLE), showlegend=False,
                     yaxis=dict(gridcolor=GRILLE, range=[bas * 0.97, fx["taux_pour_1_eur"].max() * 1.02],
                                title=f"{p['devise']} pour 1 €"))
        st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)
        vol = fx["volatilite_12m_pct"].dropna()
        st.markdown(f"Sur la période : **{variation:+.1f} %** de {p['devise']} pour 1 € "
                    f"({'la devise s’est dépréciée' if variation > 0 else 'la devise s’est appréciée'}) · "
                    f"volatilité sur 12 mois : **{vol.iloc[-1]:.1f} %**" if len(vol) else "")

with c2.container(border=True, key="carte_f2"):
    an = requete("select * from gold.indicateurs_annuels where wgi_va is not null and annee = "
                 "(select max(annee) from gold.indicateurs_annuels where wgi_va is not null)")
    an = an[an["iso3"] != "FRA"]
    titre_carte("Gouvernance", f"Banque mondiale WGI {int(an['annee'].iloc[0])} · de -2,5 (faible) à +2,5 (fort)")
    ligne = an[an["iso3"] == iso3].iloc[0]
    axes = list(WGI.values()) + [list(WGI.values())[0]]
    valeurs = [ligne[c] for c in WGI] + [ligne[list(WGI)[0]]]
    moyenne = [an[c].mean() for c in WGI] + [an[list(WGI)[0]].mean()]
    fig = go.Figure()
    fig.add_scatterpolar(r=moyenne, theta=axes, name="moyenne des 22", line=dict(color=GRIS, dash="dot", width=1.5),
                         hovertemplate="%{theta} : %{r:.2f}<extra>moyenne</extra>")
    fig.add_scatterpolar(r=valeurs, theta=axes, name=choix, fill="toself", fillcolor="rgba(134,191,58,0.30)",
                         line=dict(color=S1, width=2), hovertemplate="%{theta} : %{r:.2f}<extra></extra>")
    mise_en_page(fig, 320, margin=dict(l=70, r=70, t=30, b=10), polar=dict(bgcolor="white", radialaxis=dict(range=[-2.5, 2.5], gridcolor=GRILLE,
                                                                        tickfont=dict(size=9, color=ENCRE_2)),
                                      angularaxis=dict(gridcolor=GRILLE, tickfont=dict(size=10))),
                 legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center"))
    st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)

# ------------------------------------------------------------------ inflation et taux + conformité
c3, c4 = st.columns([3, 2])
with c3.container(border=True, key="carte_f3"):
    titre_carte("Inflation et taux directeur", "Moyennes annuelles (Banque mondiale, BIS) · pointillés : taux de la BCE")
    serie = requete("select annee, inflation_pct, taux_directeur_moyen_pct from gold.indicateurs_annuels "
                    "where iso3 = :iso3 and annee >= 2005 order by annee", iso3=iso3)
    bce = requete("select annee, taux_directeur_moyen_pct as bce from gold.indicateurs_annuels "
                  "where iso3 = 'DEU' and annee >= 2005 order by annee")
    fig = go.Figure()
    fig.add_bar(x=serie["annee"], y=serie["inflation_pct"], name="inflation", marker_color=S2,
                hovertemplate="%{x} : inflation %{y:.1f} %<extra></extra>")
    fig.add_scatter(x=serie["annee"], y=serie["taux_directeur_moyen_pct"], name="taux directeur", mode="lines+markers",
                    line=dict(color=VERT_FONCE, width=2), marker=dict(size=5),
                    hovertemplate="%{x} : taux directeur %{y:.2f} %<extra></extra>")
    if not p["zone_euro"]:
        fig.add_scatter(x=bce["annee"], y=bce["bce"], name="taux BCE", mode="lines",
                        line=dict(color=GRIS, width=1.5, dash="dot"), hovertemplate="%{x} : BCE %{y:.2f} %<extra></extra>")
    mise_en_page(fig, 280, barcornerradius=4, xaxis=dict(gridcolor=GRILLE),
                 yaxis=dict(gridcolor=GRILLE, title="%", zerolinecolor="#c9cfca"),
                 legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0))
    st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)
    if serie["taux_directeur_moyen_pct"].isna().all():
        st.caption("Pas de taux directeur pour ce pays dans les données BIS : le score de risque lui attribue "
                   "le risque maximal sur cette composante.")

with c4.container(border=True, key="carte_f4"):
    titre_carte("Conformité : le détail", f"Plénière GAFI du {pd.Timestamp(p['gafi_date_pleniere']):%d/%m/%Y}")
    gafi = {"none": ("aucune liste", FOND_VERT), "grey_list": ("liste grise", FOND_JAUNE),
            "black_list": ("liste noire", FOND_ROUGE)}[p["fatf_status"]]
    ue_fond = FOND_JAUNE if p["state_cooperation_with_eu"] == 1 else FOND_VERT
    fsi_fond = FOND_JAUNE if p["fsi_2026_score"] >= p["seuil_fsi"] else FOND_VERT
    lignes = [
        ("GAFI (blanchiment)", case(*gafi)),
        ("Liste UE des juridictions non coopératives", case(p["liste_ue"], ue_fond)),
        ("Échange automatique d'informations avec la France",
         case("oui", FOND_VERT) if p["echange_crs_avec_france"] else case("non", FOND_JAUNE)),
        (f"Opacité financière (FSI 2026, seuil {p['seuil_fsi']:.0f})",
         case(f"{p['fsi_2026_score']:.1f} · rang {int(p['fsi_2026_rank'])}", fsi_fond)),
        ("Bilan", case(p["conformite"])),
    ]
    st.markdown("<table style='width:100%;border-collapse:collapse;font-size:0.9rem'>" + "".join(
        f"<tr style='border-bottom:1px solid #eef1ed'><td style='padding:7px 4px;color:{ENCRE_2}'>{a}</td>"
        f"<td style='padding:7px 4px;text-align:right'>{b}</td></tr>" for a, b in lignes) + "</table>",
                unsafe_allow_html=True)
    if p["conformite"] != "Conforme":
        st.caption(f"À vérifier : {p['motifs']}")
    st.caption("Accords avec la France : " + (p["instruments_avec_france"] or "aucun"))

# ------------------------------------------------------------------ coût observé + économie
c5, c6 = st.columns([3, 2])
with c5.container(border=True, key="carte_f5"):
    titre_carte("Coût observé des envois vers ce pays (RPW)",
                "Coût total médian d'un envoi d'environ 500 USD, par pays d'envoi · trait plein : versé en devise "
                "locale, pointillés : versé en euro")
    obs = requete("""select corridor, source_code, period_std, payout_currency, cout_total_median_pct, nb_offres
                     from gold.cout_corridor_periode
                     where destination_code = :iso3 and type_prestataire = 'tous'
                       and payout_currency <> 'USD'   -- versements en dollars : hors sujet
                       and source_code <> 'TUR'       -- envois depuis la Turquie : marges atypiques
                     order by period_std""", iso3=iso3)
    if obs.empty and p["zone_euro"]:
        st.info(f"Pas d'envoi à observer : {choix} est en zone euro, le transfert depuis la France est un "
                "virement SEPA sans change (coût de change nul par construction).")
    elif obs.empty:
        st.info(f"Le RPW n'observe aucun envoi vers {choix}. Le coût affiché en haut est une **estimation** "
                f"(méthode « {p['methode_cout']} »).")
    else:
        couleurs = [S1, S2, S3, "#e0972a", VERT_FONCE, GRIS]
        fig = go.Figure()
        for i, ((corr, dev), g) in enumerate(obs.groupby(["corridor", "payout_currency"])):
            fig.add_scatter(x=g["period_std"], y=g["cout_total_median_pct"], mode="lines",
                            name=f"depuis {g['source_code'].iloc[0]} (versé en {dev})",
                            line=dict(color=couleurs[i % len(couleurs)], width=2,
                                      dash="solid" if dev != "EUR" else "dot"),
                            hovertemplate="%{x} : %{y:.2f} %<extra>" + f"{corr} {dev}" + "</extra>")
        mise_en_page(fig, 270, xaxis=dict(gridcolor=GRILLE, nticks=8), yaxis=dict(gridcolor=GRILLE, title="% du montant"),
                     legend=dict(orientation="h", y=-0.18, font=dict(size=10)))
        st.plotly_chart(fig, width="stretch", config=CONFIG_GRAPHIQUE)
    st.caption(f"Méthode retenue pour la France : {p['commentaire']}")

with c6.container(border=True, key="carte_f6"):
    titre_carte("Économie et composantes du risque", p["periode_risque"])
    eco = requete("select annee, croissance_pib_pct, dette_publique_pct_pib from gold.indicateurs_annuels "
                  "where iso3 = :iso3 and croissance_pib_pct is not null order by annee desc limit 1", iso3=iso3)
    med = pays[["volatilite_change_pct", "inflation_moy_5ans_pct", "ecart_taux_bce_pts", "gouvernance_moy"]].median()
    lignes = [("Croissance du PIB", f"{eco['croissance_pib_pct'].iloc[0]:+.1f} %" if len(eco) else "-",
               f"en {int(eco['annee'].iloc[0])}" if len(eco) else ""),
              ("Dette publique", f"{eco['dette_publique_pct_pib'].iloc[0]:.0f} % du PIB"
               if len(eco) and pd.notna(eco['dette_publique_pct_pib'].iloc[0]) else "-", "")]
    composantes = [("Volatilité du change (12 mois)", "volatilite_change_pct", "%", False),
                   ("Inflation moyenne sur 5 ans", "inflation_moy_5ans_pct", "%", False),
                   ("Écart de taux avec la BCE", "ecart_taux_bce_pts", " pts", False),
                   ("Gouvernance (moyenne WGI)", "gouvernance_moy", "", True)]
    for lib, col, unite, haut_bon in composantes:
        v = p[col]
        if pd.isna(v):
            lignes.append((lib, case("manquant", FOND_ROUGE), "risque maximal"))
            continue
        favorable = (v >= med[col]) if haut_bon else (v <= med[col])
        lignes.append((lib, case(f"{v:.2f}{unite}", FOND_VERT if favorable else FOND_JAUNE),
                       f"médiane des 22 : {med[col]:.2f}{unite}"))
    st.markdown("<table style='width:100%;border-collapse:collapse;font-size:0.9rem'>" + "".join(
        f"<tr style='border-bottom:1px solid #eef1ed'><td style='padding:7px 4px;color:{ENCRE_2}'>{a}</td>"
        f"<td style='padding:7px 4px;text-align:right'>{b}<br><span style='font-size:0.75rem;color:#9aa39d'>{c}</span>"
        f"</td></tr>" for a, b, c in lignes) + "</table>", unsafe_allow_html=True)
    st.caption("Vert : meilleur que la médiane des 22 destinations · jaune : moins bon.")
