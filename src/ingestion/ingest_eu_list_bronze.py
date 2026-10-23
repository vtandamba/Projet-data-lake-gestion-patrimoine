"""
Ingestion — Liste UE des juridictions non coopératives à des fins fiscales
==========================================================================
Zone BRONZE : récupération brute des trois listes de pays de la page.

La page affiche chaque liste deux fois : sous forme de graphique Datawrapper
(iframe) et sous forme de « Text version » (texte HTML). On lit la version
texte, qui suit chacun des trois titres de section :
  - « Listed: these countries do not cooperate with the EU… »        (annexe I)
  - « Countries which cooperate with the EU and have pending… »      (annexe II)
  - « Countries which cooperate with the EU and have no pending… »   (coopératifs)

Source  : https://www.consilium.europa.eu/en/policies/eu-list-of-non-cooperative-jurisdictions/
Licence : site du Conseil de l'UE, réutilisation autorisée avec mention de la source.
          >>> Citer le Conseil de l'Union européenne comme source dans le rapport. <<<

Principe bronze : on enregistre les données TELLES QUELLES, sans nettoyage.
Colonnes : Section (titre exact de la page), Country (nom tel qu'écrit),
           Revision (date de mise à jour de la liste, telle qu'écrite).
Le nettoyage (codes ISO, code de statut 0/1/2, dates) se fera en zone SILVER.

Sorties :
  data/bronze/eu_noncoop_list_AAAAMMJJ.csv    données extraites
  data/bronze/eu_noncoop_list_AAAAMMJJ.html   copie de la page (pour retraitement)
"""

import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup, NavigableString, Tag

URL = "https://www.consilium.europa.eu/en/policies/eu-list-of-non-cooperative-jurisdictions/"
OUTPUT_DIR = Path("data/bronze")
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}
# Motifs qui reconnaissent les trois titres de section
SECTIONS = [
    re.compile(r"do not cooperate", re.I),
    re.compile(r"cooperate with the EU and have pending commitments", re.I),
    re.compile(r"cooperate with the EU and have no pending commitments", re.I),
]


def recuperer_html() -> str:
    """Télécharge la page ; passe par un vrai navigateur (Playwright) si le site bloque."""
    try:
        reponse = requests.get(URL, headers=HEADERS, timeout=60)
        if reponse.status_code == 200 and "cooperate" in reponse.text:
            return reponse.text
        print(f"[!] Réponse inattendue (HTTP {reponse.status_code}), essai avec Playwright…")
    except requests.RequestException as exc:
        print(f"[!] Erreur réseau ({exc}), essai avec Playwright…")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"], locale="en-US")
        page.goto(URL, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(5000)
        html = page.content()
        browser.close()
        return html


def nettoyer_espaces(texte: str) -> str:
    """Retire seulement les espaces en trop autour du texte (pas de nettoyage métier)."""
    return re.sub(r"\s+", " ", texte).strip(" ,; ")


def ressemble_a_un_pays(texte: str) -> bool:
    t = nettoyer_espaces(texte)
    return (1 < len(t) <= 60 and not re.search(r"\d", t) and len(t.split()) <= 6
            and t.lower() not in {"text version", "listed"} and "press release" not in t.lower())


def pays_apres_titre(titre: Tag) -> list[str]:
    """Pays listés entre ce titre et le titre suivant (bloc « Text version »)."""
    def fin(el):
        # On s'arrête au titre suivant, quel que soit son niveau : sur le site,
        # les titres de section sont des <h4>.
        return (isinstance(el, Tag) and el is not titre
                and el.name in ("h1", "h2", "h3", "h4", "h5", "h6"))

    pays = []
    for el in titre.next_elements:           # cas normal : liste à puces <li>
        if fin(el):
            break
        if isinstance(el, Tag) and el.name == "li" and ressemble_a_un_pays(el.get_text(" ")):
            pays.append(nettoyer_espaces(el.get_text(" ")))

    if not pays:                              # repli : pays séparés par des virgules
        morceaux = []
        for el in titre.next_elements:
            if fin(el):
                break
            if isinstance(el, NavigableString) and el.parent.name not in ("script", "style"):
                morceaux.append(str(el))
        pays = [nettoyer_espaces(m) for m in re.split(r"[,\n;]", "\n".join(morceaux))
                if ressemble_a_un_pays(m)]
    return list(dict.fromkeys(pays))


def date_de_revision(soup: BeautifulSoup) -> str:
    """Date de mise à jour telle qu'écrite sur la page (communiqué, sinon timeline)."""
    texte = soup.get_text(" ")
    m = re.search(r"press release,\s*(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})", texte)
    if m:
        return m.group(1)
    m = re.search(r"\b\d{2}/\d{2}/\d{4}\b", texte)
    return m.group(0) if m else ""


def extraire(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    titres = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    revision = date_de_revision(soup)
    lignes = []
    for motif in SECTIONS:
        titre = next((t for t in titres if motif.search(t.get_text(" "))), None)
        if titre is None:
            print(f"[!] Section introuvable : {motif.pattern}")
            continue
        for pays in pays_apres_titre(titre):
            lignes.append({"Section": nettoyer_espaces(titre.get_text(" ")),
                           "Country": pays, "Revision": revision})
    return pd.DataFrame(lignes, columns=["Section", "Country", "Revision"])


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now().strftime("%Y%m%d")

    html = recuperer_html()
    (OUTPUT_DIR / f"eu_noncoop_list_{horodatage}.html").write_text(html, encoding="utf-8")

    df = extraire(html)
    if df.empty:
        raise SystemExit("[X] Aucun pays extrait : la structure de la page a peut-être changé.")

    sortie = OUTPUT_DIR / f"eu_noncoop_list_{horodatage}.csv"
    df.to_csv(sortie, index=False)

    print(f"\n[OK] Bronze enregistré : {sortie}")
    print(f"     {df.shape[0]} lignes, {df.shape[1]} colonnes")
    print(f"     Révision de la liste : {df['Revision'].iloc[0] or 'non trouvée'}")
    print("\nNombre de pays par section (à comparer avec la page) :")
    for section, n in df.groupby("Section", sort=False).size().items():
        print(f"  {n:>3}  {section[:80]}")


if __name__ == "__main__":
    main()