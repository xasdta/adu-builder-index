"""Generate the static site from data/builders.json into site/.

Plain HTML/CSS, relative links (works at any base path), JSON-LD for
search/AI citation, honest methodology and disclaimers throughout.
"""
import html
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = json.load(open(ROOT / "data" / "builders.json"))
SITE = ROOT / "docs"
STATS = DATA["stats"]
BUILDERS = DATA["builders"]
TODAY = time.strftime("%B %d, %Y")
CONTACT_EMAIL = "xasdta@gmail.com"
CLAIM_URL = (f"mailto:{CONTACT_EMAIL}?subject=Claim%20my%20builder%20profile"
             "&body=Company%20name%3A%0AWA%20license%20number%3A%0AWebsite%3A%0A"
             "What%20should%20we%20add%20or%20correct%3F%0A")
RESERVE_URL = (f"mailto:{CONTACT_EMAIL}?subject=Founding%20featured%20slot%20request"
               "&body=Company%20name%3A%0AWA%20license%20number%3A%0AWebsite%3A%0A"
               "Phone%3A%0AOne-line%20blurb%20for%20your%20featured%20card%3A%0A")
# Set to a Stripe Payment Link to take $99/mo payments directly on the site.
STRIPE_LINK = None
# Web3Forms access key (web3forms.com) — when set, contact buttons use the
# on-site form at get-featured.html instead of mailto links.
WEB3FORMS_KEY = None
FORM_URL = "get-featured.html"
FEATURE_URL = STRIPE_LINK or (FORM_URL if WEB3FORMS_KEY else RESERVE_URL)
if WEB3FORMS_KEY:
    CLAIM_URL = FORM_URL
FEATURED_SLOTS = 3
_featured_path = ROOT / "data" / "featured.json"
FEATURED = (json.load(open(_featured_path))["builders"]
            if _featured_path.exists() else [])
BY_SLUG = {b["slug"]: b for b in BUILDERS}


def featured_section(depth=0):
    pre = "../" * depth
    cards = []
    for f in FEATURED[:FEATURED_SLOTS]:
        b = BY_SLUG.get(f["slug"])
        if not b:
            continue
        contact = ""
        if f.get("website"):
            contact = f'<a class="button" href="{esc(f["website"])}">Visit website</a>'
        cards.append(f"""<div class="fcard">
<p class="flabel">Featured · paid placement</p>
<h3><a href="{pre}builders/{b['slug']}.html">{esc(b['name'])}</a></h3>
<p class="fstat">{b['permits_completed']} completed ADU permits on record · {license_chip(b)}</p>
<p>{esc(f.get('blurb', ''))}</p>
{contact}
</div>""")
    open_slots = FEATURED_SLOTS - len(cards)
    if not cards:
        return f"""<section id="featured">
<div class="fbanner">
  <div>
    <p class="flabel">Featured builders · {open_slots} founding slots</p>
    <p>Verified builders get top placement here — clearly labeled, never affecting the rankings below. Founding rate: <strong>$99/mo, locked for life</strong>.</p>
  </div>
  <a class="button" href="{pre}for-builders.html">Get featured →</a>
</div>
</section>"""
    if open_slots > 0:
        cards.append(f"""<div class="fcard open">
<p class="flabel">{open_slots} founding slot{"s" if open_slots > 1 else ""} open</p>
<p><strong>$99/mo, locked for life.</strong> Top placement, license-verified, rankings never affected.</p>
<a class="button" href="{pre}for-builders.html">Get featured →</a>
</div>""")
    return f"""<section id="featured">
<h2>Featured builders</h2>
<p class="fine">Paid placements, clearly labeled. Being featured never changes a builder's rank in the table below — <a href="{pre}methodology.html">see methodology</a>.</p>
<div class="featured-grid">{''.join(cards)}</div>
</section>"""


def esc(s):
    return html.escape(str(s or ""))


def money(v):
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return "—"


def license_chip(b):
    lic = b.get("license")
    if not lic:
        return '<span class="chip chip-na" title="No exact match found in WA L&amp;I contractor registry — the builder may be licensed under a different business name">license unmatched</span>'
    if lic["status"] == "ACTIVE":
        return f'<span class="chip chip-ok" title="WA L&amp;I license {esc(lic["number"])}, expires {esc(lic["expires"])}">license active</span>'
    return f'<span class="chip chip-warn" title="WA L&amp;I reports status {esc(lic["status"])} for license {esc(lic["number"])}">license {esc(lic["status"].lower())}</span>'


