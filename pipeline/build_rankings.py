"""Aggregate ADU permits into builder rankings and join WA L&I license data.

Inputs:  data/seattle_permits.json  (from fetch_seattle.py)
Output:  data/builders.json         (ranked builders + site-wide stats)

License join: exact uppercase businessname match against L&I Contractor
License Data (data.wa.gov m8qx-ubtq), preferring CONSTRUCTION CONTRACTOR
records with the latest effective date. Unmatched builders are flagged
"unmatched" — never assumed unlicensed.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
LNI = "https://data.wa.gov/resource/m8qx-ubtq.json"

SUFFIX_RE = re.compile(
    r",?\s+(LLC|L L C|INC|CORP|CORPORATION|CO|COMPANY|LTD|LP|PLLC|P\.?S\.?)\.?$",
    re.IGNORECASE)


def canon(name):
    n = re.sub(r"[^A-Z0-9& ]", " ", name.upper())
    n = re.sub(r"\s+", " ", n).strip()
    prev = None
    while prev != n:
        prev = n
        n = SUFFIX_RE.sub("", n).strip()
    return n


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "builder"


def fetch_lni(names):
    """Exact-uppercase-name lookup in chunks; returns {upper_name: [records]}."""
    found = defaultdict(list)
    names = sorted(set(names))
    for i in range(0, len(names), 40):
        chunk = names[i:i + 40]
        quoted = ",".join("'" + n.replace("'", "''") + "'" for n in chunk)
        params = urllib.parse.urlencode({
            "$where": f"upper(businessname) in({quoted})",
            "$limit": 500,
        })
        req = urllib.request.Request(f"{LNI}?{params}",
                                     headers={"User-Agent": "adu-builder-index/0.1"})
        with urllib.request.urlopen(req, timeout=60) as r:
            for rec in json.load(r):
                found[rec["businessname"].upper().strip()].append(rec)
        time.sleep(0.5)
    return found


def pick_license(records):
    """Prefer construction-contractor records, newest effective date."""
    if not records:
        return None
    cc = [r for r in records if r.get("contractorlicensetypecode") == "CC"] or records
    cc.sort(key=lambda r: r.get("licenseeffectivedate", ""), reverse=True)
    active = [r for r in cc if r.get("contractorlicensestatus") == "ACTIVE"]
    return (active or cc)[0]


def main():
    permits = json.load(open(DATA / "seattle_permits.json"))["permits"]

    by_builder = defaultdict(list)
    for p in permits:
        name = (p.get("contractorcompanyname") or "").strip()
        if name:
            by_builder[name.upper()].append(p)

    # Merge trivially-different names under a canonical key
    merged = defaultdict(list)
    display = {}
    for raw, plist in by_builder.items():
        key = canon(raw)
        merged[key].extend(plist)
        if key not in display or len(raw) < len(display[key]):
            display[key] = raw.title().replace("Llc", "LLC").replace("Inc", "Inc.")

    lni = fetch_lni([raw for raw in by_builder])
    lni_by_canon = defaultdict(list)
    for raw_name, recs in lni.items():
        lni_by_canon[canon(raw_name)].extend(recs)

    builders = []
    for key, plist in merged.items():
        completed = [p for p in plist if p.get("statuscurrent") == "Completed"]
        years = sorted({(p.get("issueddate") or p.get("applieddate") or "")[:4]
                        for p in plist if p.get("issueddate") or p.get("applieddate")})
        costs = sorted(float(p["estprojectcost"]) for p in plist
                       if p.get("estprojectcost") and float(p["estprojectcost"]) > 10000)
        lic = pick_license(lni_by_canon.get(key, []))
        builders.append({
            "slug": slugify(display[key]),
            "name": display[key],
            "permits_total": len(plist),
            "permits_completed": len(completed),
            "first_year": years[0] if years else None,
            "last_year": years[-1] if years else None,
            "median_cost": costs[len(costs) // 2] if costs else None,
            "license": None if not lic else {
                "number": lic.get("contractorlicensenumber"),
                "status": lic.get("contractorlicensestatus"),
                "type": lic.get("contractorlicensetypecodedesc"),
                "effective": (lic.get("licenseeffectivedate") or "")[:10],
                "expires": (lic.get("licenseexpirationdate") or "")[:10],
                "city": lic.get("city"),
                "ubi": lic.get("ubi"),
            },
            "permits": sorted([{
                "permitnum": p.get("permitnum"),
                "description": (p.get("description") or "")[:400],
                "status": p.get("statuscurrent"),
                "issued": (p.get("issueddate") or "")[:10],
                "completed": (p.get("completeddate") or "")[:10],
                "cost": p.get("estprojectcost"),
                "address": p.get("originaladdress1"),
                "zip": p.get("originalzip"),
                "link": (p.get("link") or {}).get("url"),
            } for p in plist], key=lambda x: x["issued"] or "", reverse=True),
        })

    builders.sort(key=lambda b: (b["permits_completed"], b["permits_total"]),
                  reverse=True)

    year_counts = defaultdict(int)
    for p in permits:
        y = (p.get("issueddate") or "")[:4]
        if y and y >= "2010":
            year_counts[y] += 1

    stats = {
        "city": "Seattle",
        "total_permits": len(permits),
        "completed_permits": sum(1 for p in permits
                                 if p.get("statuscurrent") == "Completed"),
        "attributed_permits": sum(len(b["permits"]) for b in builders),
        "builders_listed": len(builders),
        "permits_by_year": dict(sorted(year_counts.items())),
        "generated": time.strftime("%Y-%m-%d"),
    }
    out = DATA / "builders.json"
    out.write_text(json.dumps({"stats": stats, "builders": builders}, indent=1))
    matched = sum(1 for b in builders if b["license"])
    active = sum(1 for b in builders
                 if b["license"] and b["license"]["status"] == "ACTIVE")
    print(f"{len(builders)} builders | {matched} license-matched | {active} active licenses")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
