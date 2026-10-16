(function () {
  "use strict";

  var AXES = {
    E1: { label: "Nike et la puissance américaine", kind: "Géopolitique : guerre commerciale, boycotts", color: "var(--e1)" },
    E2: { label: "Production et routes d'approvisionnement", kind: "Géopolitique : Asie, droits de douane, mer Rouge", color: "var(--e2)" },
    E3: { label: "Athlètes Nike et nouvelle géographie du tennis", kind: "Géopolitique : Arabie saoudite, sportswashing", color: "var(--e3)" },
    T4: { label: "Performances et polémiques des joueurs", kind: "Tendance sportive", color: "var(--t4)" },
    T5: { label: "Distribution Nike et marché du tennis", kind: "Tendance commerciale", color: "var(--t5)" }
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
        row.n++; row[it.reliability] = (row[it.reliability] || 0) + 1;
        if (it.signals && it.signals.length) row.hot++;
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
      if (state.hot && !(it.signals && it.signals.length)) return false;
      if (state.q && norm(it.title + " " + it.source).indexOf(state.q) === -1) return false;
      return true;
    });
    list.sort(state.sort === "score"
      ? function (a, b) { return (b.score - a.score) || (b._t - a._t); }
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
    ["feed", "kept", "refs", "method"].forEach(function (name) { $("#view-" + name).hidden = name !== v; });
  }
  Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (t) {
    t.addEventListener("click", function () { showView(t.getAttribute("data-view")); });
  });

  // ---------- CSV export ----------
  function csvCell(v) { v = v == null ? "" : String(v); return '"' + v.replace(/"/g, '""') + '"'; }
  $("#export").addEventListener("click", function () {
    var list = keptList();
    var fromKept = list.length > 0;
    if (!fromKept) list = filtered();
    var rows = [["Date", "Axe", "Intitulé de l'axe", "Fiabilité", "Titre", "Source", "Lien", "Mots-signaux", "Note (impact pour Tie Break)"]];
    list.forEach(function (it) {
      rows.push([fmtDate(it._t), it.axis, AXES[it.axis] ? AXES[it.axis].label : "", it.reliability, it.title, it.source, it.url,
        (it.signals || []).join(", "), fromKept && kept[it.id] ? kept[it.id].note : ""]);
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
