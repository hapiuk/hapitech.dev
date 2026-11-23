/* static/js/hub.js — hapitech.report: filter + "show more" for reviews, report dialog, business search */
(function () {
  var list = document.querySelector("[data-reviews]");
  if (list) {
    var STEP = 10, limit = STEP, filter = "all", more = document.querySelector(".hb-more");
    function apply() {
      var shown = 0, matches = 0;
      list.querySelectorAll(".hb-review").forEach(function (el) {
        var hit = filter === "all" || el.getAttribute("data-r") === filter || (filter === "replied" && el.getAttribute("data-replied") === "yes");
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
