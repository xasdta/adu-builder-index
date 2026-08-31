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
# Stripe Payment Link for the $99/mo featured subscription. Shown as the
# payment step AFTER license verification — never as the primary CTA, so
# nobody pays before we verify them.
STRIPE_LINK = "https://buy.stripe.com/eVq9ASh2Saml6q8a5s0Ny00"
# Web3Forms access key (web3forms.com) — when set, contact buttons use the
# on-site form at get-featured.html instead of mailto links.
WEB3FORMS_KEY = "d253e17f-0e35-4f0a-a5c4-cfa9df78a199"
FORM_URL = "get-featured.html"
FEATURE_URL = FORM_URL if WEB3FORMS_KEY else RESERVE_URL
if WEB3FORMS_KEY:
    CLAIM_URL = FORM_URL
FEATURED_SLOTS = 3
_featured_path = ROOT / "data" / "featured.json"
FEATURED = (json.load(open(_featured_path))["builders"]
            if _featured_path.exists() else [])
_claims_path = ROOT / "data" / "claims.json"
CLAIMS = {c["slug"]: c for c in (json.load(open(_claims_path))["builders"]
                                 if _claims_path.exists() else [])}
BY_SLUG = {b["slug"]: b for b in BUILDERS}
# Covered cities: slug page + homepage card blurb. Add a city here after its
# fetch_<city>.py lands and build_rankings picks it up.
CITIES = [
    {"name": "Seattle", "page": "seattle-adu-builders.html",
     "blurb": "The largest ADU market in Washington — citywide legalization in 2019 sent permits soaring."},
    {"name": "Bellevue", "page": "bellevue-adu-builders.html",
     "blurb": "Bellevue flags ADU permits explicitly and still publishes contractor names, so attribution here is current."},
]
CITY_PAGE = {c["name"]: c["page"] for c in CITIES}


def featured_section(city=None, depth=0):
    """Featured cards. With a city, shows that city's slots; without, shows
    every featured builder across cities (homepage hub)."""
    pre = "../" * depth
    entries = [f for f in FEATURED if not city or f.get("city") == city]
    cards = []
    for f in entries[:FEATURED_SLOTS if city else None]:
        b = BY_SLUG.get(f["slug"])
        if not b:
            continue
        contact = ""
        if f.get("website"):
            contact = f'<a class="button" href="{esc(f["website"])}">Visit website</a>'
        where = "" if city else f' · {esc(f.get("city", ""))}'
        cards.append(f"""<div class="fcard">
<p class="flabel">Featured · paid placement{where}</p>
<h3><a href="{pre}builders/{b['slug']}.html">{esc(b['name'])}</a></h3>
<p class="fstat">{b['permits_completed']} completed ADU permits on record · {license_chip(b)}</p>
<p>{esc(f.get('blurb', ''))}</p>
{contact}
</div>""")

    label = f"in {esc(city)}" if city else "across all cities"
    open_slots = (FEATURED_SLOTS - len(cards)) if city else 0
    if not cards:
        scope = f"{FEATURED_SLOTS} founding slots {label}" if city else "Founding slots open in every city"
        return f"""<section id="featured">
<div class="fbanner">
  <div>
    <p class="flabel">Featured builders · {scope}</p>
    <p>Verified builders get top placement here — clearly labeled, never affecting the rankings below. Founding rate: <strong>$99/mo, locked for life</strong>.</p>
  </div>
  <a class="button" href="{pre}for-builders.html">Get featured →</a>
</div>
</section>"""
    if open_slots > 0:
        cards.append(f"""<div class="fcard open">
<p class="flabel">{open_slots} founding slot{"s" if open_slots > 1 else ""} open {label}</p>
<p><strong>$99/mo, locked for life.</strong> Top placement, license-verified, rankings never affected.</p>
<a class="button" href="{pre}for-builders.html">Get featured →</a>
</div>""")
    return f"""<section id="featured">
<h2>Featured builders{"" if not city else f" — {esc(city)}"}</h2>
<p class="fine">Paid placements, clearly labeled. Being featured never changes a builder's rank in the tables below — <a href="{pre}methodology.html">see methodology</a>.</p>
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


SITE_BASE = "https://adubuilderindex.com"


def rel(url, pre):
    """Prefix site-relative URLs with the page's depth prefix."""
    return url if url.startswith(("mailto:", "http", "#")) else pre + url


