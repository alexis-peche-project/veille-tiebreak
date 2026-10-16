"""Liste blanche des sources acceptees par la veille Tie Break.

Seuls les articles publies par un site de cette liste sont conserves.
Chaque site recoit un niveau de fiabilite :
  A = source primaire officielle (entreprise, institution sportive ou publique)
  B = agence de presse ou grand media d'information
  C = media specialise reconnu (tennis, sport business, mode, logistique, think tank)
  D = acteur engage (ONG, plaidoyer) : utile pour reperer un signal, a recouper

Pour ajouter un site : ajoutez son domaine (sans www.) et son nom tel qu'il
apparait dans Google Actualites dans la bonne categorie.
"""
import re
import urllib.parse

SOURCES = {
    "A": {
        "domains": [
            "nike.com", "sec.gov", "atptour.com", "wtatennis.com", "itftennis.com",
            "fft.fr", "rolandgarros.com", "wada-ama.org", "itia.tennis", "olympics.com",
            "europa.eu", "ustr.gov", "whitehouse.gov", "wto.org", "economie.gouv.fr",
            "douane.gouv.fr", "sports.gouv.fr", "elysee.fr", "imf.org", "unctad.org",
        ],
        "names": [
            "nike news", "nike, inc", "about nike", "atp tour", "wta", "itf", "fédération française de tennis",
            "roland-garros", "world anti-doping agency", "itia", "european commission",
            "commission européenne", "ustr", "white house", "wto", "ministère",
        ],
    },
    "B": {
        "domains": [
            "reuters.com", "afp.com", "apnews.com", "lemonde.fr", "lesechos.fr", "lefigaro.fr",
            "francetvinfo.fr", "france24.com", "rfi.fr", "radiofrance.fr", "liberation.fr",
            "lequipe.fr", "ouest-france.fr", "nicematin.com", "bfmtv.com", "leparisien.fr",
            "latribune.fr", "challenges.fr", "lexpress.fr", "lepoint.fr", "20minutes.fr",
            "courrierinternational.com", "letemps.ch", "rts.ch", "lesoir.be", "rtbf.be",
            "theguardian.com", "bbc.com", "bbc.co.uk", "cnn.com", "nytimes.com",
            "washingtonpost.com", "ft.com", "bloomberg.com", "wsj.com", "cnbc.com",
            "economist.com", "politico.eu", "politico.com", "euronews.com", "aljazeera.com",
            "scmp.com", "asia.nikkei.com", "nikkei.com", "lloydslist.com", "latimes.com",
            "elpais.com", "corriere.it", "gazzetta.it", "marca.com", "dw.com", "eurosport.fr",
            "eurosport.com", "telegraph.co.uk", "rmcsport.bfmtv.com", "sudouest.fr", "ladepeche.fr",
            "timesofindia.indiatimes.com",
        ],
        "names": [
            "reuters", "afp", "associated press", "ap news", "le monde", "les echos", "le figaro",
            "franceinfo", "france 24", "rfi", "radio france", "france inter", "libération",
            "l'équipe", "ouest-france", "nice-matin", "bfmtv", "bfm business", "le parisien",
            "la tribune", "challenges", "l'express", "le point", "20 minutes",
            "courrier international", "le temps", "rts", "le soir", "rtbf", "the guardian",
            "bbc", "cnn", "the new york times", "the washington post", "financial times",
            "bloomberg", "the wall street journal", "cnbc", "the economist", "politico",
            "euronews", "al jazeera", "south china morning post", "nikkei asia",
            "lloyd's list", "los angeles times", "el país", "corriere della sera",
            "la gazzetta dello sport", "marca", "deutsche welle", "eurosport", "the telegraph",
            "rmc sport", "sud ouest", "la dépêche", "ladepeche.fr", "the times of india",
        ],
    },
    "C": {
        "domains": [
            # tennis
            "tennismajors.com", "tennis.com", "tennisactu.net", "welovetennis.fr", "universtennis.com",
            "puntodebreak.com", "ubitennis.net", "ubitennis.com", "tennistemple.com",
            "tennisworldusa.org",
            # sport business
            "sportbusiness.com", "sportico.com", "sportspromedia.com", "frontofficesports.com",
            "sportstrategies.com", "sportbuzzbusiness.fr", "insidethegames.biz", "thestadiumbusiness.com",
            # mode, distribution
            "fashionnetwork.com", "fashionunited.fr", "fashionunited.com", "fashionunited.uk",
            "businessoffashion.com", "footwearnews.com", "wwd.com", "retaildive.com",
            "supplychaindive.com", "just-style.com", "lsa-conso.fr", "insideretail.asia",
            "fibre2fashion.com", "sgbonline.com", "sportsgoodsforum.com",
            # logistique maritime
            "freightwaves.com", "joc.com", "splash247.com", "theloadstar.com",
            "portsetcorridors.com", "journalmarinemarchande.eu", "lantenne.com",
            "lloydslistintelligence.com", "gcaptain.com", "maritime-executive.com",
            # geopolitique, analyse
            "iris-france.org", "ifri.org", "chathamhouse.org", "csis.org", "brookings.edu",
            "aspi.org.au", "carnegieendowment.org", "lowyinstitute.org", "legrandcontinent.eu",
            "diploweb.com", "theconversation.com", "arabnews.com", "thenationalnews.com",
        ],
        "names": [
            "tennis majors", "tennis.com", "tennisactu", "tennis actu", "we love tennis", "punto de break",
            "puntodebreak", "univers tennis", "the maritime executive",
            "ubitennis", "tennistemple", "sportbusiness", "sportico", "sportspro",
            "front office sports", "sport stratégies", "sportbuzz business", "inside the games",
            "the stadium business", "fashionnetwork", "fashion network", "fashionunited",
            "the business of fashion", "footwear news", "wwd", "retail dive", "supply chain dive",
            "just style", "lsa", "inside retail", "fibre2fashion", "freightwaves",
            "journal of commerce", "splash247", "the loadstar", "ports et corridors",
            "journal de la marine marchande", "gcaptain", "iris", "ifri", "chatham house",
            "csis", "brookings", "aspi", "carnegie", "lowy institute", "le grand continent",
            "diploweb", "the conversation", "arab news", "the national",
        ],
    },
    "D": {
        "domains": [
            "amnesty.org", "amnesty.fr", "hrw.org", "business-humanrights.org",
            "cleanclothes.org", "collectif-ethique-sur-etiquette.org", "playthegame.org",
        ],
        "names": [
            "amnesty", "human rights watch", "business & human rights",
            "clean clothes", "éthique sur l'étiquette", "play the game",
        ],
    },
}


def domain_of(url):
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    host = urllib.parse.urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _domain_match(host, dom):
    return host == dom or host.endswith("." + dom)


def _name_match(name, key):
    return re.search(r"(^|[^a-z0-9])" + re.escape(key) + r"($|[^a-z0-9])", name) is not None


def grade_source(name="", url=""):
    """Retourne A, B, C ou D si la source est dans la liste blanche, sinon None."""
    host = domain_of(url)
    if host:
        for grade in ("A", "B", "C", "D"):
            for dom in SOURCES[grade]["domains"]:
                if _domain_match(host, dom):
                    return grade
        if host != "news.google.com":
            return None  # domaine connu mais hors liste : on rejette
    n = (name or "").lower().strip()
    for grade in ("A", "B", "C", "D"):
        for key in SOURCES[grade]["names"]:
            if n == key or _name_match(n, key):
                return grade
    return None
