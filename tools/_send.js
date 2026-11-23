/* shared ending for the review export scripts (inlined by the admin page / build): show a small panel with
   "Send to HapiTech" (opens HapiTech admin and hands the reviews over) and "Download file". */
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
