# Projet-data-lake-gestion-patrimoine

Data lake construit selon une architecture medallion (bronze/silver/gold) pour analyser le coût, la fiscalité et le risque des transferts d'argent internationaux depuis la France.

## Architecture

- **Bronze** : données brutes, telles que collectées depuis les sources (scraping, exports, API), sans transformation.
- **Silver** : données nettoyées, normalisées et structurées, prêtes à être croisées entre sources.
- **Gold** : données agrégées et enrichies, orientées analyse (coût, fiscalité, risque des transferts internationaux).

## Installation

```bash
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
playwright install chromium
```

## Sources de données

- **Financial Secrecy Index (FSI)** — Tax Justice Network, licence [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). À citer dans tous les usages et publications dérivées.
