"""Measure the identity check on contacts whose LinkedIn profile you already know.

Usage: python evaluate.py known_contacts.csv
The CSV needs these columns: first_name, last_name, email, company, linkedin_url."""
import csv
import logging
import re
import sys
from collections import Counter

from identify import identify


def slug(url):
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url or "")
    return m.group(1).lower() if m else None


counts = Counter()
with open(sys.argv[1], newline="") as f:
    for row in csv.DictReader(f):
        lead = {"first": row["first_name"], "last": row["last_name"],
                "email": row["email"], "company": row["company"]}
        try:
            identity, person, _, _ = identify(lead, lead["email"].rsplit("@", 1)[-1].lower())
        except Exception:
            logging.exception("identify failed for %s", lead["email"])
            identity, person = "error", None
        picked = slug(((person or {}).get("input") or {}).get("url"))
        if identity == "verified":
            outcome = "right person" if picked == slug(row["linkedin_url"]) else "wrong person"
        else:
            outcome = {"job_change": "job change flagged",
                       "error": "error"}.get(identity, "no usable match")
        counts[outcome] += 1
        print(f"{lead['first']} {lead['last']}: {outcome} ({picked})")

print()
for outcome, n in counts.most_common():
    print(f"{outcome:20} {n}")
