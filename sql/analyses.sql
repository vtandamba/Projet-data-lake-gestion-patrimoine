-- =============================================================================
-- Requêtes d'analyse du data lake « gestion patrimoniale internationale »
-- =============================================================================
-- Base : PostgreSQL (docker compose), schémas silver et gold.
-- Chaque requête commence par une ligne d'en-tête lue par executer_requetes.py :
--     -- @<code> | <question> | <visuel conseillé> | <catégorie du sujet>
-- Catégories du sujet : 1 ingestion/profilage, 2 nettoyage/qualité, 3 fédération,
-- 4 préparation gold, 5 analyse interactive.
--
-- Exécuter tout le fichier :
--   Get-Content sql\analyses.sql | docker exec -i data_lake_postgres psql -U data_lake -d data_lake
-- Ou, plus lisible :
--   python src\analyse\executer_requetes.py            (toutes)
--   python src\analyse\executer_requetes.py Q14        (une seule)
-- =============================================================================


-- =============================================================================
-- PARTIE 0 - REQUÊTES TECHNIQUES (catégories 1 et 2 du sujet)
-- =============================================================================

-- @P1 | Profilage de la source RPW après chargement : volume, couverture et complétude | tableau | 1 ingestion/profilage
SELECT feuille,
       COUNT(*)                                                    AS nb_offres,
       COUNT(DISTINCT corridor)                                    AS nb_corridors,
       COUNT(DISTINCT firm)                                        AS nb_prestataires,
       MIN(period_std)                                             AS premiere_periode,
       MAX(period_std)                                             AS derniere_periode,
       ROUND(100.0 * AVG((cc2_total_cost_pct IS NULL)::int), 1)    AS pct_cout_500usd_manquant,
       ROUND(100.0 * AVG((payout_currency IS NULL)::int), 1)       AS pct_devise_versement_manquante,
       ROUND(100.0 * AVG((speed_actual IS NULL)::int), 1)          AS pct_delai_manquant
FROM silver.rpw
GROUP BY feuille
ORDER BY feuille;


-- @P2 | Qualité : corrections appliquées à RPW entre bronze et silver | tableau (ou barres) | 2 nettoyage/qualité
-- Chaque ligne = un type de problème détecté au profilage et l'action corrective appliquée.
WITH total AS (SELECT COUNT(*)::numeric AS n FROM silver.rpw)
SELECT probleme, action_corrective, nb_lignes, ROUND(100 * nb_lignes / total.n, 2) AS pct_lignes
FROM (
    SELECT 'devise de versement non fournie (aucune colonne dans la source)' AS probleme,
           'déduite du produit, des notes ou des taux BIS'   AS action_corrective,
           COUNT(*) FILTER (WHERE payout_source IS NOT NULL) AS nb_lignes FROM silver.rpw
    UNION ALL
    SELECT 'devise de versement impossible à déduire', 'laissée vide, signalée',
           COUNT(*) FILTER (WHERE payout_currency IS NULL) FROM silver.rpw
    UNION ALL
    SELECT 'taux interbancaire exprimé dans une autre devise', 'remplacé par le taux BIS de la bonne devise',
           COUNT(*) FILTER (WHERE inter_fx_remplace) FROM silver.rpw
    UNION ALL
    SELECT 'devise de la note différente de la devise versée', 'signalée (devise_note_differente)',
           COUNT(*) FILTER (WHERE devise_note_differente) FROM silver.rpw
    UNION ALL
    SELECT 'taux de change de l''offre suspect', 'signalé (cc2_lcu_fx_rate_suspect)',
           COUNT(*) FILTER (WHERE cc2_lcu_fx_rate_suspect) FROM silver.rpw
    UNION ALL
    SELECT 'taux promotionnel ou marché parallèle', 'coût ajusté recalculé (cc2_cout_ajuste_pct)',
           COUNT(*) FILTER (WHERE cout_ajuste_applique) FROM silver.rpw
    UNION ALL
    SELECT 'offres en double dans un même relevé', 'numérotées (rang_doublon), seule la 1re est gardée en gold',
           COUNT(*) FILTER (WHERE rang_doublon > 1) FROM silver.rpw
    UNION ALL
    SELECT 'noms de prestataires écrits de plusieurs façons', 'normalisés (firm, firm_original conservé)',
           COUNT(*) FILTER (WHERE firm <> firm_original) FROM silver.rpw
    UNION ALL
    SELECT 'produit ou délai non renseigné', 'imputé à partir des autres colonnes',
           COUNT(*) FILTER (WHERE product_impute OR speed_impute) FROM silver.rpw
) controles, total
ORDER BY nb_lignes DESC;


