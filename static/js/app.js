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

/* My plan: transaction history: latest 8 first ("Show older" adds 8 more), filter by year / month or text */
(function () {
  var list = document.querySelector("[data-txn-list]");
  if (!list) return;
  var period = document.querySelector("[data-txn-period]"), search = document.querySelector("[data-txn-search]");
  var none = document.querySelector(".txn__none"), more = document.querySelector(".txn__more");
  var STEP = 8, limit = STEP;
  function apply() {
    var p = period.value, q = search.value.trim().toLowerCase(), shown = 0, matches = 0;
    var filtering = !!(p || q);
    list.querySelectorAll(".txn__item").forEach(function (li) {
      var m = li.getAttribute("data-month");
      var hit = (!p || m === p || m.slice(0, 4) === p) && (!q || li.getAttribute("data-text").toLowerCase().indexOf(q) > -1);
      if (hit) matches++;
      var show = hit && (filtering || shown < limit);
      if (show) shown++;
      li.hidden = !show;
    });
    none.hidden = matches > 0;
    more.hidden = filtering || matches <= limit;
  }
  period.addEventListener("change", apply); search.addEventListener("input", apply);
  more.querySelector("button").addEventListener("click", function () { limit += STEP; apply(); });
  apply();
})();

/* Support HapiTech: small button -> choose PayPal / Revolut -> (PayPal only) choose amount -> thank-you.
   Revolut asks for the amount itself, so nobody enters it twice. Aaron is told which option was picked. */
(function () {
  var dlg = document.getElementById("supportDialog"), open = document.querySelector("[data-support-open]");
  if (!dlg || !open) return;
  var pick = dlg.querySelector("[data-support-pick]"), thanks = dlg.querySelector("[data-support-thanks]");
  var panes = dlg.querySelectorAll("[data-support-amount-for]");
  function show(el) { pick.hidden = true; thanks.hidden = true; panes.forEach(function (p) { p.hidden = true; }); el.hidden = false; }
  open.addEventListener("click", function () {
    show(pick);
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
  });
  dlg.querySelectorAll("[data-support-close]").forEach(function (b) { b.addEventListener("click", function () { dlg.close(); }); });
  dlg.querySelectorAll("[data-support-back]").forEach(function (b) { b.addEventListener("click", function () { show(pick); }); });
  dlg.querySelectorAll("[data-support-step]").forEach(function (b) {
    b.addEventListener("click", function () { show(dlg.querySelector('[data-support-amount-for="' + b.getAttribute("data-support-step") + '"]')); });
  });
  panes.forEach(function (pane) {
    var go = pane.querySelector("[data-support-way]"), note = pane.querySelector("[data-other-note]");
    function set(n) {
      var p = go.getAttribute("data-amount-param");
      go.href = go.getAttribute("data-base") + (n && p ? p.replace("{n}", n) : "");
      go.setAttribute("data-amount", n || "");
      note.hidden = !!n;
    }
    pane.querySelectorAll("[data-amount]").forEach(function (c) {
      if (c === go) return;
      c.addEventListener("click", function () {
        pane.querySelectorAll(".support__chip").forEach(function (x) { x.classList.toggle("is-on", x === c); });
        set(c.getAttribute("data-amount"));
      });
    });
    set("5");
  });
  dlg.querySelectorAll("[data-support-way]").forEach(function (a) {
    a.addEventListener("click", function () {
      var token = (document.querySelector('meta[name="csrf-token"]') || {}).content;
      fetch("/portal/support", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        body: JSON.stringify({ method: a.getAttribute("data-support-way"), amount: a.getAttribute("data-amount") || "" }) }).catch(function () {});
      setTimeout(function () { show(thanks); }, 300);    // the payment page opens in a new tab
    });
  });
})();

