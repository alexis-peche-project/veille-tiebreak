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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sources import grade_source, domain_of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "veille.json")
KEEP_DAYS = 120
MAX_ITEMS = 1500

# Axes de veille : 3 enjeux geopolitiques + 2 tendances non geopolitiques.
AXES = {
    "E1": {
        "label": "Guerre commerciale et image americaine de Nike",
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
        "label": "Chaine de valeur, RSE et normes europeennes",
        "queries_fr": [
            "Nike RSE",
            "Nike usine Vietnam",
            "Nike travail forcé",
            "règlement européen travail forcé textile",
            "devoir de vigilance textile CSRD omnibus",
            "mer Rouge conteneurs Suez",
        ],
        "queries_en": [
            "Nike sustainability",
            "Nike supply chain workers wages",
            "Nike tariffs",
            "Red Sea shipping Suez containers",
            "Xinjiang cotton brands",
        ],
    },
    "E3": {
        "label": "Tennis : sport power saoudien et gouvernance",
        "queries_fr": [
            "Arabie saoudite tennis",
            "PIF ATP WTA",
            "Six Kings Slam",
            "ITIA dopage tennis",
            "PTPA procès ATP WTA",
        ],
        "queries_en": [
            "Saudi Arabia tennis PIF",
            "Six Kings Slam",
            "PTPA lawsuit ATP WTA",
            "tennis governance premium tour",
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
        "label": "Nike en bourse, distribution et marche du tennis",
        "queries_fr": [
            "Nike action bourse",
            "Nike résultats trimestriels",
            "Nike revendeurs distribution",
            "marché du tennis France",
        ],
        "queries_en": [
            "Nike stock shares",
            "Nike market value",
            "Nike earnings guidance",
            "Nike wholesale partners",
        ],
    },
}

SIGNAL_WORDS = [
    "boycott", "droits de douane", "tarif", "tariff", "sanction", "suspension",
    "suspendu", "polémique", "controverse", "controversy", "retard", "delay",
    "rupture", "pénurie", "shortage", "xinjiang", "ouïghour", "uyghur",
    "sportswashing", "dopage", "doping", "blessure", "injury", "forfait",
    "withdraw", "retrait", "houthi", "suez", "mer rouge", "red sea", "grève",
    "strike", "hausse des prix", "price increase", "rappel", "recall",
    "revendeur", "wholesale", "licenciement", "layoff",
]


def feed_url(query, lang):
    q = urllib.parse.quote(query + " when:30d")
    if lang == "fr":
        return "https://news.google.com/rss/search?q=%s&hl=fr&gl=FR&ceid=FR:fr" % q
    return "https://news.google.com/rss/search?q=%s&hl=en-US&gl=US&ceid=US:en" % q


def fetch(url, tries=3, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (veille-tiebreak; +https://github.com)"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
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
    "E1": 'Nike (boycott OR tariffs OR controversy)',
    "E2": 'Nike (sustainability OR Vietnam OR Xinjiang OR factories OR workers)',
    "E3": 'tennis ("Saudi Arabia" OR Riyadh OR sportswashing)',
    "T4": 'Nike (Sinner OR Alcaraz OR Sabalenka)',
    "T5": 'Nike (shares OR stock OR wholesale OR earnings)',
}


def gdelt_items(query):
    params = urllib.parse.urlencode({
        "query": query, "mode": "artlist", "format": "json",
        "maxrecords": "50", "timespan": "7d", "sort": "datedesc",
    })
    raw = fetch("https://api.gdeltproject.org/api/v2/doc/doc?" + params, timeout=60)
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
    existing = {}
    for it in store.get("items", []):
        if it.get("query") == "sélection vérifiée":
            existing[it["id"]] = it
            continue
        g = grade_source(it.get("source", ""), it.get("domain", ""))
        if g is None:
            continue
        it["reliability"] = g
        existing[it["id"]] = it
    seen_titles = {norm_key(it["title"]) for it in existing.values()}

    counters = {"added": 0, "errors": 0, "rejected": 0}

    def ingest(entries, axis, lang, q, origin):
        for it in entries:
            key = norm_key(it["title"])
            if not key or key in seen_titles:
                continue
            grade = grade_source(it["source"], it["source_url"])
            if grade is None:
                counters["rejected"] += 1
                continue
            sc, hits = score(it, grade)
            iid = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
            existing[iid] = {
                "id": iid,
                "title": it["title"],
                "url": it["url"],
                "source": it["source"],
                "domain": domain_of(it["source_url"]),
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
        "stats": {"added_last_run": added, "feed_errors_last_run": errors,
                  "rejected_last_run": counters["rejected"]},
        "items": items,
    }
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("Termine : %d nouveaux articles, %d rejetes (hors liste), %d au total, %d flux en erreur." % (added, counters["rejected"], len(items), errors))


if __name__ == "__main__":
    main()
