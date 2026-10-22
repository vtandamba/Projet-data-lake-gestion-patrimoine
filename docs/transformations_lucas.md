# Transformations des sources 1 (feuille 2), 2 et 8

Passage de la zone **bronze** (`data/bronze/lucas/`) à la zone **silver** (`data/silver/lucas/`), réalisé en Python (pandas).

```bash
python src/transformation/transform_lucas_silver.py
```

À lancer depuis la racine du dépôt. Option `--refresh` : re-télécharge la liste des pays depuis l'API Banque mondiale
(sinon la copie locale est utilisée ; elle est téléchargée automatiquement si elle est absente).
Dépendances : `pandas`, `pyarrow` (Parquet), `requests` (uniquement avec `--refresh`).
Le script vide `data/silver/lucas/` avant d'écrire (les dossiers des autres membres ne sont pas touchés). **Fermer les fichiers silver ouverts dans Excel avant de le lancer** (Windows verrouille les fichiers ouverts).

## Fichiers en entrée (bronze)

| Source | Fichier | Rôle |
|---|---|---|
| 1 (feuille 2) | `data/bronze/lucas/Countries.csv` | Classification des pays (feuille « Countries » du classeur RPW) |
| complément 1 | `data/bronze/lucas/worldbank_countries_api.json` | Réponse brute de l'API Banque mondiale v2 `/country` (région et groupe de revenu actuels) |
| complément 1 | `src/transformation/reference/country_currency.csv` | Table pays → devise ISO 4217 **construite à la main**, avec l'historique depuis 2011 |
| 2 | `data/bronze/lucas/eurofxref-hist.xml` | Taux de change de référence BCE |
| 8 | `data/bronze/lucas/2026 Capital Gains Tax Rates in Europe  Tax Foundation Europe.csv` | Taux d'imposition des plus-values |

Dans `data/`, seule la zone silver est versionnée (voir `.gitignore`) : la copie de l'API Banque mondiale n'est pas
dans Git et le script la retélécharge si elle est absente. Le référentiel des devises est rangé avec le code car il est
construit à la main.

## Fichiers en sortie (silver, `data/silver/lucas/`)

| Fichier | Lignes × colonnes | Clé |
|---|---|---|
| `countries-silver` | 213 × 8 | `iso3` |
| `currency_history-silver` | 13 × 4 | `iso3` + `currency_code` |
| `ecb_exchange_rates-silver` | 221 499 × 3 | `date` + `currency_code` |
| `capital_gains_tax_europe-silver` | 35 × 4 | `iso3` |
| `_metadata.json` | — | Source, fichiers d'origine, date de chargement et constantes de chaque table |
| `quality_report.txt` | — | Journal des contrôles et anomalies détectées |

Chaque table est écrite en CSV (UTF-8) et en Parquet. Les types (dates, booléens, catégorie ordonnée) ne sont conservés que dans le Parquet : c'est le format à privilégier.

```
countries ──iso3──> capital_gains_tax_europe
    │
    ├─currency_code──> ecb_exchange_rates   (EUR : taux = 1, non stocké)
    └─iso3──> currency_history              (devise en vigueur avant un changement)
```

## Conventions communes à toutes les tables

| Règle | Application |
|---|---|
| Noms de colonnes | snake_case, en anglais ; booléens préfixés par `is_` |
| Pays | identifié par `iso3` ; libellé `country_name` = **nom Banque mondiale** dans toutes les tables |
| Devises | `currency_code` (ISO 4217) |
| Dates | ISO `AAAA-MM-JJ` |
| Taux et pourcentages | en **fraction** : 0.275 = 27,5 % |
| Valeurs manquantes | null (cellule vide en CSV), jamais `..`, `-` ou chaîne vide |
| **Pas de répétition** | Aucune colonne constante, aucune colonne calculable à partir d'une autre, aucune ligne en double. Les informations valables pour toute une table (source, date de chargement, trimestre de classification, année fiscale) sont dans `_metadata.json`. **Le script refuse d'écrire une table qui ne respecte pas cette règle.** |
| Nom des fichiers | `<table>-silver.csv` / `<table>-silver.parquet` |

---

## Source 1 (feuille 2) : `countries-silver`

