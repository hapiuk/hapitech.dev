/* HapiTech dashboards (/admin, /portal). No dependencies. */
(function () {
  "use strict";
  var root = document.documentElement;
  var body = document.body;

  /* theme */
  var themeBtn = document.getElementById("themeToggle");
  function applyTheme(t) {
    root.setAttribute("data-theme", t);
    if (themeBtn) themeBtn.setAttribute("aria-label", t === "light" ? "Switch to dark theme" : "Switch to light theme");
  }
  applyTheme(root.getAttribute("data-theme") === "light" ? "light" : "dark");
  if (themeBtn) themeBtn.addEventListener("click", function () {
    var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
    applyTheme(next);
    try { localStorage.setItem("theme", next); } catch (e) {}
  });

  /* off-canvas side nav (phones) */
  document.querySelectorAll("[data-side-open]").forEach(function (b) {
    b.addEventListener("click", function () { body.classList.add("side-open"); });
  });
  document.querySelectorAll("[data-side-close]").forEach(function (b) {
    b.addEventListener("click", function () { body.classList.remove("side-open"); });
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") body.classList.remove("side-open"); });

  /* confirm before destructive submits: <button data-confirm="Delete this job?"> */
  document.addEventListener("click", function (e) {
    var el = e.target.closest("[data-confirm]");
    if (el && !window.confirm(el.getAttribute("data-confirm"))) { e.preventDefault(); e.stopPropagation(); }
  }, true);

  /* every non-GET form gets the CSRF token if the template forgot it */
  var token = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  document.querySelectorAll("form").forEach(function (f) {
    if ((f.getAttribute("method") || "get").toLowerCase() === "post" && !f.querySelector('input[name="csrf_token"]')) {
      var i = document.createElement("input");
      i.type = "hidden"; i.name = "csrf_token"; i.value = token; f.appendChild(i);
    }
  });
  window.HT = {
    csrf: token,
    post: function (url, data) {
      return fetch(url, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        body: JSON.stringify(data || {})
      }).then(function (r) { return r.json().catch(function () { return { ok: false }; }); });
    }
  };

  /* copy buttons: <button data-copy="#inputId"> */
  document.querySelectorAll("[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () {
      var src = document.querySelector(b.getAttribute("data-copy"));
      if (!src) return;
      var text = src.value || src.textContent;
      var done = function () { var t = b.textContent; b.textContent = "Copied"; setTimeout(function () { b.textContent = t; }, 1500); };
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () { src.select && src.select(); });
      else { src.select && src.select(); try { document.execCommand("copy"); done(); } catch (e) {} }
    });
  });

  /* auto-submit selects: <select data-autosubmit> */
  document.querySelectorAll("select[data-autosubmit]").forEach(function (s) {
    s.addEventListener("change", function () { s.form.submit(); });
  });
})();
