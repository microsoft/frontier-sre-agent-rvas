/* =====================================================================
   SCENARIO EXPLORER — render, search, filter, and detail drawer logic.
   Depends on scenarios-data.js, scenario-skills-data.js and skill-library.js.
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
  if (typeof SCENARIO_SKILLS === "undefined" || !window.SkillLibrary) {
    resultsCount.textContent = "The skill catalog could not be loaded. Rebuild the website or reload the page.";
    resultsCount.setAttribute("role", "alert");
    return;
  }

  var categoryBySlug = {};
  var categoryOrder = {};
  (SCENARIO_CATEGORIES || []).forEach(function (c, index) {
    categoryBySlug[c.slug] = c;
    categoryOrder[c.slug] = index;
  });
  var orderedScenarios = SCENARIOS.slice().sort(function (a, b) {
    return categoryOrder[a.category] - categoryOrder[b.category];
  });
  var stats = {
    total: SCENARIOS.length,
    areas: new Set(SCENARIOS.map(function (s) { return s.category; })).size,
    quickWins: SCENARIOS.filter(function (s) { return s.topPick; }).length,
    modes: new Set(SCENARIOS.map(function (s) { return s.mode; })).size
  };
  document.querySelectorAll("[data-scenario-stat]").forEach(function (node) {
    var count = stats[node.dataset.scenarioStat];
    node.textContent = String(count);
    node.setAttribute("data-count", String(count));
  });
  var skillById = {};
  SCENARIO_SKILLS.forEach(function (skill) { skillById[skill.id] = skill; });

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

  function savingsBadge(scenario, detail) {
    if (scenario.timeSaved === "Not estimated") return "";
    var label = scenario.timeSaved + (detail ? " time savings" : " savings");
    var explanation = "Operator time savings, not Azure bill savings.";
    if (scenario.timeSavedEstimate) {
      if (detail) label += " (estimated)";
      explanation += " " + scenario.timeSavedEstimate + " Not measured or guaranteed.";
    }
    return '<span class="scenario-badge ' + timeBadgeClass(scenario.timeSaved) +
      '" title="' + escapeHtml(explanation).replace(/"/g, "&quot;") + '">' + escapeHtml(label) + '</span>';
  }

  /* ── Filtering ───────────────────────────────────────────────────── */
  function matches(scenario) {
    if (state.category && scenario.category !== state.category) return false;
    if (state.mode && scenario.mode !== state.mode) return false;
    if (state.topPickOnly && !scenario.topPick) return false;
    if (state.query) {
      var skillText = (scenario.skills || []).map(function (id) {
        var skill = skillById[id];
        return skill ? skill.id + " " + skill.title + " " + skill.description + " " + skill.categoryLabel : id;
      }).join(" ");
      var haystack = (scenario.title + " " + scenario.description + " " + scenario.samplePrompt + " " + skillText).toLowerCase();
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
      savingsBadge(scenario, false) +
      '<span class="scenario-badge">' + (scenario.skills || []).length + ' skill(s)</span>' +
      '</div>';
    card.addEventListener("click", function () { openDrawer(scenario); });
    return card;
  }

  function render() {
    var filtered = orderedScenarios.filter(matches);
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
  var drawerSavingsNote = document.getElementById("scenario-drawer-savings-note");
  var drawerDesc = document.getElementById("scenario-drawer-desc");
  var drawerPrompt = document.getElementById("scenario-drawer-prompt");
  var drawerFrequency = document.getElementById("scenario-drawer-frequency");
  var drawerClose = document.getElementById("scenario-drawer-close");
  var copyBtn = document.getElementById("scenario-copy-btn");
  var copyStatus = document.getElementById("scenario-copy-status");
  var drawerSkills = document.getElementById("scenario-drawer-skills");
  var background = document.querySelectorAll("body > header, body > main, body > footer");
  var currentScenario = null;
  var previousFocus = null;
  var previousOverflow = "";

  function renderSkills(scenario) {
    drawerSkills.textContent = "";
    var ids = scenario.skills || [];
    if (!ids.length) {
      drawerSkills.appendChild(SkillLibrary.element("p", "scenario-action-status", "No skill has been mapped to this scenario."));
    }
    ids.forEach(function (id) {
      var skill = skillById[id];
      if (!skill) {
        var error = SkillLibrary.element("p", "scenario-action-status", "Mapped skill unavailable: " + id + ". Rebuild the skill catalog.");
        error.setAttribute("role", "alert");
        drawerSkills.appendChild(error);
        return;
      }
      drawerSkills.appendChild(SkillLibrary.createCard(skill));
    });
  }

  function openDrawer(scenario) {
    if (!drawer.classList.contains("open")) {
      previousFocus = document.activeElement;
      previousOverflow = document.body.style.overflow;
    }
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
      savingsBadge(scenario, true);
    drawerSavingsNote.hidden = !scenario.timeSavedEstimate;
    drawerSavingsNote.textContent = scenario.timeSavedEstimate
      ? "Estimated operator time savings: " + scenario.timeSavedEstimate +
        " Not measured or guaranteed. Actual savings depend on evidence readiness and investigation complexity. This is not an estimate of Azure bill reductions."
      : "";
    copyBtn.textContent = "Copy prompt";
    copyStatus.textContent = "";
    renderSkills(scenario);
    drawer.inert = false;
    drawer.setAttribute("aria-hidden", "false");
    background.forEach(function (node) { node.inert = true; });
    document.body.style.overflow = "hidden";
    drawer.classList.add("open");
    drawerOverlay.classList.add("open");
    drawer.querySelector(".drawer-body").scrollTop = 0;
    drawerClose.focus();
  }

  function closeDrawer() {
    drawer.classList.remove("open");
    drawerOverlay.classList.remove("open");
    drawer.inert = true;
    drawer.setAttribute("aria-hidden", "true");
    background.forEach(function (node) { node.inert = false; });
    document.body.style.overflow = previousOverflow;
    if (previousFocus && previousFocus.isConnected) previousFocus.focus();
    currentScenario = null;
  }

  drawerClose.addEventListener("click", closeDrawer);
  drawerOverlay.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && drawer.classList.contains("open")) closeDrawer();
    if (e.key === "Tab" && drawer.classList.contains("open")) {
      var controls = Array.from(drawer.querySelectorAll("button:not(:disabled), a[href], summary, [tabindex='0']"))
        .filter(function (node) { return node.offsetParent !== null; });
      var first = controls[0];
      var last = controls[controls.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  });

  copyBtn.addEventListener("click", function () {
    if (!currentScenario) return;
    var scenario = currentScenario;
    SkillLibrary.copyWithFeedback(scenario.samplePrompt, copyBtn, copyStatus, "Sample prompt copied.",
      function () { return currentScenario === scenario; });
  });

  render();
})();