### Problèmes constatés
- Encodage Windows-1252 (« Côte d'Ivoire », « Curaçao », « Türkiye » mal lus par défaut), séparateur `;`.
- Ligne de titre fusionnée au-dessus des en-têtes ; elle contient la date de classification (« updated Q3 2025 »).
- 3 colonnes fantômes vides ; valeurs manquantes codées `..`.
- `ZAR` (ancien code du Zaïre, doublon de `COD`) et `ANT` (Antilles néerlandaises, dissoutes en 2010, sans donnée).
- `region` vide pour 75 pays (pays à revenu élevé non régionalisés dans cette feuille).
- Colonne `G8/G20` qui mélange deux informations ; la Russie y figure encore au G8 (exclue en 2014).

### Transformations
1. Lecture en `cp1252` ; la date de classification (`2025-Q3`) est extraite de la ligne de titre et rangée dans `_metadata.json`.
2. Suppression des 3 colonnes vides, renommage en snake_case, `..` → null, suppression des espaces.
3. Suppression des lignes `ZAR` et `ANT`.
4. **Confrontation avec l'API Banque mondiale**, avec une règle unique : une valeur manquante de la feuille RPW n'est
   complétée par l'API que si les deux sources concordent sur toutes les valeurs renseignées.
   - **Région** : aucune divergence → les **75 régions manquantes sont complétées**.
   - **Groupe de revenu** : 6 divergences (JOR, FSM, PHL, LKA, VNM passés en Upper middle income ; TGO en Lower middle income).
     La feuille RPW donne la classification **2025-Q3**, l'API la classification **actuelle** (révisée chaque 1er juillet) :
     ce sont deux millésimes. `income_group` est donc **conservé tel que publié en 2025-Q3**, cohérent avec la période
     des données RPW, et **VEN reste vide** : il n'était pas classé en 2025-Q3 (l'API actuelle le classe Lower middle income).
     Le détail est écrit par le script dans `quality_report.txt`.
