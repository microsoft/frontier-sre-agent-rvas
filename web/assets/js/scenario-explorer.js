/* =====================================================================
   SCENARIO EXPLORER — render, search, filter, and detail drawer logic.
   Depends on SCENARIO_CATEGORIES / SCENARIOS from scenarios-data.js.
   ===================================================================== */
(function () {
  "use strict";

  var grid = document.getElementById("scenario-grid");
  var emptyState = document.getElementById("scenario-empty");
  var resultsCount = document.getElementById("scenario-results-count");
  var searchInput = document.getElementById("scenario-search-input");
  var modeFilter = document.getElementById("scenario-mode-filter");
  var topPickToggle = document.getElementById("scenario-toppick-toggle");
  var chipsContainer = document.getElementById("scenario-category-chips");

  if (!grid || typeof SCENARIOS === "undefined") return;

  var categoryBySlug = {};
  (SCENARIO_CATEGORIES || []).forEach(function (c) { categoryBySlug[c.slug] = c; });

  var state = { query: "", category: "", mode: "", topPickOnly: false };

  /* ── Build category filter chips ────────────────────────────────── */
  SCENARIO_CATEGORIES.forEach(function (cat) {
    var count = SCENARIOS.filter(function (s) { return s.category === cat.slug; }).length;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "scenario-chip";
    btn.dataset.category = cat.slug;
    btn.style.setProperty("--card-color", cat.color);
    btn.textContent = cat.label + " (" + count + ")";
    chipsContainer.appendChild(btn);
  });

  function timeBadgeClass(timeSaved) {
    var t = (timeSaved || "").toLowerCase();
    if (t === "high") return "scenario-badge-time-high";
    if (t === "medium") return "scenario-badge-time-medium";
    return "scenario-badge-time-low";
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str == null ? "" : str;
    return div.innerHTML;
  }

  /* ── Filtering ───────────────────────────────────────────────────── */
  function matches(scenario) {
    if (state.category && scenario.category !== state.category) return false;
    if (state.mode && scenario.mode !== state.mode) return false;
    if (state.topPickOnly && !scenario.topPick) return false;
    if (state.query) {
      var haystack = (scenario.title + " " + scenario.description + " " + scenario.samplePrompt).toLowerCase();
      if (haystack.indexOf(state.query) === -1) return false;
    }
    return true;
  }

  /* ── Rendering ───────────────────────────────────────────────────── */
  function renderCard(scenario) {
    var cat = categoryBySlug[scenario.category] || { label: scenario.category, color: "#1A77E3" };
    var card = document.createElement("button");
    card.type = "button";
    card.className = "scenario-card";
    card.style.setProperty("--card-color", cat.color);
    card.setAttribute("data-id", scenario.id);
    card.innerHTML =
      '<div class="scenario-card-top">' +
      '<span class="scenario-card-category">' + escapeHtml(cat.label) + '</span>' +
      (scenario.topPick ? '<span class="scenario-card-star" title="Quick win">★</span>' : "") +
      '</div>' +
      '<div class="scenario-card-title">' + escapeHtml(scenario.title) + '</div>' +
      '<div class="scenario-card-desc">' + escapeHtml(scenario.description) + '</div>' +
      '<div class="scenario-card-footer">' +
      '<span class="scenario-badge scenario-badge-mode">' + escapeHtml(scenario.mode) + '</span>' +
      '<span class="scenario-badge ' + timeBadgeClass(scenario.timeSaved) + '">' + escapeHtml(scenario.timeSaved) + ' savings</span>' +
      '</div>';
    card.addEventListener("click", function () { openDrawer(scenario); });
    return card;
  }

  function render() {
    var filtered = SCENARIOS.filter(matches);
    grid.innerHTML = "";
    var frag = document.createDocumentFragment();
    filtered.forEach(function (s) { frag.appendChild(renderCard(s)); });
    grid.appendChild(frag);
    emptyState.hidden = filtered.length !== 0;
    resultsCount.textContent = filtered.length + " of " + SCENARIOS.length + " scenarios";
  }

  /* ── Toolbar events ──────────────────────────────────────────────── */
  var searchDebounce;
  searchInput.addEventListener("input", function () {
    clearTimeout(searchDebounce);
    var val = searchInput.value;
    searchDebounce = setTimeout(function () {
      state.query = val.trim().toLowerCase();
      render();
    }, 120);
  });

  modeFilter.addEventListener("change", function () {
    state.mode = modeFilter.value;
    render();
  });

  topPickToggle.addEventListener("click", function () {
    state.topPickOnly = !state.topPickOnly;
    topPickToggle.classList.toggle("active", state.topPickOnly);
    topPickToggle.setAttribute("aria-pressed", String(state.topPickOnly));
    render();
  });

  chipsContainer.addEventListener("click", function (e) {
    var btn = e.target.closest(".scenario-chip");
    if (!btn) return;
    state.category = btn.dataset.category || "";
    chipsContainer.querySelectorAll(".scenario-chip").forEach(function (c) {
      c.classList.toggle("active", c === btn);
    });
    render();
  });

  /* ── Detail drawer ───────────────────────────────────────────────── */
  var drawer = document.getElementById("scenario-drawer");
  var drawerOverlay = document.getElementById("scenario-drawer-overlay");
  var drawerCategory = document.getElementById("scenario-drawer-category");
  var drawerTitle = document.getElementById("scenario-drawer-title");
  var drawerBadges = document.getElementById("scenario-drawer-badges");
  var drawerDesc = document.getElementById("scenario-drawer-desc");
  var drawerPrompt = document.getElementById("scenario-drawer-prompt");
  var drawerFrequency = document.getElementById("scenario-drawer-frequency");
  var drawerClose = document.getElementById("scenario-drawer-close");
  var copyBtn = document.getElementById("scenario-copy-btn");
  var currentScenario = null;

  function openDrawer(scenario) {
    currentScenario = scenario;
    var cat = categoryBySlug[scenario.category] || { label: scenario.category };
    drawerCategory.textContent = cat.label;
    drawerTitle.textContent = scenario.title;
    drawerDesc.textContent = scenario.description;
    drawerPrompt.textContent = scenario.samplePrompt;
    drawerFrequency.textContent = scenario.frequency || "—";
    drawerBadges.innerHTML =
      (scenario.topPick ? '<span class="scenario-badge scenario-card-star" style="color:#b45309;border-color:rgba(180,83,9,.3);background:rgba(180,83,9,.08);">★ Quick win</span>' : "") +
      '<span class="scenario-badge scenario-badge-mode">' + escapeHtml(scenario.mode) + '</span>' +
      '<span class="scenario-badge ' + timeBadgeClass(scenario.timeSaved) + '">' + escapeHtml(scenario.timeSaved) + ' time savings</span>';
    copyBtn.textContent = "Copy prompt";
    copyBtn.classList.remove("copied");
    drawer.classList.add("open");
    drawerOverlay.classList.add("open");
    drawer.querySelector(".drawer-body").scrollTop = 0;
  }

  function closeDrawer() {
    drawer.classList.remove("open");
    drawerOverlay.classList.remove("open");
  }

  drawerClose.addEventListener("click", closeDrawer);
  drawerOverlay.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && drawer.classList.contains("open")) closeDrawer();
  });

  copyBtn.addEventListener("click", function () {
    if (!currentScenario) return;
    var text = currentScenario.samplePrompt;
    function markCopied() {
      copyBtn.textContent = "Copied ✓";
      copyBtn.classList.add("copied");
      setTimeout(function () {
        copyBtn.textContent = "Copy prompt";
        copyBtn.classList.remove("copied");
      }, 1800);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(markCopied).catch(function () {
        fallbackCopy(text, markCopied);
      });
    } else {
      fallbackCopy(text, markCopied);
    }
  });

  function fallbackCopy(text, onDone) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (err) { /* no-op */ }
    document.body.removeChild(ta);
    onDone();
  }

  render();
})();
