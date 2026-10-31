/* HapiTech homepage behaviour: nav, reveal-on-scroll, release terminal,
   background signal field, contact form. No dependencies. */
(function () {
  "use strict";

  var reduce = (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) ||
    /[?&]still=1\b/.test(location.search);   /* review pin: settled page, no motion */

  /* ---------- nav: scrolled state + mobile toggle ---------- */
  var nav = document.getElementById("nav");
  var toggle = document.getElementById("navToggle");
  var links = document.getElementById("navLinks");

  function onScroll() {
    if (nav) nav.classList.toggle("is-scrolled", window.scrollY > 8);
  }
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
    links.addEventListener("click", function (e) {
      if (e.target.closest("a")) closeMenu();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeMenu();
    });
  }

  /* ---------- reveal on scroll ---------- */
  var revealables = document.querySelectorAll(".reveal, .flow__step");
  if (!reduce && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.add("is-in");
          io.unobserve(en.target);
        }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    revealables.forEach(function (el, i) {
      el.style.transitionDelay = el.classList.contains("row") || el.classList.contains("case") || el.classList.contains("lab__item")
        ? (Array.prototype.indexOf.call(el.parentNode.children, el) * 70) + "ms" : "";
      io.observe(el);
    });
  } else {
    revealables.forEach(function (el) { el.classList.add("is-in"); });
  }

  /* ---------- release terminal: lines appear in sequence ---------- */
  var term = document.querySelector("#termBody code");
  if (term && !reduce) {
    var caret = term.querySelector(".caret");
    if (caret) caret.remove();
    var parts = term.innerHTML.split("\n");
    term.innerHTML = parts.map(function (l) { return '<span class="line">' + l + "</span>"; }).join("");
    var lines = term.querySelectorAll(".line");
    var last = lines[lines.length - 1];
    if (last) {
      var c = document.createElement("span");
      c.className = "caret";
      last.appendChild(c);
    }
    var i = 0;
    (function step() {
      if (i >= lines.length) return;
      lines[i].classList.add("on");
      var isCmd = lines[i].textContent.trim().charAt(0) === "$";
      i += 1;
      setTimeout(step, isCmd ? 520 : 260);
    })();
  }

  /* ---------- background: a quiet field of nodes ---------- */
  var cv = document.getElementById("field");
  if (cv && cv.getContext && !reduce) {
    var ctx = cv.getContext("2d");
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var W = 0, H = 0, pts = [], mouse = { x: -9999, y: -9999 };
    var running = true;

    function resize() {
      W = window.innerWidth; H = window.innerHeight;
      cv.width = W * dpr; cv.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var n = Math.round(Math.min(70, (W * H) / 22000));
      pts = [];
      for (var k = 0; k < n; k++) {
        pts.push({ x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - .5) * .18, vy: (Math.random() - .5) * .18 });
      }
    }
    resize();
    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", function (e) { mouse.x = e.clientX; mouse.y = e.clientY; }, { passive: true });
    document.addEventListener("visibilitychange", function () {
      running = !document.hidden;
      if (running) requestAnimationFrame(frame);
    });

    function frame() {
      if (!running) return;
      ctx.clearRect(0, 0, W, H);
      var LINK = 140;
      for (var a = 0; a < pts.length; a++) {
        var p = pts[a];
        p.x += p.vx; p.y += p.vy;
        if (p.x < -20) p.x = W + 20; if (p.x > W + 20) p.x = -20;
        if (p.y < -20) p.y = H + 20; if (p.y > H + 20) p.y = -20;
        for (var b = a + 1; b < pts.length; b++) {
          var q = pts[b], dx = p.x - q.x, dy = p.y - q.y, d = Math.sqrt(dx * dx + dy * dy);
          if (d < LINK) {
            ctx.strokeStyle = "rgba(108,182,255," + (0.09 * (1 - d / LINK)).toFixed(3) + ")";
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
          }
        }
        var md = Math.hypot(p.x - mouse.x, p.y - mouse.y);
        var glow = md < 180 ? 1 - md / 180 : 0;
        ctx.fillStyle = glow > 0 ? "rgba(94,242,184," + (0.25 + glow * 0.6).toFixed(3) + ")" : "rgba(160,190,230,0.22)";
        ctx.beginPath(); ctx.arc(p.x, p.y, 1.2 + glow * 1.4, 0, Math.PI * 2); ctx.fill();
      }
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  /* ---------- contact form (POST /contact, JSON) ---------- */
  var form = document.getElementById("contactForm");
  var btn = document.getElementById("sendContact");
  var status = document.getElementById("contactStatus");

  function say(msg, kind) {
    status.textContent = msg;
    status.className = "form__status" + (kind ? " is-" + kind : "");
  }

  if (form && btn && status) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var fields = {
        name: document.getElementById("contactName"),
        email: document.getElementById("contactEmail"),
        message: document.getElementById("contactMessage")
      };
      var bad = null;
      Object.keys(fields).forEach(function (k) {
        var el = fields[k];
        var ok = el.value.trim() !== "" && (k !== "email" || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(el.value.trim()));
        el.setAttribute("aria-invalid", ok ? "false" : "true");
        if (!ok && !bad) bad = el;
      });
      if (bad) { say("Please complete every field with a valid email.", "err"); bad.focus(); return; }

      btn.disabled = true; btn.textContent = "Sending…"; say("");
      fetch("/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          name: fields.name.value.trim(),
          email: fields.email.value.trim(),
          message: fields.message.value.trim(),
          client: "hapitech.dev homepage"
        })
      })
        .then(function (res) {
          var ct = (res.headers.get("content-type") || "").toLowerCase();
          return (ct.indexOf("application/json") > -1 ? res.json() : Promise.resolve({}))
            .then(function (data) { return { ok: res.ok, data: data || {} }; });
        })
        .then(function (r) {
          if (r.ok && r.data.success !== false) {
            say(r.data.message || "Sent. We'll get back to you shortly.", "ok");
            form.reset();
          } else {
            say(r.data.message || "Could not send right now. Please try again shortly.", "err");
          }
        })
        .catch(function () { say("Network error. Please check your connection and try again.", "err"); })
        .then(function () { btn.disabled = false; btn.textContent = "Send message"; });
    });
  }
})();
