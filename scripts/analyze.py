#!/usr/bin/env python3
"""Tri et analyse de la veille Tie Break avec l'API Claude.

1. Tri : chaque nouvel article recoit une note de pertinence (0 a 3), l'axe
   corrige si besoin, l'impact pour Tie Break en une phrase et la force du signal.
   Modele rapide et peu couteux (Claude Haiku).
2. Analyse : une fois par jour (ou a la demande), synthese des articles
   pertinents des 14 derniers jours : tendances par axe, signaux faibles,
   matrice de priorite, recommandations. Modele plus puissant (Claude Sonnet).

Sans cle ANTHROPIC_API_KEY, le script ne fait rien et le site reste fonctionnel.
La cle est stockee dans les secrets GitHub du depot (jamais dans le site).
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "veille.json")
AN_DIR = os.path.join(ROOT, "data", "analyses")
API_URL = "https://api.anthropic.com/v1/messages"
TRIAGE_MODEL = os.environ.get("TRIAGE_MODEL", "claude-haiku-5-5")
ANALYSIS_MODEL = os.environ.get("ANALYSIS_MODEL", "claude-sonnet-5-5")
TRIAGE_BATCH = 20
TRIAGE_MAX_PER_RUN = 240
ANALYSIS_EVERY_HOURS = 20
ANALYSIS_WINDOW_DAYS = 14

CONTEXT = """Tu assistes un etudiant en M2 management du sport qui realise une veille geopolitique pour Tie Break.
Tie Break : magasin de tennis independant a Nice, 2 salaries, 18 ans d'existence, l'un des 3 revendeurs officiels Nike Tennis en France.
Nike = 70 % du chiffre d'affaires et 100 % du textile et des chaussures (raquettes et accessoires : Wilson, Yonex, Babolat, Dunlop).
Clientele : joueurs de club, competiteurs, loisirs, touristes et clientele internationale. Concurrence : sites web (Tennis-Point, Tennis Warehouse), Decathlon, Intersport, Nice Smash.
Probleme operationnel : livraisons Nike en retard, collections recues apres les Grands Chelems. Site e-commerce en construction.
Question de veille : dans quelle mesure l'exposition geopolitique et mediatique de Nike et de ses athletes cree-t-elle des risques et des opportunites pour les ventes de Tie Break d'ici 2028, et comment le magasin doit-il y repondre ?
Axes :
E1 Guerre commerciale et image americaine de Nike (tensions Etats-Unis/UE, droits de douane, appels au boycott, prises de position de Nike)
E2 Chaine de valeur, RSE et normes europeennes (usines en Asie, travail force, salaires des sous-traitants, Xinjiang, engagements climat de Nike, reglementation UE : CSRD, devoir de vigilance, reglement travail force ; fret et mer Rouge)
E3 Tennis : sport power saoudien et gouvernance (PIF, Arabie saoudite, sportswashing, ATP/WTA/ITF, ITIA, AMA, TAS, plainte PTPA)
T4 Performances et polemiques des joueurs Nike (Sinner, Alcaraz, Sabalenka...) : victoires, blessures, affaires
T5 Nike en bourse, distribution et marche du tennis (cours et capitalisation, resultats, strategie wholesale, collections, marche francais)"""


def call_claude(model, system, user, max_tokens):
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                data = json.loads(r.read().decode("utf-8"))
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            usage = data.get("usage", {})
            print("  modele %s : %s tokens en entree, %s en sortie" % (
                model, usage.get("input_tokens"), usage.get("output_tokens")))
            return text
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:300]
            print("  ! erreur API %s : %s" % (exc.code, detail), file=sys.stderr)
            if exc.code in (400, 401, 403, 404):
                return None
        except Exception as exc:  # noqa: BLE001
            print("  ! erreur reseau : %s" % exc, file=sys.stderr)
        time.sleep(10 * (attempt + 1))
    return None


def extract_json(text):
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    for opener, closer in (("[", "]"), ("{", "}")):
        a, b = text.find(opener), text.rfind(closer)
        if a != -1 and b > a:
            try:
                return json.loads(text[a:b + 1])
            except ValueError:
                continue
    return None


def salvage_objects(text):
    """Recupere les objets JSON complets d'un tableau tronque ou mal forme."""
    out = []
    for m in re.finditer(r"\{[^{}]*\}", text or ""):
        try:
            out.append(json.loads(m.group(0)))
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------- tri
TRIAGE_SYSTEM = CONTEXT + """

Ta tache : trier des articles de presse pour cette veille. Pour chaque article (tu ne vois que le titre, la source et la date), reponds avec :
- "id" : l'identifiant recu
- "r" : pertinence de 0 a 3. 0 = hors sujet (homonyme, sujet sans lien avec Nike, le tennis, le commerce international ou la logistique Asie-Europe) ; 1 = contexte lointain ; 2 = utile pour un axe ; 3 = important, a lire en priorite pour Tie Break.
- "axe" : E1, E2, E3, T4 ou T5 (corrige l'axe propose s'il est faux)
- "impact" : une phrase de 25 mots maximum, en francais, qui dit ce que l'article change ou pourrait changer pour Tie Break (ventes, image, approvisionnement, calendrier). Vide si r = 0.
- "signal" : "fort" (evenement avere, consequence probable), "faible" (premier indice, rumeur, annonce a confirmer) ou "aucun".
Reste factuel : ne deduis rien que le titre ne permet pas. Reponds UNIQUEMENT par un tableau JSON, sans texte autour."""