def page(title, desc, body, depth=0, canonical=None, jsonld=None, path=None):
    if canonical is None and path is not None:
        canonical = f"{SITE_BASE}/{path}".rstrip("/") if path else SITE_BASE + "/"
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
<script defer src="/_vercel/insights/script.js"></script>
{ld}
</head>
<body>
<header class="top">
  <a class="brand" href="{pre}index.html">ADU Builder Index</a>
  <nav>
    <a href="{pre}index.html#cities">Cities</a>
    <a href="{pre}index.html#rankings">All builders</a>
    <a href="{pre}seattle-adu-costs.html">Cost report</a>
    <a href="{pre}methodology.html">Methodology</a>
    <a href="{pre}for-builders.html" class="cta">For builders</a>
  </nav>
</header>
<main>
{body}
</main>
<footer>
  <p><strong>ADU Builder Index</strong> — permit-verified accessory dwelling unit builders. Currently covering Seattle and Bellevue, WA; more Washington cities coming.</p>
  <p class="fine">Data sources: City of Seattle SDCI Building Permits, City of Bellevue Open Data (both open data), and the Washington State L&amp;I Contractor License registry, as published on {esc(STATS['generated'])}. Rankings reflect only permits with contractor attribution in public records; absence from this index is not a statement about any builder. License statuses are reproduced as reported by WA L&amp;I and may change. This site does not provide recommendations or referrals — verify any contractor directly at <a href="https://secure.lni.wa.gov/verify/">lni.wa.gov/verify</a>. Corrections: <a href="{rel(CLAIM_URL, pre)}">contact us</a>.</p>
</footer>
</body>
</html>"""


def trend_chart(city="Seattle"):
    src = STATS["by_city"][city]["permits_by_year"]
    years = {y: n for y, n in src.items() if "2014" <= y <= "2025"}
    mx = max(years.values())
    bars = "".join(
        f'<div class="bar" style="height:{round(100*n/mx)}%" title="{y}: {n} permits">'
        f'<span class="bar-n">{n}</span><span class="bar-y">{y[2:]}</span></div>'
        for y, n in years.items())
    return f'<div class="chart" role="img" aria-label="ADU permits issued by year, 2014 to 2025">{bars}</div>'


def city_cards(depth=0):
    pre = "../" * depth
    cards = ""
    for c in CITIES:
        cb = STATS["by_city"][c["name"]]
        n_builders = sum(1 for b in BUILDERS if c["name"] in b["cities"])
        cards += f"""<a class="citycard" href="{pre}{c['page']}">
<h3>{esc(c['name'])}</h3>
<p class="citystats"><b>{cb['total']:,}</b> ADU permits · <b>{n_builders}</b> builders indexed</p>
<p>{esc(c['blurb'])}</p>
<span class="citylink">View {esc(c['name'])} rankings →</span>
</a>"""
    return f'<div class="citygrid">{cards}</div>'


def claimed_chip(b):
    if b["slug"] not in CLAIMS:
        return ""
    return ' <span class="chip chip-claimed" title="Profile claimed and verified by the company">claimed ✓</span>'


def builder_row(rank, b):
    yrs = f"{b['first_year']}–{b['last_year']}" if b["first_year"] != b["last_year"] else b["first_year"]
    return (f'<tr><td class="num">{rank}</td>'
            f'<td><a href="builders/{b["slug"]}.html">{esc(b["name"])}</a>{claimed_chip(b)}</td>'
            f'<td class="num">{b["permits_completed"]}</td>'
            f'<td class="num">{b["permits_total"]}</td>'
            f'<td class="num">{esc(yrs)}</td>'
            f'<td>{esc(" · ".join(sorted(b["cities"])))}</td>'
            f'<td class="num">{money(b["median_cost"])}</td>'
            f'<td>{license_chip(b)}</td></tr>')


def build_index():
    ranked = [b for b in BUILDERS if b["permits_completed"] >= 1][:50]
    rows = "".join(builder_row(i + 1, b) for i, b in enumerate(ranked))
    active_n = sum(1 for b in BUILDERS
                   if b.get("license") and b["license"]["status"] == "ACTIVE")
    city_list = " and ".join(c["name"] for c in CITIES)
    jsonld = {"@context": "https://schema.org", "@type": "Dataset",
              "name": "Washington ADU Builder Rankings",
              "description": f"Accessory dwelling unit builders in {city_list}, WA ranked by completed building permits, from city open permit data joined with WA L&I contractor licenses.",
              "dateModified": STATS["generated"],
              "isBasedOn": ["https://data.seattle.gov/resource/76t5-zqzr",
                            "https://data.bellevuewa.gov/",
                            "https://data.wa.gov/resource/m8qx-ubtq"]}
    body = f"""
