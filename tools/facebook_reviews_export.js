/* tools/facebook_reviews_export.js (v2) — export a Facebook page's reviews for HapiTech's review import.
   How: open the page's Reviews tab (e.g. facebook.com/RayGHandymanservice/reviews), press F12 → Console,
   paste this whole file, press Enter. Leave the tab open; it scrolls by itself. When it says "Done" a file
   <page>-facebook-reviews-<date>.json downloads: upload it in HapiTech Admin → Reviews → Import.
   It only reads the page (nothing is posted or changed). Stop it any time by reloading the page.

   v2: each review POST is one unit (Facebook marks comments, not posts, as "articles", so v1 collected replies
   one by one). Posts are found by their permalink; replies are the comments inside each post. */
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const clean = t => (t || "").replace(/ /g, " ").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  const posts = new Map();                         // permalink -> review (Facebook unloads old posts as you scroll)
  const pageName = clean((document.querySelector("h1") || {}).innerText || "");

  function clickAll(re) {
    document.querySelectorAll('div[role="button"], span[role="button"]').forEach(b => {
      const t = (b.innerText || "").trim();
      if (t.length < 40 && re.test(t)) { try { b.click(); } catch (e) {} }
    });
  }
  function permalink(a) {
    try { const u = new URL(a.href); return u.origin + u.pathname + (u.searchParams.get("story_fbid") ? "?story_fbid=" + u.searchParams.get("story_fbid") + "&id=" + u.searchParams.get("id") : ""); }
    catch (e) { return a.href; }
  }
  // the post containing an element = the largest ancestor that holds exactly one review header ("… recommends …")
  function postOf(el) {
    let best = null, n = el;
    while (n && n !== document.body) {
      const t = n.innerText || "";
      const m = t.match(/\b(recommends|doesn't recommend|does not recommend)\b/g);
      if (m && m.length === 1) best = n;
      if (m && m.length > 1) break;
      n = n.parentElement;
    }
    return best;
  }
  function timeOf(a) {
    return clean(a.getAttribute("aria-label") || (a.querySelector("[aria-label]") || {}).getAttribute?.("aria-label") || a.innerText);
  }
  function grab() {
    const links = document.querySelectorAll('a[href*="/posts/"], a[href*="story_fbid"], a[href*="/permalink/"], a[href*="/reviews/"][href*="pfbid"]');
    links.forEach(a => {
      const post = postOf(a);
      if (!post || post.__ht) return;
      const comments = [...post.querySelectorAll('[role="article"]')];
      const commentText = comments.map(c => clean(c.innerText));
      let raw = clean(post.innerText);
      commentText.forEach(c => { raw = raw.replace(c, ""); });
      const head = raw.split("\n").find(l => /\b(recommends|doesn't recommend|does not recommend)\b/.test(l)) || "";
      const author = clean(head.split(/\s+(recommends|doesn't recommend|does not recommend)\b/)[0]);
      const msg = post.querySelector('[data-ad-comet-preview="message"], [data-ad-preview="message"]');
      const photos = [...post.querySelectorAll("img")].filter(i => !i.closest('[role="article"]') && (i.naturalWidth || i.width) >= 180 && /fbcdn|scontent/.test(i.src)).map(i => i.src);
      const key = permalink(a);
      const replies = comments.map(c => ({
        label: c.getAttribute("aria-label") || "",
        text: clean(c.innerText),
        time: (() => { const t = c.querySelector('a[href*="comment_id"]'); return t ? timeOf(t) : ""; })(),
      }));
      const old = posts.get(key);
      const item = { id: key, author, recommends: !/doesn't recommend|does not recommend/.test(head), header: head,
                     time: timeOf(a), text: clean(msg ? msg.innerText : ""), photos, replies, raw };
      if (!old || item.text.length > old.text.length || replies.length > old.replies.length || photos.length > old.photos.length) posts.set(key, item);
    });
  }
  function summary() {
    const t = document.body.innerText;
    const m = t.match(/(\d{1,3})%\s*recommend\s*\(?([\d,]+)\s*Reviews?\)?/i) || t.match(/Rating\s*·\s*(\d{1,3})%\s*recommend\s*\(([\d,]+)/i);
    return m ? { recommend_pct: +m[1], count: +m[2].replace(/,/g, "") } : {};
  }

  console.log("%cHapiTech: collecting Facebook reviews… keep this tab open.", "font-weight:bold");
  const top = summary();
  let still = 0, last = -1;
  for (let i = 0; i < 500 && still < 10; i++) {
    clickAll(/^(See more|View more comments|View \d+ more comments?|View \d+ repl(y|ies)|\d+ repl(y|ies)|View all \d+ replies)$/i);
    await sleep(500); grab();
    window.scrollBy(0, Math.round(window.innerHeight * 0.7));
    await sleep(1300);
    if (posts.size === last) still++; else { still = 0; last = posts.size; console.log(`… ${posts.size} reviews so far`); }
  }
  clickAll(/^See more$/i); await sleep(800); grab();
  const page = (location.pathname.split("/").filter(Boolean)[0] || "facebook-page").toLowerCase();
  const out = { format: "hapitech-reviews/1", source: "facebook", page, business: pageName, url: location.href,
                copied_at: new Date().toISOString(), summary: Object.keys(top).length ? top : summary(),
                count: posts.size, reviews: [...posts.values()] };
  if (!posts.size) console.warn("Couldn't find any review posts. Scroll to the first review and run it again, or send Claude a screenshot.");
  const blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
  const link = Object.assign(document.createElement("a"),
    { href: URL.createObjectURL(blob), download: `${page}-facebook-reviews-${out.copied_at.slice(0, 10)}.json` });
  document.body.appendChild(link); link.click(); link.remove();
  console.log(`%cDone: ${posts.size} reviews${out.summary.count ? " (Facebook says " + out.summary.count + ")" : ""} saved to ${link.download}`, "font-weight:bold;color:green");
})();