-- =============================================================================
-- BESOIN 1 - COÛT DU TRANSFERT
-- =============================================================================

-- @Q01 | Combien coûte le change pour 100 000 € envoyés depuis la France, et avec quelle fiabilité ? | barres horizontales, couleur = méthode | 4 gold
-- Lecture : la couleur compte autant que la longueur. Seuls les groupes B et C sont observés
-- (corridors depuis la zone euro) ; le groupe D est une estimation identique pour 5 pays ;
-- le groupe A (zone euro) n'a pas de change par construction (règle SEPA).
SELECT c.nom_fr                                AS destination,
       c.devise,
       c.groupe_cout,
       c.methode_cout,
       c.fiabilite,
       c.marge_change_pct,
       c.cout_change_eur_pour_100k,
       c.montant_recu_avant_frais_eur_pour_100k
FROM gold.cout_transfert_france c
ORDER BY c.cout_change_eur_pour_100k, c.nom_fr;


-- @Q02 | Dans le coût d'un envoi, quelle part vient des frais et quelle part du change ? | barres empilées (frais + marge) par corridor | 5 analyse
-- Les relevés portent sur environ 500 USD : pour un gros montant (100 000 €), les frais fixes
-- deviennent négligeables et la marge de change représente l'essentiel du coût.
-- Dernier trimestre observé, envois depuis un pays de la zone euro (situation la plus proche
-- d'un client français), versement en devise locale (hors EUR et USD), tous prestataires.
WITH derniere AS (
    SELECT MAX(period_std) AS periode FROM gold.cout_corridor_periode
)
SELECT c.corridor,
       c.source_code                      AS pays_envoi,
       c.destination_code                 AS pays_reception,
       c.payout_currency                  AS devise_versee,
       c.nb_offres,
       c.frais_median_pct,
       c.marge_change_mediane_pct,
       c.cout_total_median_pct,
       ROUND((100 * c.marge_change_mediane_pct
              / NULLIF(c.cout_total_median_pct, 0))::numeric, 0) AS part_change_pct
FROM gold.cout_corridor_periode c
JOIN gold.dim_pays envoi ON envoi.iso3 = c.source_code AND envoi.zone_euro
CROSS JOIN derniere
WHERE c.period_std = derniere.periode
  AND c.type_prestataire = 'tous'
  AND c.payout_currency NOT IN ('EUR', 'USD')
ORDER BY c.cout_total_median_pct DESC;


-- @Q03 | Les banques sont-elles plus chères que les opérateurs de transfert ? | boîtes à moustaches par type de prestataire | 5 analyse
-- Offres depuis 2023, envoyées depuis la zone euro et versées en devise locale
-- (situation d'un client français qui convertit ses euros).
SELECT type_prestataire,
       COUNT(*)                                                                    AS nb_offres,
       COUNT(DISTINCT firm)                                                        AS nb_prestataires,
       ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY cc2_total_cost_pct)::numeric, 2) AS q1_cout_pct,
       ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY cc2_total_cost_pct)::numeric, 2) AS mediane_cout_pct,
       ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY cc2_total_cost_pct)::numeric, 2) AS q3_cout_pct,
       ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY cc2_fx_margin)::numeric, 2)      AS mediane_marge_change_pct,
       ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY frais_pct_cc2)::numeric, 2)      AS mediane_frais_pct
FROM gold.offres_rpw o
JOIN gold.dim_pays envoi ON envoi.iso3 = o.source_code AND envoi.zone_euro
WHERE o.period_std >= '2023Q1'
  AND o.payout_currency NOT IN ('EUR', 'USD')
  AND o.cc2_total_cost_pct IS NOT NULL
GROUP BY type_prestataire
ORDER BY mediane_cout_pct DESC;


