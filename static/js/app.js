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

/* My website: edit cards in place, live character counts, find-as-you-type */
(function () {
  document.querySelectorAll(".site-card").forEach(function (card) {
    var view = card.querySelector(".site-card__view"), form = card.querySelector(".site-card__form");
    if (!form) return;
    var open = function (on) {
      form.hidden = !on; view.hidden = on; card.classList.toggle("is-editing", on);
      if (on) form.querySelectorAll("textarea").forEach(function (t) { t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight + 2, 420) + "px"; });
      if (on) { var f = form.querySelector("input,textarea"); if (f) { f.focus(); f.setSelectionRange(f.value.length, f.value.length); } }
    };
    card.querySelector("[data-site-edit]").addEventListener("click", function () { open(true); });
    form.querySelector("[data-site-cancel]").addEventListener("click", function () { form.reset(); open(false); });
    form.querySelectorAll("[data-counter-for]").forEach(function (c) {
      var f = form.querySelector('[name="' + c.getAttribute("data-counter-for") + '"]');
      var upd = function () { var left = f.maxLength - f.value.length; c.textContent = left + " characters left"; c.style.color = left < 20 ? "var(--warn,#f59e0b)" : ""; };
      f.addEventListener("input", upd); upd();
    });
    form.querySelectorAll("textarea").forEach(function (t) {
      var fit = function () { t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight + 2, 420) + "px"; };
      t.addEventListener("input", fit); setTimeout(fit, 0);
    });
  });
  var find = document.querySelector("[data-site-find]");
  if (find) find.addEventListener("input", function () {
    var q = find.value.trim().toLowerCase(), any = false;
    document.querySelectorAll(".edit-item").forEach(function (el) {
      var hit = !q || (el.getAttribute("data-find") || "").toLowerCase().indexOf(q) > -1;
      el.hidden = !hit; any = any || hit;
    });
    document.querySelectorAll(".site-section").forEach(function (s) { s.hidden = !s.querySelector(".edit-item:not([hidden])"); });
    var none = document.querySelector(".site-find__none"); if (none) none.hidden = any;
  });
})();

/* Settings → Dashboard look: brand / HapiTech colours, dark / light (saved on this device) */
(function () {
  var root = document.documentElement;
  function current(kind) { return root.getAttribute(kind === "accent" ? "data-accent" : "data-theme"); }
  function paint() {
    document.querySelectorAll("[data-look]").forEach(function (b) {
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", current(b.getAttribute("data-look")) === b.getAttribute("data-val") ? "true" : "false");
    });
  }
  document.querySelectorAll("[data-look]").forEach(function (b) {
    b.addEventListener("click", function () {
      var kind = b.getAttribute("data-look"), val = b.getAttribute("data-val");
      root.setAttribute(kind === "accent" ? "data-accent" : "data-theme", val);
      try { localStorage.setItem(kind, val); } catch (e) {}
      paint();
    });
  });
  paint();
})();

/* "Everyone" tick box */
document.querySelectorAll("[data-check-all]").forEach(function (all) {
  var boxes = all.closest("fieldset").querySelectorAll('input[name="to"]');
  var sync = function () { all.checked = Array.prototype.every.call(boxes, function (b) { return b.checked; }); };
  all.addEventListener("change", function () { boxes.forEach(function (b) { b.checked = all.checked; }); });
  boxes.forEach(function (b) { b.addEventListener("change", sync); }); sync();
});

