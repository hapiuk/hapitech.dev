/* static/js/hub.js — hapitech.report: filter + "show more" for reviews, report dialog, business search */
(function () {
  var list = document.querySelector("[data-reviews]");
  if (list) {
    var STEP = 10, limit = STEP, filter = "all", more = document.querySelector(".hb-more");
    function apply() {
      var shown = 0, matches = 0;
      list.querySelectorAll(".hb-review").forEach(function (el) {
        var hit = filter === "all" || el.getAttribute("data-r") === filter || el.getAttribute("data-s") === filter || (filter === "replied" && el.getAttribute("data-replied") === "yes");
        if (hit) matches++;
        var show = hit && shown < limit;
        if (show) shown++;
        el.hidden = !show;
      });
      more.hidden = matches <= limit;
      document.querySelectorAll(".hb-chip[data-filter]").forEach(function (c) { c.setAttribute("aria-pressed", c.getAttribute("data-filter") === filter ? "true" : "false"); });
    }
    document.querySelectorAll("[data-filter]").forEach(function (b) {
      b.addEventListener("click", function () { filter = b.getAttribute("data-filter"); limit = STEP; apply(); });
    });
    more.querySelector("button").addEventListener("click", function () { limit += STEP; apply(); });
    if (location.hash.indexOf("#review-") === 0) { limit = 1000; }
    apply();
  }
  var dlg = document.getElementById("reportDialog");
  if (dlg) {
    var form = dlg.querySelector("[data-report-form]"), msg = dlg.querySelector("[data-report-msg]"), target = null;
    document.querySelectorAll("[data-report]").forEach(function (b) {
      b.addEventListener("click", function () { target = b.getAttribute("data-report"); form.reset(); msg.textContent = ""; msg.className = "hb-msg"; dlg.showModal(); });
    });
    dlg.querySelector("[data-report-close]").addEventListener("click", function () { dlg.close(); });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var token = (document.querySelector('meta[name="csrf-token"]') || {}).content;
      msg.textContent = "Sending…";
      fetch(target, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        body: JSON.stringify({ reason: form.reason.value, details: form.details.value, email: form.email.value }) })
        .then(function (r) { return r.json(); })
        .then(function (d) { msg.textContent = d.message || ""; msg.className = "hb-msg " + (d.ok ? "is-ok" : "is-err"); if (d.ok) setTimeout(function () { dlg.close(); }, 2500); })
        .catch(function () { msg.textContent = "Couldn't send. Please email aaron@hapitech.dev."; msg.className = "hb-msg is-err"; });
    });
  }
  var search = document.querySelector("[data-biz-search]");
  if (search) search.addEventListener("input", function () {
    var q = search.value.trim().toLowerCase();
    document.querySelectorAll("[data-biz]").forEach(function (el) { el.hidden = q && el.getAttribute("data-biz").toLowerCase().indexOf(q) < 0; });
  });
})();

/* --- the fun bits: reveal on scroll, counters, donut + score ring, card tilt --- */
(function () {
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  function countUp(el) {
    var to = parseFloat(el.getAttribute("data-count")) || 0, dec = +(el.getAttribute("data-dec") || 0), suf = el.getAttribute("data-suffix") || "";
    if (reduce) { el.textContent = to.toFixed(dec) + suf; return; }
    var t0 = null;
    function step(t) { t0 = t0 || t; var k = Math.min(1, (t - t0) / 1300), e = 1 - Math.pow(1 - k, 3);
      el.textContent = (to * e).toFixed(dec) + suf; if (k < 1) requestAnimationFrame(step); }
    requestAnimationFrame(step);
  }
  var io = "IntersectionObserver" in window ? new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (!en.isIntersecting) return;
      var el = en.target; el.classList.add("hb-in"); io.unobserve(el);
      if (el.hasAttribute("data-count")) countUp(el);
      if (el.classList.contains("hb-donut")) { el.style.setProperty("--g", el.getAttribute("data-g")); el.style.setProperty("--f", el.getAttribute("data-f")); }
      if (el.classList.contains("hb-ring")) el.style.setProperty("--p", el.getAttribute("data-p"));
    });
  }, { threshold: 0.2 }) : null;
  document.querySelectorAll(".reveal, [data-count], .hb-donut, .hb-ring, .hb-biz, .hb-card").forEach(function (el) {
    if (io) io.observe(el); else { el.classList.add("hb-in"); }
  });
  if (!reduce) document.querySelectorAll("[data-tilt]").forEach(function (card) {
    card.addEventListener("mousemove", function (e) {
      var r = card.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
      card.style.transform = "perspective(900px) rotateY(" + (x * 7) + "deg) rotateX(" + (-y * 7) + "deg) translateY(-3px)";
    });
    card.addEventListener("mouseleave", function () { card.style.transform = ""; });
  });
  var none = document.querySelector("[data-biz-none]"), search = document.querySelector("[data-biz-search]");
  if (search && none) search.addEventListener("input", function () {
    setTimeout(function () { none.hidden = !!document.querySelector("[data-biz]:not([hidden])"); }, 0);
    if (search.value && location.hash !== "#businesses") document.getElementById("businesses").scrollIntoView({ behavior: "smooth" });
  });
})();
