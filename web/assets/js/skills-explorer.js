(function () {
  "use strict";

  var grid = document.getElementById("skills-grid");
  var results = document.getElementById("skills-results-count");
  var search = document.getElementById("skills-search-input");
  var chips = document.getElementById("skills-category-chips");
  var empty = document.getElementById("skills-empty");
  if (!grid) return;
  if (typeof SCENARIO_SKILLS === "undefined" || !window.SkillLibrary) {
    results.textContent = "The skill library could not be loaded. Rebuild the website or reload the page.";
    results.setAttribute("role", "alert");
    return;
  }

  var category = "";
  var query = "";
  var categories = new Map();
  SCENARIO_SKILLS.forEach(function (skill) {
    if (!categories.has(skill.category)) {
      categories.set(skill.category, { label: skill.categoryLabel, count: 0 });
    }
    categories.get(skill.category).count++;
  });
  categories.forEach(function (info, id) {
    var chip = SkillLibrary.element("button", "scenario-chip", info.label + " (" + info.count + ")");
    chip.type = "button";
    chip.dataset.category = id;
    chip.setAttribute("aria-pressed", "false");
    chips.appendChild(chip);
  });
  document.getElementById("skills-total").textContent = SCENARIO_SKILLS.length;
  document.getElementById("skills-category-total").textContent = categories.size;

  function render() {
    var filtered = SCENARIO_SKILLS.filter(function (skill) {
      var text = (skill.id + " " + skill.title + " " + skill.description + " " + skill.categoryLabel).toLowerCase();
      return (!category || skill.category === category) && (!query || text.indexOf(query) !== -1);
    });
    var fragment = document.createDocumentFragment();
    filtered.forEach(function (skill) {
      fragment.appendChild(SkillLibrary.createCard(skill, "h2"));
    });
    grid.replaceChildren(fragment);
    results.textContent = filtered.length + " of " + SCENARIO_SKILLS.length + " skills";
    empty.hidden = filtered.length !== 0;
  }

  search.addEventListener("input", function () {
    query = search.value.trim().toLowerCase();
    render();
  });
  chips.addEventListener("click", function (event) {
    var chip = event.target.closest("button[data-category]");
    if (!chip || !chips.contains(chip)) return;
    category = chip.dataset.category;
    chips.querySelectorAll("button").forEach(function (button) {
      var active = button === chip;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    render();
  });
  render();
})();
