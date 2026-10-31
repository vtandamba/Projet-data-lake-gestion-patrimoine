# Projet-data-lake-gestion-patrimoine

Data lake construit selon une architecture medallion (bronze/silver/gold) pour analyser le coût, la fiscalité et le risque des transferts d'argent internationaux depuis la France.

**Cas d'usage.** Un conseiller patrimonial accompagne un client résidant en France qui souhaite transférer une partie de son patrimoine vers un autre pays européen. Le data lake lui permet de comparer **22 destinations** selon trois besoins :

1. **le coût du transfert** (frais et marge de change) ;
2. **l'évolution et le risque** de la destination (change, inflation, taux directeurs, gouvernance) ;
3. **la conformité et la fiscalité**, puis la recommandation d'une destination selon les priorités du client.

Projet M2 DS4SC (Université de Tours, Blois) - module Data Lake & ingénierie des données.

---

## Démarrage rapide (Docker)

Prérequis : Docker Desktop. La zone `data/silver` est versionnée dans le dépôt ; `data/gold` n'a pas besoin d'être remplie au préalable.

Depuis un clone, deux commandes suffisent :

```bash
docker compose up -d --build postgres application   # base PostgreSQL + application conseiller
docker compose run --rm gold                         # construit data/gold depuis data/silver, puis charge silver + gold dans la base
```

Le service `gold` exécute `src/gold/construire_gold.py` (les 9 tables gold, rapports dans `reports/gold_*.txt`), puis `src/gold/charger_postgres.py`. Si la construction échoue, le chargement n'est pas lancé. Une fois `data/gold` rempli, `docker compose run --rm chargement` suffit pour recharger la base sans reconstruire gold.