<section class="hero">
  <p class="eyebrow">{esc(city_list)}, Washington · updated {esc(TODAY)}</p>
  <h1>ADU builders, ranked by permits actually pulled</h1>
  <p class="dek">Every builder here is ranked by <strong>completed accessory-dwelling-unit permits</strong> in official city building records — not reviews, not ads. License status is cross-checked against the Washington L&amp;I contractor registry.</p>
  <div class="stats">
    <div><b>{STATS['total_permits']:,}</b><span>ADU permits tracked</span></div>
    <div><b>{STATS['completed_permits']:,}</b><span>completed builds</span></div>
    <div><b>{STATS['builders_listed']}</b><span>builders indexed</span></div>
    <div><b>{active_n}</b><span>active state licenses verified</span></div>
  </div>
</section>
<section id="cities">
  <h2>Browse by city</h2>
  <p>Each city page ranks builders by their permit record in that city.</p>
  {city_cards()}
</section>
{featured_section()}
<section id="rankings">
  <h2>All builders, every city</h2>
  <p>Ranked by completed ADU permits where city records attribute a contractor. <a href="methodology.html">How this works and what it misses →</a></p>
  <div class="tablebox"><table>
  <thead><tr><th>#</th><th>Builder</th><th>Completed</th><th>All permits</th><th>Years</th><th>Cities</th><th>Median est. cost</th><th>WA license</th></tr></thead>
  <tbody>{rows}</tbody></table></div>
  <p><a href="builders/index.html">All {STATS['builders_listed']} indexed builders →</a></p>
</section>
<section>
  <h2>What an ADU costs</h2>
  <p>We computed real costs and timelines from thousands of permits: median detached-ADU cost, permitting time, and construction time. <a href="seattle-adu-costs.html">Read the Seattle ADU cost report →</a></p>
</section>
<section class="callout">
  <h2>Are you an ADU builder?</h2>
  <p>Claim your profile, correct your permit history, and get found by homeowners comparing verified track records. <a href="for-builders.html">Learn more →</a></p>
</section>"""
    (SITE / "index.html").write_text(page(
        f"ADU Builder Index — {city_list} ADU builders ranked by permits",
        f"ADU and DADU builders in {city_list}, WA ranked by completed building permits from official city records, with state contractor license verification.",
        body, jsonld=jsonld, path=""))


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
        claim = CLAIMS.get(b["slug"])
        jsonld = {"@context": "https://schema.org", "@type": "GeneralContractor",
                  "name": b["name"],
                  "areaServed": (claim or {}).get("service_area") or (", ".join(sorted(b["cities"])) + ", WA"),
                  "description": f"ADU builder with {b['permits_completed']} completed accessory dwelling unit permits on record."}
        contact_html = ""
        if claim:
            jsonld.update({k2: v for k2, v in
                           [("url", claim.get("website")),
                            ("telephone", claim.get("phone"))] if v})
            rows_c = ""
            if claim.get("website"):
                rows_c += f'<dt>Website</dt><dd><a href="{esc(claim["website"])}">{esc(claim["website"].removeprefix("https://").removeprefix("http://").rstrip("/"))}</a></dd>'
            if claim.get("phone"):
                rows_c += f'<dt>Phone</dt><dd><a href="tel:{esc(claim["phone"])}">{esc(claim["phone"])}</a></dd>'
            if claim.get("service_area"):
                rows_c += f'<dt>Service area</dt><dd>{esc(claim["service_area"])}</dd>'
            contact_html = f"""<section>
  <h2>Contact</h2>
  <dl class="lic">{rows_c}</dl>
  <p class="fine">Profile claimed and verified by the company on {esc(claim.get("claimed_date", ""))}.</p>
