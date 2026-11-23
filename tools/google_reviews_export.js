/* tools/google_reviews_export.js — export a business's Google reviews (with stars, photos and the owner's replies)
   for HapiTech's review import.
   How: open the business on Google Maps (maps.google.com, search the business, click it), open the "Reviews" tab,
   choose Sort → Newest, then press F12 → Console, paste this whole file and press Enter. Leave the tab open;
   it scrolls the reviews list by itself. When it says "Done" a file <business>-google-reviews-<date>.json downloads:
   upload it in HapiTech Admin → Reviews → Import. It only reads the page; nothing is posted or changed. */
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const clean = t => (t || "").replace(/ /g, " ").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  const seen = new Map();                                   // Google review id -> review
  const business = clean((document.querySelector("h1") || {}).innerText || "");

  function scroller() {                                     // the scrollable reviews panel
    let n = document.querySelector("[data-review-id]");
    while (n && n !== document.body) {
      const s = getComputedStyle(n);
      if (/(auto|scroll)/.test(s.overflowY) && n.scrollHeight > n.clientHeight + 40) return n;
      n = n.parentElement;
    }
    return null;
  }
  function expand() {                                       // "More" on long reviews and replies
    document.querySelectorAll('button[aria-label="See more"], button[aria-expanded="false"][jsaction*="expand"], button.w8nwRe')
      .forEach(b => { try { b.click(); } catch (e) {} });
  }
  function bgUrl(el) {
    const m = (el.getAttribute("style") || "").match(/url\(["']?([^"')]+)["']?\)/);
    return m ? m[1].replace(/=w\d+-h\d+[^&]*$/, "=w1600-h1600").replace(/=s\d+[^&]*$/, "=s1600") : null;
  }
  function grab() {
    document.querySelectorAll("div[data-review-id][aria-label]").forEach(el => {
      const id = el.getAttribute("data-review-id");
      const starEl = el.querySelector('[role="img"][aria-label*="star" i], [aria-label*="stars" i]');
      const stars = starEl ? parseInt((starEl.getAttribute("aria-label").match(/(\d)/) || [])[1] || "0", 10) : null;
      // date: the short text next to the stars ("3 months ago", "Edited a year ago")
      let date = "";
      if (starEl) {
        const sib = starEl.parentElement && [...starEl.parentElement.children].map(c => clean(c.innerText)).find(t => /ago$/.test(t));
        date = sib || "";
      }
      if (!date) date = ([...el.querySelectorAll("span")].map(s => clean(s.innerText)).find(t => /^(Edited )?(a|an|\d+) \w+ ago$/.test(t)) || "");
      // owner's reply
      let reply = null;
      const respHead = [...el.querySelectorAll("span, div")].find(s => /^Response from the owner/.test(clean(s.innerText)) && clean(s.innerText).length < 80);
      if (respHead) {
        const box = respHead.parentElement && respHead.parentElement.parentElement || respHead.parentElement;
        const txt = clean(box.innerText).replace(/^Response from the owner\s*/, "");
        const m = txt.match(/^((Edited )?(a|an|\d+) \w+ ago)\s*\n?/);
        reply = { date: m ? m[1] : "", text: clean(m ? txt.slice(m[0].length) : txt) };
      }
      // the review text (Google keeps it in a span with lang; fall back to the longest plain block)
      const textEl = el.querySelector(".wiI7pd") || [...el.querySelectorAll("span[lang], div[lang]")][0];
      let text = clean(textEl ? textEl.innerText : "");
      if (reply && text === reply.text) text = "";
      const photos = [...el.querySelectorAll("button[style*='background-image'], div[style*='background-image']")]
        .filter(b => !respHead || !respHead.parentElement.contains(b)).map(bgUrl).filter(u => u && /googleusercontent/.test(u));
      const tags = [...el.querySelectorAll("span")].map(s => clean(s.innerText)).filter(t => /^(Great price|Reasonable price|Overpriced|Expensive|Inexpensive)$/.test(t));
      const item = { id, author: el.getAttribute("aria-label"), rating: stars, date, text, photos: [...new Set(photos)],
                     price: tags[0] || null, reply, raw: clean(el.innerText) };
      const old = seen.get(id);
      if (!old || item.text.length > old.text.length || (item.reply && !old.reply) || item.photos.length > old.photos.length) seen.set(id, item);
    });
  }
  function summary() {
    const t = document.body.innerText;
    const m = t.match(/(\d\.\d)\s*\n?\s*(?:★+\s*)?\n?\s*\(?([\d,]+)\)?\s*reviews?/i);
    return m ? { rating: +m[1], count: +m[2].replace(/,/g, "") } : {};
  }

  const box = scroller();
  if (!box) { console.warn("Open the business's Reviews tab on Google Maps first (so the reviews list is showing), then run this again."); return; }
  console.log("%cHapiTech: collecting Google reviews… keep this tab open.", "font-weight:bold");
  let still = 0, last = -1;
  for (let i = 0; i < 600 && still < 10; i++) {
    expand(); await sleep(350); grab();
    box.scrollTop = box.scrollHeight;
    await sleep(1200);
    if (seen.size === last) still++; else { still = 0; last = seen.size; console.log(`… ${seen.size} reviews so far`); }
  }
  expand(); await sleep(700); grab();
  const slug = (business || "google-business").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const out = { format: "hapitech-reviews/1", source: "google", business, url: location.href,
                copied_at: new Date().toISOString(), summary: summary(), count: seen.size, reviews: [...seen.values()] };
  const blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
  const link = Object.assign(document.createElement("a"),
    { href: URL.createObjectURL(blob), download: `${slug}-google-reviews-${out.copied_at.slice(0, 10)}.json` });
  document.body.appendChild(link); link.click(); link.remove();
  console.log(`%cDone: ${seen.size} reviews${out.summary.count ? " (Google says " + out.summary.count + ")" : ""} saved to ${link.download}`, "font-weight:bold;color:green");
})();