-- @Q04 | Le coût d'un transfert a-t-il baissé entre 2011 et 2025 ? | courbes par type de prestataire | 5 analyse
-- Même périmètre que Q03 : envois depuis la zone euro, versement en devise locale.
SELECT LEFT(period_std, 4)::int                                                     AS annee,
       type_prestataire,
       COUNT(*)                                                                     AS nb_offres,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cc2_total_cost_pct)::numeric, 2) AS cout_median_pct
FROM gold.offres_rpw o
JOIN gold.dim_pays envoi ON envoi.iso3 = o.source_code AND envoi.zone_euro
WHERE o.payout_currency NOT IN ('EUR', 'USD')
  AND o.cc2_total_cost_pct IS NOT NULL
GROUP BY 1, 2
UNION ALL
SELECT LEFT(period_std, 4)::int, 'tous', COUNT(*),
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cc2_total_cost_pct)::numeric, 2)
FROM gold.offres_rpw o
JOIN gold.dim_pays envoi ON envoi.iso3 = o.source_code AND envoi.zone_euro
WHERE o.payout_currency NOT IN ('EUR', 'USD')
  AND o.cc2_total_cost_pct IS NOT NULL
GROUP BY 1
ORDER BY annee, type_prestataire;


-- @Q05 | Quels prestataires sont à la fois peu chers et rapides ? | nuage de points coût x délai, taille = nb offres | 5 analyse
-- Offres depuis 2023 envoyées depuis la zone euro et versées en devise locale,
-- prestataires présents dans au moins 10 relevés.
-- speed_rang : 1 = moins d'une heure ... 6 = 6 jours ou plus.
SELECT firm                                                                           AS prestataire,
       MODE() WITHIN GROUP (ORDER BY type_prestataire)                                AS type_prestataire,
       COUNT(*)                                                                       AS nb_offres,
       COUNT(DISTINCT corridor)                                                       AS nb_corridors,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cc2_total_cost_pct)::numeric, 2) AS cout_median_pct,
       ROUND(AVG(speed_rang)::numeric, 1)                                             AS delai_moyen_rang
FROM gold.offres_rpw o
JOIN gold.dim_pays envoi ON envoi.iso3 = o.source_code AND envoi.zone_euro
WHERE o.period_std >= '2023Q1'
  AND o.payout_currency NOT IN ('EUR', 'USD')
  AND o.cc2_total_cost_pct IS NOT NULL
GROUP BY firm
HAVING COUNT(*) >= 10
ORDER BY cout_median_pct, delai_moyen_rang;


-- =============================================================================
-- BESOIN 2 - ÉVOLUTION ET RISQUE
-- =============================================================================

-- @Q06 | Quelles devises hors euro sont les plus volatiles ? | barres (volatilité 12 mois et 5 ans) | 5 analyse
-- Volatilité annualisée = écart-type des rendements logarithmiques quotidiens x racine(252).
WITH dernier AS (
    SELECT DISTINCT ON (devise) devise, date, taux_pour_1_eur, volatilite_12m_pct
    FROM gold.taux_change_jour
    WHERE volatilite_12m_pct IS NOT NULL
    ORDER BY devise, date DESC
),
cinq_ans AS (
    SELECT devise,
           100 * STDDEV_SAMP(rendement_log) * SQRT(252) AS volatilite_5ans_pct
    FROM gold.taux_change_jour
    WHERE date >= (SELECT MAX(date) FROM gold.taux_change_jour) - INTERVAL '5 years'
    GROUP BY devise
)
SELECT d.devise,
       STRING_AGG(p.nom_fr, ', ' ORDER BY p.nom_fr)  AS pays,
       d.date::date                                  AS date_dernier_taux,
       d.taux_pour_1_eur,
       ROUND(d.volatilite_12m_pct::numeric, 1)       AS volatilite_12m_pct,
       ROUND(c.volatilite_5ans_pct::numeric, 1)      AS volatilite_5ans_pct
FROM dernier d
JOIN cinq_ans c USING (devise)
JOIN gold.dim_pays p ON p.devise = d.devise AND p.iso3 <> 'FRA'
GROUP BY d.devise, d.date, d.taux_pour_1_eur, d.volatilite_12m_pct, c.volatilite_5ans_pct
ORDER BY volatilite_12m_pct DESC;