</section>"""
        if claim:
            callout = f'<p>Want top placement? <a href="../for-builders.html">Become a featured builder</a> — $99/mo founding rate, license-verified, rankings never affected.</p>'
        else:
            callout = f'<p>Is this your company? <a href="{rel(CLAIM_URL, "../")}">Claim this profile</a> free to add your website, contact details, and corrections — or <a href="../for-builders.html">get featured at the top of the rankings page</a> ($99/mo founding rate).</p>'
        body = f"""
<section class="hero small">
  <p class="eyebrow"><a href="../index.html">← All builders</a></p>
  <h1>{esc(b['name'])}{claimed_chip(b)}</h1>
  <div class="stats">
    <div><b>{b['permits_completed']}</b><span>completed ADU permits</span></div>
    <div><b>{b['permits_total']}</b><span>total ADU permits</span></div>
    <div><b>{esc(b['first_year'] or '—')}–{esc(b['last_year'] or '—')}</b><span>active years on record</span></div>
    <div><b>{money(b['median_cost'])}</b><span>median est. project cost</span></div>
  </div>
</section>
{contact_html}
<section>
  <h2>Washington state license</h2>
  {lic_html}
</section>
<section>
  <h2>Permit record</h2>
  <p class="fine">Every ADU-related permit in covered city records naming this contractor. Links go to each city's official permit portal.</p>
  <div class="tablebox"><table>
  <thead><tr><th>Permit</th><th>City</th><th>Issued</th><th>Status</th><th>Est. cost</th><th>Address</th><th>Description</th></tr></thead>
  <tbody>{permit_rows}</tbody></table></div>
</section>
<section class="callout">
  {callout}
</section>"""
        (SITE / "builders" / f"{b['slug']}.html").write_text(page(
            f"{b['name']} — ADU builder, Seattle | ADU Builder Index",
            f"{b['name']}: {b['permits_completed']} completed ADU permits in city records, {esc(b['first_year'])}–{esc(b['last_year'])}. Permit history and WA license status.",
            body, depth=1, jsonld=jsonld, path=f"builders/{b['slug']}.html"))

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
        body, depth=1, path="builders/index.html"))


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
        body, path="methodology.html"))


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
    <li><a href="{FEATURE_URL}">Request your slot</a> — tell us your company name and license number.</li>
    <li>We verify your WA L&amp;I license is active and confirm your permit record — before any payment.</li>
    <li>Once verified, subscribe securely{f' via <a href="{STRIPE_LINK}">Stripe</a>' if STRIPE_LINK else ""} and your featured card is live within one business day.</li>
  </ol>
  <p><a class="button" href="{FEATURE_URL}">Get featured — $99/mo →</a> <a class="button secondary" href="{CLAIM_URL}">Claim your free profile →</a></p>
</section>"""
    (SITE / "for-builders.html").write_text(page(
        "For builders | ADU Builder Index",
        "Claim your ADU builder profile, correct your permit record, and reach homeowners comparing verified track records in Seattle.",
        body, path="for-builders.html"))


