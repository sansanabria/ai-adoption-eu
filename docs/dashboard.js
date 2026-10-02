// Tooltips for chart marks, and linked highlighting between the country map and the ranked list.
// Every value a tooltip shows is also printed on the page; tooltips only add rank and detail.
(function () {
  "use strict";

  var tip = document.createElement("div");
  tip.className = "tooltip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = true;
  var valueEl = document.createElement("strong");
  valueEl.className = "tip-value";
  var labelEl = document.createElement("span");
  labelEl.className = "tip-label";
  var noteEl = document.createElement("span");
  noteEl.className = "tip-note";
  tip.append(valueEl, labelEl, noteEl);
  document.body.appendChild(tip);

  var current = null;

  function markLinked(el, on) {
    var code = el.getAttribute("data-code");
    if (!code) return;
    var selector = '[data-code="' + CSS.escape(code) + '"]';
    document.querySelectorAll(selector).forEach(function (node) {
      node.classList.toggle("is-active", on);
    });
  }

  function place(x, y) {
    var gap = 14;
    var width = tip.offsetWidth;
    var height = tip.offsetHeight;
    var left = x + gap;
    var top = y + gap;
    if (left + width > window.innerWidth - 8) left = x - width - gap;
    if (top + height > window.innerHeight - 8) top = y - height - gap;
    left = Math.min(left, window.innerWidth - width - 8);
    top = Math.min(top, window.innerHeight - height - 8);
    tip.style.transform = "translate(" + Math.max(8, left) + "px," + Math.max(8, top) + "px)";
  }

  function show(el, x, y) {
    if (current && current !== el) markLinked(current, false);
    current = el;
    valueEl.textContent = el.getAttribute("data-tip-value") || "";
    labelEl.textContent = el.getAttribute("data-tip-label") || "";
    noteEl.textContent = el.getAttribute("data-tip-note") || "";
    noteEl.hidden = !noteEl.textContent;
    tip.hidden = false;
    markLinked(el, true);
    if (x === undefined) {
      var box = el.getBoundingClientRect();
      x = box.left + box.width / 2;
      y = box.top;
    }
    place(x, y);
  }

  function hide() {
    if (current) markLinked(current, false);
    current = null;
    tip.hidden = true;
  }

  function markFrom(event) {
    return event.target instanceof Element ? event.target.closest("[data-tip-value]") : null;
  }

  document.addEventListener("pointerover", function (event) {
    if (event.pointerType === "touch") return;
    var el = markFrom(event);
    if (el) show(el, event.clientX, event.clientY);
  });

  document.addEventListener("pointermove", function (event) {
    if (current && event.pointerType !== "touch" && markFrom(event) === current) place(event.clientX, event.clientY);
  });

  document.addEventListener("pointerout", function (event) {
    var el = markFrom(event);
    var stillInside = event.relatedTarget instanceof Node && el && el.contains(event.relatedTarget);
    if (el && el === current && !stillInside) hide();
  });

  // Touch has no hover: a tap shows a mark's details, a tap anywhere else hides them.
  document.addEventListener("click", function (event) {
    var el = markFrom(event);
    if (el && el !== current) show(el);
    else if (!el) hide();
  });

  document.addEventListener("focusin", function (event) {
    var el = markFrom(event);
    if (el) show(el);
  });

  document.addEventListener("focusout", function (event) {
    if (markFrom(event) === current) hide();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") hide();
  });

  window.addEventListener("scroll", function () {
    if (!current) return;
    if (document.activeElement === current) show(current);
    else hide();
  }, { passive: true });
})();
