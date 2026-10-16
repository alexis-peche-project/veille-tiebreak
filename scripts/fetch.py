#!/usr/bin/env python3
"""Collecte automatique de la veille Tie Break.

Interroge Google Actualites (flux RSS) pour chaque axe de veille, classe chaque
article (axe, fiabilite de la source, score de signal) et fusionne le resultat
avec l'historique dans data/veille.json. Bibliotheque standard uniquement.
"""
import datetime as dt
import email.utils
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "veille.json")
KEEP_DAYS = 120
MAX_ITEMS = 1500

# Axes de veille : 3 enjeux geopolitiques + 2 tendances non geopolitiques.
AXES = {
    "E1": {
        "label": "Nike et la puissance americaine",
        "queries_fr": [
            "Nike boycott",
            "boycott marques américaines",
            "Nike droits de douane Europe",
            "Nike polémique",
            "guerre commerciale États-Unis Union européenne textile",
        ],
        "queries_en": [
            "Nike boycott",
            "Nike political controversy",
            "EU US trade war tariffs apparel",
        ],
    },
    "E2": {
        "label": "Production et routes d'approvisionnement",
        "queries_fr": [
            "Nike usine Vietnam",
            "Nike Chine Xinjiang",
            "mer Rouge conteneurs Suez",
            "fret maritime Asie Europe retards",
            "droits de douane Vietnam chaussures",
        ],
        "queries_en": [
            "Nike tariffs",
            "Nike supply chain",
            "Red Sea shipping Suez containers",
            "Vietnam footwear tariffs",
            "Xinjiang cotton brands",
        ],
    },
    "E3": {
        "label": "Athletes Nike et nouvelle geographie du tennis",
        "queries_fr": [
            "Arabie saoudite tennis",
            "PIF ATP WTA",
            "Six Kings Slam",
            "Masters 1000 Arabie saoudite",
            "sportswashing tennis",
        ],
        "queries_en": [
            "Saudi Arabia tennis PIF",
            "Six Kings Slam",
            "WTA Finals Riyadh",
            "tennis sportswashing",
        ],
    },
    "T4": {
        "label": "Performances et polemiques des joueurs",
        "queries_fr": [
            "Sinner Nike",
            "Alcaraz Nike",
            "Sabalenka Nike",
            "Alcaraz blessure",
            "Sinner blessure",
        ],
        "queries_en": [
            "Alcaraz Nike outfit",
            "Sinner Nike",
            "Sabalenka Nike",
        ],
    },
    "T5": {
        "label": "Distribution Nike et marche du tennis",
        "queries_fr": [
            "Nike revendeurs distribution",
            "Nike résultats trimestriels",
            "marché du tennis France",
            "magasin tennis Nice",
        ],
        "queries_en": [
            "Nike wholesale partners",
            "Nike earnings",
            "Nike tennis collection",
        ],
    },
}

# Fiabilite : A = source primaire officielle, B = agence / grand media,
# C = media specialise (a recouper), D = acteur engage / opinion.
RELIABILITY = [
    ("A", ["nike", "sec.gov", "atp tour", "atptour", "wta", "wtatennis", "itf", "fft",
           "fédération française de tennis", "wada", "agence mondiale antidopage",
           "commission européenne", "european commission", "gouvernement",
           "ministère", "white house", "maison blanche", "ustr", "wto", "omc"]),
    ("D", ["amnesty", "human rights watch", "hrw", "greenpeace", "blog",
           "opinion", "tribune", "medium", "substack"]),
    ("B", ["reuters", "afp", "agence france-presse", "associated press", "ap news",
           "le monde", "les echos", "le figaro", "franceinfo", "france info",
           "france 24", "france24", "rfi", "radio france", "libération",
           "liberation", "l'équipe", "lequipe", "ouest-france", "nice-matin",
           "nice matin", "bfm", "the guardian", "bbc", "cnn", "new york times",
           "washington post", "financial times", "bloomberg", "wall street journal",
           "cnbc", "the economist", "le parisien", "20 minutes", "challenges",
           "la tribune", "l'express", "le point", "nikkei", "south china morning post",
           "al jazeera", "politico", "euronews", "lloyd's list",
           # domaines (articles issus de GDELT)
           "lemonde.fr", "lesechos.fr", "lefigaro.fr", "francetvinfo.fr",
           "liberation.fr", "nicematin.com", "leparisien.fr", "20minutes.fr",
           "bfmtv.com", "theguardian.com", "nytimes.com", "washingtonpost.com",
           "ft.com", "wsj.com", "apnews.com", "aljazeera.com", "scmp.com",
           "lloydslist", "ouest-france.fr", "latribune.fr", "lexpress.fr", "lepoint.fr"]),
]

SIGNAL_WORDS = [
    "boycott", "droits de douane", "tarif", "tariff", "sanction", "suspension",
    "suspendu", "polémique", "controverse", "controversy", "retard", "delay",
    "rupture", "pénurie", "shortage", "xinjiang", "ouïghour", "uyghur",
    "sportswashing", "dopage", "doping", "blessure", "injury", "forfait",
    "withdraw", "retrait", "houthi", "suez", "mer rouge", "red sea", "grève",
    "strike", "hausse des prix", "price increase", "rappel", "recall",
    "revendeur", "wholesale", "licenciement", "layoff",
]


def classify_reliability(source):
    s = (source or "").lower()
    for grade, keys in RELIABILITY:
        for k in keys:
            if len(k) <= 4:
                if re.search(r"(^|[^a-z])" + re.escape(k) + r"($|[^a-z])", s):
                    return grade
            elif k in s:
                return grade
    return "C"


