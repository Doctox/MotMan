#!/usr/bin/env python3
"""Search a compact full-frame arrowword fill from frequent French words."""
from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from wordfreq import iter_wordlist, zipf_frequency


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bitset_grid_filler import fill_bitset  # noqa: E402
from build_compact_7x8_review import family_key  # noqa: E402
from editorial_fill_quality import answer_usage  # noqa: E402


@dataclass(frozen=True)
class Slot:
    index: int
    slot_id: str
    direction: str
    clue_cell: tuple[int, int]
    cells: tuple[tuple[int, int], ...]


OWNER_SHORT = {
    "ADN", "ADO", "AGE", "AH", "AIE", "AIR", "AMI", "AN", "ARC", "ART", "AS", "AXE", "BAC", "BAL", "BAN",
    "BAR", "BAS", "BEC", "BD", "BIO", "BLE", "BOL", "BON", "BOX", "BUS", "BUT",
    "AU", "CA", "CAP", "CAR", "CAS", "CB", "CD", "CDI", "CE", "CES", "CET", "CI", "COQ", "COR", "CPE",
    "CLE", "COU", "CRI", "CRU", "CV", "DE", "DIX", "DOC", "DON", "DOS", "DU", "DUC", "DUE", "DUO",
    "DUR", "EAU", "ELU", "EN", "ERE", "ES", "ETE", "ET", "EU", "EUX", "EX", "FAC", "FAN", "FEU", "FIL",
    "FIN", "FOI", "FOU", "FUT", "GAZ", "HLM", "HOP", "HUM", "IL", "ILS", "JE", "JET", "JEU",
    "GO", "HA", "IA", "IF", "JUS", "KO", "LA", "LAC", "LE", "LIS", "LOI",
    "LIT", "LOT", "LU", "LUI", "MA", "MAI", "MAL", "MAP", "ME", "MER", "MET", "MIE", "MIG",
    "MOI", "MOT", "MU", "MUR", "NE", "NET", "NEZ", "NI",
    "NIL", "NO", "NOM", "NON", "OH", "OM", "ON", "ONU", "OR", "OS", "OSE", "OU", "OUI", "PAC", "PI", "PO", "PU",
    "PAN", "PAS", "PC", "PDG", "PIC", "PIE", "PIN", "PLU", "PNG", "POP", "POT", "PRO",
    "PUB", "PUR",
    "QUE", "QUI", "RAP", "RAS", "RAT", "RIS", "RIZ", "ROI", "RU", "RUE", "SAC", "SEC", "SEL", "SI", "SIX", "SKI",
    "SA", "SE", "SMS", "SOI", "SOL", "SON", "SOU", "SUD", "SU", "TA", "TE", "TGV", "TIG", "TIR", "TOM",
    "TOI", "TON", "TOT", "TPE", "TRI", "TU", "TV", "UN", "UNE", "VA", "VAL", "VAN", "VAS", "VIE", "VIF",
    "QR", "USE", "UT", "VIN", "VIS", "VIT", "VOL", "VOS", "VS", "VU", "VUE", "WC", "WEB", "XI", "XL",
    # Charnières courtes, modernes ou très courantes. Elles restent une liste
    # fermée : wordfreq ne peut donc pas réintroduire des fragments au hasard.
    "AIL", "ANE", "APP", "AUX", "BAT", "BIP", "BIS", "BLA", "BOT", "BUG", "BYE",
    "CDD", "COL", "DES", "DIT", "DVD", "ECO", "EGO", "EST", "EVE", "FEE", "FIT",
    "FUN", "GEL", "GIF", "GPS", "GYM", "ICI", "ION", "IRA", "JOB", "KIT", "LAS",
    "LED", "LES", "LIN", "LYS", "MAG", "MAX", "MDR", "MEC", "MIN", "MIS", "MIX",
    "MON", "NEE", "NID", "NOS", "NUL", "ONT", "OUF", "PAR", "PDF", "PEU",
    "PIB", "PME", "PUE", "RDV", "RER", "RIT", "ROC", "RPG", "SAS", "SES", "SIM",
    "SOS", "SPA", "SUR", "TAC", "TAF", "TAG", "TAS", "TEL", "TES", "TOC", "TOP",
    "TUE", "TVA", "USB", "VAR", "VER", "VTT", "WII", "WOW", "YEN", "ZEN", "ZOO",
}
# Le pilote 7×8 n'a plus aucune exception à deux lettres. La liste historique
# reste lisible dans le diff, mais ces formes ne peuvent plus entrer au solveur.
OWNER_SHORT = {answer for answer in OWNER_SHORT if len(answer) >= 3}
# Domaine fermé pour les nouveaux pilotes. OWNER_SHORT reste disponible pour
# relire les anciens lots, mais ne constitue plus une validation éditoriale.
PILOT_SAFE_SHORT = {
    "ADO", "AGE", "AIL", "AMI", "ANE", "APP", "ARC", "ART", "AXE",
    "BAC", "BAL", "BAN", "BAR", "BAS", "BEC", "BIO", "BLE", "BOA", "BON", "BOT",
    "BOX", "BUG", "BUS", "BUT", "CAP", "CAR", "CAS", "CDD", "CDI",
    "CLE", "COL", "COQ", "COR", "COU", "CPE", "CRI", "CRU", "DIX",
    "DOC", "DON", "DOS", "DUC", "DUO", "DUR", "EAU", "ELU", "ETE", "FAN", "FEU", "FUT",
    "FIL", "FIN", "FOI", "FOU", "GAZ", "GEL", "GIF", "GPS", "HLM",
    "ION", "IRM", "JET", "JEU", "JOB", "JUS", "KIT", "LAC", "LED",
    "LIN", "LIT", "LOI", "LOT", "LYS", "MAL", "MAP", "MDR", "MER", "MIE", "MIX",
    "MOT", "MUR", "NET", "NEZ", "NID", "NIL", "NOM", "NON", "OIE",
    "NUS", "ONU", "PAC", "PAN", "PAS", "PDF", "PDG", "PIC", "PIB", "PIE", "PIN",
    "PME", "PNG", "POP", "POT", "PRE", "PRO", "PUB", "PUR", "RAP", "RAS",
    "RAT", "RDV", "RER", "RIB", "RIZ", "ROC", "ROI", "RPG", "RUE",
    "SAC", "SAS", "SEC", "SEL", "SIM", "SIX", "SKI", "SMS", "SOL",
    "SOS", "SOU", "SUD", "TAF", "TAG", "TAS", "TGV", "TIR", "TOC",
    "TPE", "TRI", "TTC", "TVA", "ULM", "USB", "VAN", "VER", "VIF",
    "VIN", "VIS", "VOL", "VTT", "VUE", "WEB", "WII", "WOW", "YEN",
    "ZEN", "ZIP", "ZOO",
    # Courts usuels, noms connus et sigles dont l'indice peut être univoque.
    "ARA", "ARE", "AYA", "BOB", "BTS", "CAF", "CEP", "CIL", "ENA",
    "EPI", "EVA", "FBI", "GAG", "HUB", "KEN", "KFC", "KID", "KIR",
    "LEO", "LOU", "MAT", "MIA", "NEM", "NEO", "NOE", "ODE", "OMS",
    "ONG", "QCM", "RAM", "RIO", "RTT", "SAM", "SET", "TEE", "TIC",
    "TNT", "TOM", "THE", "VIP", "WOK", "AIR", "ILE",
    # Un seul de ces mots-outils au maximum par pilote (contrôlé par le solveur).
    "AUX", "DES", "ICI", "MON", "OUI", "PAR", "PEU", "SON", "SUR", "TOI", "TON", "UNE",
    # Références modernes/sigles connus, toujours avec un indice explicite.
    "AFK", "BFF", "BMX", "DLC", "FAQ", "FPS", "GTA", "IRL", "JDR",
    "JPG", "LAN", "LOL", "MMO", "NBA", "NFC", "PNJ", "POV", "PVP",
    "SAV", "TER", "VOD", "VPN", "VTC",
    # Complément 16-45 ans : mots autonomes, interjections et sigles que l'on
    # peut définir sans fragment ni relation approximative. Les abréviations
    # devront être signalées explicitement dans l'indice final.
    "ADN", "AIE", "ALU", "API", "ARN", "BIP", "BIS", "BLA", "BOL", "BYE",
    "CAM", "CPU", "DVD", "ECO", "EGO", "ERE", "EVE", "FAC", "FAX", "FEE",
    "FIG", "FOX", "FUN", "GPU", "GYM", "HIT", "HOP", "HUM", "LIS", "MAC",
    "MAG", "MAX", "MEC", "MOD", "NFT", "NUL", "OUF", "PSG", "ROM", "RSA",
    "SPA", "SUB", "SVP", "TAC", "TOP", "TOT", "URL", "USA", "VAL", "VIE",
}
PILOT_REVIEWED_LONG = {
    # Références largement connues, admises comme réponses textuelles.
    "ADIDAS", "AIRBNB", "ALADDIN", "AMAZON", "ANDROID", "ANGELE",
    "ASTERIX", "BARBIE", "BATMAN", "BEYONCE", "DEEZER", "DISNEY",
    "FALLOUT", "FERRARI", "GOTHAM", "GOOGLE", "IPHONE", "LACOSTE",
    "MARVEL", "MATRIX", "MICKEY", "MINNIE", "MUFASA", "NARUTO",
    "NETFLIX", "NUTELLA", "OBELIX", "ORELSAN", "PAYPAL", "PEUGEOT",
    "PIKACHU", "POKEMON", "PORSCHE", "RAYMAN", "RENAULT", "RIHANNA",
    "ROBLOX", "SAMSUNG", "SHAKIRA", "SPOTIFY", "STITCH", "STROMAE",
    "TETRIS", "TIKTOK", "TWITCH", "YOUTUBE",
    # Vocabulaire actuel absent ou mal classé dans certains lexiques papier.
    "CAPTCHA", "CONSOLE", "ESPORTS", "HASHTAG", "LAPTOP", "PODCAST",
    "SELFIE", "STORIES", "VINTAGE", "WEBTOON", "WEEKEND",
    "AFRIQUE", "ALGERIE", "ALSACE", "BERLIN", "BRESIL", "CANADA",
    "ESPAGNE", "EUROPE", "FRANCE", "ITALIE", "LONDRES", "MADRID",
    "MOSCOU", "SUISSE", "TUNISIE",
    "AMIXEM", "ANAKIN", "ARAGORN", "ARCANE", "BENZEMA", "BIGFLO",
    "BUGATTI", "CARLITO", "CITROEN", "CYPRIEN", "DANONE", "DEXTER",
    "DIABLO", "DISCORD", "DOMINGO", "EMINEM", "FEDERER", "FRIENDS",
    "FRODON", "GANDALF", "GOLLUM", "GOTAGA", "HAGRID", "HARIBO",
    "HERMES", "HUAWEI", "INOXTAG", "IRONMAN", "KAMETO",
    "KENOBI", "KINDER", "LEGOLAS", "LOUANE", "MBAPPE", "MICHOU",
    "NARCOS", "NEYMAR", "PACMAN", "PHELPS", "POKORA", "POTTER",
    "REDDIT", "REEBOK", "RIHANNA", "RONALDO", "SAURON", "SERENA",
    "SKYRIM", "SOPRANO", "THANOS", "TITANIC", "TOYOTA", "TWITTER",
    "VIANNEY", "VIKINGS", "VINTED", "VUITTON", "XIAOMI", "ZERATOR",
    "ZIDANE",
    # Réservoir culturel/numérique large : candidat au placement seulement,
    # chaque réponse reste soumise à la relecture du lot final.
    "AIRPODS", "BEREAL", "BOOKING", "CAPCUT", "CASTER", "CHANEL",
    "CHATGPT", "CHROME", "COPILOT", "CULTURA", "DROPBOX", "FIREFOX",
    "FITBIT", "FREEBOX", "GAMEPAD", "GALAXY", "GAMING", "GARMIN",
    "GEMINI", "GENSHIN", "GITHUB", "GITLAB", "HOTMAIL", "ICLOUD",
    "JORDAN", "KAHOOT", "KINDLE", "LENOVO", "MACBOOK", "MALWARE",
    "MEETIC", "MINIONS", "MISTRAL", "MOJANG", "MONSTER", "MYCANAL",
    "NOTION", "NVIDIA", "ONLINE", "OPENAI", "OUTLOOK", "PHILIPS",
    "PRIMARK", "QUIZLET", "REBOOT", "REDBULL", "REPLAY", "REVOLUT",
    "ROUTEUR", "SAFARI", "SERVEUR", "SHAZAM", "SHOPIFY", "SHORTS",
    "SPRITE", "STRIPE", "SWITCH", "THREADS", "TINDER", "TRELLO",
    "UBISOFT", "UPDATE", "UPLOAD", "WARZONE", "WIDGET", "WINDOWS",
    "YAMAHA", "ZALANDO",
    "ABONNES", "ALERTE", "APPELS", "ARCHIVE", "BACKUP", "BLOQUER",
    "CAMERA", "CASQUE", "CLAVIER", "CONTACT", "CONTENU", "COOKIE",
    "DIRECT", "DOMAINE", "DONNEES", "DOSSIER", "EMOJIS", "FICHIER",
    "FILTRES", "FOLLOW", "FORMAT", "GADGET", "HACKER", "LAPTOP",
    "LIVRER", "MANETTE", "MATCHER", "MEMOIRE", "MOBILE", "MOTEUR",
    "OFFLINE", "PARTAGE", "PIXELS", "POSTER", "PREMIUM", "PROFIL",
    "PSEUDO", "RESEAU", "SCROLL", "SELFIE", "SIGNAL", "SOURIS",
    "STICKER", "STREAM", "SWIPER", "TAGUER", "TWEETS", "VIDEOS",
    "VIRTUEL", "WEBCAM",
    "AMELIE", "ALBATOR", "AQUAMAN", "ARTHUR", "BARNEY", "BAYMAX",
    "BENDER", "BOWSER", "CAMPING", "CASPER", "CEDRIC", "CHARLIE",
    "CHARMED", "CHIHIRO", "CHOPPER", "CORTEX", "CUPHEAD", "CYBORG",
    "DALTON", "DAPHNE", "DONALD", "DUSTIN", "DWIGHT", "EGGMAN",
    "ELEVEN", "FREEZER", "GASTON", "GHIBLI", "GOONIES", "GREASE",
    "GREMLIN", "HADDOCK", "HAWKINS", "HEDWIGE", "HERCULE", "HINATA",
    "HOBBIT", "HOLMES", "HOPPER", "HOWARD", "HYRULE", "IDEFIX",
    "ITACHI", "JASMINE", "JUMANJI", "KAKASHI", "KERMIT", "KRILIN",
    "LABOUM", "LEONARD", "MALFOY", "MARLIN", "MATILDA", "MERIDA",
    "MERLIN", "METROID", "MIGUEL", "MIRABEL", "MONICA", "MORDOR",
    "MOWGLI", "MUPPETS", "NARNIA", "NELSON", "OFFICE", "OUIOUI",
    "PEANUTS", "PHOEBE", "PICCOLO", "POIROT", "POPEYE", "PUMBAA",
    "RACHEL", "SAKURA", "SASUKE", "SCOOBY", "SCRUBS", "SHADOW",
    "SHAGGY", "SHELDON", "SHENRON", "SHENRON", "SIMCITY", "SIMPSON",
    "SIRIUS", "SNOOPY", "SONGOKU", "SPIROU", "STARDEW", "TARZAN",
    "TCHALLA", "TCHOUPI", "TIGROU", "TINTIN", "TITEUF", "TOTORO",
    "TRUNKS", "URSULA", "VEGETA", "WAKANDA", "WALUIGI", "WATSON",
    "WILSON", "WINNIE",
    "ARIANA", "BEATLES", "BIEBER", "BILLIE", "BRITNEY", "BURTON",
    "CABREL", "CAMERON", "CLOONEY", "COBAIN", "COELHO", "DALIDA",
    "DOJACAT", "DUALIPA", "EILISH", "FARMER", "GOLDMAN", "JACKSON",
    "JENIFER", "JUGNOT", "JUSTICE", "LAVOINE", "LENNON", "LOMEPAL",
    "MADONNA", "MARCEAU", "MATISSE", "MENDES", "MERCURY", "MOLIERE",
    "MOZART", "MYLENE", "NEKFEU", "NIRVANA", "OBISPO", "OLIVIA",
    "ORWELL", "PRESLEY", "PROUST", "RENAUD", "ROBBIE", "RODRIGO",
    "ROWLING", "SELENA", "SHEERAN", "SINATRA", "SLIMANE", "TAUTOU",
    "TOLKIEN", "UDERZO", "WARHOL", "WEEKND",
    "AGASSI", "ALCARAZ", "ALONSO", "BECKER", "BRYANT", "DEMBELE",
    "DONCIC", "DUNCAN", "DUPONT", "GIROUD", "HAKIMI", "LEBRON",
    "LECLERC", "MAIGNAN", "MARQUEZ", "MONFILS", "MURRAY", "NTAMACK",
    "PARKER", "PAVARD", "PLATINI", "RIBERY", "SALIBA", "SAMPRAS",
    "SINNER", "THURAM", "TSONGA", "VARANE", "VIEIRA",
    "ANNECY", "ATHENES", "ATLANTA", "AVIGNON", "BANGKOK", "BOLIVIE",
    "BOSTON", "CANNES", "CHICAGO", "CHYPRE", "COLMAR", "CROATIE",
    "DUBLIN", "EGYPTE", "EIFFEL", "EVEREST", "HOUSTON", "IRLANDE",
    "ISLANDE", "LOUVRE", "MEXIQUE", "NANTES", "NAPLES", "NIAGARA",
    "NIGERIA", "OTTAWA", "PANAMA", "POLOGNE", "POMPEI", "PRAGUE",
    "QUEBEC", "RENNES", "SAHARA", "SEATTLE", "SENEGAL", "SYDNEY",
    "TAIWAN", "TORONTO", "TURQUIE", "UKRAINE", "URUGUAY", "VENISE",
    "VIENNE", "VIETNAM",
    "CESARS", "ECLIPSE", "GARROS", "GRAMMYS", "MUNDIAL", "OSCARS",
    "ROLAND",
}
# Formes plurielles volontairement admises par la ligne éditoriale. Le corpus
# de construction marque beaucoup de pluriels parfaitement naturels comme non
# attestés (ou avec un score nul), ce qui poussait le solveur vers des verbes
# conjugués et des mots de mots croisés. Cette liste reste fermée et ne contient
# que des noms courants qu'une définition au pluriel peut indiquer honnêtement.
# La famille morphologique empêche toujours de placer le singulier et le pluriel
# dans une même grille ou un même petit lot.
PILOT_REVIEWED_NATURAL_FORMS = {
    "ACHATS", "ALBUMS", "ANNEES", "APPELS", "BANQUES", "BATEAUX",
    "BISOUS", "BUDGETS", "CADEAUX", "CALCULS", "CANAUX", "CENTRES",
    "CHIENS", "COPIES", "COUPES", "DEGATS", "DESSINS", "ECRANS",
    "ENFANTS", "ENJEUX", "EQUIPES", "ERREURS", "ESSAIS", "ETOILES",
    "FEMMES", "FICHES", "FLEURS", "FRITES", "FRUITS", "GENRES",
    "GROUPES", "HOMMES", "IMAGES", "INDICES", "JARDINS", "JOUEURS",
    "LANGUES", "LETTRES", "LISTES", "LIVRES", "LOCAUX", "MAIRES",
    "MAMANS", "MATCHS", "MEDIAS", "MEMBRES", "MOYENS", "NIVEAUX",
    "NOMBRES", "NOTIONS", "OBJETS", "OPTIONS", "PARENTS", "PHOTOS",
    "PHRASES", "PIECES", "PISTES", "PLAGES", "PLANTES", "PORTES",
    "POSTES", "PROFILS", "PROJETS", "RADIOS", "RECORDS", "RESEAUX",
    "REVUES", "ROBOTS", "ROUTES", "SALONS", "SIGNES", "SORTIES",
    "SPORTS", "STADES", "STAGES", "STOCKS", "STUDIOS", "STYLES",
    "SUJETS", "TABLES", "TARIFS", "TISSUS", "TITRES", "TRAINS",
    "TRIBUS", "VALEURS", "VENTES", "VERRES", "VIDEOS", "VIGNES",
    "VILLES", "VISAGES", "VOYAGES",
}
PILOT_CONCEPT_FAMILY_OVERRIDES = {
    # Dérivations ou formes visuelles que le propriétaire perçoit comme la
    # même réponse. Elles ne doivent jamais cohabiter dans un petit plateau.
    "LATENT": "LATENCE",
    "LATENCE": "LATENCE",
    "AME": "AME-VISIBLE",
    "AMEE": "AME-VISIBLE",
    "AMEES": "AME-VISIBLE",
    "AMES": "AME-VISIBLE",
    "FER": "FER",
    "FERS": "FER",
    "ILE": "ILE",
    "ILES": "ILE",
    "MER": "MER",
    "MERS": "MER",
    "MOT": "MOT",
    "MOTS": "MOT",
}
GRAMMAR_ANSWERS = {
    "AU", "CA", "CE", "CES", "CET", "DE", "DU", "ELLE", "EN", "ES",
    "ET", "EU", "EUX", "IL", "ILS", "JE", "LA", "LE", "LES", "LUI",
    "MA", "ME", "MOI", "NE", "NI", "ON", "OU", "QUE", "QUI", "SA",
    "SE", "SI", "SOI", "SON", "TA", "TE", "TOI", "TON", "TU", "UN",
    "UNE", "VOS",
}


