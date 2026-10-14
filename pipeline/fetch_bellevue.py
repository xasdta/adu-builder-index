"""Fetch ADU permits from Bellevue Open Data (ArcGIS, ADU-flagged dataset).

Normalizes to the same schema as Seattle so build_rankings.py can merge.
Bellevue quirks handled here:
- CONTRACTOR concatenates business name + principal ("MN CUSTOM HOMES LLC
  SHAUN GORDON MCFADDEN") — we trim at the entity suffix for L&I matching.
- CONTRACTOR value "OWNER" means owner-built → treated as unattributed.
- Status "Finaled"/"Closed" maps to "Completed".
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

# The ADU-only layer (Bellevue_Permit_Data_ADU) went private in Oct 2026 ("Token Required"); the public
# all-permits layer carries the same fields, including the ADU flag.
URL = ("https://services1.arcgis.com/EYzEZbDhXZjURPbP/arcgis/rest/services/"
       "Bellevue_Permit/FeatureServer/0/query")

SUFFIX = re.compile(
    r"^(.*?\b(?:LLC|L L C|INC|CORP|CORPORATION|LTD|PLLC|P\.?S\.?|COMPANY|CO))\b",
    re.IGNORECASE)
STATUS_MAP = {"Finaled": "Completed", "Closed": "Completed",
              "Issued": "Issued", "Canceled": "Canceled",
              "Withdrawn": "Withdrawn", "Expired": "Expired"}


def iso(ms):
    if not ms:
        return None
    return time.strftime("%Y-%m-%dT00:00:00.000", time.gmtime(ms / 1000))


# The public layer's CONTRACTOR is often the latest trade contractor on the folder (electrician, HVAC),
# not the builder. Those never get credit for an ADU: we keep the builder already on file for that permit,
# or leave it unattributed.
TRADE = re.compile(r"\b(ELECTRIC(AL)?|HEATING|AIR CO?N?D?T?N?G?|AIR CONDITIONING|PLUMBING|MECHANICAL|HVAC|SOLAR|ROOFING|FIRE PROTECTION|SPRINKLER|GAS)\b", re.I)


def contractor(raw):
    v = (raw or "").strip()
    if not v or v.upper() in ("OWNER", "NONE"):
        return None
    m = SUFFIX.match(v)
    return m.group(1).strip() if m else v


def builder(raw, prev):
    c = contractor(raw)
    if c and not TRADE.search(c):
        return c
    return prev if prev and not TRADE.search(prev) else None


def main():
    params = urllib.parse.urlencode({
        "where": "ADU='Yes'", "outFields": "*", "f": "json",
        "resultRecordCount": 2000})
    req = urllib.request.Request(f"{URL}?{params}",
                                 headers={"User-Agent": "adu-builder-index/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        j = json.load(r)
    if "features" not in j:   # ArcGIS reports errors in a 200 response
        raise SystemExit(f"Bellevue query failed: {j.get('error', j)}")
    feats = [f["attributes"] for f in j["features"]]

    out = Path(__file__).resolve().parent.parent / "data" / "bellevue_permits.json"
    try:
        prev = {p["permitnum"]: p.get("contractorcompanyname") for p in json.loads(out.read_text())["permits"]}
    except (OSError, ValueError, KeyError):
        prev = {}

    permits = []
    for a in feats:
        desc = " — ".join(x for x in [a.get("PROJECTNAME"), a.get("PROJECTDESCRIPTION")] if x)
        permits.append({
            "permitnum": a.get("PERMITNUMBER"),
            "permitclassmapped": "Residential",
            "permittypedesc": a.get("PERMITTYPEDESCRIPTION"),
            "description": desc,
            "statuscurrent": STATUS_MAP.get(a.get("PERMITSTATUS"), a.get("PERMITSTATUS")),
            "applieddate": iso(a.get("APPLIEDDATE")),
            "issueddate": iso(a.get("ISSUEDDATE")),
            "completeddate": iso(a.get("FINALEDDATE")),
            "contractorcompanyname": builder(a.get("CONTRACTOR"), prev.get(a.get("PERMITNUMBER"))),
            "originaladdress1": a.get("SITEADDRESS"),
            "originalzip": (str(a.get("ZIPCODE") or "")[:5] or None),
            "estprojectcost": None,
            "adu_sqft": a.get("SQFOOTAGEADU"),
            "link": {"url": a.get("MBPSTATUSSITE")},
        })
    out.write_text(json.dumps({"city": "Bellevue", "source": URL,
                               "fetched_at": time.strftime("%Y-%m-%d"),
                               "permits": permits}, indent=1))
    attributed = sum(1 for p in permits if p["contractorcompanyname"])
    completed = sum(1 for p in permits if p["statuscurrent"] == "Completed")
    print(f"{len(permits)} Bellevue ADU permits | {attributed} attributed | {completed} completed")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
