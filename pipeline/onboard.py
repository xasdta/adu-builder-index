"""Auto-onboard new featured builders from Stripe.

Reads active subscriptions from Stripe, validates each against the WA L&I
contractor registry and our permit data, and adds clean matches to
data/featured.json. Anything ambiguous is reported for a human decision and
never published.

Needs STRIPE_SECRET_KEY in .env (a restricted key with read access to
Customers and Subscriptions is enough).

Usage:
  python3 pipeline/onboard.py            # report only, changes nothing
  python3 pipeline/onboard.py --apply    # write verified entries to featured.json
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LNI = "https://data.wa.gov/resource/m8qx-ubtq.json"
STRIPE = "https://api.stripe.com/v1"

SUFFIX = re.compile(
    r",?\s+(LLC|L L C|INC|CORP|CORPORATION|CO|COMPANY|LTD|LP|PLLC|P\.?S\.?)\.?$",
    re.IGNORECASE)


def canon(name):
    n = re.sub(r"[^A-Z0-9& ]", " ", (name or "").upper())
    n = re.sub(r"\s+", " ", n).strip()
    prev = None
    while prev != n:
        prev = n
        n = SUFFIX.sub("", n).strip()
    return n


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        sys.exit("STRIPE_SECRET_KEY not set — add it to .env (never commit it)")
    return key


def stripe_get(path, key, **params):
    url = f"{STRIPE}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def lni_lookup(name):
    """Return L&I records whose business name canonically matches."""
    q = (name or "").replace("'", "''")
    params = urllib.parse.urlencode({
        "$where": f"upper(businessname) like '{q.upper()}%'", "$limit": 50})
    req = urllib.request.Request(f"{LNI}?{params}",
                                 headers={"User-Agent": "adu-builder-index/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            recs = json.load(r)
    except Exception:
        return []
    return [x for x in recs if canon(x.get("businessname")) == canon(name)]


def subscriber_fields(sub, key):
    """Pull business name, license, website, blurb from the subscription."""
    cust = stripe_get(f"customers/{sub['customer']}", key)
    fields = {"email": cust.get("email"), "stripe_customer": cust.get("id"),
              "business": (cust.get("name") or cust.get("description") or "").strip(),
              "license": "", "website": "", "blurb": ""}
    # Payment-link custom fields land on the checkout session
    try:
        sessions = stripe_get("checkout/sessions", key, customer=cust["id"], limit=3)
        for s in sessions.get("data", []):
            for cf in s.get("custom_fields", []) or []:
                label = (cf.get("key") or "").lower()
                val = ((cf.get("text") or {}).get("value") or "").strip()
                if not val:
                    continue
                if "licen" in label:
                    fields["license"] = val
                elif "web" in label or "site" in label:
                    fields["website"] = val
                elif "blurb" in label or "descri" in label:
                    fields["blurb"] = val
            if s.get("custom_fields"):
                break
    except Exception:
        pass
    return fields


def main():
    apply = "--apply" in sys.argv
    key = load_env()
    builders = json.load(open(DATA / "builders.json"))["builders"]
    by_canon = {canon(b["name"]): b for b in builders}
    featured_path = DATA / "featured.json"
    featured = json.load(open(featured_path))
    have = {f["slug"] for f in featured["builders"]}

    subs = stripe_get("subscriptions", key, status="active", limit=100)
    print(f"{len(subs.get('data', []))} active subscription(s) in Stripe\n")

    verified, needs_review = [], []
    for sub in subs.get("data", []):
        f = subscriber_fields(sub, key)
        who = f["business"] or f["email"] or sub["id"]
        b = by_canon.get(canon(f["business"]))
        lni = lni_lookup(f["business"])
        active = [x for x in lni if x.get("contractorlicensestatus") == "ACTIVE"]

        problems = []
        if not f["business"]:
            problems.append("no business name captured at checkout")
        if not b:
            problems.append("no builder profile matches that business name")
        if not lni:
            problems.append("no WA L&I record found for that name")
        elif not active:
            statuses = ", ".join(sorted({x.get("contractorlicensestatus", "?") for x in lni}))
            problems.append(f"L&I license is not ACTIVE (status: {statuses}) — refund per guarantee")

        if problems:
            needs_review.append((who, f, problems))
            continue
        if b["slug"] in have:
            print(f"  = {who} — already featured, skipping")
            continue
        city = sorted(b["cities"])[0]
        verified.append({
            "slug": b["slug"], "city": city,
            "blurb": f["blurb"] or f"{b['permits_total']} ADU permits on record in {city}.",
            "website": f["website"], "_stripe_customer": f["stripe_customer"],
            "_license": active[0].get("contractorlicensenumber"),
        })
        print(f"  ✓ {who} — license {active[0].get('contractorlicensenumber')} ACTIVE, "
              f"profile {b['slug']}, {city}")

    for who, f, problems in needs_review:
        print(f"  ⚠ {who} ({f['email']}) — NEEDS YOU:")
        for p in problems:
            print(f"      · {p}")

    if verified and apply:
        featured["builders"].extend(verified)
        featured_path.write_text(json.dumps(featured, indent=1))
        print(f"\nwrote {len(verified)} verified builder(s) to featured.json — "
              f"run generate_site.py and push to publish")
    elif verified:
        print(f"\n{len(verified)} ready to publish. Re-run with --apply to write them.")
    if not verified and not needs_review:
        print("nothing new to onboard")


if __name__ == "__main__":
    main()