def feed_url(query, lang):
    q = urllib.parse.quote(query + " when:30d")
    if lang == "fr":
        return "https://news.google.com/rss/search?q=%s&hl=fr&gl=FR&ceid=FR:fr" % q
    return "https://news.google.com/rss/search?q=%s&hl=en-US&gl=US&ceid=US:en" % q


def fetch(url, tries=3):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (veille-tiebreak; +https://github.com)"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001
            print("  ! essai %d echoue : %s" % (i + 1, exc), file=sys.stderr)
            time.sleep(2 * (i + 1))
    return None


def parse_date(text):
    try:
        d = email.utils.parsedate_to_datetime(text)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except Exception:  # noqa: BLE001
        return dt.datetime.now(dt.timezone.utc)


def clean_title(title, source):
    title = (title or "").strip()
    if source and title.endswith(" - " + source):
        title = title[: -(len(source) + 3)]
    return re.sub(r"\s+", " ", title)


def norm_key(title):
    t = title.lower()
    t = re.sub(r"[^a-z0-9àâäçéèêëîïôöùûüœ ]", " ", t)
    return " ".join(t.split())[:90]


def parse_feed(xml_bytes):
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items
    for it in root.iter("item"):
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        source_url = src_el.get("url", "") if src_el is not None else ""
        items.append({
            "title": clean_title(it.findtext("title"), source),
            "url": (it.findtext("link") or "").strip(),
            "date": parse_date(it.findtext("pubDate") or ""),
            "source": source or "Source inconnue",
            "source_url": source_url,
        })
    return items


# GDELT (base mondiale d'actualites, API gratuite sans cle) : une requete par axe.
GDELT_QUERIES = {
    "E1": '(Nike boycott OR "boycott American brands" OR "Nike tariffs Europe")',
    "E2": '("Nike" (Vietnam OR Xinjiang OR "supply chain")) OR ("Red Sea" shipping containers)',
    "E3": '(tennis ("Saudi Arabia" OR PIF OR Riyadh OR sportswashing))',
    "T4": '((Sinner OR Alcaraz OR Sabalenka) Nike)',
    "T5": '(Nike (wholesale OR retailers OR earnings OR "tennis collection"))',
}


def gdelt_items(query):
    params = urllib.parse.urlencode({
        "query": query, "mode": "artlist", "format": "json",
        "maxrecords": "50", "timespan": "7d", "sort": "datedesc",
    })
    raw = fetch("https://api.gdeltproject.org/api/v2/doc/doc?" + params)
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8", "ignore"))
    except ValueError:
        return []
    out = []
    for a in data.get("articles", []):
        try:
            d = dt.datetime.strptime(a.get("seendate", ""), "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            d = dt.datetime.now(dt.timezone.utc)
        lang = "fr" if a.get("language", "").lower().startswith("french") else "en"
        out.append({
            "title": re.sub(r"\s+", " ", a.get("title", "")).strip(),
            "url": a.get("url", ""),
            "date": d,
            "source": a.get("domain", "Source inconnue"),
            "source_url": a.get("domain", ""),
            "lang": lang,
        })
    return out


def score(item, grade):
    text = item["title"].lower()
    hits = [w for w in SIGNAL_WORDS if w in text]
    base = {"A": 3, "B": 2, "C": 1, "D": 1}[grade]
    return base + 2 * len(hits), hits


def main():
    now = dt.datetime.now(dt.timezone.utc)
    try:
        with open(DATA, encoding="utf-8") as f:
            store = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        store = {"items": []}
    existing = {it["id"]: it for it in store.get("items", [])}
    seen_titles = {norm_key(it["title"]) for it in existing.values()}

    counters = {"added": 0, "errors": 0}

    def ingest(entries, axis, lang, q, origin):
        for it in entries:
            key = norm_key(it["title"])
            if not key or key in seen_titles:
                continue
            grade = classify_reliability(it["source"] + " " + it["source_url"])
            sc, hits = score(it, grade)
            iid = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
            existing[iid] = {
                "id": iid,
                "title": it["title"],
                "url": it["url"],
                "source": it["source"],
                "date": it["date"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "first_seen": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "axis": axis,
                "lang": it.get("lang", lang),
                "query": q,
                "origin": origin,
                "reliability": grade,
                "score": sc,
                "signals": hits,
            }
            seen_titles.add(key)
            counters["added"] += 1

    for axis, conf in AXES.items():
        for lang in ("fr", "en"):
            for q in conf["queries_" + lang]:
                print("[%s/%s] Google Actualites : %s" % (axis, lang, q))
                raw = fetch(feed_url(q, lang))
                if raw is None:
                    counters["errors"] += 1
                    continue
                ingest(parse_feed(raw)[:25], axis, lang, q, "Google Actualités")
                time.sleep(1.2)

    for axis, q in GDELT_QUERIES.items():
        print("[%s] GDELT : %s" % (axis, q))
        entries = gdelt_items(q)
        if entries is None:
            counters["errors"] += 1
        else:
            ingest(entries, axis, "en", q, "GDELT")
        time.sleep(6)  # GDELT demande au moins 5 s entre deux requetes
    added, errors = counters["added"], counters["errors"]

    cutoff = now - dt.timedelta(days=KEEP_DAYS)
    items = [it for it in existing.values() if it["date"] >= cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")]
    items.sort(key=lambda x: x["date"], reverse=True)
    items = items[:MAX_ITEMS]

    out = {
        "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "axes": {k: v["label"] for k, v in AXES.items()},
        "stats": {"added_last_run": added, "feed_errors_last_run": errors},
        "items": items,
    }
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("Termine : %d nouveaux articles, %d au total, %d flux en erreur." % (added, len(items), errors))


if __name__ == "__main__":
    main()