-- @Q07 | Comment ont évolué les devises hors euro face à l'euro sur 5 ans ? | courbes base 100 (au-dessus de 100 = la devise a perdu de la valeur) | 5 analyse
WITH mensuel AS (
    SELECT devise,
           DATE_TRUNC('month', date)::date AS mois,
           AVG(taux_pour_1_eur)            AS taux_moyen
    FROM gold.taux_change_jour
    WHERE date >= DATE_TRUNC('month', (SELECT MAX(date) FROM gold.taux_change_jour) - INTERVAL '5 years')
    GROUP BY devise, DATE_TRUNC('month', date)
)
SELECT devise,
       mois,
       ROUND(taux_moyen::numeric, 4) AS taux_moyen_pour_1_eur,
       ROUND((100 * taux_moyen / FIRST_VALUE(taux_moyen) OVER (PARTITION BY devise ORDER BY mois))::numeric, 1)
                                     AS indice_base_100
FROM mensuel
ORDER BY devise, mois;


-- @Q08 | Si le client attend 3 mois avant de convertir, dans quelle fourchette se situe le montant reçu ? | barres d'erreur (P5 - médiane - P95) par devise | 5 analyse complexe
-- Attention : un montant reçu plus élevé n'est pas forcément un gain. Pour TRY et UAH, il vient
-- surtout de la dépréciation de la devise, compensée par une forte inflation locale.
-- Méthode historique : sur les 5 dernières années, variation du taux entre chaque jour
-- et 63 jours ouvrés plus tard (environ 3 mois). Appliquée au taux du jour pour 100 000 €.
WITH paires AS (
    SELECT devise, date, taux_pour_1_eur,
           LEAD(taux_pour_1_eur, 63) OVER (PARTITION BY devise ORDER BY date) AS taux_3_mois
    FROM gold.taux_change_jour
    WHERE date >= (SELECT MAX(date) FROM gold.taux_change_jour) - INTERVAL '5 years'
),
variations AS (
    SELECT devise, taux_3_mois / taux_pour_1_eur - 1 AS variation
    FROM paires
    WHERE taux_3_mois IS NOT NULL
),
quantiles AS (
    SELECT devise,
           COUNT(*)                                                    AS nb_fenetres,
           PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY variation)     AS p05,
           PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY variation)     AS p50,
           PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY variation)     AS p95
    FROM variations
    GROUP BY devise
),
aujourdhui AS (
    SELECT DISTINCT ON (devise) devise, taux_pour_1_eur
    FROM gold.taux_change_jour
    ORDER BY devise, date DESC
)
SELECT q.devise,
       q.nb_fenetres,
       ROUND((100000 * a.taux_pour_1_eur)::numeric, 0)            AS recu_aujourdhui_devise_locale,
       ROUND((100000 * a.taux_pour_1_eur * (1 + q.p05))::numeric, 0) AS recu_3_mois_p05,
       ROUND((100000 * a.taux_pour_1_eur * (1 + q.p50))::numeric, 0) AS recu_3_mois_median,
       ROUND((100000 * a.taux_pour_1_eur * (1 + q.p95))::numeric, 0) AS recu_3_mois_p95,
       ROUND((100 * q.p05)::numeric, 1)                           AS variation_p05_pct,
       ROUND((100 * q.p50)::numeric, 1)                           AS variation_mediane_pct,
       ROUND((100 * q.p95)::numeric, 1)                           AS variation_p95_pct
FROM quantiles q
JOIN aujourdhui a USING (devise)
ORDER BY (q.p95 - q.p05) DESC;


