/* tools/google_reviews_export.js (v2) — export a business's Google reviews (stars, text, photos, owner's replies)
   for HapiTech's review import. Works in BOTH places Google shows reviews:
     • Google Search: search the business, click "Google reviews" / the reviews count so the reviews pop-up opens
     • Google Maps: open the business, click the "Reviews" tab
   Sorting by "Newest" is best. Then press F12 → Console, paste this whole file, press Enter and leave the tab alone;
   it scrolls the reviews by itself. When it says "Done", a <business>-google-reviews-<date>.json file downloads:
   upload it in HapiTech Admin → Reviews → Import. It only reads the page; nothing is posted or changed.

   v2: finds each review by its star rating ("Rated 5.0 out of 5" on Search, "5 stars" on Maps) instead of Maps-only
   page structure, so it works in the Search pop-up too. */
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const clean = t => (t || "").replace(/ /g, " ").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  const STAR = /(?:Rated\s*)?([1-5])(?:[.,]\d)?\s*(?:stars?|out of 5)/i;
  const AGO = /^(Edited )?(a|an|\d+) (minute|hour|day|week|month|year)s? ago(\s*(on|via) Google)?$/i;
  const seen = new Map();

  const starEls = () => [...document.querySelectorAll("[aria-label]")].filter(e => STAR.test(e.getAttribute("aria-label")) && e.getAttribute("aria-label").length < 60);
  const business = clean((document.querySelector('[data-attrid="title"], h1.DUwDvf, h1') || {}).innerText || "") || clean(document.title.split(" - ")[0].split(" · ")[0]);

  // the review box around a star rating = the largest ancestor that holds just this one rating
  function boxOf(star) {
    let best = star, n = star.parentElement;
    while (n && n !== document.body) {
      const k = [...n.querySelectorAll("[aria-label]")].filter(e => STAR.test(e.getAttribute("aria-label")) && e.getAttribute("aria-label").length < 60).length;
      if (k > 1) break;
      best = n; n = n.parentElement;
    }
    return best;
  }
  function scroller() {
    let n = (starEls()[0] || {}).parentElement;
    while (n && n !== document.body) {
      const s = getComputedStyle(n);
      if (/(auto|scroll)/.test(s.overflowY) && n.scrollHeight > n.clientHeight + 40) return n;
      n = n.parentElement;
    }
    return null;                                            // no inner scroller: scroll the page itself
  }
  function expand() {                                       // "More" / "See more" / "Read more" on long reviews and replies
    document.querySelectorAll('a[role="button"], span[role="button"], button, a.review-more-link').forEach(b => {
      const t = clean(b.innerText), l = b.getAttribute("aria-label") || "";
      if ((/^(More|See more|Read more|Full review)$/i.test(t) || /^See more$/i.test(l)) && !b.__ht) { b.__ht = 1; try { b.click(); } catch (e) {} }
    });
  }
  function photoUrls(box, skip) {
    const out = [];
    box.querySelectorAll("img, [style*='background-image']").forEach(el => {
      if (skip && skip.contains(el)) return;
      let u = el.tagName === "IMG" ? (el.currentSrc || el.src) : ((el.getAttribute("style") || "").match(/url\(["']?([^"')]+)["']?\)/) || [])[1];
      if (!u || !/googleusercontent|ggpht/.test(u)) return;
      const w = el.tagName === "IMG" ? (el.naturalWidth || el.width) : el.getBoundingClientRect().width;
      if (w && w < 56) return;                              // avatars
      out.push(u.replace(/=w\d+-h\d+[^&"']*$/, "=w1600-h1600").replace(/=s\d+(-[a-z0-9-]+)?$/, "=s1600"));
    });
    return [...new Set(out)];
  }
  function grab() {
    starEls().forEach(star => {
      const box = boxOf(star);
      const lines = clean(box.innerText).split("\n").map(l => l.trim()).filter(Boolean);
      if (!lines.length) return;
      const stars = parseInt(star.getAttribute("aria-label").match(STAR)[1], 10);
      // author: Maps puts it on the box; Search has it as the first line / profile link
      const author = clean(box.getAttribute("aria-label") && !STAR.test(box.getAttribute("aria-label")) ? box.getAttribute("aria-label")
        : ((box.querySelector('a[href*="/maps/contrib/"], a[href*="contrib"]') || {}).innerText || lines[0]));
      const dateLine = lines.find(l => AGO.test(l)) || "";
      if (/^\d([.,]\d)?$/.test(author) || !dateLine) return;     // rating-summary rows and business cards, not reviews
      // owner's reply
      let reply = null, replyBox = null;
      const headIdx = lines.findIndex(l => /^Response from the owner/i.test(l));
      if (headIdx >= 0) {
        replyBox = [...box.querySelectorAll("div, span")].find(d => /^Response from the owner/i.test(clean(d.innerText)) && d.children.length) || null;
        const rest = lines.slice(headIdx + 1);
        const rDate = rest[0] && /ago$/.test(rest[0].replace(/^Response from the owner\s*/i, "")) ? rest.shift() : (lines[headIdx].replace(/^Response from the owner\s*/i, "") || "");
        reply = { date: clean(rDate), text: rest.filter(l => !/^(Like|Share|More)$/i.test(l)).join("\n") };
      }
      // review text: what's between the date (and price tags) and the reply / photos
      const tagRe = /^(Great price|Reasonable price|Overpriced|Expensive|Inexpensive|New|Price assessment|Services?|Positive|Critical|Hide|Report|Like|Share|\d+ reviews?(·\d+ photos?)?|Local Guide.*|\d+ photos?)$/i;
      let start = lines.indexOf(dateLine) + 1;
      const end = headIdx >= 0 ? headIdx : lines.length;
      const stopAt = lines.findIndex((l, i) => i >= start && /^(Price assessment|Services|Like|Share)$/.test(l));
      const body = lines.slice(start > 0 ? start : 1, stopAt > 0 ? Math.min(stopAt, end) : end)
        .filter(l => l !== author && !tagRe.test(l) && !AGO.test(l) && !/^(More|See more|Read more)$/i.test(l) && !/^[\ue000-\uf8ff\s]*$/.test(l));
      const price = (lines.find(l => /^(Great price|Reasonable price|Overpriced|Expensive|Inexpensive)$/i.test(l)) || null);
      const id = box.getAttribute("data-review-id") || box.querySelector("[data-review-id]")?.getAttribute("data-review-id")
        || ("t:" + (author + "|" + body.join(" ").slice(0, 80)).toLowerCase().replace(/\s+/g, " "));
      const item = { id, author, rating: stars, date: dateLine.replace(/\s*(on|via) Google$/i, ""), text: body.join("\n"),
                     photos: photoUrls(box, replyBox), price, reply, raw: clean(box.innerText) };
      const old = seen.get(id);
      if (!old || item.text.length > old.text.length || (item.reply && !old.reply) || item.photos.length > old.photos.length) seen.set(id, item);
    });
  }
  function summary() {
    const t = document.body.innerText;
    const m = t.match(/(\d[.,]\d)\s*\n?\s*(?:★+\s*)?\n?\s*\(?([\d,]+)\)?\s*(?:Google\s*)?reviews?/i);
    return m ? { rating: +m[1].replace(",", "."), count: +m[2].replace(/,/g, "") } : {};
  }

  if (!starEls().length) { console.warn("No reviews showing. Open the business's reviews (Search: click the reviews count; Maps: the Reviews tab) and run this again."); return; }
  const box = scroller();
  console.log("%cHapiTech: collecting Google reviews… keep this tab open.", "font-weight:bold");
  let still = 0, last = -1;
  for (let i = 0; i < 600 && still < 10; i++) {
    expand(); await sleep(450); grab();
    if (box) box.scrollTop = box.scrollHeight; else window.scrollBy(0, Math.round(window.innerHeight * 0.8));
    await sleep(1300);
    if (seen.size === last) still++; else { still = 0; last = seen.size; console.log(`… ${seen.size} reviews so far`); }
  }
  expand(); await sleep(800); grab();
  const slug = (business || "google-business").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 50);
  const out = { format: "hapitech-reviews/1", source: "google", business, url: location.href,
                copied_at: new Date().toISOString(), summary: summary(), count: seen.size, reviews: [...seen.values()] };
  htFinish(out, `${slug}-google-reviews-${out.copied_at.slice(0, 10)}.json`);
  console.log(`%cDone: ${seen.size} reviews${out.summary.count ? " (Google says " + out.summary.count + ")" : ""}`, "font-weight:bold;color:green");

function htFinish(out, filename) {
  const base = (window.__HT_BASE || "").replace(/\/$/, "");
  const save = () => {
    const blob = new Blob([JSON.stringify(out)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: filename });
    document.body.appendChild(a); a.click(); a.remove();
  };
  const panel = document.createElement("div");
  panel.style.cssText = "position:fixed;z-index:2147483647;right:16px;bottom:16px;width:320px;padding:16px;border-radius:16px;background:#16181d;color:#fff;font:14px/1.45 -apple-system,Segoe UI,Roboto,Arial,sans-serif;box-shadow:0 12px 40px rgba(0,0,0,.45)";
  const btn = "display:inline-block;margin:10px 8px 0 0;padding:9px 14px;border-radius:999px;border:0;font:600 13px/1 inherit;cursor:pointer;";
  panel.innerHTML = `<b style="font-size:15px">HapiTech: ${out.count} reviews collected</b><div style="opacity:.75;margin-top:4px">${out.summary && out.summary.count ? (out.source === "google" ? "Google" : "Facebook") + " says " + out.summary.count + "." : ""}</div><div data-msg style="margin-top:6px;opacity:.9"></div>`
    + (base ? `<button data-send style="${btn}background:#fff;color:#16181d">Send to HapiTech</button>` : "")
    + `<button data-dl style="${btn}background:#2c3038;color:#fff">Download file</button><button data-x style="${btn}background:transparent;color:#aaa">Close</button>`;
  document.body.appendChild(panel);
  const msg = t => { panel.querySelector("[data-msg]").textContent = t; };
  panel.querySelector("[data-dl]").onclick = save;
  panel.querySelector("[data-x]").onclick = () => panel.remove();
  const send = panel.querySelector("[data-send]");
  if (send) send.onclick = () => {
    const w = window.open(base + "/admin/reviews/receive", "hapitech_receive");
    let done = false;
    const onMsg = e => {
      if (e.origin !== base) return;
      if (e.data && e.data.type === "ht-ready" && !done) { done = true; w.postMessage({ type: "ht-reviews", data: Object.assign({}, out, { network: undefined }) }, base); msg("Sent ✓ Check the HapiTech tab."); }
    };
    window.addEventListener("message", onMsg);
    setTimeout(() => { if (!done) { msg("Couldn't hand it over (the browser blocked it), so the file has downloaded instead. Upload it in Admin → Reviews → Import."); save(); } }, 20000);
  };
  if (!base) save();
}
})();
