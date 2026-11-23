/* tools/facebook_reviews_export.js — copy a Facebook page's reviews into one file, for HapiTech's review import.
   How: open the page's Reviews tab (e.g. facebook.com/RayGHandymanservice/reviews) in Chrome or Firefox,
   press F12 → Console, paste this whole file, press Enter. Leave the tab open; it scrolls by itself.
   When it says "Done", a file called <page>-facebook-reviews-<date>.json downloads. Send that file to Claude.
   It only reads what's on your screen (nothing is posted or changed), and you can stop it any time: reload the page. */
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const seen = new Map();                        // review text -> data (Facebook removes old ones as you scroll)
  const clean = t => (t || "").replace(/ /g, " ").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  const isTop = el => !el.parentElement.closest('[role="article"]');

  function expand() {                             // open every "See more" so we get the whole review
    document.querySelectorAll('div[role="button"], span[role="button"]').forEach(b => {
      if (/^(See more|See More|Vairāk|Rādīt vairāk)$/.test(b.innerText.trim())) { try { b.click(); } catch (e) {} }
    });
  }
  function grab() {
    document.querySelectorAll('[role="article"]').forEach(a => {
      if (!isTop(a)) return;
      const replies = [...a.querySelectorAll('[role="article"]')].map(r => clean(r.innerText)).filter(Boolean);
      let text = clean(a.innerText);
      replies.forEach(r => { text = text.replace(r, "").trim(); });            // keep the review and its replies apart
      if (!text || text.length < 3) return;
      const key = text.slice(0, 160);
      const old = seen.get(key);
      if (!old || text.length > old.text.length || replies.length > old.replies.length) {
        const time = a.querySelector('a[href*="/posts/"], a[href*="story_fbid"], a[aria-label] abbr, abbr');
        seen.set(key, { text, replies, time: time ? (time.getAttribute("aria-label") || time.title || time.innerText) : "" });
      }
    });
  }
  console.log("%cHapiTech: collecting reviews… keep this tab open.", "font-weight:bold");
  let still = 0, last = 0;
  for (let i = 0; i < 400 && still < 8; i++) {
    expand(); await sleep(400); grab();
    window.scrollBy(0, Math.round(window.innerHeight * 0.8));
    await sleep(1200);
    if (seen.size === last) still++; else { still = 0; last = seen.size; console.log(`… ${seen.size} reviews so far`); }
  }
  expand(); await sleep(600); grab();
  const page = (location.pathname.split("/").filter(Boolean)[0] || "facebook-page").toLowerCase();
  const out = { page, url: location.href, copied_at: new Date().toISOString(), count: seen.size, reviews: [...seen.values()] };
  const blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
  const link = Object.assign(document.createElement("a"),
    { href: URL.createObjectURL(blob), download: `${page}-facebook-reviews-${out.copied_at.slice(0, 10)}.json` });
  document.body.appendChild(link); link.click(); link.remove();
  console.log(`%cDone: ${seen.size} reviews saved to ${link.download}`, "font-weight:bold;color:green");
})();