-- @Q09 | Où en sont l'inflation et le taux directeur de chaque pays par rapport à la zone euro ? | nuage de points inflation x taux directeur | 3 fédération (Banque mondiale + BIS)
-- Requête de fédération sur la zone silver : inflation Banque mondiale (API JSON)
-- + taux directeurs BIS (fichiers SDMX), rapprochés par le code iso3.
-- Pays de la zone euro : taux de la BCE (série BIS XM, iso3 EMU).
WITH annee_ref AS (
    SELECT MAX(date::int) AS annee
    FROM silver.wb_api
    WHERE indicator_id = 'FP.CPI.TOTL.ZG' AND value IS NOT NULL
),
inflation AS (
    SELECT w.countryiso3code AS iso3, w.value AS inflation_pct
    FROM silver.wb_api w, annee_ref r
    WHERE w.indicator_id = 'FP.CPI.TOTL.ZG' AND w.date::int = r.annee
),
taux AS (
    SELECT b.iso3, AVG(b.taux_directeur_pct) AS taux_directeur_pct
    FROM silver.bis_cbpol b, annee_ref r
    WHERE EXTRACT(YEAR FROM b.date) = r.annee
    GROUP BY b.iso3
)
SELECT p.nom_fr                                                  AS pays,
       p.zone_euro,
       r.annee,
       ROUND(i.inflation_pct::numeric, 1)                        AS inflation_pct,
       ROUND(t.taux_directeur_pct::numeric, 2)                   AS taux_directeur_pct,
       CASE WHEN p.zone_euro THEN 'BCE' ELSE 'banque centrale nationale' END AS source_taux,
       ROUND((t.taux_directeur_pct - i.inflation_pct)::numeric, 1) AS taux_reel_pts,
       ROUND((t.taux_directeur_pct - bce.taux_directeur_pct)::numeric, 2) AS ecart_bce_pts
FROM gold.dim_pays p
CROSS JOIN annee_ref r
LEFT JOIN inflation i ON i.iso3 = p.iso3
LEFT JOIN taux t      ON t.iso3 = CASE WHEN p.zone_euro THEN 'EMU' ELSE p.iso3 END
LEFT JOIN taux bce    ON bce.iso3 = 'EMU'
ORDER BY inflation_pct DESC NULLS LAST;


-- @Q10 | Quel est le profil de gouvernance de chaque pays ? | carte de chaleur pays x dimension WGI | 4 gold
-- Scores WGI de -2,5 (faible) à +2,5 (fort), dernière année disponible.
SELECT p.nom_fr                         AS pays,
       a.annee,
       ROUND(a.wgi_va::numeric, 2)      AS voix_et_responsabilite,
       ROUND(a.wgi_pv::numeric, 2)      AS stabilite_politique,
       ROUND(a.wgi_ge::numeric, 2)      AS efficacite_gouvernement,
       ROUND(a.wgi_rq::numeric, 2)      AS qualite_reglementation,
       ROUND(a.wgi_rl::numeric, 2)      AS etat_de_droit,
       ROUND(a.wgi_cc::numeric, 2)      AS controle_corruption,
       ROUND(((a.wgi_va + a.wgi_pv + a.wgi_ge + a.wgi_rq + a.wgi_rl + a.wgi_cc) / 6)::numeric, 2) AS moyenne
FROM gold.indicateurs_annuels a
JOIN gold.dim_pays p USING (iso3)
WHERE a.annee = (SELECT MAX(annee) FROM gold.indicateurs_annuels WHERE wgi_va IS NOT NULL)
ORDER BY moyenne DESC;


-- =============================================================================
-- BESOIN 3 - CONFORMITÉ, RISQUE ET RECOMMANDATION
-- =============================================================================

-- @Q11 | Quelles destinations posent un problème de conformité, et pourquoi ? | tableau coloré (vert / orange) | 3 fédération (GAFI + UE + OCDE + Tax Justice Network + Tax Foundation)
-- Requête de fédération sur la zone silver : cinq sources de formats différents
-- (page web GAFI, liste UE, relations OCDE, indice FSI, fiscalité Tax Foundation).
-- Règle : à vérifier si liste grise/noire GAFI, liste UE (annexe I ou II),
-- pas d'échange automatique (CRS) avec la France, ou FSI >= 60.
WITH dest AS (
    SELECT iso3, nom_fr FROM gold.dim_pays WHERE iso3 <> 'FRA'
),
crs AS (
    SELECT from_country AS iso3,
           STRING_AGG(DISTINCT legal_instrument, ', ') AS instruments
    FROM silver.oecd_aeoi_relations
    WHERE to_country = 'FRA'
    GROUP BY from_country
),
regles AS (
    SELECT d.nom_fr                                       AS destination,
           ROUND((100 * t.capital_gains_tax_rate)::numeric, 1) AS taux_plus_value_pct,
           f.fatf_status                                  AS statut_gafi,
           e.classification                               AS liste_ue,
           c.instruments                                  AS echange_auto_avec_france,
           s.fsi_2026_score,
           ARRAY_REMOVE(ARRAY[
               CASE WHEN f.fatf_status IN ('grey_list', 'black_list') THEN CASE f.fatf_status WHEN 'grey_list' THEN 'liste grise GAFI' ELSE 'liste noire GAFI' END END,
               CASE WHEN e.state_cooperation_with_eu = 1 THEN 'liste UE des juridictions non coopératives (' || e.classification || ')' END,
               CASE WHEN c.instruments IS NULL THEN 'pas d''échange automatique avec la France' END,
               CASE WHEN s.fsi_2026_score >= 60 THEN 'opacité financière élevée (FSI ' || s.fsi_2026_score || ')' END
           ], NULL)                                       AS motifs
    FROM dest d
    LEFT JOIN silver.fatf f                            ON f.iso3 = d.iso3
    LEFT JOIN silver.eu_noncoop_list e                 ON e.country = d.iso3
    LEFT JOIN crs c                                    ON c.iso3 = d.iso3
    LEFT JOIN silver.fsi_2026_silver s                 ON s.iso3 = d.iso3
    LEFT JOIN silver.capital_gains_tax_europe_silver t ON t.iso3 = d.iso3
)
SELECT destination,
       CASE WHEN CARDINALITY(motifs) = 0 THEN 'Conforme' ELSE 'À vérifier' END AS conformite,
       ARRAY_TO_STRING(motifs, ' ; ')                 AS motifs,
       statut_gafi, liste_ue, echange_auto_avec_france, fsi_2026_score, taux_plus_value_pct