/* Report an issue: remembers the previous dashboard page, sends page + device details */
(function () {
  var KEY = "lastPage", prev = null;
  try { prev = sessionStorage.getItem(KEY); sessionStorage.setItem(KEY, location.pathname + location.search); } catch (e) {}
  if (prev === location.pathname + location.search) prev = null;
  var dlg = document.getElementById("reportDialog"), open = document.querySelector("[data-report-open]");
  if (!dlg || !open) return;
  var form = dlg.querySelector("[data-report-form]"), msg = dlg.querySelector("[data-report-msg]");
  if (prev) dlg.querySelector("[data-report-before]").hidden = false;
  open.addEventListener("click", function () {
    msg.textContent = ""; form.reset();
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
    form.querySelector("textarea").focus();
  });
  dlg.querySelector("[data-report-close]").addEventListener("click", function () { dlg.close(); });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var btn = form.querySelector("button[type=submit]"); btn.disabled = true; msg.textContent = "Sending…";
    var token = (document.querySelector('meta[name="csrf-token"]') || {}).content;
    fetch("/portal/issue", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify({ what: form.what.value, on_before: form.on_before.checked, page: location.pathname + location.search,
        before: prev || "", device: navigator.userAgent, screen: screen.width + "x" + screen.height + " (window " + innerWidth + "x" + innerHeight + ")" }) })
      .then(function (r) { return r.json(); })
      .then(function (d) { msg.textContent = d.message || (d.ok ? "Sent." : "Something went wrong."); if (d.ok) setTimeout(function () { dlg.close(); }, 1800); })
      .catch(function () { msg.textContent = "Couldn't send. Please try again, or email aaron@hapitech.dev."; })
      .then(function () { btn.disabled = false; });
  });
})();

/* EN | LV switch: saved on this device, English by default */
(function () {
  var cur = "en"; try { cur = localStorage.getItem("lang") === "lv" ? "lv" : "en"; } catch (e) {}
  document.querySelectorAll("[data-lang]").forEach(function (b) {
    b.setAttribute("aria-pressed", b.getAttribute("data-lang") === cur ? "true" : "false");
    b.addEventListener("click", function () {
      var v = b.getAttribute("data-lang");
      if (v === cur) return;
      try { localStorage.setItem("lang", v); } catch (e) {}
      location.reload();
    });
  });
})();

/* My plan: filter the transaction history by month or text */
(function () {
  var list = document.querySelector("[data-txn-list]");
  if (!list) return;
  var month = document.querySelector("[data-txn-month]"), search = document.querySelector("[data-txn-search]");
  var none = document.querySelector(".txn__none");
  function apply() {
    var m = month.value, q = search.value.trim().toLowerCase(), any = false;
    list.querySelectorAll(".txn__item").forEach(function (li) {
      var hit = (!m || li.getAttribute("data-month") === m) && (!q || li.getAttribute("data-text").toLowerCase().indexOf(q) > -1);
      li.hidden = !hit; any = any || hit;
    });
    if (none) none.hidden = any;
  }
  month.addEventListener("input", apply); search.addEventListener("input", apply);
  document.querySelector("[data-txn-clear]").addEventListener("click", function () { month.value = ""; search.value = ""; apply(); });
})();

/* Support HapiTech: small button -> box with payment options -> thank-you (and Aaron is told) */
(function () {
  var dlg = document.getElementById("supportDialog"), open = document.querySelector("[data-support-open]");
  if (!dlg || !open) return;
  var amount = "5", pick = dlg.querySelector("[data-support-pick]"), thanks = dlg.querySelector("[data-support-thanks]");
  function links() {
    dlg.querySelectorAll("[data-support-way]").forEach(function (a) {
      var p = a.getAttribute("data-amount-param");
      a.href = a.getAttribute("data-base") + (p && amount ? p.replace("{n}", amount) : "");
    });
  }
  open.addEventListener("click", function () {
    pick.hidden = false; thanks.hidden = true;
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
  });
  dlg.querySelectorAll("[data-support-close]").forEach(function (b) { b.addEventListener("click", function () { dlg.close(); }); });
  dlg.querySelectorAll("[data-amount]").forEach(function (c) {
    c.addEventListener("click", function () {
      dlg.querySelectorAll("[data-amount]").forEach(function (x) { x.classList.toggle("is-on", x === c); });
      amount = c.getAttribute("data-amount"); links();
    });
  });
  dlg.querySelectorAll("[data-support-way]").forEach(function (a) {
    a.addEventListener("click", function () {
      var token = (document.querySelector('meta[name="csrf-token"]') || {}).content;
      fetch("/portal/support", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        body: JSON.stringify({ method: a.getAttribute("data-support-way"), amount: amount }) }).catch(function () {});
      setTimeout(function () { pick.hidden = true; thanks.hidden = false; }, 300);   // the payment page opens in a new tab
    });
  });
  links();
})();
