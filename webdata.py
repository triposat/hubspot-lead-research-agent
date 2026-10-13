import json
import os
import re
import time
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()  # read .env; variables already set in the shell take precedence

API = "https://api.brightdata.com"
HEADERS = {"Authorization": f"Bearer {os.environ['BRIGHTDATA_API_TOKEN']}"}
SERP_ZONE = os.environ.get("BRIGHTDATA_SERP_ZONE", "serp_api")
UNLOCKER_ZONE = os.environ.get("BRIGHTDATA_UNLOCKER_ZONE", "web_unlocker")
PROFILES = "gd_l1viktl72bvl7bjuj0"   # LinkedIn people profiles
COMPANIES = "gd_l1vikfnt1wgvvqz95w"  # LinkedIn company pages


def _request(zone, url, **options):
    """Fetch through a SERP or Unlocker zone. The target's own status code
    travels in the x-brd-status-code header, so check it, not only HTTP 200."""
    for attempt in range(4):
        try:
            r = requests.post(f"{API}/request", headers=HEADERS, timeout=120,
                              json={"zone": zone, "url": url, "format": "raw", **options})
            status = int(r.headers.get("x-brd-status-code", r.status_code))
            if status < 400 and r.text:
                return r.text
            problem = f"{status} {r.headers.get('x-brd-error', '')}"
        except requests.RequestException as e:  # a dropped connection or a timeout
            problem = repr(e)
        if attempt < 3:
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"{zone} {url}: {problem}")


def google_results(query):
    """Google's organic results as parsed JSON, through the SERP API."""
    params = urlencode({"q": query, "hl": "en", "gl": "us", "brd_json": 1})
    page = _request(SERP_ZONE, f"https://www.google.com/search?{params}")
    return json.loads(page).get("organic", [])


def linkedin_candidates(first, last, company, per_query=3):
    """Top LinkedIn results from 2 differently worded searches, as {profile URL: result title}."""
    queries = [f'site:linkedin.com/in "{first} {last}" {company}',
               f'"{first} {last}" {company} linkedin']
    found, failed = {}, 0
    for q in queries:
        try:
            organic = google_results(q)
        except RuntimeError:
            failed += 1
            continue
        hits = [(m.group(1).lower(), item.get("title", "")) for item in organic
                if (m := re.search(r"linkedin\.com/in/([^/?#]+)", item.get("link", "")))]
        for slug, title in hits[:per_query]:
            found.setdefault(f"https://www.linkedin.com/in/{slug}/", title)
    if failed == len(queries):  # a search that never ran is an error, not "no match"
        raise RuntimeError(f"both searches failed for {first} {last}")
    return found


def scrape(dataset_id, urls, wait=300):
    """Synchronous scrape. A job that runs longer than the synchronous time limit
    comes back as HTTP 202 with a snapshot_id, so poll it instead of failing."""
    for attempt in range(4):
        r = requests.post(f"{API}/datasets/v3/scrape", headers=HEADERS, timeout=120,
                          params={"dataset_id": dataset_id, "format": "json",
                                  "include_errors": "true"},
                          json={"input": [{"url": u} for u in urls]})
        if r.status_code != 429:  # on a rate limit, wait and try again
            break
        time.sleep(int(r.headers.get("retry-after", 2 ** (attempt + 2))))
    r.raise_for_status()
    if r.status_code == 200:
        return r.json()
    snapshot = r.json()["snapshot_id"]
    deadline = time.time() + wait
    while time.time() < deadline:
        time.sleep(10)
        progress = requests.get(f"{API}/datasets/v3/progress/{snapshot}",
                                headers=HEADERS, timeout=30).json()
        if progress["status"] == "ready":
            return requests.get(f"{API}/datasets/v3/snapshot/{snapshot}",
                                headers=HEADERS, params={"format": "json"},
                                timeout=60).json()
        if progress["status"] == "failed":
            break
    raise TimeoutError(f"snapshot {snapshot} did not finish")


def dataset_search(first, last, company, size=3):
    """Profiles from Bright Data's LinkedIn dataset whose first name, last name, and
    current company contain the lead's values."""
    filters = [{"name": "first_name", "operator": "includes", "value": first},
               {"name": "last_name", "operator": "includes", "value": last},
               {"name": "current_company_name", "operator": "includes", "value": company}]
    for attempt in range(4):
        r = requests.post(f"{API}/datasets/search/{PROFILES}", headers=HEADERS, timeout=60, json={
            "mode": "sync", "size": size, "filter": {"operator": "and", "filters": filters}})
        if r.status_code != 429:
            break
        if attempt < 3:
            time.sleep(int(r.headers.get("retry-after", 2 ** (attempt + 2))))
    if r.status_code == 422:
        return []
    r.raise_for_status()
    hits = []
    for p in r.json().get("hits", []):
        if m := re.search(r"linkedin\.com/in/([^/?#]+)", p.get("url") or ""):
            # Store the normalized URL where a scraped record keeps its input
            url = f"https://www.linkedin.com/in/{m.group(1).lower()}/"
            hits.append(p | {"input": {"url": url}})
    return hits


INVISIBLE = re.compile("[\u200b-\u200d\u2060\ufeff]")


def homepage_markdown(domain, limit=6000):
    """The company site as Markdown, without zero-width characters,
    cut to a size the brief needs."""
    page = _request(UNLOCKER_ZONE, f"https://{domain}",
                    data_format="markdown", country="us")
    return INVISIBLE.sub("", page)[:limit]
