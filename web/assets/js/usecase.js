/* =====================================================================
   USE CASE PAGE — documentation, requirements and download for one use
   case. Data comes from usecases.json; the guide is usecases/<id>/README.md.
   ===================================================================== */
(function () {
  "use strict";

  var REPO_BLOB = "https://github.com/microsoft/frontier-sre-agent-rvas/blob/main/";
  var REPO_TREE = "https://github.com/microsoft/frontier-sre-agent-rvas/tree/main/";
  var TRIGGER_LABELS = { schedule: "Scheduled", chat: "On-demand", alert: "Event-driven" };
  var AUTONOMY_LABELS = { "read-only": "Read-only", approval: "Needs approval", autonomous: "Autonomous" };
  var STATUS_LABELS = { idea: "Idea", draft: "Draft", built: "Built", validated: "Validated" };
  var CONTENT_LABELS = {
    skills: "Skills", subagents: "Subagents", tools: "Tools",
    scheduledTasks: "Scheduled tasks", permissions: "Permission scripts"
  };

  function $(id) { return document.getElementById(id); }
  function el(tag, text, cls) {
    var n = document.createElement(tag);
    if (text != null) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  }
  function badge(text, cls) { return el("span", text, "scenario-badge " + (cls || "scenario-badge-mode")); }

  function fail(message) {
    var box = $("uc-error");
    box.textContent = message;
    box.hidden = false;
  }

  var id = new URLSearchParams(location.search).get("id");
  if (!id) { fail("No use case selected. Pick one from the Scenario Explorer."); return; }

  fetch("usecases.json", { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (data) {
      var uc = (data.usecases || []).filter(function (u) { return u.id === id; })[0];
      if (!uc) { fail("Use case \"" + id + "\" was not found."); return; }
      if (!uc.page) {
        location.replace("scenarios.html#explorer");
        return;
      }
      render(uc, data);
    })
    .catch(function () { fail("The use case could not be loaded. Try again later."); });

  function render(uc, data) {
    var domain = (data.domains || []).filter(function (d) { return d.slug === uc.domain; })[0] || { label: uc.domain };
    document.title = uc.title + " — Azure SRE Agent — RVAS";
    $("uc-category").textContent = domain.label;
    $("uc-title").textContent = uc.title;
    $("uc-summary").textContent = uc.summary;
    $("uc-github").href = REPO_TREE + uc.path;

    var badges = $("uc-badges");
    badges.appendChild(badge(STATUS_LABELS[uc.status] || uc.status));
    if (uc.autonomy) badges.appendChild(badge(AUTONOMY_LABELS[uc.autonomy] || uc.autonomy));
    badges.appendChild(badge((uc.trigger || []).map(function (t) { return TRIGGER_LABELS[t] || t; }).join(" + ")));
    if (uc.timeSaved) badges.appendChild(badge(uc.timeSaved + " time savings"));
    $("uc-head").hidden = false;

    if (uc.download) {
      var file = uc.download.url.split("/").pop();
      var dl = $("uc-download");
      dl.href = uc.download.url;
      dl.hidden = false;
      var v = $("uc-version");
      v.textContent = "v" + uc.download.version + " · " + file;
      v.hidden = false;
      $("uc-sha-cmd").textContent = "sha256sum -c " + file + ".sha256";
      var sha = el("a", "Checksum", "uc-sha-link");
      sha.href = uc.download.sha256Url;
      v.appendChild(document.createTextNode(" · "));
      v.appendChild(sha);
      $("uc-install").hidden = false;
    }

    renderSide(uc);
    renderGuide(uc);
    $("uc-body").hidden = false;
  }

  function renderSide(uc) {
    var pkg = uc.package || {};

    if (uc.samplePrompt) {
      $("uc-prompt").textContent = uc.samplePrompt;
      $("uc-prompt-card").hidden = false;
      var btn = $("uc-copy");
      btn.addEventListener("click", function () {
        function done() {
          btn.textContent = "Copied ✓";
          btn.classList.add("copied");
          setTimeout(function () { btn.textContent = "Copy prompt"; btn.classList.remove("copied"); }, 1800);
        }
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(uc.samplePrompt).then(done);
      });
    }

    var contents = $("uc-contents");
    var listed = pkg.contents || {};
    var keys = Object.keys(CONTENT_LABELS).filter(function (k) { return (listed[k] || []).length; });
    if (keys.length) {
      keys.forEach(function (k) { contents.appendChild(el("li", listed[k].length + " × " + CONTENT_LABELS[k])); });
    } else {
      var c = uc.components || {};
      [["skill", "Skill"], ["subagent", "Subagent"], ["tool", "Tool"], ["task", "Scheduled task"],
       ["permissions", "Permission script"], ["tests", "Tests"], ["sampleReport", "Sample report"]]
        .filter(function (p) { return c[p[0]]; })
        .forEach(function (p) { contents.appendChild(el("li", p[1])); });
      if (!contents.children.length) contents.appendChild(el("li", "Documentation only"));
    }

    var roles = (pkg.requires && pkg.requires.roles) || [];
    var connectors = (pkg.requires && pkg.requires.connectors) || [];
    var reqs = $("uc-requires");
    roles.forEach(function (r) { reqs.appendChild(el("li", r)); });
    connectors.forEach(function (r) { reqs.appendChild(el("li", "Connector: " + r)); });
    $("uc-requires-card").hidden = !reqs.children.length;

    var params = pkg.parameters || {};
    var dl = $("uc-params");
    Object.keys(params).forEach(function (k) {
      dl.appendChild(el("dt", k, "mono"));
      dl.appendChild(el("dd", params[k]));
    });
    $("uc-params-card").hidden = !Object.keys(params).length;

    var meta = $("uc-meta");
    function row(label, value) {
      if (!value) return;
      var d = el("div");
      d.appendChild(el("dt", label));
      d.appendChild(el("dd", value));
      meta.appendChild(d);
    }
    row("Frequency", uc.frequency);
    row("Products", (uc.products || []).join(", "));
    row("API version", pkg.apiVersion);
    row("Package version", pkg.version);
  }

  function renderGuide(uc) {
    var base = "usecases/" + uc.id + "/";
    fetch(base + "README.md", { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.text(); })
      .then(function (text) {
        var box = $("uc-markdown");
        box.innerHTML = marked.parse(text);
        // The page's own title and summary replace the guide's first heading.
        var h1 = box.querySelector("h1");
        if (h1) h1.remove();
        box.querySelectorAll("img").forEach(function (img) {
          var src = img.getAttribute("src") || "";
          if (!/^(https?:|data:|\/)/.test(src)) img.setAttribute("src", base + src);
          img.loading = "lazy";
        });
        // Files that are not published on the site open on GitHub.
        box.querySelectorAll("a[href]").forEach(function (a) {
          var href = a.getAttribute("href");
          if (/^(https?:|mailto:|#)/.test(href)) { if (!href.startsWith("#")) { a.target = "_blank"; a.rel = "noopener"; } return; }
          a.href = REPO_BLOB + uc.path + "/" + href.replace(/^\.\//, "");
          a.target = "_blank";
          a.rel = "noopener";
        });
      })
      .catch(function () {
        $("uc-markdown").textContent = "The guide could not be loaded. Open the use case on GitHub instead.";
      });
  }
})();