SITE_BASE = "https://xasdta.github.io/adu-builder-index"


def rel(url, pre):
    """Prefix site-relative URLs with the page's depth prefix."""
    return url if url.startswith(("mailto:", "http", "#")) else pre + url


def page(title, desc, body, depth=0, canonical=None, jsonld=None):
    pre = "../" * depth
    ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{f'<link rel="canonical" href="{esc(canonical)}">' if canonical else ''}
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;700;800&family=Source+Sans+3:ital,wght@0,400;0,600;1,400&family=Spline+Sans+Mono:wght@400;600&display=swap">
<link rel="stylesheet" href="{pre}style.css?v={STATS['generated']}">
{ld}
</head>
<body>
<header class="top">
  <a class="brand" href="{pre}index.html">ADU Builder Index</a>
  <nav>
    <a href="{pre}index.html#rankings">Rankings</a>
    <a href="{pre}methodology.html">Methodology</a>
    <a href="{pre}for-builders.html" class="cta">For builders</a>
  </nav>
</header>
<main>
{body}
</main>
<footer>
  <p><strong>ADU Builder Index</strong> — permit-verified accessory dwelling unit builders. Currently covering Seattle, WA; more Washington cities coming.</p>
  <p class="fine">Data sources: City of Seattle SDCI Building Permits (open data) and Washington State L&amp;I Contractor License registry, as published on {esc(STATS['generated'])}. Rankings reflect only permits with contractor attribution in public records; absence from this index is not a statement about any builder. License statuses are reproduced as reported by WA L&amp;I and may change. This site does not provide recommendations or referrals — verify any contractor directly at <a href="https://secure.lni.wa.gov/verify/">lni.wa.gov/verify</a>. Corrections: <a href="{rel(CLAIM_URL, pre)}">contact us</a>.</p>
</footer>
</body>
</html>"""


def trend_chart():
    years = {y: n for y, n in STATS["permits_by_year"].items() if "2014" <= y <= "2025"}
    mx = max(years.values())
    bars = "".join(
        f'<div class="bar" style="height:{round(100*n/mx)}%" title="{y}: {n} permits">'
        f'<span class="bar-n">{n}</span><span class="bar-y">{y[2:]}</span></div>'
        for y, n in years.items())
    return f'<div class="chart" role="img" aria-label="ADU permits issued in Seattle by year, 2014 to 2025">{bars}</div>'


def builder_row(rank, b):
    yrs = f"{b['first_year']}–{b['last_year']}" if b["first_year"] != b["last_year"] else b["first_year"]
    return (f'<tr><td class="num">{rank}</td>'
            f'<td><a href="builders/{b["slug"]}.html">{esc(b["name"])}</a></td>'
            f'<td class="num">{b["permits_completed"]}</td>'
            f'<td class="num">{b["permits_total"]}</td>'
            f'<td class="num">{esc(yrs)}</td>'
            f'<td class="num">{money(b["median_cost"])}</td>'
            f'<td>{license_chip(b)}</td></tr>')


def build_index():
    ranked = [b for b in BUILDERS if b["permits_completed"] >= 1][:50]
    rows = "".join(builder_row(i + 1, b) for i, b in enumerate(ranked))
    active_n = sum(1 for b in BUILDERS if b.get("license") and b["license"]["status"] == "ACTIVE")
    jsonld = {"@context": "https://schema.org", "@type": "Dataset",
              "name": "Seattle ADU Builder Rankings",
              "description": "Accessory dwelling unit builders in Seattle ranked by completed building permits, from City of Seattle open permit data joined with WA L&I contractor licenses.",
              "dateModified": STATS["generated"],
              "isBasedOn": ["https://data.seattle.gov/resource/76t5-zqzr", "https://data.wa.gov/resource/m8qx-ubtq"]}
    body = f"""
<section class="hero">
  <p class="eyebrow">Seattle, Washington · updated {esc(TODAY)}</p>
  <h1>ADU builders, ranked by permits actually pulled</h1>
  <p class="dek">Every builder here is ranked by <strong>completed accessory-dwelling-unit permits</strong> in Seattle's official building records — not reviews, not ads. License status is cross-checked against the Washington L&amp;I contractor registry.</p>
  <div class="stats">
    <div><b>{STATS['total_permits']:,}</b><span>ADU permits tracked</span></div>
    <div><b>{STATS['completed_permits']:,}</b><span>completed builds</span></div>
    <div><b>{STATS['builders_listed']}</b><span>builders indexed</span></div>
    <div><b>{active_n}</b><span>active state licenses verified</span></div>
  </div>