def triage(store):
    todo = [it for it in store["items"] if "ai" not in it]
    todo.sort(key=lambda x: x["date"], reverse=True)
    todo = todo[:TRIAGE_MAX_PER_RUN]
    if not todo:
        print("Tri : aucun nouvel article.")
        return 0
    print("Tri : %d articles a classer avec %s" % (len(todo), TRIAGE_MODEL))
    by_id = {it["id"]: it for it in todo}
    done = 0
    for i in range(0, len(todo), TRIAGE_BATCH):
        batch = todo[i:i + TRIAGE_BATCH]
        lines = ["%s | axe propose %s | %s | %s | %s" % (
            it["id"], it["axis"], it["source"], it["date"][:10], it["title"]) for it in batch]
        text = call_claude(TRIAGE_MODEL, TRIAGE_SYSTEM, "Articles :\n" + "\n".join(lines), 6000)
        result = extract_json(text)
        if not isinstance(result, list):
            result = salvage_objects(text)
            print("  lot partiellement lisible : %d objets recuperes" % len(result))
            if not result:
                print("  ! reponse illisible : %s" % (text or "")[:200].replace("\n", " "), file=sys.stderr)
                continue
        time.sleep(3)
        for row in result:
            it = by_id.get(str(row.get("id", "")))
            if not it:
                continue
            try:
                r = max(0, min(3, int(row.get("r", 0))))
            except (TypeError, ValueError):
                r = 0
            axe = row.get("axe") if row.get("axe") in ("E1", "E2", "E3", "T4", "T5") else it["axis"]
            it["ai"] = {
                "r": r,
                "impact": str(row.get("impact", ""))[:300],
                "signal": row.get("signal") if row.get("signal") in ("fort", "faible", "aucun") else "aucun",
                "model": TRIAGE_MODEL,
            }
            if axe != it["axis"]:
                it["axis_original"] = it["axis"]
                it["axis"] = axe
            done += 1
    print("Tri : %d articles classes." % done)
    return done


# ---------------------------------------------------------------- analyse
ANALYSIS_SYSTEM = CONTEXT + """

Ta tache : rediger l'analyse de veille du jour a partir des articles fournis (titre, source, fiabilite A a D, date, impact deja estime). Tu raisonnes comme un analyste de veille : faits verifies, signaux repetes, tendance expliquee. Tu cites tes sources par leur identifiant entre crochets, par exemple [a1b2c3d4e5f6]. Tu n'inventes aucun fait absent des articles. Quand un point repose sur une seule source C ou D, tu le dis. Tu distingues toujours le fait, l'interpretation et la projection : quand les sources divergent sur la cause d'un evenement, tu donnes la version officielle et l'interpretation des medias separement, sans trancher. Tu n'emploies pas le mot sportwashing comme une preuve : tu qualifies (diversification economique, prestige, diversion).

Reponds UNIQUEMENT par un objet JSON de cette forme :
{
 "synthese": "4 a 6 phrases : ce qui a change cette periode et ce que cela implique pour Tie Break",
 "axes": [
   {"axe": "E1", "tendance": "hausse | stable | baisse | calme",
    "resume": "2 a 3 phrases",
    "faits": [{"texte": "fait date et sourcé", "ids": ["..."]}],
    "signaux_faibles": [{"texte": "...", "ids": ["..."]}],
    "risque": "pour Tie Break, une phrase", "opportunite": "pour Tie Break, une phrase"}
   ... un objet par axe E1, E2, E3, T4, T5 ...
 ],
 "priorites": [{"sujet": "...", "axe": "E1", "probabilite": 1, "impact": 3, "justification": "une phrase"}],
 "recommandations": [{"action": "action concrete et realiste pour une TPE de 2 salaries", "axe": "E2", "horizon": "immediat | 3 mois | 12 mois", "destinataire": "gerant | vendeur | e-commerce"}],
 "a_verifier": ["point a recouper avant de l'utiliser dans le dossier"]
}
probabilite et impact sont notes de 1 (faible) a 3 (fort). 4 a 8 priorites, 3 a 5 recommandations."""


