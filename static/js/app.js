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

/* install-as-app banner (dashboards). Shown on phones/tablets until installed or dismissed. */
(function () {
  "use strict";
  var bar = document.getElementById("installBanner");
  if (!bar) return;
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register(bar.getAttribute("data-sw"), { scope: bar.getAttribute("data-scope") }).catch(function () {});
  }
  var standalone = (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) || window.navigator.standalone;
  var key = "installDismissed:" + bar.getAttribute("data-scope");
  var dismissed = false;
  try { dismissed = Number(localStorage.getItem(key) || 0) > Date.now(); } catch (e) {}
  var ua = navigator.userAgent || "";
  var touch = (navigator.maxTouchPoints || 0) > 0 || /Android|iPhone|iPad|Mobile/i.test(ua);
  if (standalone || dismissed || !touch) return;

  var ios = /iPhone|iPad|iPod/i.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  function hint(which) {
    bar.querySelectorAll("[data-install-hint]").forEach(function (h) { h.hidden = h.getAttribute("data-install-hint") !== which; });
  }
  var deferred = null, go = bar.querySelector("[data-install-go]");
  if (ios) { hint("ios"); bar.hidden = false; }
  else {
    window.addEventListener("beforeinstallprompt", function (e) {
      e.preventDefault(); deferred = e; hint("prompt"); go.hidden = false; bar.hidden = false;
    });
    /* browsers without an install prompt (e.g. Firefox): show the menu instructions instead */
    setTimeout(function () { if (!deferred) { hint("other"); bar.hidden = false; } }, 2500);
  }
  go.addEventListener("click", function () {
    if (!deferred) return;
    deferred.prompt();
    deferred.userChoice.then(function () { deferred = null; bar.hidden = true; });
  });
  window.addEventListener("appinstalled", function () { bar.hidden = true; });
  bar.querySelector("[data-install-close]").addEventListener("click", function () {
    bar.hidden = true;
    try { localStorage.setItem(key, String(Date.now() + 14 * 864e5)); } catch (e) {}   /* ask again in 2 weeks */
  });
})();

/* long review text: clamp to 4 lines with a "Read more" toggle */
(function () {
  document.querySelectorAll(".review__body").forEach(function (p) {
    p.classList.add("is-clamped");
    if (p.scrollHeight <= p.clientHeight + 2) { p.classList.remove("is-clamped"); return; }
    var b = document.createElement("button");
    b.type = "button"; b.className = "review__more"; b.textContent = "Read more";
    b.addEventListener("click", function () {
      var open = p.classList.toggle("is-clamped") === false;
      b.textContent = open ? "Show less" : "Read more";
    });
    p.insertAdjacentElement("afterend", b);
  });
})();

/* dashboard home: cycle tips */
(function () {
  var card = document.querySelector(".tip[data-tips]");
  if (!card) return;
  var tips = JSON.parse(card.getAttribute("data-tips")), i = Number(card.getAttribute("data-start")) || 0;
  card.querySelector(".tip__next").addEventListener("click", function () {
    i = (i + 1) % tips.length;
    card.querySelector(".tip__text").textContent = tips[i];
  });
})();

/* posts: share with photos (phone share sheet), copy text */
(function () {
  function copy(btn, text) {
    (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () {
      var t = btn.textContent; btn.textContent = "Copied ✓"; setTimeout(function () { btn.textContent = t; }, 1600);
    }, function () { window.prompt("Copy this:", text); });
  }
  document.querySelectorAll("[data-copy-text]").forEach(function (b) {
    b.addEventListener("click", function () { copy(b, b.getAttribute("data-copy-text")); });
  });
  document.querySelectorAll("[data-share]").forEach(function (b) {
    b.addEventListener("click", function () {
      var url = b.getAttribute("data-url"), text = b.getAttribute("data-text");
      var photos = JSON.parse(b.getAttribute("data-photos") || "[]");
      var full = text + (url ? "\n\n" + url : "");
      if (!navigator.share) { copy(b, full); return; }
      b.disabled = true;
      Promise.all(photos.slice(0, 6).map(function (src, i) {
        return fetch(src).then(function (r) { return r.blob(); }).then(function (bl) {
          return new File([bl], "photo-" + (i + 1) + "." + ((bl.type.split("/")[1] || "jpg").replace("jpeg", "jpg")), { type: bl.type || "image/jpeg" });
        });
      })).catch(function () { return []; }).then(function (files) {
        var data = { title: text.split("\n")[0], text: full };
        if (files.length && navigator.canShare && navigator.canShare({ files: files })) data.files = files;
        else if (url) { data.text = text; data.url = url; }
        return navigator.share(data);
      }).catch(function () {}).then(function () { b.disabled = false; });
    });
  });
})();
