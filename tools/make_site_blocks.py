"""tools/make_site_blocks.py — make more of a client site editable in "My website", without changing how it looks.

For each piece of text listed below it: finds it in the site's template (whitespace-insensitive), swaps it for a
block call, and records the block (key, type, label, group, default = the current text) in the order it appears
on the page. It writes the same list to both:
  <site>/static/hapitech/blocks.json        (the site's defaults, used until the client edits something)
  hapitech.dev/utils/site_blocks/<domain>.json (what "My website" lists, in site order)
Run from the hapitech.dev folder:  python tools/make_site_blocks.py ../clients/rolandshandyman.co.uk
Safe to re-run: text that's already a block is left alone and just re-recorded.
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ws(snippet):
    """Regex for an HTML snippet that ignores differences in whitespace."""
    return r"\s+".join(re.escape(t) for t in snippet.split())


def to_text(fragment):
    """HTML fragment -> the plain text a client edits (**bold**, [link](url), line breaks)."""
    t = re.sub(r"<br\s*/?>\s*", "\n", fragment)
    t = re.sub(r"<(strong|b)>(.*?)</\1>", r"**\2**", t, flags=re.S)
    t = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"[\2](\1)", t, flags=re.S)
    t = re.sub(r"<[^>]+>", "", t)
    t = "\n".join(" ".join(line.split()) for line in t.split("\n"))
    return html.unescape(t).strip()


def page_text(fragment):
    """A legal page's main content -> editable text: '## ' headings, '- ' bullets, blank lines between paragraphs."""
    out = []
    for m in re.finditer(r"<(h2|h3|p|li)[^>]*>(.*?)</\1>", fragment, flags=re.S):
        tag, inner = m.group(1), to_text(m.group(2))
        if not inner:
            continue
        out.append(("## " if tag in ("h2", "h3") else "- " if tag == "li" else "") + inner.replace("\n", " "))
    text, prev_li = [], False
    for line in out:                       # keep bullets together, blank line between everything else
        li = line.startswith("- ")
        if text and not (li and prev_li):
            text.append("")
        text.append(line)
        prev_li = li
    return "\n".join(text)