def build_city_page(city, slug_html, blurb):
    cb = STATS["by_city"][city]
    local = [b for b in BUILDERS if city in b["cities"]]
    local.sort(key=lambda b: (b["cities"][city]["completed"],
                              b["cities"][city]["total"]), reverse=True)
    rows = ""
    for i, b in enumerate(local, 1):
        yrs = f"{b['first_year']}–{b['last_year']}" if b["first_year"] != b["last_year"] else b["first_year"]
        rows += (f'<tr><td class="num">{i}</td>'
                 f'<td><a href="builders/{b["slug"]}.html">{esc(b["name"])}</a>{claimed_chip(b)}</td>'
                 f'<td class="num">{b["cities"][city]["completed"]}</td>'
                 f'<td class="num">{b["cities"][city]["total"]}</td>'
                 f'<td class="num">{esc(yrs)}</td>'
                 f'<td>{license_chip(b)}</td></tr>')
    attributed = sum(b["cities"][city]["total"] for b in local)
    jsonld = {"@context": "https://schema.org", "@type": "Dataset",
              "name": f"{city} ADU Builder Rankings",
              "description": f"Accessory dwelling unit builders in {city}, WA ranked by permits in city records, license-verified.",
              "dateModified": STATS["generated"]}
    body = f"""
<section class="hero small">
  <p class="crumb"><a href="index.html#cities">← All cities</a></p>
  <p class="eyebrow">{esc(city)}, Washington · updated {esc(TODAY)}</p>
  <h1>{esc(city)} ADU builders, ranked by permits</h1>
  <p class="dek">{blurb}</p>
  <div class="stats">
    <div><b>{cb['total']:,}</b><span>ADU permits tracked</span></div>
    <div><b>{cb['completed']:,}</b><span>completed</span></div>
    <div><b>{len(local)}</b><span>builders with {esc(city)} ADU permits</span></div>
    <div><b>{attributed}</b><span>attributed permits</span></div>
  </div>
</section>
<section>
  <h2>{esc(city)} ADU permits by year</h2>
  {trend_chart(city)}
</section>
{featured_section(city)}
<section id="rankings">
  <h2>Rankings — {esc(city)}</h2>
  <p>Ranked by completed ADU permits attributed in {esc(city)} city records. <a href="methodology.html">Methodology →</a></p>
  <div class="tablebox"><table>
  <thead><tr><th>#</th><th>Builder</th><th>Completed in {esc(city)}</th><th>{esc(city)} permits</th><th>Years active</th><th>WA license</th></tr></thead>
  <tbody>{rows}</tbody></table></div>
  <p><a href="index.html#cities">← All cities</a> · <a href="index.html#rankings">All-cities rankings →</a></p>
</section>"""
    (SITE / slug_html).write_text(page(
        f"{city} ADU builders ranked by permits | ADU Builder Index",
        f"ADU and DADU builders in {city}, WA ranked by building permits from city records, with state license verification.",
        body, jsonld=jsonld, path=slug_html))


