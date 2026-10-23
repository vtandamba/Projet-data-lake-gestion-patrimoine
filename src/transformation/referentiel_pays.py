import difflib
import re
import unicodedata

# Les 23 pays du périmètre : iso3 -> (nom normalisé, membre de l'UE)
PERIMETRE = {
    "AUT": ("Austria", 1), "BEL": ("Belgium", 1), "BGR": ("Bulgaria", 1),
    "HRV": ("Croatia", 1), "CZE": ("Czechia", 1), "EST": ("Estonia", 1),
    "FRA": ("France", 1), "DEU": ("Germany", 1), "HUN": ("Hungary", 1),
    "ITA": ("Italy", 1), "LVA": ("Latvia", 1), "LTU": ("Lithuania", 1),
    "NLD": ("Netherlands", 1), "NOR": ("Norway", 0), "POL": ("Poland", 1),
    "PRT": ("Portugal", 1), "ROU": ("Romania", 1), "ESP": ("Spain", 1),
    "SWE": ("Sweden", 1), "CHE": ("Switzerland", 0), "TUR": ("Türkiye", 0),
    "UKR": ("Ukraine", 0), "GBR": ("United Kingdom", 0),
}

# Autres écritures rencontrées dans les sources (minuscules) -> iso3
VARIANTES = {
    "czech republic": "CZE",          # OCDE (ancien nom)
    "siwtzerland": "CHE",             # OCDE (faute de frappe)
    "turkey": "TUR", "turkiye": "TUR",
    "uk": "GBR", "great britain": "GBR",
    "united kingdom of great britain and northern ireland": "GBR",
    "the netherlands": "NLD", "netherlands (the)": "NLD",
    "slovak republic": None,          # hors périmètre, listé pour mémoire
}

_NOM_VERS_ISO3 = {nom.lower(): iso3 for iso3, (nom, _) in PERIMETRE.items()}


def normaliser(nom) -> str:
    """Unicode NFC, espaces insécables, apostrophes typographiques, espaces multiples."""
    if nom is None:
        return ""
    t = unicodedata.normalize("NFC", str(nom))
    t = t.replace(" ", " ").replace("’", "'")
    return re.sub(r"\s+", " ", t).strip()


def vers_iso3(nom) -> str | None:
    """Code ISO3 si le pays fait partie du périmètre, sinon None."""
    cle = normaliser(nom).lower()
    if cle in _NOM_VERS_ISO3:
        return _NOM_VERS_ISO3[cle]
    return VARIANTES.get(cle)


def noms_suspects(noms) -> dict:
    """Noms non reconnus mais très proches d'un pays du périmètre (faute de frappe probable)."""
    references = [nom for nom, _ in PERIMETRE.values()]
    suspects = {}
    for nom in sorted(set(noms)):
        if vers_iso3(nom) or normaliser(nom).lower() in VARIANTES:
            continue
        proche = difflib.get_close_matches(normaliser(nom), references, n=1, cutoff=0.88)  # 0.88 : détecte « Siwtzerland » (0.91), ignore « Australia » (0.875)
        if proche:
            suspects[nom] = proche[0]
    return suspects