def normalized(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.upper())
    return "".join(character for character in folded if "A" <= character <= "Z")


def parse_cell(value: str) -> tuple[int, int]:
    row, column = value.split(",", 1)
    return int(row), int(column)


def parse_fixed_answer(value: str) -> tuple[int, str]:
    slot, answer = value.split(":", 1)
    normalized_answer = normalized(answer)
    if not normalized_answer:
        raise argparse.ArgumentTypeError("La réponse imposée ne peut pas être vide")
    return int(slot), normalized_answer


def hybrid_metadata_is_eligible(
    metadata: dict | None, *, allow_inflected_verbs: bool = False
) -> bool:
    """Keep the hybrid domain broad without reintroducing verb inflections.

    The large domain already rejects conjugated and participial verb forms.
    Hybrid must apply the same rule after intersecting wordfreq with the
    attested French lexicon; otherwise frequent forms such as ``ENVERRA`` or
    ``STOPPE`` bypass the editorial contract merely because wordfreq ranks
    them highly.
    """
    if metadata is None:
        return False
    if metadata.get("attestedCommonForm") is not True:
        return False
    if str(metadata.get("partOfSpeech") or "") == "proper-noun":
        return False
    return not (
        str(metadata.get("partOfSpeech") or "") == "verb"
        and str(metadata.get("formType") or "") != "lemma"
        and not allow_inflected_verbs
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--columns", type=int, default=7)
    parser.add_argument("--rows", type=int, default=8)
    parser.add_argument("--pivot", action="append", type=parse_cell, default=[])
    parser.add_argument(
        "--shape-file", type=Path,
        help="Bibliothèque JSON de silhouettes arbitraires validées.",
    )
    parser.add_argument(
        "--shape-id",
        help="Identifiant de la silhouette à charger depuis --shape-file.",
    )
    parser.add_argument("--minimum-zipf", type=float, default=3.3)
    parser.add_argument(
        "--lexicon", choices=("large", "wordfreq", "hybrid", "central"), default="large"
    )
    parser.add_argument("--minimum-constructor-score", type=float, default=15.0)
    parser.add_argument(
        "--allow-inflected-verbs", action="store_true",
        help="Diagnostic seulement : autorise les formes verbales conjuguées.",
    )
    parser.add_argument("--low-quality-threshold", type=float, default=0.0)
    parser.add_argument("--max-low-quality", type=int)
    parser.add_argument("--minimum-familiarity-zipf", type=float)
    parser.add_argument("--max-unfamiliar-answers", type=int)
    parser.add_argument("--curated-short-only", action="store_true")
    parser.add_argument("--pilot-safe-short-only", action="store_true")
    parser.add_argument(
        "--prefer-pilot-safe-short",
        action="store_true",
        help="Pénalise les 3-lettres non relus sans les exclure du diagnostic.",
    )
    parser.add_argument("--minimum-images", type=int, default=0)
    parser.add_argument("--maximum-grammar-answers", type=int, default=2)
    parser.add_argument("--seconds", type=float, default=90.0)
    parser.add_argument("--solution-limit", type=int, default=32_768)
    parser.add_argument("--explore-randomly", action="store_true")
    parser.add_argument(
        "--branching-strategy", choices=("cell", "slot"), default="cell"
    )
    parser.add_argument(
        "--cell-letter-order", choices=("quality", "support"), default="quality"
    )
    parser.add_argument("--seed", type=int, default=780300)
    parser.add_argument(
        "--reference-catalog", "--exclude-catalog",
        dest="reference_catalog", type=Path, action="append", default=[],
        help="Catalogue de référence : ses réponses sont pénalisées, pas interdites.",
    )
    parser.add_argument("--exclude-answer", action="append", default=[])
    parser.add_argument(
        "--avoid-fill", type=Path, action="append", default=[],
        help="Remplissage signé à éviter sans interdire ses mots individuellement.",
    )
    parser.add_argument("--minimum-solution-distance", type=int, default=1)
    parser.add_argument(
        "--fixed-answer",
        action="append",
        type=parse_fixed_answer,
        default=[],
        metavar="SLOT:REPONSE",
        help="Impose une réponse à un slot sans modifier la silhouette.",
    )
    parser.add_argument("--repair-candidate", type=Path)
    parser.add_argument(
        "--repair-grid-id",
        help="Identifiant de grille lorsque le candidat de réparation contient un lot.",
    )
    parser.add_argument("--repair-answer", action="append", default=[])
    parser.add_argument("--repair-radius", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def excluded_answers(requested: list[str]) -> set[str]:
    excluded = {normalized(answer) for answer in requested}
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    excluded.update(blacklist.get("rejectedAnswers", []))
    excluded.discard("")
    return excluded


def load_reference_solutions(paths: list[Path]) -> list[dict[int, str]]:
    solutions: list[dict[int, str]] = []
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        candidates = []
        if isinstance(document.get("answers"), dict):
            candidates.append(document["answers"])
        for grid in document.get("grids", []):
            if isinstance(grid.get("slotAnswers"), dict):
                candidates.append(grid["slotAnswers"])
        for alternative in document.get("alternatives", []):
            if isinstance(alternative.get("answers"), dict):
                candidates.append(alternative["answers"])
        for candidate in candidates:
            normalized_candidate = {
                int(slot): normalized(str(answer))
                for slot, answer in candidate.items()
                if normalized(str(answer))
            }
            if normalized_candidate:
                solutions.append(normalized_candidate)
    return solutions


def rotation_cooldown_usage(document: dict) -> Counter[str]:
    """Convert editorial cooldowns to search penalties, never hard bans.

    A cooldown records fatigue, not a defect in the answer.  Keeping it in the
    hard exclusion set made a good familiar word mathematically unavailable
    even after the active catalogue had rotated.  The solver already knows how
    to penalise repeated usage, so expose the historical pressure through that
    same mechanism.
    """
    usage: Counter[str] = Counter()
    for item in document.get("rotationCooldownAnswers", []):
        if isinstance(item, dict):
            answer = normalized(str(item.get("answer", "")))
            observed = max(1, int(item.get("observedActiveUses") or 1))
        else:
            answer = normalized(str(item))
            observed = 1
        if answer:
            usage[answer] = max(usage[answer], observed)
    return usage


def build_slots_from_clue_cells(
    columns: int, rows: int, clue_cells: set[tuple[int, int]]
) -> tuple[list[list[int]], list[dict], list[Slot]]:
    frame = {(0, column) for column in range(columns)} | {
        (row, 0) for row in range(1, rows)
    }
    clues = set(clue_cells)
    if not frame <= clues:
        missing = sorted(frame - clues)
        raise ValueError(f"Cadre de définitions incomplet : {missing}")
    if any(
        row < 0 or column < 0 or row >= rows or column >= columns
        for row, column in clues
    ):
        raise ValueError("Une case-définition sort de la grille")
    raw_slots: list[dict] = []
    for clue_cell in sorted(clues):
        for direction, delta in (("across", (0, 1)), ("down", (1, 0))):
            row = clue_cell[0] + delta[0]
            column = clue_cell[1] + delta[1]
            cells = []
            while 0 <= row < rows and 0 <= column < columns and (row, column) not in clues:
                cells.append([row, column])
                row += delta[0]
                column += delta[1]
            if len(cells) <= 1:
                # Un singleton dans un axe ne ressemble pas à une entrée et
                # reste valide si l'autre axe couvre effectivement sa lettre.
                continue
            if len(cells) < 3:
                raise ValueError(
                    "Segment de moins de trois lettres interdit : "
                    f"case {list(clue_cell)}, direction {direction}, longueur {len(cells)}"
                )
            index = len(raw_slots)
            raw_slots.append({
                "slotId": f"slot-{index + 1:02d}",
                "direction": direction,
                "arrow": "right" if direction == "across" else "down",
                "clueCell": list(clue_cell),
                "cells": cells,
                "length": len(cells),
            })
    slots = [
        Slot(
            index=index,
            slot_id=item["slotId"],
            direction=item["direction"],
            clue_cell=tuple(item["clueCell"]),
            cells=tuple(tuple(cell) for cell in item["cells"]),
        )
        for index, item in enumerate(raw_slots)
    ]
    clue_cells_with_answers = {
        tuple(item["clueCell"])
        for item in raw_slots
    }
    isolated_clues = sorted(
        tuple(clue_cell)
        for clue_cell in clues
        if tuple(clue_cell) != (0, 0)
        and tuple(clue_cell) not in clue_cells_with_answers
    )
    if isolated_clues:
        raise ValueError(
            "Cases-definition sans fleche ni reponse : "
            f"{[list(cell) for cell in isolated_clues]}"
        )
    letter_cells = {
        (row, column)
        for row in range(1, rows)
        for column in range(1, columns)
        if (row, column) not in clues
    }
    coverage: dict[tuple[int, int], set[str]] = defaultdict(set)
    for item in raw_slots:
        for cell in item["cells"]:
            coverage[tuple(cell)].add(item["direction"])
    covered = set(coverage)
    if covered != letter_cells:
        missing = sorted(letter_cells - covered)
        raise ValueError(f"Cases non couvertes par la silhouette : {missing}")
    return [list(cell) for cell in sorted(clues)], raw_slots, slots


def build_slots(
    columns: int, rows: int, pivots: set[tuple[int, int]]
) -> tuple[list[list[int]], list[dict], list[Slot]]:
    frame = {(0, column) for column in range(columns)} | {
        (row, 0) for row in range(1, rows)
    }
    if any(
        row <= 0 or column <= 0 or row >= rows or column >= columns
        for row, column in pivots
    ):
        raise ValueError("Un pivot doit rester à l'intérieur du cadre")
    return build_slots_from_clue_cells(columns, rows, frame | pivots)


def load_shape_definition(path: Path, shape_id: str | None) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    shapes = document.get("shapes") if isinstance(document, dict) else None
    if not isinstance(shapes, list):
        shapes = [document]
    if shape_id is None:
        if len(shapes) != 1:
            raise ValueError("--shape-id est obligatoire pour une bibliothèque multi-silhouettes")
        shape = shapes[0]
    else:
        matches = [shape for shape in shapes if str(shape.get("shapeId")) == shape_id]
        if len(matches) != 1:
            raise ValueError(f"Silhouette introuvable ou dupliquée : {shape_id}")
        shape = matches[0]
    if not isinstance(shape, dict):
        raise ValueError("Silhouette JSON invalide")
    return shape


def build_slots_from_shape(
    shape: dict,
) -> tuple[int, int, str, list[list[int]], list[dict], list[Slot]]:
    columns = int(shape.get("columns", 0))
    rows = int(shape.get("rows", 0))
    shape_id = str(shape.get("shapeId") or "arbitrary-shape")
    if columns < 2 or rows < 2:
        raise ValueError("Dimensions de silhouette invalides")
    clue_cells = {
        tuple(map(int, cell))
        for cell in shape.get("clueCells", [])
        if isinstance(cell, list) and len(cell) == 2
    }
    clues, canonical_raw, canonical_slots = build_slots_from_clue_cells(
        columns, rows, clue_cells
    )
    supplied = shape.get("slots")
    if not isinstance(supplied, list):
        return columns, rows, shape_id, clues, canonical_raw, canonical_slots

    ordered = sorted(supplied, key=lambda item: int(item.get("slotIndex", -1)))
    if [int(item.get("slotIndex", -1)) for item in ordered] != list(range(len(ordered))):
        raise ValueError("Les slotIndex de la silhouette doivent être contigus depuis zéro")

    def signature(item: dict) -> tuple:
        return (
            str(item.get("direction")),
            tuple(map(int, item.get("clueCell", []))),
            tuple(tuple(map(int, cell)) for cell in item.get("cells", [])),
        )

    if {signature(item) for item in ordered} != {signature(item) for item in canonical_raw}:
        raise ValueError("Les slots fournis ne correspondent pas aux runs maximaux de la silhouette")

    raw_slots: list[dict] = []
    slots: list[Slot] = []
    for index, item in enumerate(ordered):
        direction = str(item.get("direction"))
        arrow = str(item.get("arrow") or ("right" if direction == "across" else "down"))
        expected_arrow = "right" if direction == "across" else "down"
        cells = [list(map(int, cell)) for cell in item.get("cells", [])]
        if direction not in {"across", "down"} or arrow != expected_arrow:
            raise ValueError(f"Direction ou flèche invalide au slot {index}")
        if int(item.get("length", len(cells))) != len(cells) or len(cells) < 3:
            raise ValueError(f"Longueur invalide au slot {index}")
        slot_id = str(item.get("slotId") or f"slot-{index + 1:02d}")
        raw = {
            "slotId": slot_id,
            "slotIndex": index,
            "direction": direction,
            "arrow": arrow,
            "clueCell": list(map(int, item.get("clueCell", []))),
            "cells": cells,
            "length": len(cells),
        }
        raw_slots.append(raw)
        slots.append(Slot(
            index=index,
            slot_id=slot_id,
            direction=direction,
            clue_cell=tuple(raw["clueCell"]),
            cells=tuple(tuple(cell) for cell in cells),
        ))
    return columns, rows, shape_id, clues, raw_slots, slots


def main() -> int:
    args = parse_args()
    if args.shape_file:
        if args.pivot:
            raise ValueError("--pivot et --shape-file sont mutuellement exclusifs")
        shape = load_shape_definition(args.shape_file, args.shape_id)
        columns, rows, source_shape_id, clues, raw_slots, slots = build_slots_from_shape(shape)
    else:
        if args.shape_id:
            raise ValueError("--shape-id exige --shape-file")
        columns, rows = args.columns, args.rows
        clues, raw_slots, slots = build_slots(columns, rows, set(args.pivot))
        source_shape_id = "compact-" + "-".join(
            [f"{columns}x{rows}", *[f"pivot-{row}-{column}" for row, column in args.pivot]]
        )
    lengths = sorted({len(slot.cells) for slot in slots})
    excluded = excluded_answers(args.exclude_answer)
    active_usage = answer_usage(args.reference_catalog)
    blacklist_document = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    for answer, historical_uses in rotation_cooldown_usage(blacklist_document).items():
        active_usage[answer] = max(active_usage[answer], historical_uses)
    excluded_families = {family_key(answer) for answer in excluded}
    # A repair request means the rejected answer must disappear, not merely
    # that its slot may be searched again. Without this exclusion the quality
    # optimiser can select the exact same bad answer and report a fake repair.
    excluded.update(normalized(answer) for answer in args.repair_answer)
    excluded_families.update(family_key(answer) for answer in args.repair_answer)
    requested_fixed_answers = dict(args.fixed_answer)
    reference_solutions = load_reference_solutions(args.avoid_fill)
    if len(requested_fixed_answers) != len(args.fixed_answer):
        raise ValueError("Un même slot ne peut recevoir deux réponses imposées")
    for index, answer in requested_fixed_answers.items():
        if not 0 <= index < len(slots):
            raise ValueError(f"Slot imposé hors limites : {index}")
        expected_length = len(slots[index].cells)
        if len(answer) != expected_length:
            raise ValueError(
                f"{answer} mesure {len(answer)} lettres, mais le slot {index} en exige {expected_length}"
            )
        if answer in excluded or family_key(answer) in excluded_families:
            raise ValueError(f"Réponse imposée exclue ou blacklistée : {answer}")
    words_by_length = {length: [] for length in lengths}
    scores: dict[str, float] = {}
    zipf_scores: dict[str, float] = {}
    spellings: dict[str, str] = {}
    lemmas: dict[str, str] = {}
    central_metadata: dict[str, dict] = {}
    lexical_metadata_by_answer: dict[str, dict] = {}
    if args.lexicon == "central":
        with gzip.open(
            ROOT / "src/data/crossword.central.json.gz", "rt", encoding="utf-8"
        ) as stream:
            entries = json.load(stream).get("entries", [])
        for item in entries:
            answer = normalized(str(item.get("answer", "")))
            if (
                len(answer) not in words_by_length
                or answer in excluded
                or family_key(answer) in excluded_families
                or answer in scores
                or item.get("generatorEligible") is not True
                or item.get("canonicalForGenerator") is not True
                or (
                    (args.curated_short_only or args.pilot_safe_short_only)
                    and len(answer) <= 3
                    and answer not in (
                        PILOT_SAFE_SHORT if args.pilot_safe_short_only else OWNER_SHORT
                    )
                )
            ):
                continue
            spelling = str(item.get("spelling") or answer.lower())
            frequency = float(zipf_frequency(spelling, "fr"))
            editorial_frequency = float(item.get("frequency", 0.0))
            scores[answer] = 20.0 + editorial_frequency
            zipf_scores[answer] = frequency
            spellings[answer] = spelling
            lemmas[answer] = family_key(str(item.get("lemma") or answer))
            words_by_length[len(answer)].append(answer)
            central_metadata[answer] = {
                "centralClue": item.get("clue", ""),
                "sourceClue": item.get("sourceClue", ""),
                "sourceId": item.get("sourceId", ""),
                "sourceUrl": item.get("sourceUrl", ""),
                "editorialStatus": item.get("editorialStatus", ""),
            }
    elif args.lexicon == "large":
        with gzip.open(
            ROOT / "src/data/fill.wordlist.large.json.gz", "rt", encoding="utf-8"
        ) as stream:
            entries = json.load(stream).get("entries", [])
        for item in entries:
            answer = normalized(str(item.get("answer", "")))
            score = float(item.get("constructorScore", 0.0))
            spelling = str(item.get("spelling") or answer.lower())
            frequency = float(zipf_frequency(spelling, "fr"))
            if (
                len(answer) not in words_by_length
                or answer in excluded
                or family_key(answer) in excluded_families
                or answer in scores
                or not item.get("attestedCommonForm", False)
                or (
                    item.get("partOfSpeech") == "verb"
                    and item.get("formType") != "lemma"
                    and not args.allow_inflected_verbs
                )
                or score < args.minimum_constructor_score
                or frequency < args.minimum_zipf
                or (
                    (args.curated_short_only or args.pilot_safe_short_only)
                    and len(answer) <= 3
                    and answer not in (
                        PILOT_SAFE_SHORT if args.pilot_safe_short_only else OWNER_SHORT
                    )
                )
            ):
                continue
            scores[answer] = score
            zipf_scores[answer] = frequency
            spellings[answer] = spelling
            lemmas[answer] = family_key(str(item.get("lemma") or answer))
            words_by_length[len(answer)].append(answer)
            lexical_metadata_by_answer[answer] = {
                "partOfSpeech": item.get("partOfSpeech"),
                "formType": item.get("formType"),
                "sourceFrequency": item.get("sourceFrequency"),
                "schoolFrequency": item.get("schoolFrequency"),
            }
    else:
        lexical_metadata: dict[str, dict] = {}
        if args.lexicon == "hybrid":
            # wordfreq is excellent for ranking everyday usage but contains
            # names and English leakage.  The large French word list is much
            # better at confirming that a spelling is actually lexicalised.
            # Their intersection keeps the breadth of inflected French while
            # removing most of the web-corpus noise.
            with gzip.open(
                ROOT / "src/data/fill.wordlist.large.json.gz", "rt", encoding="utf-8"
            ) as stream:
                entries = json.load(stream).get("entries", [])
            for item in entries:
                answer = normalized(str(item.get("answer", "")))
                if not answer or answer in lexical_metadata:
                    continue
                lexical_metadata[answer] = item
        for spelling in iter_wordlist("fr"):
            score = float(zipf_frequency(spelling, "fr"))
            if score < args.minimum_zipf:
                break
            if not spelling.isalpha():
                continue
            answer = normalized(spelling)
            metadata = lexical_metadata.get(answer)
            if (
                len(answer) not in words_by_length
                or answer in excluded
                or family_key(answer) in excluded_families
                or answer in scores
                or (
                    args.lexicon == "hybrid"
                    and not hybrid_metadata_is_eligible(
                        metadata,
                        allow_inflected_verbs=args.allow_inflected_verbs,
                    )
                )
                or (
                    (args.curated_short_only or args.pilot_safe_short_only)
                    and len(answer) <= 3
                    and answer not in (
                        PILOT_SAFE_SHORT if args.pilot_safe_short_only else OWNER_SHORT
                    )
                )
            ):
                continue
            scores[answer] = score
            zipf_scores[answer] = score
            spellings[answer] = spelling
            lemmas[answer] = family_key(
                str((metadata or {}).get("lemma") or answer)
            )
            words_by_length[len(answer)].append(answer)
    admitted_manual_short = (
        PILOT_SAFE_SHORT if args.pilot_safe_short_only else OWNER_SHORT
    )
    for answer in admitted_manual_short - excluded:
        if family_key(answer) in excluded_families:
            continue
        if len(answer) in words_by_length and answer not in scores:
            scores[answer] = 5.0
            zipf_scores[answer] = float(zipf_frequency(answer.lower(), "fr"))
            spellings[answer] = answer.lower()
            lemmas[answer] = family_key(answer)
            words_by_length[len(answer)].append(answer)
    if args.pilot_safe_short_only or args.prefer_pilot_safe_short:
        for answer in (
            PILOT_REVIEWED_LONG | PILOT_REVIEWED_NATURAL_FORMS
        ) - excluded:
            if (
                len(answer) not in words_by_length
                or family_key(answer) in excluded_families
                or answer in scores
            ):
                continue
            scores[answer] = 65.0
            zipf_scores[answer] = max(
                3.0, float(zipf_frequency(answer.lower(), "fr"))
            )
            spellings[answer] = answer.lower()
            lemmas[answer] = family_key(answer)
            words_by_length[len(answer)].append(answer)
            lexical_metadata_by_answer[answer] = {
                "partOfSpeech": "proper-noun",
                "formType": "editorial-reviewed",
                "sourceFrequency": None,
                "schoolFrequency": None,
            }
    if args.prefer_pilot_safe_short:
        for answer in list(scores):
            if len(answer) == 3 and answer not in PILOT_SAFE_SHORT:
                scores[answer] = min(scores[answer], -100.0)
    # Proper names and pop-culture references are intentionally absent from
    # the general construction lexicon. They can enter only through an
    # explicit, reviewed fixed answer and never broaden the automatic pool.
    for answer in requested_fixed_answers.values():
        if answer not in scores:
            scores[answer] = 25.0
            zipf_scores[answer] = float(zipf_frequency(answer.lower(), "fr"))
            spellings[answer] = answer.lower()
            lemmas[answer] = family_key(answer)
            words_by_length[len(answer)].append(answer)
    for answer, family in PILOT_CONCEPT_FAMILY_OVERRIDES.items():
        if answer in scores:
            lemmas[answer] = family
    indexed = {
        length: tuple(sorted(words)) for length, words in words_by_length.items()
    }
    search_scores = {
        answer: (
            scores[answer] + 5.0 * zipf_scores.get(answer, 0.0)
            if args.lexicon == "large" else scores[answer]
        ) - min(30.0, 12.0 * active_usage.get(answer, 0))
        for answer in scores
    }
    image_document = json.loads(
        (ROOT / "src/data/crossword.images-reviewed.json").read_text(encoding="utf-8")
    )
    image_answers = {
        normalized(str(item.get("answer", "")))
        for item in image_document.get("entries", [])
        if normalized(str(item.get("answer", ""))) in scores
    }
    indexes = (
        indexed,
        None,
        search_scores,
        lemmas,
        {answer: set() for answer in scores},
        {answer: "normal" for answer in scores},
        image_answers,
    )
    fixed_answers: dict[int, str] = dict(requested_fixed_answers)
    released_indexes: set[int] = set()
    if args.repair_candidate:
        previous = json.loads(args.repair_candidate.read_text(encoding="utf-8"))
        if isinstance(previous.get("grids"), list):
            if not args.repair_grid_id:
                raise ValueError(
                    "--repair-grid-id est obligatoire pour réparer une grille issue d'un lot"
                )
            matches = [
                grid for grid in previous["grids"]
                if grid.get("id") == args.repair_grid_id
            ]
            if len(matches) != 1:
                raise ValueError(f"Grille de réparation introuvable : {args.repair_grid_id}")
            previous = matches[0]
        repair_answers = {normalized(answer) for answer in args.repair_answer}
        slot_index_by_id = {
            str(slot.get("slotId")): index for index, slot in enumerate(raw_slots)
        }
        previous_entries = previous.get("answers")
        if not isinstance(previous_entries, list):
            previous_entries = previous.get("words", [])
        slot_index_by_cells = {
            tuple(tuple(cell) for cell in slot["cells"]): index
            for index, slot in enumerate(raw_slots)
        }

        def previous_slot_index(item: dict) -> int:
            if "slotIndex" in item:
                return int(item["slotIndex"])
            if item.get("slotId") is not None:
                return slot_index_by_id[str(item["slotId"])]
            cells = tuple(tuple(cell) for cell in item.get("cells", []))
            if cells not in slot_index_by_cells:
                raise ValueError(
                    "Chemin de réponse de réparation absent de la silhouette cible"
                )
            return slot_index_by_cells[cells]

        previous_by_index = {
            previous_slot_index(item): normalized(item["answer"])
            for item in previous_entries
        }
        released_indexes = {
            index for index, answer in previous_by_index.items()
            if answer in repair_answers
        }
        for _step in range(max(0, args.repair_radius)):
            released_cells = {
                tuple(cell)
                for index in released_indexes
                for cell in raw_slots[index]["cells"]
            }
            released_indexes.update(
                index for index, slot in enumerate(raw_slots)
                if any(tuple(cell) in released_cells for cell in slot["cells"])
            )
        repaired_fixed_answers = {
            index: answer
            for index, answer in previous_by_index.items()
            if index not in released_indexes and answer in scores
        }
        for index, answer in repaired_fixed_answers.items():
            if index in fixed_answers and fixed_answers[index] != answer:
                raise ValueError(f"Conflit de réponse imposée au slot {index}")
            fixed_answers[index] = answer
    telemetry: dict = {}
    solution_records: list[dict] = []
    undesirable_answers = {
        answer for answer, score in scores.items()
        if score < args.low_quality_threshold
    }
    if args.minimum_familiarity_zipf is not None:
        undesirable_answers.update(
            answer for answer in scores
            if len(answer) > 3
            and zipf_scores.get(answer, 0.0) < args.minimum_familiarity_zipf
            and answer not in PILOT_REVIEWED_LONG
        )
    undesirable_limit = (
        args.max_unfamiliar_answers
        if args.max_unfamiliar_answers is not None
        else args.max_low_quality
    )
    solution = fill_bitset(
        slots,
        indexes,
        random.Random(args.seed),
        None,
        max_grammar_answers=args.maximum_grammar_answers,
        grammar_answers=GRAMMAR_ANSWERS,
        max_seconds=args.seconds,
        node_limit=100_000_000,
        require_image=args.minimum_images > 0,
        minimum_images=max(1, args.minimum_images),
        prefer_constraint_support=True,
        constraint_support_bucket_size=3,
        branching_strategy=args.branching_strategy,
        cell_letter_order=args.cell_letter_order,
        fixed_answers=fixed_answers,
        undesirable_answers=undesirable_answers,
        max_undesirable_answers=undesirable_limit,
        quality_scores=search_scores,
        answer_usage=active_usage,
        answer_families=lemmas,
        solution_limit=args.solution_limit,
        solution_sink=solution_records,
        reference_solutions=reference_solutions,
        minimum_solution_distance=args.minimum_solution_distance,
        explore_randomly=args.explore_randomly,
        telemetry=telemetry,
    )
    payload = {
        "version": 1,
        "kind": "compact-word-first-pilot",
        "columns": columns,
        "rows": rows,
        "sourceShapeId": source_shape_id,
        "sourceShapeFile": str(args.shape_file) if args.shape_file else None,
        "catalogModified": False,
        "publicationEligible": False,
        "complete": solution is not None,
        "minimumZipf": args.minimum_zipf,
        "lexicon": args.lexicon,
        "minimumConstructorScore": args.minimum_constructor_score,
        "minimumFamiliarityZipf": args.minimum_familiarity_zipf,
        "maxUnfamiliarAnswers": args.max_unfamiliar_answers,
        "excludedAnswerCount": len(excluded),
        "activeReferenceAnswerCount": len(active_usage),
        "activeRepeatPolicy": "score-penalty-not-global-ban",
        "repairCandidate": str(args.repair_candidate) if args.repair_candidate else None,
        "releasedSlotIndexes": sorted(released_indexes),
        "fixedAnswerCount": len(fixed_answers),
        "avoidedFillCount": len(reference_solutions),
        "minimumSolutionDistance": args.minimum_solution_distance,
        "requestedFixedAnswers": {
            str(index): answer for index, answer in sorted(requested_fixed_answers.items())
        },
        "clueCells": clues,
        "rawSlots": raw_slots,
        "geometryAudit": {
            "valid": True,
            "totalCells": columns * rows,
            "letterCells": len({tuple(cell) for item in raw_slots for cell in item["cells"]}),
            "orphanLetters": 0,
            "unusedDefinitionCells": 0,
        },
        "candidateCounts": {str(length): len(indexed[length]) for length in lengths},
        "availableImageAnswers": len(image_answers),
        "solverTelemetry": telemetry,
        "alternativeCount": len(solution_records),
        "alternatives": solution_records,
        "answers": [],
    }
    if solution is not None:
        payload["answers"] = [
            {
                "slotIndex": index,
                "answer": solution[index],
                "spelling": spellings[solution[index]],
                "lemma": lemmas.get(solution[index], solution[index]),
                "constructorScore": scores[solution[index]] if args.lexicon == "large" else None,
                "wordfreqZipf": zipf_scores.get(solution[index], scores[solution[index]]),
                **central_metadata.get(solution[index], {}),
                **lexical_metadata_by_answer.get(solution[index], {}),
            }
            for index in sorted(solution)
        ]
        payload["imageAnswers"] = sorted(
            item["answer"] for item in payload["answers"]
            if item["answer"] in image_answers
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "complete": payload["complete"],
        "answers": [item["answer"] for item in payload["answers"]],
        "telemetry": telemetry,
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if solution is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