class Site:
    def __init__(self, site_dir):
        self.dir = site_dir
        self.path = os.path.join(site_dir, "templates", "home.html")
        self.t = open(self.path, encoding="utf-8").read()
        self.defs = {}

    def rec(self, key, typ, label, group, default, **kw):
        self.defs[key] = dict(key=key, type=typ, label=label, group=group, default=default, **kw)

    def text(self, key, snippet, label, group, max_length=None, rich=False, paras=False, typ=None):
        """Replace `snippet` (exact HTML, whitespace-insensitive) with a block call."""
        call = (f"{{{{ rich('{key}', paras=True) }}}}" if paras else f"{{{{ rich('{key}') }}}}" if rich
                else f"{{{{ block('{key}') }}}}")
        if call in self.t:
            m = None
        else:
            found = list(re.finditer(ws(snippet), self.t))
            if len(found) != 1:
                raise SystemExit(f"{key}: expected 1 match, found {len(found)}")
            m = found[0]
        default = self.defaults_cache.get(key) if m is None else (
            "\n\n".join(to_text(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", snippet, flags=re.S)) if paras else to_text(snippet))
        if m is not None:
            self.t = self.t[:m.start()] + call + self.t[m.end():]
        self.rec(key, typ or ("longtext" if (paras or rich or len(default) > 70) else "text"), label, group, default,
                 max_length=max_length)

    def list(self, key, items_html, label, group, tag="span"):
        call = f"{{% for x in items('{key}') %}}<{tag}>{{{{ x }}}}</{tag}>{{% endfor %}}"
        if call in self.t:
            default = self.defaults_cache.get(key)
        else:
            found = list(re.finditer(ws(items_html), self.t))
            if len(found) != 1:
                raise SystemExit(f"{key}: expected 1 match, found {len(found)}")
            default = [to_text(x) for x in re.findall(rf"<{tag}>(.*?)</{tag}>", items_html, flags=re.S)]
            m = found[0]
            self.t = self.t[:m.start()] + call + self.t[m.end():]
        self.rec(key, "list", label, group, default, help="One per line.")

    def existing(self, group_of):
        """Blocks already in the template as block('key', 'default') (the original services ones)."""
        for m in re.finditer(r"block\('([^']+)',\s*'((?:[^'\\]|\\.)*)'\)", self.t):
            key, default = m.group(1), m.group(2).replace("\\'", "'")
            g, label, ml = group_of(key, default)
            self.rec(key, "longtext" if len(default) > 70 else "text", label, g, default, max_length=ml)

    def legal(self, name, label):
        p = os.path.join(self.dir, "templates", f"{name}.html")
        t = open(p, encoding="utf-8").read()
        key = f"legal.{name}.page"
        if f"edited('{key}')" not in t:
            m = re.search(r"(<h1>.*?</h1>\s*(?:<p[^>]*>\s*Last updated[^<]*</p>)?)(.*?)(\s*</section>\s*</main>|\s*</div>\s*</main>)", t, flags=re.S)
            if not m:
                raise SystemExit(f"{name}: couldn't find the page content")
            body = m.group(2)
            default = page_text(body)
            t = t[:m.start(2)] + f"\n{{% if edited('{key}') %}}{{{{ page('{key}') }}}}{{% else %}}" + body + "{% endif %}" + t[m.end(2):]
            open(p, "w", encoding="utf-8").write(t)
        else:
            default = self.defaults_cache.get(key)
        self.rec(key, "page", label, "Legal pages", default,
                 help="## starts a heading, - starts a bullet point, **bold**, [link text](https://…). Leave a blank line between paragraphs.")

    def save(self, domain):
        open(self.path, "w", encoding="utf-8").write(self.t)
        order = {k: self.t.find(f"'{k}'") for k in self.defs}
        legal = [d for k, d in self.defs.items() if k.startswith("legal.")]
        main = sorted((d for k, d in self.defs.items() if not k.startswith("legal.")), key=lambda d: order[d["key"]])
        out = [dict(d, sort=i) for i, d in enumerate(main + legal)]
        os.makedirs(os.path.join(self.dir, "static", "hapitech"), exist_ok=True)
        for p in (os.path.join(self.dir, "static", "hapitech", "blocks.json"),
                  os.path.join(ROOT, "utils", "site_blocks", f"{domain}.json")):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{domain}: {len(out)} editable blocks")

    @property
    def defaults_cache(self):
        p = os.path.join(self.dir, "static", "hapitech", "blocks.json")
        try:
            return {d["key"]: d["default"] for d in json.load(open(p, encoding="utf-8"))}
        except (OSError, ValueError):
            return {}


def rolands(site_dir):
    s = Site(site_dir)
    s.text("hero.title", "Home maintenance done right", "Top of page: heading", "Top of page", 60)
    s.text("hero.text", "Fast, friendly, and tidy — everything from small fixes to carefully finished projects.",
           "Top of page: text under the heading", "Top of page", 160)
    titles = {"furniture": "Furniture Assembly", "wall": "Wall Mounting", "electrical": "Minor Electrical Work", "plumbing": "Minor Plumbing Work"}

    def grp(key, default):
        svc = key.split(".")[1]
        if key.endswith(".title"):
            return "Services", f"{titles.get(svc, svc)}: heading", 40
        return "Services", f"{titles.get(svc, svc)}: intro", 260
    s.existing(grp)
    # accordions, section by section (titles like "What's Included" repeat, so work inside each section)
    acc = re.compile(r'(<button class="accordion-toggle" type="button">\s*<span>)(.*?)(</span>.*?<div class="accordion-content">\s*<p>)(.*?)(</p>)', re.S)
    for svc, name in titles.items():
        start = s.t.find(f"block('services.{svc}.title'")
        end = s.t.find("</section>", start)
        sec, n, out, pos = s.t[start:end], 0, [], 0
        for m in acc.finditer(sec):
            n += 1
            k = f"services.{svc}.acc{n}"
            if "block(" in m.group(2):
                s.rec(f"{k}.title", "text", f"{name}: dropdown {n} title", "Services", s.defaults_cache.get(f"{k}.title"), max_length=50)
                s.rec(f"{k}.text", "longtext", f"{name}: dropdown {n} text", "Services", s.defaults_cache.get(f"{k}.text"), max_length=600)
                continue
            s.rec(f"{k}.title", "text", f"{name}: dropdown {n} title", "Services", to_text(m.group(2)), max_length=50)
            s.rec(f"{k}.text", "longtext", f"{name}: dropdown {n} text", "Services", to_text(m.group(4)), max_length=600)
            out.append(sec[pos:m.start()] + m.group(1) + f"{{{{ block('{k}.title') }}}}" + m.group(3)
                       + f"\n\t\t\t\t\t\t\t\t{{{{ rich('{k}.text') }}}}\n\t\t\t\t\t\t\t" + m.group(5))
            pos = m.end()
        if out:
            s.t = s.t[:start] + "".join(out) + sec[pos:] + s.t[end:]
    s.text("area.title", '<h2>Service Area</h2>', "Service area: heading", "Service area", 40)
    s.t = s.t.replace("{{ block('area.title') }}", "<h2>{{ block('area.title') }}</h2>", 1) if "<h2>{{ block('area.title') }}</h2>" not in s.t else s.t
    s.text("area.text", """<p>
							Roland’s Handyman is based in <strong>Wolverhampton</strong> and covers
							<strong>up to a 30-mile radius</strong> for most jobs.
						</p>

						<p>
							This includes Wolverhampton and surrounding towns and villages.
							If your job falls outside this area, it can still be arranged —
							a <strong>small additional mileage charge</strong> will apply per mile.
						</p>

						<p>
							If you’re unsure whether your location is covered, feel free to get in touch.
						</p>""", "Service area: text", "Service area", 900, paras=True)
    s.text("gallery.title", "<h2>Featured Work</h2>", "Gallery: section name", "Gallery", 40)
    s.t = s.t.replace("{{ block('gallery.title') }}", "<h2>{{ block('gallery.title') }}</h2>", 1) if "<h2>{{ block('gallery.title') }}</h2>" not in s.t else s.t
    s.text("gallery.sub", "A few recent jobs — tap any photo to browse the full gallery.", "Gallery: line under the name", "Gallery", 120)
    s.text("posts.title", "<h2>Latest Work</h2>", "Latest work: section name", "Latest work", 40)
    s.t = s.t.replace("{{ block('posts.title') }}", "<h2>{{ block('posts.title') }}</h2>", 1) if "<h2>{{ block('posts.title') }}</h2>" not in s.t else s.t
    s.text("reviews.title", "<h2>Customer Reviews</h2>", "Reviews: section name", "Reviews", 40)
    s.t = s.t.replace("{{ block('reviews.title') }}", "<h2>{{ block('reviews.title') }}</h2>", 1) if "<h2>{{ block('reviews.title') }}</h2>" not in s.t else s.t
    s.text("contact.title", "<h3>Request a quote</h3>", "Quote form: heading", "Quote form", 40)
    s.t = s.t.replace("{{ block('contact.title') }}", "<h3>{{ block('contact.title') }}</h3>", 1) if "<h3>{{ block('contact.title') }}</h3>" not in s.t else s.t
    s.legal("privacy", "Privacy policy")
    s.legal("terms", "Terms of service")
    s.save("rolandshandyman.co.uk")


def rayg(site_dir):
    s = Site(site_dir)
    s.text("hero.title", "Professional Home Improvement Services", "Top of page: heading", "Top of page", 60)
    s.text("hero.text", "Bathrooms • Kitchens • Carpentry • Loft Conversions • Extensions • Paving", "Top of page: text under the heading", "Top of page", 160)
    s.text("about.title", "<h2>About Me</h2>", "About: heading", "About", 40)
    s.t = s.t.replace("{{ block('about.title') }}", "<h2>{{ block('about.title') }}</h2>", 1) if "<h2>{{ block('about.title') }}</h2>" not in s.t else s.t
    s.text("about.text", """<p>
					I'm based in the Wolverhampton area, offering a wide range of handyman
					services to homes and businesses across the local area. No job is too
					small — from a single repair to a full room refresh, I supply an honest,
					reliable service you can depend on.
				</p>

				<p>
					Get in touch to have a chat about your next job — I'm always happy to help.
				</p>""", "About: text", "About", 900, paras=True)
    s.list("about.tags", """<span>Painting &amp; Decorating</span>
					<span>Laminate Flooring</span>
					<span>Woodwork &amp; Carpentry</span>
					<span>Decking</span>
					<span>Curtain Poles &amp; Blinds</span>
					<span>TV Wall Mounting</span>
					<span>Furniture Assembly</span>
					<span>Door Installation</span>
					<span>Minor Electrical</span>
					<span>Plumbing</span>
					<span>Kitchen Refurbishment</span>
					<span>Bathroom Refurbishment</span>""", "About: the little tags", "About")
    s.text("services.heading", "<h2>Our Services</h2>", "Services: section name", "Services", 40)
    s.t = s.t.replace("{{ block('services.heading') }}", "<h2>{{ block('services.heading') }}</h2>", 1) if "<h2>{{ block('services.heading') }}</h2>" not in s.t else s.t
    names = {"bathrooms": "Bathrooms", "kitchens": "Kitchens", "carpentry": "Carpentry", "lofts": "Loft Conversions",
             "extensions": "Extensions", "paving": "Paving & Landscaping"}

    def grp(key, default):
        svc = key.split(".")[1]
        return ("Services", f"{names.get(svc, svc)}: name", 32) if key.endswith(".title") else ("Services", f"{names.get(svc, svc)}: description", 110)
    s.existing(grp)
    s.text("promo1.title", "<h2>Full Residential &amp; Commercial Renovations</h2>", "Feature box 1: heading", "Feature boxes", 60)
    s.t = s.t.replace("{{ block('promo1.title') }}", "<h2>{{ block('promo1.title') }}</h2>", 1) if "<h2>{{ block('promo1.title') }}</h2>" not in s.t else s.t
    s.text("promo1.text", """Renovations are a big part of what I do. I offer full renovation and
				remodelling services for both residential and commercial properties,
				taking care of the entire process — from strip-out to finishing touches,
				including painting, tiling, plastering and more. I always aim to complete
				work on time and within budget, so get in touch to find out how I can help
				with your next project.""", "Feature box 1: text", "Feature boxes", 700, typ="longtext")
    s.text("promo2.title", "<h2>A Fresh Lick of Paint</h2>", "Feature box 2: heading", "Feature boxes", 60)
    s.t = s.t.replace("{{ block('promo2.title') }}", "<h2>{{ block('promo2.title') }}</h2>", 1) if "<h2>{{ block('promo2.title') }}</h2>" not in s.t else s.t
    s.text("promo2.text", """Getting a smooth, professional finish takes more than a steady hand —
				it's easy to end up disappointed if you're not sure what you're doing.
				I'll turn up on time, work cleanly, finish to a high standard, and tidy
				up after myself. All you need to do is put the kettle on.""", "Feature box 2: text", "Feature boxes", 700, typ="longtext")
    s.text("intro.title", "Quality Work. Honest Service.", "Intro: heading", "Intro", 60)
    s.text("intro.text", """Whether you're renovating a kitchen, fitting a new bathroom, building an extension or simply
			need reliable property maintenance, RayG Handyman Services delivers professional workmanship
			with attention to every detail.""", "Intro: text", "Intro", 500, typ="longtext")
    s.text("gallery.title", "Our Work", "Gallery: section name", "Gallery", 40)
    s.text("gallery.sub", "A few recent jobs — tap any photo to browse the full gallery.", "Gallery: line under the name", "Gallery", 120)
    s.text("posts.title", "<h2>Latest Work</h2>", "Latest work: section name", "Latest work", 40)
    s.t = s.t.replace("{{ block('posts.title') }}", "<h2>{{ block('posts.title') }}</h2>", 1) if "<h2>{{ block('posts.title') }}</h2>" not in s.t else s.t
    s.text("reviews.title", """<h2>
			Customer Reviews
		</h2>""", "Reviews: section name", "Reviews", 40)
    s.t = s.t.replace("{{ block('reviews.title') }}", "<h2>{{ block('reviews.title') }}</h2>", 1) if "<h2>{{ block('reviews.title') }}</h2>" not in s.t else s.t
    s.text("cta.title", "Ready to Start Your Next Project?", "Call to action: heading", "Call to action", 60)
    s.text("cta.text", "Get in touch today for a free, no-obligation quotation.", "Call to action: text", "Call to action", 160)
    s.text("footer.tagline", "Professional Home Improvements", "Footer: tagline", "Footer", 60)
    s.text("footer.payment", "Payment accepted: Cash / Bank Transfer", "Footer: payment line", "Footer", 80)
    s.text("contact.title", "<h2>Request a Free Quote</h2>", "Quote form: heading", "Quote form", 40)
    s.t = s.t.replace("{{ block('contact.title') }}", "<h2>{{ block('contact.title') }}</h2>", 1) if "<h2>{{ block('contact.title') }}</h2>" not in s.t else s.t
    s.legal("privacy", "Privacy policy")
    s.legal("terms", "Terms of service")
    s.save("rayghandymanservice.co.uk")


if __name__ == "__main__":
    d = os.path.abspath(sys.argv[1])
    {"rolandshandyman.co.uk": rolands, "rayghandymanservice.co.uk": rayg}[os.path.basename(d)](d)