def analysis_due(force):
    if force:
        return True
    path = os.path.join(AN_DIR, "latest.json")
    try:
        with open(path, encoding="utf-8") as f:
            last = json.load(f).get("generated", "")
        t = dt.datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        return dt.datetime.now(dt.timezone.utc) - t > dt.timedelta(hours=ANALYSIS_EVERY_HOURS)
    except Exception:  # noqa: BLE001
        return True


def analyse(store, force):
    if not analysis_due(force):
        print("Analyse : la derniere date de moins de %d h, rien a faire." % ANALYSIS_EVERY_HOURS)
        return
    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(days=ANALYSIS_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pool = [it for it in store["items"] if it["date"] >= since and it.get("ai", {}).get("r", 0) >= 2]
    pool.sort(key=lambda x: (x["ai"]["r"], {"A": 3, "B": 2, "C": 1, "D": 1}[x["reliability"]], x["date"]), reverse=True)
    pool = pool[:160]
    if len(pool) < 15:
        since30 = (now - dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        pool = [it for it in store["items"] if it["date"] >= since30 and it.get("ai", {}).get("r", 0) >= 2][:160]
    if len(pool) < 5:
        print("Analyse : trop peu d'articles pertinents (%d) pour une analyse." % len(pool))
        return
    print("Analyse : %d articles transmis a %s" % (len(pool), ANALYSIS_MODEL))
    lines = ["[%s] %s | %s | fiabilite %s | axe %s | pertinence %s | %s | impact estime : %s" % (
        it["id"], it["date"][:10], it["source"], it["reliability"], it["axis"], it["ai"]["r"],
        it["title"], it["ai"].get("impact", "")) for it in pool]
    user = "Date du jour : %s. Periode couverte : %d derniers jours.\nArticles :\n%s" % (
        now.strftime("%Y-%m-%d"), ANALYSIS_WINDOW_DAYS, "\n".join(lines))
    raw = call_claude(ANALYSIS_MODEL, ANALYSIS_SYSTEM, user, 16000)
    result = extract_json(raw)
    if not isinstance(result, dict) or "synthese" not in result:
        print("  ! analyse illisible : %s" % (raw or "")[-300:].replace("\n", " "), file=sys.stderr)
        return
    valid = {it["id"] for it in pool}
    sources = {it["id"]: {"title": it["title"], "url": it["url"], "source": it["source"],
                          "date": it["date"][:10], "reliability": it["reliability"]} for it in pool}
    result["generated"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    result["model"] = ANALYSIS_MODEL
    result["window_days"] = ANALYSIS_WINDOW_DAYS
    result["n_articles"] = len(pool)
    result["sources"] = {k: v for k, v in sources.items() if k in valid}
    os.makedirs(AN_DIR, exist_ok=True)
    stamp = now.strftime("%Y-%m-%d")
    for name in ("latest.json", stamp + ".json"):
        with open(os.path.join(AN_DIR, name), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    idx_path = os.path.join(AN_DIR, "index.json")
    try:
        with open(idx_path, encoding="utf-8") as f:
            idx = json.load(f)
    except Exception:  # noqa: BLE001
        idx = {"analyses": []}
    idx["analyses"] = [a for a in idx["analyses"] if a["date"] != stamp]
    idx["analyses"].insert(0, {"date": stamp, "file": stamp + ".json", "n_articles": len(pool)})
    idx["analyses"] = idx["analyses"][:60]
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
    print("Analyse enregistree : data/analyses/%s.json" % stamp)


def main():
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        print("Pas de cle ANTHROPIC_API_KEY : tri et analyse ignores.")
        return
    with open(DATA, encoding="utf-8") as f:
        store = json.load(f)
    triage(store)
    store["ai_updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=1)
    analyse(store, force=os.environ.get("FORCE_ANALYSIS", "") == "true")


if __name__ == "__main__":
    main()
