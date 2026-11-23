/* tools/facebook_reviews_export.js (v3) — export a Facebook page's reviews for HapiTech's review import.
   How: open the page's Reviews tab (e.g. facebook.com/RayGHandymanservice/reviews), press F12 → Console,
   paste this whole file, press Enter. Leave the tab open; it scrolls by itself. When it says "Done" a file
   <page>-facebook-reviews-<date>.json downloads: upload it in HapiTech Admin → Reviews → Import.
   It only reads the page (nothing is posted or changed). Stop it any time by reloading the page.

   v3: each review is found from its "X recommends Y" headline (so the word "recommend" in the review text no longer
   confuses it); names come from the profile link (no hidden "Facebook" text); and, as a safety net, it keeps the
   review data Facebook's own page downloads while scrolling, so anything the page-reading misses can be recovered. */
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const clean = t => (t || "").replace(/ /g, " ").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  const HEAD = /^(.{1,80}?)\s+(recommends|doesn't recommend|does not recommend)\s+(.{1,120})$/;
  const posts = new Map();
  const pageName = clean((document.querySelector("h1") || {}).innerText || "");

  // --- safety net: keep Facebook's own review data as the page loads more (only responses mentioning recommendations)
  const net = [];
  const keep = (url, text) => { if (/graphql/.test(url || "") && /recommend/i.test(text || "") && net.length < 400) net.push(text.slice(0, 3000000)); };
  const xo = XMLHttpRequest.prototype.open, xs = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__u = u; return xo.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function () { this.addEventListener("load", () => { try { keep(this.__u, this.responseText); } catch (e) {} }); return xs.apply(this, arguments); };
  const fo = window.fetch;
  window.fetch = function (input) { return fo.apply(this, arguments).then(r => { try { const u = typeof input === "string" ? input : input.url; if (/graphql/.test(u)) r.clone().text().then(t => keep(u, t)); } catch (e) {} return r; }); };
  // reviews already on the page when we start came with the page itself
  document.querySelectorAll('script[type="application/json"]').forEach(s => { if (/recommendation/i.test(s.textContent)) net.push(s.textContent.slice(0, 3000000)); });

  function clickAll(re) {
    document.querySelectorAll('div[role="button"], span[role="button"]').forEach(b => {
      const t = (b.innerText || "").trim();
      if (t.length < 40 && re.test(t) && !b.__ht) { b.__ht = 1; try { b.click(); } catch (e) {} }
    });
  }
  function headers() {                                   // the smallest elements whose own text is "X recommends Y."
    const out = [];
    document.querySelectorAll("h2, h3, h4, strong, span, div").forEach(el => {
      const tc = el.textContent || "";
      if (tc.length > 320 || !/recommend/i.test(tc)) return;          // cheap check before the slow one
      const t = clean(el.innerText);
      if (t.length > 240 || t.includes("\n") || !HEAD.test(t.replace(/\.$/, ""))) return;
      if ([...el.children].some(c => HEAD.test(clean(c.innerText).replace(/\.$/, "")))) return;
      out.push(el);
    });
    return out;
  }
  function permalink(a) {
    try {
      const u = new URL(a.href);
      const keepQ = ["story_fbid", "id", "fbid"].filter(k => u.searchParams.get(k)).map(k => k + "=" + u.searchParams.get(k)).join("&");
      return u.origin + u.pathname + (keepQ ? "?" + keepQ : "");
    } catch (e) { return a.href; }
  }
  function timeOf(a) {
    if (!a) return "";
    return clean(a.getAttribute("aria-label") || (a.querySelector("[aria-label]") || { getAttribute: () => "" }).getAttribute("aria-label") || a.innerText);
  }
  function grab() {
    const hs = headers();
    const set = new Set(hs);
    const count = n => hs.reduce((k, h) => k + (n.contains(h) ? 1 : 0), 0);
    hs.forEach(h => {
      let post = h;                                       // grow to the largest block holding just this headline
      while (post.parentElement && post.parentElement !== document.body && count(post.parentElement) === 1) post = post.parentElement;
      if (post === h) return;
      const head = clean(h.innerText).replace(/\.$/, "");
      const m = head.match(HEAD);
      const prof = h.querySelector("a[href]") || post.querySelector('a[href*="facebook.com/"][role="link"]');
      const author = clean(prof && prof.innerText && head.startsWith(clean(prof.innerText)) ? prof.innerText : m[1]).replace(/^(ok)?(Facebook)+/i, "");
      const link = post.querySelector('a[href*="/posts/"], a[href*="story_fbid"], a[href*="/permalink/"], a[href*="pfbid"]');
      const comments = [...post.querySelectorAll('[role="article"]')];
      let raw = clean(post.innerText);
      comments.forEach(c => { raw = raw.replace(clean(c.innerText), ""); });
      const msg = post.querySelector('[data-ad-comet-preview="message"], [data-ad-preview="message"]');
      const photos = [...post.querySelectorAll("img")].filter(i => !i.closest('[role="article"]') && (i.naturalWidth || i.width) >= 180 && /fbcdn|scontent/.test(i.src)).map(i => i.src);
      const time = timeOf(link);
      const key = link ? permalink(link) : "h:" + author + "|" + time;
      const replies = comments.map(c => ({
        label: c.getAttribute("aria-label") || "",
        text: clean(c.innerText),
        time: timeOf(c.querySelector('a[href*="comment_id"]')),
      }));
      const item = { id: key, author, recommends: m[2] === "recommends", header: head, time,
                     text: clean(msg ? msg.innerText : ""), photos, replies, raw };
      const old = posts.get(key);
      if (!old || item.text.length > old.text.length || replies.length > old.replies.length || photos.length > old.photos.length) posts.set(key, item);
    });
  }
  function summary() {
    const t = document.body.innerText;
    const m = t.match(/(\d{1,3})%\s*recommend\s*\(?([\d,]+)\s*Reviews?\)?/i);
    return m ? { recommend_pct: +m[1], count: +m[2].replace(/,/g, "") } : {};
  }

  console.log("%cHapiTech: collecting Facebook reviews… keep this tab open.", "font-weight:bold");
  const top = summary();
  let still = 0, last = -1;
  for (let i = 0; i < 500 && still < 12; i++) {
    clickAll(/^(See more|View more comments|View \d+ more comments?|View \d+ repl(y|ies)|\d+ repl(y|ies)|View all \d+ replies)$/i);
    await sleep(600); grab();
    window.scrollBy(0, Math.round(window.innerHeight * 0.6));
    await sleep(1400);
    if (posts.size === last) still++; else { still = 0; last = posts.size; console.log(`… ${posts.size} reviews so far`); }
  }
  clickAll(/^See more$/i); await sleep(900); grab();
  XMLHttpRequest.prototype.open = xo; XMLHttpRequest.prototype.send = xs; window.fetch = fo;
  const page = (location.pathname.split("/").filter(Boolean)[0] || "facebook-page").toLowerCase();
  const sum = Object.keys(top).length ? top : summary();
  const out = { format: "hapitech-reviews/1", source: "facebook", page, business: pageName, url: location.href,
                copied_at: new Date().toISOString(), summary: sum, count: posts.size, reviews: [...posts.values()], network: net };
  const blob = new Blob([JSON.stringify(out)], { type: "application/json" });
  const link = Object.assign(document.createElement("a"),
    { href: URL.createObjectURL(blob), download: `${page}-facebook-reviews-${out.copied_at.slice(0, 10)}.json` });
  document.body.appendChild(link); link.click(); link.remove();
  console.log(`%cDone: ${posts.size} reviews${sum.count ? " (Facebook says " + sum.count + ")" : ""} saved to ${link.download}`, "font-weight:bold;color:green");
})();
