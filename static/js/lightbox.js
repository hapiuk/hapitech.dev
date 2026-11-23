/* static/js/lightbox.js — review photos open full size on the same page (not a new tab).
   Mark each photo link with data-lightbox="<group>": photos in the same group can be flicked through.
   Without JavaScript the link still opens the photo itself. Used on hapitech.dev, hapitech.report
   and the dashboards. */
(function () {
  "use strict";
  var css = ".lb{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;" +
    "background:rgba(8,10,14,.92);opacity:0;transition:opacity .18s;touch-action:pan-y}" +
    ".lb.is-open{opacity:1}" +
    ".lb__img{max-width:94vw;max-height:84vh;border-radius:10px;box-shadow:0 10px 40px rgba(0,0,0,.5);" +
    "object-fit:contain;user-select:none;-webkit-user-select:none}" +
    ".lb__btn{position:absolute;border:0;background:rgba(255,255,255,.12);color:#fff;width:46px;height:46px;" +
    "border-radius:50%;font-size:26px;line-height:46px;text-align:center;cursor:pointer;padding:0}" +
    ".lb__btn:hover,.lb__btn:focus-visible{background:rgba(255,255,255,.24);outline:none}" +
    ".lb__close{top:14px;right:14px}.lb__prev{left:12px;top:50%;margin-top:-23px}.lb__next{right:12px;top:50%;margin-top:-23px}" +
    ".lb__cap{position:absolute;left:16px;right:16px;bottom:14px;text-align:center;color:#d8dbe2;font:14px/1.4 system-ui,sans-serif}" +
    "@media (max-width:600px){.lb__prev,.lb__next{top:auto;bottom:44px;margin:0}}";

  var box, img, cap, prev, next, items = [], idx = 0, lastFocus = null;

  function build() {
    var st = document.createElement("style");
    st.textContent = css;
    document.head.appendChild(st);
    box = document.createElement("div");
    box.className = "lb";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", "Photo");
    box.innerHTML = '<img class="lb__img" alt="">' +
      '<button type="button" class="lb__btn lb__close" aria-label="Close">\u00d7</button>' +
      '<button type="button" class="lb__btn lb__prev" aria-label="Previous photo">\u2039</button>' +
      '<button type="button" class="lb__btn lb__next" aria-label="Next photo">\u203a</button>' +
      '<p class="lb__cap"></p>';
    img = box.querySelector(".lb__img");
    cap = box.querySelector(".lb__cap");
    prev = box.querySelector(".lb__prev");
    next = box.querySelector(".lb__next");
    box.addEventListener("click", function (e) {
      if (e.target === prev) return go(-1);
      if (e.target === next) return go(1);
      if (e.target !== img) close();               // backdrop or ×
    });
    var x0 = null;
    box.addEventListener("touchstart", function (e) { x0 = e.touches[0].clientX; }, { passive: true });
    box.addEventListener("touchend", function (e) {
      if (x0 === null) return;
      var dx = e.changedTouches[0].clientX - x0;
      x0 = null;
      if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1);
    });
    document.body.appendChild(box);
  }

  function show() {
    var a = items[idx], im = a.querySelector("img");
    img.src = a.getAttribute("href");
    img.alt = (im && im.alt) || "";
    cap.textContent = (img.alt ? img.alt : "") + (items.length > 1 ? (img.alt ? " \u00b7 " : "") + (idx + 1) + " of " + items.length : "");
    prev.hidden = next.hidden = items.length < 2;
  }

  function go(d) {
    if (items.length < 2) return;
    idx = (idx + d + items.length) % items.length;
    show();
  }

  function open(a) {
    if (!box) build();
    var g = a.getAttribute("data-lightbox");
    items = g ? Array.prototype.slice.call(document.querySelectorAll('a[data-lightbox="' + g.replace(/"/g, '\\"') + '"]')) : [a];
    idx = Math.max(0, items.indexOf(a));
    lastFocus = document.activeElement;
    show();
    box.style.display = "flex";
    document.documentElement.style.overflow = "hidden";
    requestAnimationFrame(function () { box.classList.add("is-open"); });
    box.querySelector(".lb__close").focus();
  }

  function close() {
    if (!box || box.style.display === "none") return;
    box.classList.remove("is-open");
    box.style.display = "none";
    img.removeAttribute("src");
    document.documentElement.style.overflow = "";
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[data-lightbox]");
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button > 0) return;   // let "open in new tab" still work
    e.preventDefault();
    open(a);
  });
  document.addEventListener("keydown", function (e) {
    if (!box || box.style.display === "none" || !box.classList.contains("is-open")) return;
    if (e.key === "Escape") close();
    else if (e.key === "ArrowLeft") go(-1);
    else if (e.key === "ArrowRight") go(1);
  });
})();