FROM regles
ORDER BY CARDINALITY(motifs) DESC, fsi_2026_score DESC NULLS LAST;


-- @Q12 | Quel est le niveau de risque de chaque destination ? | barres triées colorées par niveau | 4 gold
SELECT nom_fr                     AS destination,
       devise,
       score_risque,
       niveau_risque,
       volatilite_change_pct,
       inflation_moy_5ans_pct,
       ecart_taux_bce_pts,
       gouvernance_moy,
       NULLIF(donnees_manquantes, '') AS donnees_manquantes
FROM gold.risque_pays
ORDER BY score_risque DESC;


-- @Q13 | Scénario expatriation : si le client s'installe dans le pays, la fiscalité pèse-t-elle plus que le transfert ? | barres empilées (coût de change + impôt) avec repère « reste résident français » | 3 fédération (RPW + Tax Foundation)
-- Important : tant que le client reste résident fiscal en France, ses plus-values sont imposées en
-- France (prélèvement forfaitaire unique, 30 % prélèvements sociaux compris), quel que soit le pays
-- où l'argent est placé. Le taux du pays de destination ne compte que s'il s'y installe.
-- Taux : taux généraux de la Tax Foundation (hors exonérations liées à la durée de détention).
-- Hypothèses modifiables : 100 000 € transférés puis investis, plus-value de 20 % à la revente.
WITH hypotheses AS (
    SELECT 100000::numeric AS montant_eur, 20::numeric AS plus_value_pct, 30::numeric AS pfu_france_pct
),
calcul AS (
    SELECT c.nom_fr                                                         AS destination,
           c.methode_cout,
           c.cout_change_eur_pour_100k::numeric * h.montant_eur / 100000    AS cout_change_eur,
           COALESCE(f.taux_plus_value_pct, 0)::numeric                      AS taux_plus_value_pct,
           h.montant_eur * h.plus_value_pct / 100
               * COALESCE(f.taux_plus_value_pct, 0)::numeric / 100          AS impot_si_expatrie_eur,
           h.montant_eur * h.plus_value_pct / 100 * h.pfu_france_pct / 100  AS impot_si_resident_france_eur
    FROM gold.cout_transfert_france c
    JOIN gold.fiscalite_conformite f USING (iso3)
    CROSS JOIN hypotheses h
)
SELECT destination,
       methode_cout,
       ROUND(cout_change_eur, 0)                                 AS cout_change_eur,
       taux_plus_value_pct,
       ROUND(impot_si_expatrie_eur, 0)                           AS impot_si_expatrie_eur,
       ROUND(cout_change_eur + impot_si_expatrie_eur, 0)         AS total_si_expatrie_eur,
       ROUND(impot_si_resident_france_eur, 0)                    AS impot_si_resident_france_eur,
       ROUND(impot_si_resident_france_eur - impot_si_expatrie_eur, 0) AS economie_impot_expatriation_eur,
       CASE WHEN cout_change_eur > impot_si_expatrie_eur
            THEN 'transfert' ELSE 'fiscalité' END                AS poste_dominant_si_expatrie