</section>
<section>
  <h2>Seattle's ADU boom, in permits</h2>
  {trend_chart()}
  <p class="fine">Permits issued per year mentioning an ADU/DADU, City of Seattle SDCI data. Seattle legalized attached and detached ADUs citywide in 2019; permits have roughly tripled since.</p>
</section>
{featured_section()}
<section id="rankings">
  <h2>Builder rankings</h2>
  <p>Ranked by completed ADU permits where city records attribute a contractor. <a href="methodology.html">How this works and what it misses →</a></p>
  <div class="tablebox"><table>
  <thead><tr><th>#</th><th>Builder</th><th>Completed</th><th>All permits</th><th>Years</th><th>Median est. cost</th><th>WA license</th></tr></thead>
  <tbody>{rows}</tbody></table></div>
  <p><a href="builders/index.html">All {STATS['builders_listed']} indexed builders →</a></p>
</section>
<section class="callout">
  <h2>Are you an ADU builder?</h2>
  <p>Claim your profile, correct your permit history, and get found by homeowners comparing verified track records. <a href="for-builders.html">Learn more →</a></p>
</section>"""
    (SITE / "index.html").write_text(page(
        "ADU Builder Index — Seattle ADU builders ranked by permits",
        "Seattle ADU and DADU builders ranked by completed building permits from official city records, with Washington contractor license verification.",
        body, jsonld=jsonld))


def build_builder_pages():
    (SITE / "builders").mkdir(exist_ok=True)
    for b in BUILDERS:
        lic = b.get("license")
        lic_html = ""
        if lic:
            lic_html = f"""<dl class="lic">
<dt>License</dt><dd class="mono">{esc(lic['number'])}</dd>
<dt>Status</dt><dd>{license_chip(b)}</dd>
<dt>Type</dt><dd>{esc(lic['type'])}</dd>
<dt>Expires</dt><dd>{esc(lic['expires'])}</dd>
<dt>Registered in</dt><dd>{esc(lic['city'])}, WA</dd>
</dl>
<p class="fine">As reported by WA L&amp;I on {esc(STATS['generated'])}. Always re-verify at <a href="https://secure.lni.wa.gov/verify/">lni.wa.gov/verify</a>.</p>"""
        else:
            lic_html = '<p class="fine">No exact business-name match in the WA L&amp;I registry — this builder may hold a license under a different legal name. <a href="https://secure.lni.wa.gov/verify/">Check the registry directly</a>.</p>'
        permit_rows = "".join(
            f'<tr><td class="mono">{f"<a href=\"{esc(p["link"])}\">{esc(p["permitnum"])}</a>" if p.get("link") else esc(p["permitnum"])}</td>'
            f'<td>{esc(p["issued"] or "—")}</td><td>{esc(p["status"])}</td>'
            f'<td class="num">{money(p["cost"])}</td>'
            f'<td>{esc(p["address"])}</td>'
            f'<td class="desc">{esc(p["description"])}</td></tr>'
            for p in b["permits"])
        jsonld = {"@context": "https://schema.org", "@type": "GeneralContractor",
                  "name": b["name"],
                  "areaServed": "Seattle, WA",
                  "description": f"ADU builder with {b['permits_completed']} completed accessory dwelling unit permits on record in Seattle."}
        body = f"""
<section class="hero small">
  <p class="eyebrow"><a href="../index.html">← All builders</a></p>
  <h1>{esc(b['name'])}</h1>
  <div class="stats">
    <div><b>{b['permits_completed']}</b><span>completed ADU permits</span></div>
    <div><b>{b['permits_total']}</b><span>total ADU permits</span></div>
    <div><b>{esc(b['first_year'] or '—')}–{esc(b['last_year'] or '—')}</b><span>active years on record</span></div>
    <div><b>{money(b['median_cost'])}</b><span>median est. project cost</span></div>
  </div>
</section>
<section>
  <h2>Washington state license</h2>
  {lic_html}