5. `G8/G20` → `is_g20` et **`is_g7`** (liste G7 explicite, sans la Russie).
6. `income_group` typé en **catégorie ordonnée** (Low < Lower middle < Upper middle < High) : on peut trier et comparer sans colonne de rang.
7. **`currency_code`** (devise actuelle) et **`currency_since`** (date d'entrée en vigueur, uniquement si elle a changé depuis 2011).
8. **`lending_category` supprimée** (catégorie de prêt IDA/IBRD/Blend, sans rapport avec l'objet du projet).

| Colonne | Type | Description |
|---|---|---|
| `iso3` | texte | Code pays (Banque mondiale : `KSV` pour le Kosovo, `CHI` pour les îles Anglo-Normandes) |
| `country_name` | texte | Nom Banque mondiale |
| `region` | texte | Région Banque mondiale (7 modalités, aucune valeur nulle) |
| `income_group` | catégorie ordonnée | Groupe de revenu, classification 2025-Q3 (null pour VEN, non classé à cette date) |
| `currency_code` | texte | Devise actuelle (ISO 4217) |
| `currency_since` | date | Date de passage à la devise actuelle ; null = inchangée depuis 2011 (13 pays renseignés) |
| `is_g20` | booléen | Membre du G20 (19 pays) |
| `is_g7` | booléen | Membre du G7 |

## Référentiel : `currency_history-silver`

Construit à la main (aucune source fournie ne relie pays et devises). Ne contient **que les anciennes devises** ; la devise
actuelle est déjà dans `countries`. Sert à joindre un taux BCE à une date passée : passages à l'euro (LVA 2014, LTU 2015,
HRV 2023, BGR 2026) et redénominations (BYN 2016, MRU/STN 2018, VES 2018, SLE 2022, XCG 2025, Zimbabwe 2019/2024).

| Colonne | Description |
|---|---|
| `iso3`, `currency_code` | Pays et ancienne devise |
| `valid_from` | Début de validité ; null = déjà en vigueur avant 2011 |
| `valid_to` | Dernier jour de validité |

Pour connaître la devise d'un pays à une date `d` : la ligne de `currency_history` telle que `d <= valid_to` (et `d >= valid_from` si renseigné), sinon `countries.currency_code`.


## Source 2 : `ecb_exchange_rates-silver`

### Constats
- 221 499 cotations, 7 119 jours ouvrés (04/01/1999 → 21/10/2026), 41 devises. Aucun doublon, aucun taux nul ou négatif.
- Pas de cotation les week-ends et jours fériés TARGET (normal).
- 12 devises discontinues : passage à l'euro (CYP, MTL, SIT, SKK, EEK, LVL, LTL, HRK, BGN), redénomination (TRL, ROL),
  suspension (RUB depuis mars 2022). La liste et les motifs sont dans `_metadata.json`, les dates dans `quality_report.txt`.
- ISK : aucune cotation entre fin 2008 et le 01/02/2018 (suspension après la crise islandaise).

### Transformations
1. Aplatissement du XML en table longue `date`, `currency_code`, `rate_per_eur` ; typage date et décimal ; tri par devise puis date.
2. Rien d'autre n'est ajouté, volontairement :
   - **pas de lignes EUR** : le taux vaut toujours 1, il se remplace à la jointure (`fillna(1)` ou condition sur `EUR`) ;
   - **pas de taux inverse** : `1 / rate_per_eur` ;
   - **pas d'indicateur de devise discontinue** : c'est une propriété de la devise, pas de chaque cotation (dernière date de cotation, ou `_metadata.json`).

| Colonne | Type | Description |
|---|---|---|
| `date` | date | Jour de cotation |
| `currency_code` | texte | Devise (ISO 4217) |
| `rate_per_eur` | décimal | Unités de devise pour 1 EUR |

> Limite importante : seuls **77 pays sur 213** ont une devise cotée par la BCE (27 en euro + 50 autres).
> Pour les autres devises (corridors de transfert vers l'Afrique, l'Asie du Sud…), il faudra une autre source de taux de change.

## Source 8 : `capital_gains_tax_europe-silver`

### Problèmes constatés
- CSV mal échappé (chaque ligne entre guillemets, guillemets internes doublés) : lu comme une seule colonne.
- Pays et code ISO2 dans le même champ (`Austria (AT)`) ; taux en texte avec `%` ; `-` pour « pas de commentaire ».
- Noms différents de la Banque mondiale : Czech Republic, Slovakia, Turkey.

### Transformations
1. Réparation de l'échappement, puis lecture CSV.
2. Extraction du code ISO2 → `iso3` (35/35 pays retrouvés dans `countries`).
3. **`country_name` remplacé par le nom Banque mondiale** (Czechia, Slovak Republic, Türkiye).
4. **`capital_gains_tax_rate` en fraction** : `"27.5%"` → `0.275`.
5. `comments` : `-` → null ; texte d'origine conservé sans correction.
6. L'année fiscale (2026, identique pour toutes les lignes) est dans `_metadata.json`.

| Colonne | Type | Description |
|---|---|---|
| `iso3` | texte | Code pays |
| `country_name` | texte | Nom Banque mondiale |
| `capital_gains_tax_rate` | décimal | Taux marginal supérieur (fraction) |
| `comments` | texte | Commentaire Tax Foundation (null si absent) |

### Points d'attention dans les commentaires (texte d'origine, non corrigé)
- Un taux de 0 % (Grèce, Slovénie, Luxembourg, Suisse, Turquie…) dépend souvent de conditions (durée de détention, part détenue).
  Portugal : 19,6 % affiché, mais le commentaire mentionne 28 % avec abattements.
- Estonie : « From 20% in 2024 » (phrase tronquée) ; Luxembourg : « aAdependency » ; Roumanie : « 356 days » (probablement 365).

---

## Récapitulatif des colonnes supprimées ou déplacées

| Origine | Colonne | Décision | Raison |
|---|---|---|---|
| Source 1 | 3 colonnes `Unnamed` | Supprimées | Vides |
| Source 1 | `Lending category` | Supprimée | Sans rapport avec le projet, 70 nulls |
| Source 1 | `G8/G20` | Remplacée par `is_g20`, `is_g7` | Deux informations dans une colonne ; G8 obsolète |
| Source 1 | date de classification (titre) | → `_metadata.json` | Une seule valeur pour toute la table |
| Source 1 | rang du groupe de revenu | Non créé | L'ordre est porté par le type catégorie ordonnée |
| Référentiel | devises actuelles | Non dupliquées | Déjà dans `countries.currency_code` |
| Source 2 | lignes EUR, `eur_per_unit`, `is_discontinued` | Non créées | Constante, calcul, propriété de la devise |
| Toutes | `source_name`, `source_file`, `loaded_at` | → `_metadata.json` | Identiques sur toutes les lignes |
| Source 8 | `Country` | Remplacée par `iso3` + `country_name` (BM) | Nom et code mélangés, noms non harmonisés |
| Source 8 | `Top Marginal Capital Gains Tax Rate` | Remplacée par `capital_gains_tax_rate` | Texte avec `%` → fraction |
| Source 8 | année fiscale | → `_metadata.json` | Une seule valeur (2026) |

## Colonne conservée mais à écarter en analyse (gold)
- `comments` : texte libre, utile seulement pour interpréter les taux à 0 %.