FROM calcul
ORDER BY total_si_expatrie_eur, destination;


-- @Q14 | Quelle destination recommander selon les priorités du client ? | classement pondéré (barres) + stabilité du trio de tête entre profils | 5 analyse interactive complexe
-- Paramètres modifiables (dans Metabase : variables {{...}}). Chaque critère est ramené entre
-- 0 (le plus défavorable) et 100 (le plus favorable) puis pondéré ; les poids sont renormalisés.
-- La fiscalité du pays ne compte que dans le scénario expatriation (voir Q13) : pour un client
-- qui reste résident fiscal en France, elle est identique partout et son poids est ignoré.
WITH parametres AS (
    SELECT 0.35::numeric AS poids_cout,
           0.40::numeric AS poids_risque,
           0.25::numeric AS poids_fiscalite,
           0.25::numeric AS poids_conformite,
           FALSE         AS scenario_expatriation,
           FALSE         AS exclure_a_verifier
),
poids AS (   -- poids effectifs, renormalisés pour que leur somme fasse 1
    SELECT poids_cout / total AS w_cout, poids_risque / total AS w_risque,
           poids_fisc / total AS w_fiscalite, poids_conformite / total AS w_conformite,
           exclure_a_verifier
    FROM (SELECT p.*,
                 CASE WHEN scenario_expatriation THEN poids_fiscalite ELSE 0 END AS poids_fisc,
                 poids_cout + poids_risque + poids_conformite
                 + CASE WHEN scenario_expatriation THEN poids_fiscalite ELSE 0 END AS total
          FROM parametres p) t
),
base AS (
    SELECT d.iso3, d.nom_fr, d.devise, d.zone_euro,
           c.cout_change_eur_pour_100k::numeric        AS cout,
           c.fiabilite                                 AS fiabilite_cout,
           r.score_risque::numeric                     AS risque,
           r.niveau_risque,
           COALESCE(f.taux_plus_value_pct, 0)::numeric AS impot,
           f.conformite,
           f.motifs
    FROM gold.dim_pays d
    JOIN gold.cout_transfert_france c USING (iso3)
    JOIN gold.risque_pays r           USING (iso3)
    JOIN gold.fiscalite_conformite f  USING (iso3)
),
notes AS (
    SELECT b.*,
           100 * (MAX(cout)   OVER () - cout)   / NULLIF(MAX(cout)   OVER () - MIN(cout)   OVER (), 0) AS note_cout,
           100 * (MAX(risque) OVER () - risque) / NULLIF(MAX(risque) OVER () - MIN(risque) OVER (), 0) AS note_risque,
           100 * (MAX(impot)  OVER () - impot)  / NULLIF(MAX(impot)  OVER () - MIN(impot)  OVER (), 0) AS note_fiscalite,
           CASE WHEN conformite = 'Conforme' THEN 100 ELSE 0 END                                       AS note_conformite
    FROM base b
),
scores AS (
    SELECT n.*, w.w_cout, w.w_risque, w.w_fiscalite, w.w_conformite,
           n.note_cout * w.w_cout + n.note_risque * w.w_risque
         + n.note_fiscalite * w.w_fiscalite + n.note_conformite * w.w_conformite AS score
    FROM notes n
    CROSS JOIN poids w
    WHERE NOT (w.exclure_a_verifier AND n.conformite <> 'Conforme')
)
SELECT RANK() OVER (ORDER BY score DESC)          AS rang,
       iso3,
       nom_fr                                     AS destination,
       devise,
       ROUND(score, 1)                            AS score_global,
       ROUND(note_cout, 0)                        AS note_cout,
       ROUND(note_risque, 0)                      AS note_risque,
       ROUND(note_fiscalite, 0)                   AS note_fiscalite,
       note_conformite,
       ROUND(w_cout, 3)       AS poids_cout_effectif,
       ROUND(w_risque, 3)     AS poids_risque_effectif,
       ROUND(w_fiscalite, 3)  AS poids_fiscalite_effectif,
       ROUND(w_conformite, 3) AS poids_conformite_effectif,
       cout                                       AS cout_change_eur_pour_100k,
       fiabilite_cout,
       risque                                     AS score_risque,
       impot                                      AS taux_plus_value_pct,
       conformite,
       motifs