/* My plan: "Request work" opens the request box (and re-opens after sending, so they see it listed) */
(function () {
  var dlg = document.getElementById("workDialog"), open = document.querySelector("[data-work-open]");
  if (!dlg || !open) return;
  function show() { if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", ""); }
  open.addEventListener("click", show);
  dlg.querySelector("[data-work-close]").addEventListener("click", function () { dlg.close(); });
  if (location.hash === "#work") show();
})();

/* Any [data-open-dlg="id"] opens that dialog: fills [data-fill]/[data-fill-href]/[data-fill-value] and
   toggles [data-show-if]/[data-hide-if] from the button's data-*, then puts the cursor in the first box. */
(function () {
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-open-dlg]");
    if (b) {
      var dlg = document.getElementById(b.getAttribute("data-open-dlg")); if (!dlg) return;
      var d = b.dataset;
      dlg.querySelectorAll("[data-fill]").forEach(function (el) { if (!el.hasAttribute("data-default")) el.setAttribute("data-default", el.textContent); el.textContent = d[el.getAttribute("data-fill")] || el.getAttribute("data-default"); });
      dlg.querySelectorAll("[data-fill-href]").forEach(function (el) { el.href = d[el.getAttribute("data-fill-href")] || "#"; });
      dlg.querySelectorAll("[data-show-if]").forEach(function (el) { el.hidden = !d[el.getAttribute("data-show-if")]; });
      dlg.querySelectorAll("[data-hide-if]").forEach(function (el) { el.hidden = !!d[el.getAttribute("data-hide-if")]; });
      dlg.querySelectorAll("[data-fill-value]").forEach(function (el) { var v = d[el.getAttribute("data-fill-value")]; el.value = v ? v + (el.getAttribute("data-suffix") || "") : ""; });
      dlg.querySelectorAll("[data-fill-action]").forEach(function (el) { el.setAttribute("action", d[el.getAttribute("data-fill-action")]); });
      if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
      var f = dlg.querySelector("input:not([type=hidden]),textarea"); if (f) { f.focus(); f.setSelectionRange && f.setSelectionRange(f.value.length, f.value.length); }
      return;
    }
    var c = e.target.closest("[data-close-dlg]"); if (c) { c.closest("dialog").close(); return; }
    var p = e.target.closest("[data-pick]");
    if (p) { var inp = p.closest("form").querySelector("input[name=what]"); inp.value = p.getAttribute("data-pick"); inp.focus(); }
  });
})();

/* Review search: typing searches after a short pause; the cursor stays at the end of the box after reload */
(function () {
  var box = document.querySelector("[data-live-search]"); if (!box) return;
  var t;
  box.addEventListener("input", function () { clearTimeout(t); t = setTimeout(function () { box.form.requestSubmit ? box.form.requestSubmit() : box.form.submit(); }, 650); });
  if (box.value) { var n = box.value.length; box.setSelectionRange(n, n); }
})();

/* Long lists: show 20 at a time with a "Show more" button. A link to #r123 still shows that one. */
(function () {
  document.querySelectorAll("[data-paged]").forEach(function (box) {
    var step = +box.getAttribute("data-paged") || 20, items = [].slice.call(box.children), shown = step;
    if (items.length <= step) return;
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "btn btn--ghost btn--sm paged-more";
    function draw() {
      items.forEach(function (el, i) { el.hidden = i >= shown; });
      var left = items.length - shown;
      btn.hidden = left <= 0; btn.textContent = "Show " + Math.min(step, left) + " more (" + left + " left)";
    }
    btn.addEventListener("click", function () { shown += step; draw(); });
    var target = location.hash && document.getElementById(location.hash.slice(1));
    if (target && items.indexOf(target) >= step) shown = items.indexOf(target) + 1;
    box.after(btn); draw();
  });
})();

/* Emails: one preview at a time, with a "Preview for" switch */
(function () {
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-prev]"); if (!b) return;
    var id = b.getAttribute("data-prev"), sec = id.split("-")[0];
    document.querySelectorAll('[data-prev^="' + sec + '-"]').forEach(function (x) { x.setAttribute("aria-selected", x === b ? "true" : "false"); });
    document.querySelectorAll('[data-prev-box^="' + sec + '-"]').forEach(function (x) { x.hidden = x.getAttribute("data-prev-box") !== id; });
  });
  var h = location.hash && document.querySelector(location.hash + "[data-prev-box]");
  if (h) { var t = document.querySelector('[data-prev="' + h.getAttribute("data-prev-box") + '"]'); if (t) t.click(); }
})();

