"""Fetch ADU/DADU building permits from Seattle Open Data (SDCI Building Permits).

Dataset: https://data.seattle.gov/resource/76t5-zqzr.json (public SODA API, no key).
Broad server-side candidate filter, then precise client-side regex filter to
avoid substring false positives ("ADULT", "GRADUATE", etc.).
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://data.seattle.gov/resource/76t5-zqzr.json"
FIELDS = ",".join([
    "permitnum", "permitclass", "permitclassmapped", "permittypedesc",
    "description", "housingcategory", "housingunitsadded", "estprojectcost",
    "applieddate", "issueddate", "completeddate", "statuscurrent",
    "contractorcompanyname", "originaladdress1", "originalzip",
    "latitude", "longitude", "link",
])
WHERE = (
    "upper(description) LIKE '%ACCESSORY DWELLING%' "
    "OR upper(description) LIKE '%DADU%' "
    "OR upper(description) LIKE '%ADU%' "
    "OR housingcategory = 'Pre-Approved DADU Plans'"
)

# Word-boundary match: ADU / ADUs / DADU / DADUs / AADU / "accessory dwelling"
ADU_RE = re.compile(r"\b[AD]?ADUS?\b|ACCESSORY DWELLING", re.IGNORECASE)


def fetch_all():
    rows, offset, page = [], 0, 10000
    while True:
        params = urllib.parse.urlencode({
            "$select": FIELDS,
            "$where": WHERE,
            "$limit": page,
            "$offset": offset,
            "$order": "permitnum",
        })
        req = urllib.request.Request(
            f"{BASE}?{params}",
            headers={"User-Agent": "adu-builder-index/0.1 (data pipeline)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            batch = json.load(r)
        rows.extend(batch)
        print(f"  fetched {len(batch)} (total {len(rows)})")
        if len(batch) < page:
            break
        offset += page
        time.sleep(1)
    return rows


def is_adu(row):
    if row.get("housingcategory") == "Pre-Approved DADU Plans":
        return True
    return bool(ADU_RE.search(row.get("description", "")))


def main():
    out = Path(__file__).resolve().parent.parent / "data" / "seattle_permits.json"
    raw = fetch_all()
    kept = [r for r in raw if is_adu(r)]
    dropped = len(raw) - len(kept)
    print(f"kept {len(kept)} ADU permits, dropped {dropped} false positives")
    out.write_text(json.dumps({"city": "Seattle", "source": BASE,
                               "fetched_at": time.strftime("%Y-%m-%d"),
                               "permits": kept}, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