</section>
<section>
  <h2>Permit record</h2>
  <p class="fine">Every ADU-related permit in Seattle city records naming this contractor. Links go to the city's official permit portal.</p>
  <div class="tablebox"><table>
  <thead><tr><th>Permit</th><th>Issued</th><th>Status</th><th>Est. cost</th><th>Address</th><th>Description</th></tr></thead>
  <tbody>{permit_rows}</tbody></table></div>
</section>
<section class="callout">
  <p>Is this your company? <a href="{rel(CLAIM_URL, '../')}">Claim this profile</a> free to add photos, service areas, and corrections — or <a href="../for-builders.html">get featured at the top of the rankings page</a> ($99/mo founding rate).</p>
</section>"""
        (SITE / "builders" / f"{b['slug']}.html").write_text(page(
            f"{b['name']} — ADU builder, Seattle | ADU Builder Index",
            f"{b['name']}: {b['permits_completed']} completed ADU permits in Seattle city records, {esc(b['first_year'])}–{esc(b['last_year'])}. Permit history and WA license status.",
            body, depth=1, jsonld=jsonld))

    # A–Z list
    items = "".join(
        f'<li><a href="{b["slug"]}.html">{esc(b["name"])}</a> '
        f'<span class="fine">{b["permits_total"]} permit{"s" if b["permits_total"] != 1 else ""}</span></li>'
        for b in sorted(BUILDERS, key=lambda x: x["name"].lower()))
    body = f"""<section class="hero small"><p class="eyebrow"><a href="../index.html">← Home</a></p>
<h1>All indexed builders</h1>
<p class="dek">Every contractor named on at least one ADU permit in Seattle city records.</p></section>
<section><ul class="azlist">{items}</ul></section>"""
    (SITE / "builders" / "index.html").write_text(page(
        "All ADU builders in Seattle | ADU Builder Index",
        "Alphabetical list of every contractor attributed on ADU permits in Seattle open data.",
        body, depth=1))


def build_methodology():
    body = f"""
<section class="hero small"><h1>Methodology</h1>
<p class="dek">What this index measures, where the data comes from, and what it can't see.</p></section>
<section>
  <h2>Sources</h2>
  <p>Permit data comes from the <a href="https://data.seattle.gov/Permitting/Building-Permits/76t5-zqzr">City of Seattle SDCI Building Permits</a> open dataset. We include permits whose description references an accessory dwelling unit (ADU, DADU, AADU) or that use Seattle's pre-approved DADU plan program — {STATS['total_permits']:,} permits as of {esc(STATS['generated'])}. License data comes from the <a href="https://data.wa.gov/Labor/L-I-Contractor-License-Data-General/m8qx-ubtq">Washington L&amp;I Contractor License registry</a>, refreshed with each site build.</p>
  <h2>How rankings work</h2>
  <p>Builders are ranked by <strong>completed ADU permits</strong> attributed to them in city records, with total permits as the tiebreaker. We merge obvious name variants of the same company and match businesses to state licenses by exact legal name.</p>
  <h2>What this misses — read this</h2>
  <p>Seattle stopped publishing contractor names on most permit records after 2021, so recent projects are under-attributed: {STATS['attributed_permits']} of {STATS['total_permits']:,} tracked permits name a contractor. A builder's absence here, or a low count, is <strong>not evidence they haven't built ADUs</strong> — it means city open data doesn't attribute those permits. We are enriching recent records and expanding city coverage; builders can <a href="{CLAIM_URL}">claim their profile</a> to submit permit numbers we can verify against city records.</p>
  <h2>License statuses</h2>
  <p>"Active", "expired", and "suspended" chips reproduce the state registry verbatim as of the build date. Licenses change; a mismatch can also mean a company operates under a different legal name. Always re-verify at <a href="https://secure.lni.wa.gov/verify/">lni.wa.gov/verify</a> before hiring.</p>
  <h2>Independence</h2>
  <p>Rankings cannot be bought. Paid placements, when offered, are labeled as such and never alter permit counts or rank order.</p>
</section>"""
    (SITE / "methodology.html").write_text(page(
        "Methodology | ADU Builder Index",
        "How ADU Builder Index ranks builders: Seattle open permit data, WA L&I license verification, and the limits of both.",
        body))


def build_for_builders():
    body = f"""