/* posts: share buttons. The post's text (title, words, link) is always copied first, because Facebook,
   Instagram and LinkedIn don't let websites fill in the text for you: you paste it. */
(function () {
  var box = document.querySelector("[data-share-box]"); if (!box) return;
  var url = box.getAttribute("data-url"), text = box.getAttribute("data-text"), msg = document.querySelector("[data-share-msg]");
  var photos = JSON.parse(box.getAttribute("data-photos") || "[]");
  var phone = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
  function say(t) { if (msg) msg.textContent = t; }
  function copy() { return navigator.clipboard ? navigator.clipboard.writeText(text).catch(function () {}) : Promise.resolve(); }
  function files() {
    return Promise.all(photos.slice(0, 6).map(function (src, i) {
      return fetch(src).then(function (r) { return r.blob(); }).then(function (bl) {
        return new File([bl], "photo-" + (i + 1) + "." + ((bl.type.split("/")[1] || "jpg").replace("jpeg", "jpg")), { type: bl.type || "image/jpeg" });
      });
    })).catch(function () { return []; });
  }
  function sheet(withPhotos) {
    if (!navigator.share) return Promise.reject();
    return (withPhotos ? files() : Promise.resolve([])).then(function (fs) {
      var data = { title: text.split("\n")[0], text: text };
      if (fs.length && navigator.canShare && navigator.canShare({ files: fs })) data.files = fs;
      else if (url) data.url = url;
      return navigator.share(data);
    });
  }
  var tip = document.getElementById("shareTip"), pending = null;
  var where = { facebook: "Facebook", instagram: "Instagram", linkedin: "LinkedIn", more: "the app you pick" };
  box.addEventListener("click", function (e) {
    var b = e.target.closest("[data-share-to]"); if (!b) return;
    var to = b.getAttribute("data-share-to");
    copy();
    if (tip && box.getAttribute("data-tip") && to !== "whatsapp" && tip.showModal) {
      pending = to;
      tip.querySelector("[data-share-tip-text]").innerHTML = "When " + where[to] + " opens, tap in the text box and <b>paste</b> your words in." +
        (to === "instagram" ? " Paste them as the caption." : "");
      tip.querySelector("[data-share-tip-off]").checked = false;
      tip.showModal(); tip.querySelector("[data-share-go]").focus();
      return;
    }
    go(to);
  });
  if (tip) tip.querySelector("[data-share-go]").addEventListener("click", function () {
    if (tip.querySelector("[data-share-tip-off]").checked) {
      box.removeAttribute("data-tip");
      var token = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
      fetch(box.getAttribute("data-prefs"), { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": token }, body: JSON.stringify({ share_tip_off: true }) }).catch(function () {});
    }
    tip.close(); if (pending) go(pending); pending = null;
  });
  function go(to) {
    if (to === "facebook") {
      if (phone && navigator.share) { say("Text copied. Pick Facebook, then paste your words in."); sheet(true).catch(function () {}); return; }
      if (!url) { say("Text copied. Publish the post first to get a link to share."); return; }
      say("Text copied. Facebook opens in a new tab: paste your words into the post.");
      window.open("https://www.facebook.com/sharer/sharer.php?u=" + encodeURIComponent(url), "_blank", "noopener");
    } else if (to === "instagram") {
      if (phone && navigator.share) { say("Text copied. Pick Instagram, then paste your words as the caption."); sheet(true).catch(function () {}); }
      else say("Instagram only lets you post from the app. Open this page on your phone and tap Instagram. (Text copied.)");
    } else if (to === "whatsapp") {
      window.open("https://wa.me/?text=" + encodeURIComponent(text), "_blank", "noopener"); say("");
    } else if (to === "linkedin") {
      say("Text copied. LinkedIn opens in a new tab: paste your words into the post.");
      window.open("https://www.linkedin.com/sharing/share-offsite/?url=" + encodeURIComponent(url), "_blank", "noopener");
    } else if (to === "more") {
      sheet(true).then(function () { say(""); }, function () { say("Text copied: paste it wherever you like."); });
    }
  }
})();

/* a checkbox that saves as soon as it's ticked */
document.querySelectorAll("[data-autosubmit-check]").forEach(function (c) { c.addEventListener("change", function () { c.form.submit(); }); });