FROM scores
ORDER BY rang, destination;


-- =============================================================================
-- PARTIE APPLICATION - DONNÉES ET QUALITÉ
-- =============================================================================

-- @D1 | Inventaire des zones silver et gold dans PostgreSQL : tables, lignes et colonnes | tableau + barres | 1 ingestion/profilage
SELECT t.table_schema AS zone,
       t.table_name   AS nom_table,
       (xpath('/row/n/text()',
              query_to_xml(format('SELECT COUNT(*) AS n FROM %I.%I', t.table_schema, t.table_name),
                           false, true, '')))[1]::text::bigint AS nb_lignes,
       (SELECT COUNT(*) FROM information_schema.columns c
        WHERE c.table_schema = t.table_schema AND c.table_name = t.table_name) AS nb_colonnes
FROM information_schema.tables t
WHERE t.table_schema IN ('silver', 'gold') AND t.table_type = 'BASE TABLE'
ORDER BY 1, 3 DESC;


-- @D2 | Fraîcheur et période couverte de chaque source | tableau | 1 ingestion/profilage
SELECT 'RPW (Banque mondiale)' AS source, 'coût des envois d''argent' AS contenu,
       MIN(period_std) AS debut, MAX(period_std) AS fin, COUNT(*) AS nb_lignes FROM silver.rpw
UNION ALL
SELECT 'BIS - taux de change', 'cours quotidiens contre USD',
       MIN(date)::date::text, MAX(date)::date::text, COUNT(*) FROM silver.bis_xru_daily
UNION ALL
SELECT 'BIS - taux directeurs', 'taux des banques centrales (quotidien)',
       MIN(date)::date::text, MAX(date)::date::text, COUNT(*) FROM silver.bis_cbpol_daily
UNION ALL
SELECT 'BIS - prix', 'indice des prix, inflation (mensuel)',
       MIN(date)::date::text, MAX(date)::date::text, COUNT(*) FROM silver.bis_cpi
UNION ALL
SELECT 'BCE - taux de référence', 'cours quotidiens contre EUR',
       MIN(date)::date::text, MAX(date)::date::text, COUNT(*) FROM silver.ecb_exchange_rates_silver
UNION ALL
SELECT 'Banque mondiale + FMI (API)', 'inflation, croissance, dette publique',
       MIN(date)::text, MAX(date)::text, COUNT(*) FROM silver.wb_api
UNION ALL
SELECT 'Banque mondiale - WGI', 'gouvernance (6 dimensions)',
       MIN(year)::text, MAX(year)::text, COUNT(*) FROM silver.wgi
UNION ALL
SELECT 'GAFI', 'listes grise et noire', MAX(plenary_date)::date::text, MAX(plenary_date)::date::text, COUNT(*)
FROM silver.fatf
UNION ALL
SELECT 'Union européenne', 'liste des juridictions non coopératives', NULL, NULL, COUNT(*) FROM silver.eu_noncoop_list
UNION ALL
SELECT 'OCDE', 'accords d''échange automatique d''informations', NULL, NULL, COUNT(*) FROM silver.oecd_aeoi_relations
UNION ALL
SELECT 'Tax Justice Network', 'indice d''opacité financière 2026', '2026', '2026', COUNT(*) FROM silver.fsi_2026_silver
UNION ALL
SELECT 'Tax Foundation', 'imposition des plus-values (Europe)', NULL, NULL, COUNT(*)
FROM silver.capital_gains_tax_europe_silver
UNION ALL
SELECT 'Référentiel pays', 'régions, devises, groupes de revenu', NULL, NULL, COUNT(*) FROM silver.countries_silver;


-- @D3 | Méthode d'estimation du coût depuis la France : nombre de pays par groupe | anneau + tableau | 4 gold
SELECT groupe_cout, methode_cout, MIN(fiabilite) AS fiabilite, COUNT(*) AS nb_pays,
       STRING_AGG(nom_fr, ', ' ORDER BY nom_fr) AS pays,
       ROUND(AVG(marge_change_pct)::numeric, 2) AS marge_moyenne_pct
FROM gold.cout_transfert_france
GROUP BY groupe_cout, methode_cout
ORDER BY groupe_cout;
