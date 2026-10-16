(function () {
  "use strict";

  var AXES = {
    E1: { label: "Guerre commerciale et image américaine de Nike", kind: "Géopolitique : tensions États-Unis / UE, boycotts", color: "var(--e1)" },
    E2: { label: "Chaîne de valeur, RSE et normes européennes", kind: "Géopolitique : Asie, travail forcé, CSRD, mer Rouge", color: "var(--e2)" },
    E3: { label: "Tennis : sport power saoudien et gouvernance", kind: "Géopolitique : PIF, ATP/WTA, ITIA, AMA, TAS", color: "var(--e3)" },
    T4: { label: "Performances et polémiques des joueurs", kind: "Tendance sportive", color: "var(--t4)" },
    T5: { label: "Nike en bourse, distribution et marché", kind: "Tendance économique et commerciale", color: "var(--t5)" }
  };
  var AXIS_KEYS = ["E1", "E2", "E3", "T4", "T5"];
  var DAY = 86400000;

  var state = {
    items: [],
    refs: [],
    axes: {},
    rel: { A: true, B: true, C: true, D: true },
    period: 7,
    sort: "date",
    hot: false,
    relevance: 1,
    q: "",
    limit: 120
  };
  AXIS_KEYS.forEach(function (k) { state.axes[k] = true; });

  // ---------- per-viewer storage (kept items, last visit) ----------
  function load(key, fallback) {
    try { var v = window.localStorage.getItem(key); return v ? JSON.parse(v) : fallback; }
    catch (e) { return fallback; }
  }
  function save(key, value) {
    try { window.localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* ignore */ }
  }
  var kept = load("tb-kept", {});
  var lastVisit = load("tb-last-visit", 0);
  save("tb-last-visit", Date.now());

  // ---------- helpers ----------
  function $(sel) { return document.querySelector(sel); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function ts(iso) { var t = Date.parse(iso); return isNaN(t) ? 0 : t; }
  var MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
  function fmtDate(t) { var d = new Date(t); return d.getDate() + " " + MONTHS[d.getMonth()] + " " + d.getFullYear(); }
  function relTime(t) {
    var diff = Date.now() - t;
    if (diff < 3600000) return "il y a " + Math.max(1, Math.round(diff / 60000)) + " min";
    if (diff < DAY) return "il y a " + Math.round(diff / 3600000) + " h";
    if (diff < 7 * DAY) return "il y a " + Math.round(diff / DAY) + " j";
    return fmtDate(t);
  }
  function fmtRefDate(s) {
    if (!s) return "";
    var p = s.split("-");
    if (p.length === 3) return parseInt(p[2], 10) + " " + MONTHS[parseInt(p[1], 10) - 1] + " " + p[0];
    if (p.length === 2) return MONTHS[parseInt(p[1], 10) - 1] + " " + p[0];
    return s;
  }
  function norm(s) {
    s = (s || "").toLowerCase();
    return s.normalize ? s.normalize("NFD").replace(/[̀-ͯ]/g, "") : s;
  }

  // ---------- data ----------
  function getJSON(url) {
    return fetch(url + "?t=" + Date.now(), { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error(url + " : " + r.status);
      return r.json();
    });
  }

  Promise.all([getJSON("data/veille.json"), getJSON("data/references.json")])
    .then(function (res) {
      var veille = res[0], refs = res[1];
      state.items = (veille.items || []).map(function (it) { it._t = ts(it.date); it._seen = ts(it.first_seen); return it; });
      state.refs = refs.items || [];
      var up = ts(veille.updated);
      $("#updated").textContent = up ? "Mise à jour " + relTime(up) + " · " + state.items.length + " articles suivis" : "En attente de la première collecte";
      buildAxisChips();
      renderAll();
      renderRefs();
    })
    .catch(function (err) {
      $("#updated").textContent = "Impossible de charger les données.";
      $("#feed").innerHTML = "";
      var li = el("li", "empty", "Les données n'ont pas pu être chargées (" + err.message + "). Rechargez la page dans quelques minutes.");
      $("#feed").appendChild(li);
    });

  // ---------- scoreboard ----------
  function renderBoard() {
    var since = Date.now() - 7 * DAY;
    var tbody = $("#scoreboard tbody");
    tbody.innerHTML = "";
    var onlyOne = selectedAxes().length === 1 ? selectedAxes()[0] : null;
    AXIS_KEYS.forEach(function (k) {
      var row = { n: 0, A: 0, B: 0, C: 0, D: 0, hot: 0 };
      state.items.forEach(function (it) {
        if (it.axis !== k || it._t < since) return;
        if (it.ai && it.ai.r === 0) return;
        row.n++; row[it.reliability] = (row[it.reliability] || 0) + 1;
        if ((it.signals && it.signals.length) || (it.ai && it.ai.signal === "fort")) row.hot++;
      });
      var tr = el("tr");
      tr.tabIndex = 0;
      tr.style.borderLeftColor = AXES[k].color;
      if (onlyOne === k) tr.className = "is-selected";
      var name = el("td", "axis-cell");
      var code = el("span", "code", k); code.style.color = "#fff";
      name.appendChild(code);
      name.appendChild(document.createTextNode(AXES[k].label));
      name.appendChild(el("span", "kind", AXES[k].kind));
      tr.appendChild(name);
      ["n", "A", "B", "C", "D", "hot"].forEach(function (c) {
        var td = el("td", null, String(row[c]));
        if (row[c] === 0) td.className = "zero";
        else if (c === "hot") td.className = "hot";
        tr.appendChild(td);
      });
      function pick() { focusAxis(k); }
      tr.addEventListener("click", pick);
      tr.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
      tbody.appendChild(tr);
    });
  }

  function focusAxis(k) {
    var only = selectedAxes().length === 1 && state.axes[k];
    AXIS_KEYS.forEach(function (a) { state.axes[a] = only ? true : a === k; });
    syncChips();
    showView("feed");
    renderAll();
  }

  // ---------- filters ----------
  function selectedAxes() { return AXIS_KEYS.filter(function (k) { return state.axes[k]; }); }

  function buildAxisChips() {
    var box = $("#axis-filter");
    box.innerHTML = "";
    var lab = el("span", "filter-label", "Axes");
    box.appendChild(lab);
    AXIS_KEYS.forEach(function (k) {
      var b = el("button", "chip");
      b.type = "button";
      b.setAttribute("data-axis", k);
      var dot = el("span", "dot"); dot.style.background = AXES[k].color;
      b.appendChild(dot);
      b.appendChild(document.createTextNode(k + " " + AXES[k].label));
      b.addEventListener("click", function () {
        state.axes[k] = !state.axes[k];
        if (!selectedAxes().length) AXIS_KEYS.forEach(function (a) { state.axes[a] = true; });
        syncChips(); renderAll();
      });
      box.appendChild(b);
    });
    syncChips();
  }
  function syncChips() {
    var all = selectedAxes().length === AXIS_KEYS.length;
    Array.prototype.forEach.call(document.querySelectorAll(".chip[data-axis]"), function (b) {
      var on = !all && state.axes[b.getAttribute("data-axis")];
      b.className = "chip" + (on ? " is-on" : "");
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  $("#q").addEventListener("input", function (e) { state.q = norm(e.target.value.trim()); state.limit = 120; renderFeed(); });
  $("#period").addEventListener("change", function (e) { state.period = parseInt(e.target.value, 10); state.limit = 120; renderFeed(); });
  $("#sort").addEventListener("change", function (e) { state.sort = e.target.value; renderFeed(); });
  $("#relevance").addEventListener("change", function (e) { state.relevance = parseInt(e.target.value, 10); state.limit = 120; renderFeed(); });
  $("#hot").addEventListener("change", function (e) { state.hot = e.target.checked; renderFeed(); });
  Array.prototype.forEach.call(document.querySelectorAll("input[name=rel]"), function (c) {
    c.addEventListener("change", function () { state.rel[c.value] = c.checked; renderFeed(); });
  });

  function filtered() {
    var since = state.period ? Date.now() - state.period * DAY : 0;
    var list = state.items.filter(function (it) {
      if (!state.axes[it.axis]) return false;
      if (!state.rel[it.reliability]) return false;
      if (since && it._t < since) return false;
      if (state.hot && !(it.signals && it.signals.length) && !(it.ai && it.ai.signal === "fort")) return false;
      if (state.relevance > 0) {
        var r = it.ai ? it.ai.r : null;
        if (r === 0) return false;
        if (state.relevance >= 2 && (r === null || r < state.relevance)) return false;
      }
      if (state.q && norm(it.title + " " + it.source).indexOf(state.q) === -1) return false;
      return true;
    });
    var rel = function (x) { return x.ai ? x.ai.r : 1.5; };
    list.sort(state.sort === "score"
      ? function (a, b) { return (b.score - a.score) || (b._t - a._t); }
      : state.sort === "relevance"
        ? function (a, b) { return (rel(b) - rel(a)) || (b._t - a._t); }
        : function (a, b) { return b._t - a._t; });
    return list;
  }

  // ---------- items ----------
  function itemNode(it, withNote) {
    var node = document.getElementById("item-tpl").content.firstElementChild.cloneNode(true);
    var tag = node.querySelector(".axis-tag");
    tag.textContent = it.axis; tag.style.color = AXES[it.axis] ? AXES[it.axis].color : "inherit";
    tag.title = AXES[it.axis] ? AXES[it.axis].label : "";
    var rel = node.querySelector(".rel");
    rel.textContent = "Fiabilité " + it.reliability; rel.className = "rel rel-" + it.reliability;
    var when = node.querySelector(".when");
    when.textContent = relTime(it._t); when.setAttribute("datetime", it.date); when.title = fmtDate(it._t);
    if (lastVisit && it._seen > lastVisit) node.querySelector(".new-dot").hidden = false;
    var a = node.querySelector(".item-title");
    a.textContent = it.title; a.href = it.url;
    node.querySelector(".item-source").textContent = it.source + (it.origin ? " · via " + it.origin : "");
    if (it.ai) {
      var rv = node.querySelector(".relev");
      rv.hidden = false;
      rv.className = "relev relev-" + it.ai.r;
      rv.textContent = it.ai.r === 0 ? "Hors sujet" : "Pertinence " + it.ai.r + "/3";
      rv.title = "Note attribuée par Claude";
      if (it.ai.impact) {
        var imp = node.querySelector(".item-impact");
        imp.hidden = false;
        imp.textContent = it.ai.impact + (it.ai.signal && it.ai.signal !== "aucun" ? " (signal " + it.ai.signal + ")" : "");
      }
    }
    var sig = node.querySelector(".item-signals");
    (it.signals || []).forEach(function (s) { sig.appendChild(el("span", null, s)); });
    var btn = node.querySelector(".keep");
    var isKept = !!kept[it.id];
    btn.setAttribute("aria-pressed", isKept ? "true" : "false");
    btn.textContent = isKept ? "Retenu" : "Retenir";
    btn.addEventListener("click", function () { toggleKeep(it); });
    if (withNote) {
      var wrap = node.querySelector(".note-wrap"); wrap.hidden = false;
      var ta = node.querySelector(".note");
      ta.value = (kept[it.id] && kept[it.id].note) || "";
      ta.addEventListener("input", function () { if (kept[it.id]) { kept[it.id].note = ta.value; save("tb-kept", kept); } });
    }
    return node;
  }

  function toggleKeep(it) {
    if (kept[it.id]) delete kept[it.id];
    else {
      var copy = {}; for (var k in it) if (k.charAt(0) !== "_") copy[k] = it[k];
      kept[it.id] = { item: copy, note: "", keptAt: Date.now() };
    }
    save("tb-kept", kept);
    renderFeed(); renderKept();
  }

  function renderFeed() {
    var list = filtered();
    var ol = $("#feed");
    ol.innerHTML = "";
    $("#result-count").textContent = list.length + (list.length > 1 ? " articles" : " article") + " correspondent aux filtres.";
    if (!list.length) {
      ol.appendChild(el("li", "empty", "Aucun article ne correspond. Élargissez la période ou réactivez des niveaux de fiabilité."));
      return;
    }
    list.slice(0, state.limit).forEach(function (it) { ol.appendChild(itemNode(it, false)); });
    if (list.length > state.limit) {
      var li = el("li");
      var more = el("button", "btn chip", "Afficher " + Math.min(120, list.length - state.limit) + " articles de plus");
      more.type = "button";
      more.addEventListener("click", function () { state.limit += 120; renderFeed(); });
      li.appendChild(more); ol.appendChild(li);
    }
  }

  function keptList() {
    return Object.keys(kept).map(function (id) {
      var it = kept[id].item; it._t = ts(it.date); it._seen = 0; return it;
    }).sort(function (a, b) { return b._t - a._t; });
  }

  function renderKept() {
    var list = keptList();
    $("#kept-count").textContent = String(list.length);
    var ol = $("#kept");
    ol.innerHTML = "";
    if (!list.length) {
      ol.appendChild(el("li", "empty", "Aucun article retenu. Dans le fil de veille, cliquez sur « Retenir » pour garder un article et lui ajouter une note."));
      return;
    }
    list.forEach(function (it) { ol.appendChild(itemNode(it, true)); });
  }

  function renderRefs() {
    var tb = $("#refs tbody");
    tb.innerHTML = "";
    state.refs.forEach(function (r) {
      var tr = el("tr");
      tr.appendChild(el("td", null, String(r.n)));
      var td = el("td");
      if (r.url) { var a = el("a", null, r.title); a.href = r.url; a.target = "_blank"; a.rel = "noopener"; td.appendChild(a); }
      else td.appendChild(document.createTextNode(r.title));
      td.appendChild(el("div", "item-source", r.source + ", " + fmtRefDate(r.date)));
      tr.appendChild(td);
      tr.appendChild(el("td", null, r.family));
      tr.appendChild(el("td", null, r.finding));
      var ax = el("td", "axis-tag", r.axis); ax.style.color = AXES[r.axis] ? AXES[r.axis].color : "inherit"; tr.appendChild(ax);
      var rc = el("td"); rc.appendChild(el("span", "rel rel-" + r.reliability, r.reliability)); tr.appendChild(rc);
      tb.appendChild(tr);
    });
  }

  function renderAll() { renderBoard(); renderFeed(); renderKept(); }

  // ---------- tabs ----------
  function showView(v) {
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (t) {
      var on = t.getAttribute("data-view") === v;
      t.className = "tab" + (on ? " is-active" : "");
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    ["feed", "analyses", "kept", "refs", "method"].forEach(function (name) { $("#view-" + name).hidden = name !== v; });
  }
  Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (t) {
    t.addEventListener("click", function () {
      var v = t.getAttribute("data-view");
      showView(v);
      try { history.replaceState(null, "", "#" + v); } catch (e) { /* ignore */ }
    });
  });
  var initial = (location.hash || "").replace("#", "");
  if (["feed", "analyses", "kept", "refs", "method"].indexOf(initial) !== -1) showView(initial);

  // ---------- analyses (Claude) ----------
  var TREND = { hausse: "En hausse", stable: "Stable", baisse: "En baisse", calme: "Calme" };
  function citeText(parent, text, sources, order) {
    var parts = String(text || "").split(/\[([0-9a-f]{12})\]/);
    parts.forEach(function (part, i) {
      if (i % 2 === 0) { if (part) parent.appendChild(document.createTextNode(part)); return; }
      var src = sources[part];
      if (!src) return;
      if (order.indexOf(part) === -1) order.push(part);
      var a = el("a", "cite", String(order.indexOf(part) + 1));
      a.href = src.url; a.target = "_blank"; a.rel = "noopener"; a.title = src.source + " : " + src.title;
      parent.appendChild(a);
    });
  }
  function citeIds(parent, ids, sources, order) {
    (ids || []).forEach(function (id) { citeText(parent, "[" + id + "]", sources, order); });
  }

  function renderAnalysis(an) {
    var body = $("#an-body");
    body.innerHTML = "";
    var src = an.sources || {};
    var order = [];
    var t = ts(an.generated);
    $("#an-meta").textContent = "Analyse rédigée par Claude le " + fmtDate(t) + " à partir de " + an.n_articles +
      " articles pertinents des " + an.window_days + " derniers jours. Ce sont des pistes à vérifier, pas des conclusions.";

    var syn = el("section", "an-block an-synth");
    syn.appendChild(el("h2", null, "Synthèse"));
    var p = el("p"); citeText(p, an.synthese, src, order); syn.appendChild(p);
    body.appendChild(syn);

    var grid = el("section", "an-axes");
    (an.axes || []).forEach(function (ax) {
      var card = el("article", "an-axis");
      card.style.borderTopColor = AXES[ax.axe] ? AXES[ax.axe].color : "var(--line)";
      var h = el("h3"); h.appendChild(el("span", "axis-tag", ax.axe));
      h.appendChild(document.createTextNode(" " + (AXES[ax.axe] ? AXES[ax.axe].label : "")));
      card.appendChild(h);
      card.appendChild(el("p", "trend trend-" + ax.tendance, TREND[ax.tendance] || ax.tendance || ""));
      var r = el("p"); citeText(r, ax.resume, src, order); card.appendChild(r);
      if (ax.faits && ax.faits.length) {
        card.appendChild(el("h4", null, "Faits"));
        var ul = el("ul");
        ax.faits.forEach(function (f) { var li = el("li"); citeText(li, f.texte, src, order); citeIds(li, f.ids, src, order); ul.appendChild(li); });
        card.appendChild(ul);
      }
      if (ax.signaux_faibles && ax.signaux_faibles.length) {
        card.appendChild(el("h4", null, "Signaux faibles"));
        var ul2 = el("ul");
        ax.signaux_faibles.forEach(function (f) { var li = el("li"); citeText(li, f.texte, src, order); citeIds(li, f.ids, src, order); ul2.appendChild(li); });
        card.appendChild(ul2);
      }
      var ro = el("dl", "ro");
      ro.appendChild(el("dt", null, "Risque")); ro.appendChild(el("dd", null, ax.risque || "Aucun identifié"));
      ro.appendChild(el("dt", null, "Opportunité")); ro.appendChild(el("dd", null, ax.opportunite || "Aucune identifiée"));
      card.appendChild(ro);
      grid.appendChild(card);
    });
    body.appendChild(grid);

    // matrice de priorité : probabilité x impact
    var mat = el("section", "an-block");
    mat.appendChild(el("h2", null, "Matrice de priorité"));
    mat.appendChild(el("p", "lead", "Chaque sujet est placé selon sa probabilité et son impact pour Tie Break. En haut à droite : à traiter en premier."));
    var m = el("div", "matrix");
    var cells = {};
    for (var imp = 3; imp >= 1; imp--) {
      var lab = el("div", "mx-ylab", ["", "Impact faible", "Impact moyen", "Impact fort"][imp]); m.appendChild(lab);
      for (var pr = 1; pr <= 3; pr++) {
        var c = el("div", "mx-cell mx-" + (imp + pr)); cells[imp + "-" + pr] = c; m.appendChild(c);
      }
    }
    m.appendChild(el("div"));
    ["Probabilité faible", "Probabilité moyenne", "Probabilité forte"].forEach(function (l) { m.appendChild(el("div", "mx-xlab", l)); });
    (an.priorites || []).forEach(function (pz) {
      var key = Math.max(1, Math.min(3, pz.impact | 0)) + "-" + Math.max(1, Math.min(3, pz.probabilite | 0));
      var tag = el("div", "mx-item");
      var code = el("span", "axis-tag", pz.axe + " "); code.style.color = AXES[pz.axe] ? AXES[pz.axe].color : "inherit";
      tag.appendChild(code); tag.appendChild(document.createTextNode(pz.sujet));
      tag.title = pz.justification || "";
      if (cells[key]) cells[key].appendChild(tag);
    });
    mat.appendChild(m);
    body.appendChild(mat);

    if (an.recommandations && an.recommandations.length) {
      var rec = el("section", "an-block");
      rec.appendChild(el("h2", null, "Recommandations"));
      var tb = el("table", "refs");
      var thr = el("tr"); ["Action", "Axe", "Horizon", "Pour"].forEach(function (x) { thr.appendChild(el("th", null, x)); });
      var th = el("thead"); th.appendChild(thr); tb.appendChild(th);
      var tbody = el("tbody");
      an.recommandations.forEach(function (rc) {
        var tr = el("tr");
        tr.appendChild(el("td", null, rc.action));
        var ax = el("td", "axis-tag", rc.axe); ax.style.color = AXES[rc.axe] ? AXES[rc.axe].color : "inherit"; tr.appendChild(ax);
        tr.appendChild(el("td", null, rc.horizon)); tr.appendChild(el("td", null, rc.destinataire));
        tbody.appendChild(tr);
      });
      tb.appendChild(tbody);
      var wrap = el("div", "table-scroll"); wrap.appendChild(tb); rec.appendChild(wrap);
      body.appendChild(rec);
    }

    if (an.a_verifier && an.a_verifier.length) {
      var av = el("section", "an-block");
      av.appendChild(el("h2", null, "À vérifier avant d'utiliser dans le dossier"));
      var ul3 = el("ul");
      an.a_verifier.forEach(function (x) { var li = el("li"); citeText(li, x, src, order); ul3.appendChild(li); });
      av.appendChild(ul3); body.appendChild(av);
    }

    if (order.length) {
      var sl = el("section", "an-block");
      sl.appendChild(el("h2", null, "Articles cités"));
      var ol = el("ol", "an-sources");
      order.forEach(function (id) {
        var s2 = src[id]; var li = el("li");
        var a = el("a", null, s2.title); a.href = s2.url; a.target = "_blank"; a.rel = "noopener";
        li.appendChild(a);
        li.appendChild(el("span", "item-source", " " + s2.source + ", " + fmtRefDate(s2.date) + ", fiabilité " + s2.reliability));
        ol.appendChild(li);
      });
      sl.appendChild(ol); body.appendChild(sl);
    }
  }

  function loadAnalyses() {
    getJSON("data/analyses/index.json").then(function (idx) {
      var list = idx.analyses || [];
      if (!list.length) throw new Error("vide");
      var pick = $("#an-pick");
      pick.innerHTML = "";
      list.forEach(function (a) { var o = el("option", null, fmtRefDate(a.date)); o.value = a.file; pick.appendChild(o); });
      $("#an-pick-wrap").hidden = list.length < 2;
      pick.onchange = function () { getJSON("data/analyses/" + pick.value).then(renderAnalysis); };
      return getJSON("data/analyses/" + list[0].file).then(renderAnalysis);
    }).catch(function () {
      $("#an-meta").textContent = "Aucune analyse pour le moment.";
      var b = $("#an-body"); b.innerHTML = "";
      b.appendChild(el("p", "empty", "Les analyses apparaîtront ici dès que la clé de l'API Claude sera ajoutée au dépôt GitHub (secret ANTHROPIC_API_KEY). La première analyse est rédigée à la collecte suivante, puis une fois par jour."));
    });
  }
  loadAnalyses();

  // ---------- CSV export ----------
  function csvCell(v) { v = v == null ? "" : String(v); return '"' + v.replace(/"/g, '""') + '"'; }
  $("#export").addEventListener("click", function () {
    var list = keptList();
    var fromKept = list.length > 0;
    if (!fromKept) list = filtered();
    var rows = [["Date", "Axe", "Intitulé de l'axe", "Fiabilité", "Pertinence (Claude)", "Titre", "Source", "Lien", "Mots-signaux", "Impact estimé par Claude", "Note personnelle"]];
    list.forEach(function (it) {
      rows.push([fmtDate(it._t), it.axis, AXES[it.axis] ? AXES[it.axis].label : "", it.reliability, it.ai ? it.ai.r : "", it.title, it.source, it.url,
        (it.signals || []).join(", "), it.ai ? it.ai.impact : "", fromKept && kept[it.id] ? kept[it.id].note : ""]);
    });
    var csv = "﻿" + rows.map(function (r) { return r.map(csvCell).join(";"); }).join("\r\n");
    var blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (fromKept ? "veille-tiebreak-retenus-" : "veille-tiebreak-fil-") + new Date().toISOString().slice(0, 10) + ".csv";
    document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  });
})();
