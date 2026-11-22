/* HapiTech public site: nav, reveal-on-scroll, contact form. No dependencies. */
(function () {
  "use strict";

  var reduce = (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) ||
    /[?&]still=1\b/.test(location.search);   /* review pin: settled page, no motion */
  if (reduce) document.documentElement.classList.add("no-motion");

  /* ---------- theme toggle (dark default; choice remembered) ---------- */
  var root = document.documentElement;
  var themeBtn = document.getElementById("themeToggle");
  var themeMeta = document.querySelector('meta[name="theme-color"]');
  function applyTheme(t) {
    root.setAttribute("data-theme", t);
    if (themeMeta) themeMeta.setAttribute("content", t === "light" ? "#f6f3ee" : "#0c0e12");
    if (themeBtn) themeBtn.setAttribute("aria-label", t === "light" ? "Switch to dark theme" : "Switch to light theme");
  }
  applyTheme(root.getAttribute("data-theme") === "light" ? "light" : "dark");
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
      applyTheme(next);
      try { localStorage.setItem("theme", next); } catch (e) {}
    });
  }

  /* ---------- nav: scrolled state + mobile toggle ---------- */
  var nav = document.getElementById("nav");
  var toggle = document.getElementById("navToggle");
  var links = document.getElementById("navLinks");

  function onScroll() { if (nav) nav.classList.toggle("is-scrolled", window.scrollY > 8); }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  function closeMenu() {
    if (!links || !toggle) return;
    links.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
  }
  if (toggle && links) {
    toggle.addEventListener("click", function () {
      var open = links.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    links.addEventListener("click", function (e) { if (e.target.closest("a")) closeMenu(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeMenu(); });
    window.addEventListener("resize", function () { if (window.innerWidth > 900) closeMenu(); });
  }

  /* ---------- reveal on scroll ---------- */
  var revealables = document.querySelectorAll(".reveal, .hero__stack");
  if (!reduce && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("is-in"); io.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    revealables.forEach(function (el) {
      if (el.classList.contains("feature") || el.classList.contains("step") || el.classList.contains("pillar") || el.classList.contains("ai-card") || el.classList.contains("news-card")) {
        el.style.transitionDelay = (Array.prototype.indexOf.call(el.parentNode.children, el) % 4) * 80 + "ms";
      }
      io.observe(el);
    });
  } else {
    revealables.forEach(function (el) { el.classList.add("is-in"); });
  }

  /* ---------- news: clamp long articles, infinite scroll ---------- */
  function setupClamps(scope) {
    (scope || document).querySelectorAll("[data-clamp]:not([data-clamp-ready])").forEach(function (body) {
      body.setAttribute("data-clamp-ready", "");
      var btn = body.nextElementSibling;
      if (!btn || !btn.classList.contains("post__expand")) return;
      function check() {
        if (body.classList.contains("is-open")) return;
        var long = body.scrollHeight > 520;
        body.classList.toggle("is-clamped", long);
        btn.hidden = !long;
      }
      check();
      body.querySelectorAll("img").forEach(function (im) { im.addEventListener("load", check); });
      btn.addEventListener("click", function () {
        var open = !body.classList.contains("is-open");
        body.classList.toggle("is-open", open);
        body.classList.toggle("is-clamped", !open);
        btn.textContent = open ? "Show less" : "Show the full article";
        if (!open) body.closest(".post").scrollIntoView({ block: "start" });
      });
    });
  }
  setupClamps();

  var feed = document.getElementById("newsFeed");
  var more = document.getElementById("feedMore");
  if (feed && more && "IntersectionObserver" in window && window.fetch) {
    var loading = false;
    function done(msg) { more.className = "feed-more"; more.innerHTML = "<p>" + msg + "</p>"; obs.disconnect(); }
    function loadMore() {
      var next = feed.getAttribute("data-next");
      if (loading || !next) return;
      loading = true;
      more.classList.add("is-loading");
      var cat = feed.getAttribute("data-cat");
      var url = "/news/items?offset=" + encodeURIComponent(next) + (cat && cat !== "all" ? "&cat=" + encodeURIComponent(cat) : "");
      fetch(url, { credentials: "same-origin" })
        .then(function (r) {
          if (!r.ok) throw new Error(r.status);
          var nxt = r.headers.get("X-Next-Offset") || "";
          return r.text().then(function (html) { return { html: html, next: nxt }; });
        })
        .then(function (res) {
          var tmp = document.createElement("div");
          tmp.innerHTML = res.html;
          var added = Array.prototype.slice.call(tmp.children);
          added.forEach(function (el) { feed.appendChild(el); });
          setupClamps(feed);
          feed.setAttribute("data-next", res.next);
          more.classList.remove("is-loading");
          if (!res.next) done("You're all caught up.");
        })
        .catch(function () {
          more.classList.remove("is-loading");
          var a = more.querySelector("a");
          if (a) a.textContent = "Couldn't load more. Try again";
        })
        .then(function () {
          loading = false;
          /* sentinel still on screen (short page): keep filling */
          if (feed.getAttribute("data-next") && more.getBoundingClientRect().top < window.innerHeight + 600) loadMore();
        });
    }
    var link = more.querySelector("a");
    if (link) link.addEventListener("click", function (e) { e.preventDefault(); loadMore(); });
    var obs = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting) loadMore();
    }, { rootMargin: "600px 0px" });
    obs.observe(more);
  }

  /* ---------- login modal + full login page ---------- */
  function csrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute("content") : "";
  }
  function postJSON(url, data) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
      body: JSON.stringify(data)
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { d._status = r.status; return d; });
    });
  }

  function initLogin(root) {
    var msg = root.querySelector("[data-login-msg]");
    var nextUrl = root.getAttribute("data-next") || "";
    var q = nextUrl ? "?next=" + encodeURIComponent(nextUrl) : "";
    function say(t, kind) { msg.textContent = t || ""; msg.className = "login__msg" + (kind ? " is-" + kind : ""); }
    var form = root.querySelector('[data-login-pane="code"]');
    var stepEmail = form.querySelector('[data-code-step="email"]');
    var stepVerify = form.querySelector('[data-code-step="verify"]');
    var sent = form.querySelector("[data-code-sent]");
    function busy(on) { form.querySelectorAll("button[type=submit]").forEach(function (b) { b.disabled = on; }); }
    function reset() {
      stepEmail.hidden = false; stepVerify.hidden = true; form.code.value = ""; say(""); busy(false);
      setTimeout(function () { form.email.focus(); }, 30);
    }
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      busy(true);
      if (!stepEmail.hidden) {
        var em = form.email.value.trim();
        if (!em) { say("Enter your email address.", "err"); busy(false); return; }
        say("Sending…");
        postJSON("/auth/code/request", { email: em }).then(function (d) {
          busy(false);
          if (!d.ok) { say(d.message || "Couldn't send a code.", "err"); return; }
          stepEmail.hidden = true; stepVerify.hidden = false;
          sent.textContent = "Check " + em + " for your code. It works for 10 minutes.";
          say(d.dev_code ? d.message : "", "ok");
          form.code.focus();
        }).catch(function () { busy(false); say("Network problem. Please try again.", "err"); });
      } else {
        say("Checking…");
        postJSON("/auth/code/verify" + q, { code: form.code.value, remember: form.remember.checked }).then(function (d) {
          if (d.ok) { say("Welcome back. Taking you to your dashboard…", "ok"); window.location.href = d.redirect || "/"; }
          else { busy(false); say(d.message || "That code didn't work.", "err"); }
        }).catch(function () { busy(false); say("Network problem. Please try again.", "err"); });
      }
    });
    form.querySelector("[data-code-restart]").addEventListener("click", reset);
    return { show: reset };
  }

  document.querySelectorAll("[data-login-root]").forEach(function (root) { root._login = initLogin(root); });
  var modal = document.getElementById("loginModal");
  if (modal && typeof modal.showModal === "function") {
    document.querySelectorAll("a[data-login]").forEach(function (a) {
      a.addEventListener("click", function (e) {
        e.preventDefault();
        if (typeof closeMenu === "function") closeMenu();
        modal.showModal();
        var root = modal.querySelector("[data-login-root]");
        if (root && root._login) root._login.show();
      });
    });
    modal.querySelector("[data-modal-close]").addEventListener("click", function () { modal.close(); });
    modal.addEventListener("click", function (e) { if (e.target === modal) modal.close(); });   /* backdrop */
  }

  /* ---------- contact form (POST /contact, JSON) ----------
     The endpoint takes name / email / message; optional fields are folded into the message. */
  var form = document.getElementById("contactForm");
  var btn = document.getElementById("sendContact");
  var status = document.getElementById("contactStatus");
  if (!form || !btn || !status) return;

  function $(id) { return document.getElementById(id); }
  function say(msg, kind) {
    status.textContent = msg;
    status.className = "form__status" + (kind ? " is-" + kind : "");
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var required = { name: $("contactName"), email: $("contactEmail"), message: $("contactMessage") };
    var bad = null;
    Object.keys(required).forEach(function (k) {
      var el = required[k], v = el.value.trim();
      var ok = v !== "" && (k !== "email" || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v));
      el.setAttribute("aria-invalid", ok ? "false" : "true");
      if (!ok && !bad) bad = el;
    });
    if (bad) { say("Please fill in your name, a valid email and a short message.", "err"); bad.focus(); return; }

    var business = $("contactBusiness").value.trim();
    var phone = $("contactPhone").value.trim();
    var need = $("contactNeed").value;
    var header = ["Looking for: " + need];
    if (business) header.push("Business: " + business);
    if (phone) header.push("Phone: " + phone);
    var message = header.join("\n") + "\n\n" + required.message.value.trim();

    btn.disabled = true; btn.textContent = "Sending…"; say("");
    fetch("/contact", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
      credentials: "same-origin",
      body: JSON.stringify({
        name: required.name.value.trim(),
        email: required.email.value.trim(),
        message: message,
        client: "hapitech.dev quote form"
      })
    })
      .then(function (res) {
        var ct = (res.headers.get("content-type") || "").toLowerCase();
        return (ct.indexOf("application/json") > -1 ? res.json() : Promise.resolve({}))
          .then(function (data) { return { ok: res.ok, data: data || {} }; });
      })
      .then(function (r) {
        if (r.ok && r.data.success !== false) {
          say("Thanks, that's on its way. You'll hear back shortly.", "ok");
          form.reset();
        } else {
          say(r.data.message || "Could not send right now. Please try again, or email aaron@hapitech.dev.", "err");
        }
      })
      .catch(function () { say("Network error. Please check your connection, or email aaron@hapitech.dev.", "err"); })
      .then(function () { btn.disabled = false; btn.textContent = "Send message"; });
  });
})();
