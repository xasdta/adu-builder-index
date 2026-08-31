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

URL = ("https://services1.arcgis.com/EYzEZbDhXZjURPbP/arcgis/rest/services/"
       "Bellevue_Permit_Data_ADU/FeatureServer/0/query")

SUFFIX = re.compile(
    r"^(.*?\b(?:LLC|L L C|INC|CORP|CORPORATION|LTD|PLLC|P\.?S\.?|COMPANY))\b",
    re.IGNORECASE)
STATUS_MAP = {"Finaled": "Completed", "Closed": "Completed",
              "Issued": "Issued", "Canceled": "Canceled",
              "Withdrawn": "Withdrawn", "Expired": "Expired"}


def iso(ms):
    if not ms:
        return None
    return time.strftime("%Y-%m-%dT00:00:00.000", time.gmtime(ms / 1000))


def contractor(raw):
    v = (raw or "").strip()
    if not v or v.upper() == "OWNER":
        return None
    m = SUFFIX.match(v)
    return m.group(1).strip() if m else v


def main():
    params = urllib.parse.urlencode({
        "where": "ADU='Yes'", "outFields": "*", "f": "json",
        "resultRecordCount": 2000})
    req = urllib.request.Request(f"{URL}?{params}",
                                 headers={"User-Agent": "adu-builder-index/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        feats = [f["attributes"] for f in json.load(r)["features"]]

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
            "contractorcompanyname": contractor(a.get("CONTRACTOR")),
            "originaladdress1": a.get("SITEADDRESS"),
            "originalzip": (str(a.get("ZIPCODE") or "")[:5] or None),
            "estprojectcost": None,
            "adu_sqft": a.get("SQFOOTAGEADU"),
            "link": {"url": a.get("MBPSTATUSSITE")},
        })
    out = Path(__file__).resolve().parent.parent / "data" / "bellevue_permits.json"
    out.write_text(json.dumps({"city": "Bellevue", "source": URL,
                               "fetched_at": time.strftime("%Y-%m-%d"),
                               "permits": permits}, indent=1))
    attributed = sum(1 for p in permits if p["contractorcompanyname"])
    completed = sum(1 for p in permits if p["statuscurrent"] == "Completed")
    print(f"{len(permits)} Bellevue ADU permits | {attributed} attributed | {completed} completed")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