> **Périmètre reproductible.** Docker couvre le chemin **silver → gold → PostgreSQL**. La phase **bronze → silver** reste une étape de préparation locale (voir [Pipeline](#pipeline-de-données)) : certaines sources bronze sont déposées à la main (fichiers téléchargés manuellement), donc elle n'est pas conteneurisée. Son résultat, `data/silver/`, est versionné pour que le reste du pipeline soit rejouable tel quel.

| Service | Adresse | Rôle |
|---|---|---|
| `application` | http://localhost:8501 | application conseiller « Passerelle » (Streamlit) |
| `postgres` | `localhost:5434`, base / utilisateur / mot de passe `data_lake` | schémas `silver` et `gold` |
| `gold` | lancé à la demande | construit `data/gold` depuis `data/silver`, puis charge silver et gold dans la base |
| `chargement` | lancé à la demande | recharge silver et gold dans la base (sans reconstruire gold) |

Arrêter : `docker compose down` (les données restent dans le volume) · tout effacer : `docker compose down -v`.
Identifiants de développement **local** uniquement : la base n'est pas exposée sur Internet.

---

## Architecture

```
 sources publiques          BRONZE                 SILVER                 GOLD               RESTITUTION
 (Excel, CSV SDMX,   ─►  fichiers bruts     ─►  CSV nettoyés      ─►  tables métier   ─►  PostgreSQL (Docker)
  API JSON, web)         data/bronze/            data/silver/          data/gold/          ├─ requêtes SQL
                         aucune modification     22 tables             9 tables            ├─ notebook
                                                 types, iso3,          coût, risque,       └─ application
                                                 doublons corrigés     conformité
```

- **Bronze** : données brutes, telles que collectées depuis les sources (scraping, exports, API), sans transformation.
- **Silver** : données nettoyées, normalisées et structurées, prêtes à être croisées entre sources (codes pays ISO3, dates typées, devises harmonisées, doublons et erreurs corrigés).
- **Gold** : données agrégées et enrichies, orientées analyse (coût, fiscalité, risque des transferts internationaux).
- **PostgreSQL** : les zones silver et gold sont chargées dans deux schémas (`silver`, `gold`) pour les requêtes SQL, le notebook et l'application.

| Zone | Format | Pourquoi |
|---|---|---|
| Bronze | format d'origine (xlsx, CSV SDMX, JSON aplati en CSV) | garder la donnée telle que reçue, pour pouvoir tout rejouer |
| Silver | CSV (UTF-8) | format commun de l'équipe, lisible et versionnable |
| Gold | CSV + PostgreSQL | tables métier interrogeables en SQL (jointures, fenêtres, agrégats) |

### Tables gold

| Table | Contenu |
|---|---|
| `dim_pays` | 23 pays (France + 22 destinations) : devise, zone euro, UE, SEPA, groupe de méthode de coût |
| `cout_transfert_france` | coût de change estimé depuis la France pour chaque destination, avec méthode et fiabilité |
| `offres_rpw` | offres de transfert observées (RPW) sur les corridors utiles |
| `cout_corridor_periode` | coûts médians par corridor, trimestre, devise de versement et type de prestataire |
| `taux_change_jour` | cours quotidiens contre l'euro, volatilité et moyenne sur 12 mois |
| `indicateurs_mensuels` | inflation, taux directeur et écart avec la BCE, par mois |
| `indicateurs_annuels` | inflation, croissance, dette publique, gouvernance (WGI), volatilité du change, par an |
| `fiscalite_conformite` | imposition des plus-values, listes GAFI et UE, échange d'informations, opacité financière |
| `risque_pays` | score de risque de 0 à 100 et niveau (faible, moyen, élevé) |

---

## Structure du dépôt

```
app/                    application conseiller (Streamlit) + Dockerfile
  app.py                point d'entrée et menu
  commun.py             connexion à la base, lecture des requêtes, thème
  vues/                 pages : simulation client, fiche pays, prestataires, données et qualité
data/                   bronze/, silver/, gold/ (non versionnés)
docs/                   note de cadrage, besoins et requêtes
notebooks/              demonstrateur.ipynb
reports/                rapports de profilage et de construction, résultats des requêtes, figures
sql/analyses.sql        toutes les requêtes d'analyse (profilage, qualité, fédération, gold, analyse)
src/ingestion/          collecte vers bronze (ingest_*_bronze.py) et profilage
src/transformation/     nettoyage vers silver (transform_*_silver.py)
src/gold/               construction des tables gold et chargement PostgreSQL
src/analyse/            exécution des requêtes et profilage
docker-compose.yml      base PostgreSQL, application, chargement, gold
docker/                 gold.Dockerfile (pipeline silver → gold → PostgreSQL)
```

---

## Installation locale (sans Docker pour Python)

```bash
python -m venv venv
source venv/Scripts/activate        # Windows PowerShell : venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium         # utilisé par l'ingestion FMI
docker compose up -d postgres       # la base seule
```

---

## Pipeline de données

Toutes les commandes se lancent depuis la racine du dépôt. Chaque script décrit ses entrées et sorties en tête de fichier.

1. **Bronze** : `python src/ingestion/ingest_<source>_bronze.py` pour les sources téléchargeables (Banque mondiale, FMI, WGI, GAFI, OCDE, liste UE, FSI) ; les fichiers RPW (Excel) et BIS (CSV SDMX) sont déposés dans `data/bronze/` puis extraits.
2. **Silver** : `python src/transformation/transform_<source>_silver.py` (un script par source).
3. **Gold** : `python src/gold/construire_gold.py` (ou, avec le chargement enchaîné, `docker compose run --rm gold`) construit les 9 tables dans l'ordre des dépendances (environ 40 s) ; un rapport par table est écrit dans `reports/gold_*.txt`.
4. **PostgreSQL** : `python src/gold/charger_postgres.py` (ou `docker compose run --rm chargement`) charge silver et gold par `COPY` et vérifie le nombre de lignes de chaque table.

---

## Requêtes, notebook et application

- **`sql/analyses.sql`** : chaque requête commence par une ligne `-- @code | question | visuel | catégorie`.
  - catégorie 1, ingestion et profilage : `P1`, `D1`, `D2` ;
  - catégorie 2, nettoyage et qualité : `P2` ;
  - catégorie 3, fédération de sources hétérogènes : `Q09` (Banque mondiale + BIS), `Q11` (GAFI + UE + OCDE + FSI + Tax Foundation), `Q13` ;
  - catégorie 4, préparation gold : `Q01`, `Q10`, `Q12`, `D3` ;
  - catégorie 5, analyse : `Q02` à `Q08`, et `Q14` (recommandation paramétrable).

  ```bash
  python src/analyse/executer_requetes.py          # toutes les requêtes, résultats dans reports/analyses/
  python src/analyse/executer_requetes.py Q14      # une seule
  ```
- **`notebooks/demonstrateur.ipynb`** : exécute les requêtes, trace un graphique par question (enregistré dans `reports/figures/`) et simule plusieurs profils de client.
- **Application « Passerelle »** (http://localhost:8501) :
  - *Simulation client* : classement des destinations selon le montant, l'horizon, le profil et l'éventuelle expatriation ;
  - *Fiche pays* : tout ce que le data lake sait d'une destination ;
  - *Prestataires* : banques et opérateurs de transfert comparés (coût, rapidité, évolution) ;
  - *Données et qualité* : architecture, sources, contrôles de qualité et méthode d'estimation.

  Sans Docker : `streamlit run app/app.py`.

---

## Qualité des données et limites

- **Corrections RPW** (bronze → silver) : devise de versement déduite, taux interbancaires dans la mauvaise devise remplacés par les taux BIS, taux promotionnels et marché parallèle signalés et recalculés, doublons numérotés, noms de prestataires normalisés (détail : requête `P2` et page *Données et qualité*).
- **Aucun envoi au départ de la France** n'existe dans le RPW vers les destinations étudiées. Le coût depuis la France est donc estimé en 4 groupes : **A** zone euro (pas de change, règle SEPA), **B** corridors observés depuis la zone euro, **C** observé depuis une autre devise, **D** estimation (médiane européenne). Chaque coût affiché indique sa méthode et sa fiabilité.
- **Petits montants** : le RPW mesure des envois de 200 et 500 USD ; pour un montant patrimonial, seule la marge de change est extrapolée.
- **Fiscalité** : un résident fiscal français est imposé en France sur ses plus-values, où que soit placé son argent ; le taux local (Tax Foundation, taux général) ne compte que dans un scénario d'expatriation.
- **Données manquantes** : pas de taux directeur pour l'Ukraine dans les données BIS (compté comme risque maximal dans le score).
- **Pondérations** du score de risque et de la recommandation : hypothèses documentées et modifiables.

---

## Sources de données

| Source | Contenu | Format d'origine |
|---|---|---|
| Banque mondiale - Remittance Prices Worldwide (RPW) | coût des envois d'argent, 2011-2025 | Excel (2 feuilles) |
| BIS (Banque des règlements internationaux) | taux de change, taux directeurs, prix | CSV SDMX |
| BCE | taux de change de référence contre l'euro | CSV |
| Banque mondiale (API WDI) et FMI (DataMapper) | inflation, croissance, dette publique | API JSON |
| Banque mondiale - Worldwide Governance Indicators | gouvernance (6 dimensions) | API JSON |
| GAFI | listes grise et noire (plénière de juin 2026) | page web |
| Union européenne | liste des juridictions non coopératives | fichier de l'équipe |
| OCDE | accords d'échange automatique d'informations | fichier de l'équipe |
| Tax Foundation | imposition des plus-values en Europe | fichier de l'équipe |
| Tax Justice Network - Financial Secrecy Index 2026 | opacité financière | CSV |

- **Financial Secrecy Index (FSI)** — Tax Justice Network, licence [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). À citer dans tous les usages et publications dérivées.
- Contours des pays de la carte : `app/assets/europe.geo.json`, d'après Natural Earth (domaine public) via le dépôt johan/world.geo.json.