<section class="hero small"><h1>For ADU builders</h1>
<p class="dek">Homeowners planning a $150K–$400K ADU are comparing verified track records here. Make sure yours is right.</p></section>
<section>
  <h2>Free, always</h2>
  <p>Claiming your profile is free: correct your permit history (we verify submitted permit numbers against city records), add your service area, website, and contact details.</p>
  <h2>Featured listing — founding rate</h2>
  <p>Featured builders appear in the <a href="index.html#featured">Featured builders section at the top of the rankings page</a> — clearly labeled, with your blurb, license verification, and a direct link to your website. Founding-builder rate: <strong>$99/month, locked for life</strong>, first {FEATURED_SLOTS} builders in Seattle. One signed ADU project pays for roughly a decade of listing. Rankings are never for sale — featured placement is clearly separated from the permit-verified table.</p>
  <h2>How to get featured</h2>
  <ol>
    <li><a href="{FEATURE_URL}">{"Subscribe here" if STRIPE_LINK else "Reserve your slot here"}</a> — tell us your company name and license number.</li>
    <li>We verify your WA L&amp;I license is active and confirm your permit record.</li>
    <li>Your featured card is live within one business day{"" if STRIPE_LINK else "; we invoice after verification, not before"}.</li>
  </ol>
  <p><a class="button" href="{FEATURE_URL}">Get featured — $99/mo →</a> <a class="button secondary" href="{CLAIM_URL}">Claim your free profile →</a></p>
</section>"""
    (SITE / "for-builders.html").write_text(page(
        "For builders | ADU Builder Index",
        "Claim your ADU builder profile, correct your permit record, and reach homeowners comparing verified track records in Seattle.",
        body))


def build_form_pages():
    if not WEB3FORMS_KEY:
        return
    body = f"""
<section class="hero small"><h1>Claim your profile or get featured</h1>
<p class="dek">Free profile claims are verified against city permit records. Featured placement is <strong>$99/mo, locked for life</strong> for founding builders — we verify your license before any invoice.</p></section>
<section>
<form class="bform" action="https://api.web3forms.com/submit" method="POST">
  <input type="hidden" name="access_key" value="{WEB3FORMS_KEY}">
  <input type="hidden" name="subject" value="ADU Builder Index — builder request">
  <input type="hidden" name="from_name" value="ADU Builder Index">
  <input type="hidden" name="redirect" value="{SITE_BASE}/thanks.html">
  <input type="checkbox" name="botcheck" class="hp" tabindex="-1" autocomplete="off">
  <fieldset>
    <legend>What do you need?</legend>
    <label class="radio"><input type="radio" name="request_type" value="Get featured ($99/mo founding rate)" checked> Get featured — $99/mo founding rate</label>
    <label class="radio"><input type="radio" name="request_type" value="Claim free profile"> Claim my free profile</label>
  </fieldset>
  <label>Company name <input type="text" name="company" required></label>
  <label>WA contractor license # <input type="text" name="license_number" required></label>
  <label>Your email <input type="email" name="email" required></label>
  <label>Website <input type="url" name="website" placeholder="https://"></label>
  <label>Phone <input type="tel" name="phone"></label>
  <label>One-line blurb for your card, plus anything to correct on your profile <textarea name="message" rows="4"></textarea></label>
  <button class="button" type="submit">Send request</button>
  <p class="fine">We reply within one business day. Featured placement is invoiced only after license verification — never before.</p>
</form>
</section>"""
    (SITE / "get-featured.html").write_text(page(
        "Get featured or claim your profile | ADU Builder Index",
        "Claim your free ADU builder profile or request a founding featured slot. Verified against Seattle permit records and the WA L&I registry.",
        body))
    tbody = """
<section class="hero small"><h1>Request received</h1>
<p class="dek">Thanks — we'll verify your license and permit record and reply within one business day.</p>
<p><a href="index.html">← Back to the rankings</a></p></section>"""
    (SITE / "thanks.html").write_text(page(
        "Request received | ADU Builder Index",
        "Your builder request was received.", tbody))


def build_assets():
    (SITE / "robots.txt").write_text("User-agent: *\nAllow: /\n")
    urls = ["index.html", "methodology.html", "for-builders.html",
            "builders/index.html"] + [f"builders/{b['slug']}.html" for b in BUILDERS]
    (SITE / "sitemap.txt").write_text("\n".join(urls))


def main():
    SITE.mkdir(exist_ok=True)
    build_index()
    build_builder_pages()
    build_methodology()
    build_for_builders()
    build_form_pages()
    build_assets()
    n = len(list((SITE).rglob("*.html")))
    print(f"generated {n} pages in {SITE}")


if __name__ == "__main__":
    main()
