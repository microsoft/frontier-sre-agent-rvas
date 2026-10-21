/* Shared skill cards and clipboard feedback for the Skills and Scenario explorers. */
(function () {
  "use strict";

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function fallbackCopy(text, container) {
    var buffer = element("textarea");
    buffer.value = text;
    buffer.style.position = "fixed";
    buffer.style.opacity = "0";
    buffer.setAttribute("aria-label", "Clipboard copy buffer");
    container.appendChild(buffer);
    buffer.select();
    try {
      if (!document.execCommand("copy")) throw new Error("The browser rejected clipboard access.");
    } finally {
      buffer.remove();
    }
  }

  async function copyWithFeedback(text, button, status, success, isCurrent) {
    var current = function () {
      return button.isConnected && !button.closest("[inert]") && (!isCurrent || isCurrent());
    };
    button.disabled = true;
    status.textContent = "";
    try {
      var container = button.closest('[role="dialog"]') || document.body;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        try {
          await navigator.clipboard.writeText(text);
        } catch (clipboardError) {
          if (current()) fallbackCopy(text, container);
          else throw clipboardError;
        }
      } else {
        fallbackCopy(text, container);
      }
      if (current()) status.textContent = success;
    } catch (error) {
      console.error("Clipboard copy failed:", error);
      if (current()) {
        status.textContent = "Copy failed. Open View instructions or select the prompt and copy it manually.";
      }
    } finally {
      button.disabled = false;
      if (current()) button.focus();
    }
  }

  function createCard(skill, headingTag) {
    var card = element("article", "scenario-skill");
    card.dataset.skillId = skill.id;
    card.appendChild(element("span", "scenario-badge scenario-badge-mode", skill.categoryLabel));
    card.appendChild(element(headingTag || "h4", "scenario-skill-title", skill.title));
    card.appendChild(element("p", "scenario-skill-description", skill.description));
    var actions = element("div", "scenario-skill-actions");
    var copy = element("button", "scenario-copy-btn", "Copy instructions");
    copy.type = "button";
    copy.setAttribute("aria-label", "Copy instructions for " + skill.title);
    var status = element("p", "scenario-action-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    copy.addEventListener("click", function () {
      copyWithFeedback(skill.instructions, copy, status,
        "Instructions copied. Download the complete bundle for required supporting files.");
    });
    actions.appendChild(copy);
    var download = element("a", "scenario-skill-download", "Download complete bundle");
    download.href = skill.bundleUrl;
    download.setAttribute("download", skill.id + ".zip");
    download.setAttribute("aria-label", "Download complete bundle for " + skill.title);
    actions.appendChild(download);
    card.appendChild(actions);
    card.appendChild(status);
    var details = element("details", "scenario-skill-details");
    details.appendChild(element("summary", "", "View instructions"));
    var instructions = element("pre", "scenario-skill-instructions", skill.instructions);
    instructions.tabIndex = 0;
    instructions.setAttribute("aria-label", "Instructions for " + skill.title);
    details.appendChild(instructions);
    card.appendChild(details);
    return card;
  }

  window.SkillLibrary = { element: element, createCard: createCard, copyWithFeedback: copyWithFeedback };
})();