def build_cost_report():
    import re as _re
    import statistics as _st
    from datetime import date as _date

    permits = json.load(open(ROOT / "data" / "seattle_permits.json"))["permits"]
    new = [p for p in permits
           if p.get("permitclassmapped") == "Residential"
           and p.get("permittypedesc") == "New"]
    # Pure detached-ADU builds: mention DADU/detached, and are not bundled
    # house+ADU projects (those permits carry the whole house's cost).
    BUNDLE = _re.compile(r"\bSFR\b|SINGLE.FAMILY|TOWNHOUSE|ROWHOUSE|LIVE.WORK",
                         _re.IGNORECASE)
    DET = _re.compile(r"\bDADU\b|DETACHED", _re.IGNORECASE)
    dadu = [p for p in new
            if DET.search(p.get("description") or "")
            and not BUNDLE.search(p.get("description") or "")]

    def _year(p, f):
        return (p.get(f) or "")[:4]

    def _days(a, b):
        try:
            return (_date.fromisoformat(b[:10]) - _date.fromisoformat(a[:10])).days
        except (ValueError, TypeError):
            return None

    by_year = {}
    for p in dadu:
        c = float(p.get("estprojectcost") or 0)
        y = _year(p, "issueddate")
        if c > 20000 and y >= "2019":
            by_year.setdefault(y, []).append(c)
    rows = ""
    for y in sorted(by_year):
        v = sorted(by_year[y])
        q = _st.quantiles(v, n=4)
        rows += (f'<tr><td class="num">{y}</td><td class="num">{len(v)}</td>'
                 f'<td class="num">{money(_st.median(v))}</td>'
                 f'<td class="num">{money(q[0])} – {money(q[2])}</td></tr>')

    recent = [c for y, vs in by_year.items() if y >= "2023" for c in vs]
    med_cost = _st.median(recent)
    perm_days = [d for d in (_days(p.get("applieddate"), p.get("issueddate"))
                             for p in new if _year(p, "issueddate") >= "2023")
                 if d is not None and 0 <= d < 2000]
    con_days = [d for d in (_days(p.get("issueddate"), p.get("completeddate"))
                            for p in new if _year(p, "completeddate") >= "2023")
                if d is not None and 30 <= d < 2000]
    med_perm, med_con = _st.median(perm_days), _st.median(con_days)

    zip_counts = {}
    for p in new:
        z = p.get("originalzip")
        if z and _year(p, "issueddate") >= "2023":
            zip_counts[z] = zip_counts.get(z, 0) + 1
    zip_rows = "".join(
        f'<tr><td class="num">{esc(z)}</td><td class="num">{n}</td></tr>'
        for z, n in sorted(zip_counts.items(), key=lambda x: -x[1])[:10])

    jsonld = {"@context": "https://schema.org", "@type": "Dataset",
              "name": "Seattle ADU Cost Report",
              "description": f"Cost, permitting-time, and construction-time statistics for accessory dwelling units in Seattle, computed from {len(new):,} new-construction ADU building permits.",
              "dateModified": STATS["generated"],
              "isBasedOn": "https://data.seattle.gov/resource/76t5-zqzr"}
    body = f"""
<section class="hero small">
  <p class="crumb"><a href="index.html">← Home</a></p>
  <p class="eyebrow">From {len(new):,} new-construction ADU permits · updated {esc(TODAY)}</p>
  <h1>What an ADU really costs in Seattle</h1>
  <p class="dek">Not estimates from contractors' marketing pages — these are the costs, permitting times, and construction times declared on actual Seattle building permits.</p>
  <div class="stats">
    <div><b>{money(med_cost)}</b><span>median detached ADU, 2023–2026 permits</span></div>
    <div><b>{med_perm:.0f} days</b><span>median permitting time (application → issue)</span></div>
    <div><b>{med_con:.0f} days</b><span>median construction time (issue → completion)</span></div>
    <div><b>~{(med_perm + med_con) / 30:.0f} months</b><span>typical application-to-done timeline</span></div>
  </div>
</section>
<section>
  <h2>Detached ADU (backyard cottage) costs by year</h2>
  <p>Estimated project cost as declared on standalone DADU new-construction permits — bundled house-plus-ADU projects are excluded so the numbers reflect the ADU alone.</p>
  <div class="tablebox"><table>
  <thead><tr><th>Year issued</th><th>Permits</th><th>Median cost</th><th>Middle 50% range</th></tr></thead>
  <tbody>{rows}</tbody></table></div>
  <p class="fine">Permit-declared estimates typically run below final all-in cost (site work, finishes, and overruns land later) — treat these as a floor, not a quote. Attached-ADU permits are excluded from cost stats because most are filed with the main house's full construction cost.</p>
</section>
<section>
  <h2>Where Seattle is building ADUs</h2>
  <p>New-construction ADU permits by ZIP code since 2023.</p>
  <div class="tablebox"><table>
  <thead><tr><th>ZIP</th><th>Permits since 2023</th></tr></thead>
  <tbody>{zip_rows}</tbody></table></div>
</section>
<section class="callout">
  <p>Comparing builders? The <a href="index.html#rankings">rankings</a> show who has actually completed ADU permits in city records, with license verification.</p>
</section>"""
    (SITE / "seattle-adu-costs.html").write_text(page(
        "Seattle ADU Cost Report — real permit data | ADU Builder Index",
        f"Median detached ADU cost in Seattle is {money(med_cost)} per 2023-2026 building permits. Real permitting times, construction times, and costs from {len(new):,} city permits.",
        body, jsonld=jsonld, path="seattle-adu-costs.html"))


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
        body, path="get-featured.html"))
    tbody = """
<section class="hero small"><h1>Request received</h1>
<p class="dek">Thanks — we'll verify your license and permit record and reply within one business day.</p>
<p><a href="index.html">← Back to the rankings</a></p></section>"""
    (SITE / "thanks.html").write_text(page(
        "Request received | ADU Builder Index",
        "Your builder request was received.", tbody, path="thanks.html"))


def build_assets():
    (SITE / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {SITE_BASE}/sitemap.xml\n")
    paths = ["", "methodology.html", "for-builders.html", "get-featured.html",
             "seattle-adu-costs.html", *[c["page"] for c in CITIES],
             "builders/index.html"] + [f"builders/{b['slug']}.html" for b in BUILDERS]
    urls = "\n".join(
        f"<url><loc>{SITE_BASE}/{p}</loc><lastmod>{STATS['generated']}</lastmod></url>"
        for p in paths)
    (SITE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n</urlset>\n")
    old = SITE / "sitemap.txt"
    if old.exists():
        old.unlink()


def main():
    SITE.mkdir(exist_ok=True)
    build_index()
    build_builder_pages()
    build_methodology()
    build_for_builders()
    build_cost_report()
    for c in CITIES:
        build_city_page(c["name"], c["page"], c["blurb"])
    build_form_pages()
    build_assets()
    n = len(list((SITE).rglob("*.html")))
    print(f"generated {n} pages in {SITE}")


if __name__ == "__main__":
    main()
