import logging
import os

from verify import FREE_MAIL, company_key, pick
from webdata import COMPANIES, PROFILES, dataset_search, linkedin_candidates, scrape

# Both fallbacks are off by default. Dataset Search needs a funded Bright Data account,
# and the agent search spends Claude tokens on each lead it runs for.
DATASET_SEARCH = os.environ.get("BRIGHTDATA_DATASET_SEARCH") == "on"
AGENT_SEARCH = os.environ.get("AGENT_SEARCH") == "on"


def company_pages(profiles, skip=()):
    links = {((p.get("current_company") or {}).get("link") or "").split("?")[0] for p in profiles}
    links = sorted(link for link in links if company_key(link) and company_key(link) not in skip)
    return {company_key(co.get("url")): co for co in scrape(COMPANIES, links)
            if not co.get("error")} if links else {}


def identify(lead, domain):
    """Find the lead's LinkedIn profile and decide whether it belongs to them.
    Returns the result, the chosen profile, its company pages, and the search titles."""
    if not (lead["first"] and lead["last"]):
        return "no_match", None, {}, {}  # a search without a full name can't be verified
    if domain in FREE_MAIL:
        return "unverified", None, {}, {}  # nothing to match the company against, so skip the cost
    company = lead["company"] or domain.split(".")[0]
    candidates = linkedin_candidates(lead["first"], lead["last"], company)
    scraped = scrape(PROFILES, list(candidates)) if candidates else []
    profiles = [p for p in scraped if not p.get("error")]
    companies = company_pages(profiles)
    identity, person = pick(lead, profiles, companies, candidates)

    if DATASET_SEARCH and identity != "verified" and lead["company"]:
        # Google missed the profile or found a namesake, so search the LinkedIn dataset directly.
        try:
            extra = [p for p in dataset_search(lead["first"], lead["last"], lead["company"])
                     if p["input"]["url"] not in candidates]
            if extra:
                companies |= company_pages(extra, skip=companies)
                profiles += extra
                identity, person = pick(lead, profiles, companies, candidates)
        except Exception:  # keep the first result if the fallback fails
            logging.exception("dataset search failed for %s", lead["email"])

    if AGENT_SEARCH and identity != "verified":
        # Let Claude try other searches. Only the identity check can accept what it finds.
        from search_agent import agent_search  # needed only when AGENT_SEARCH is on
        try:
            found, more, titles, _ = agent_search(lead, company_pages)
            if found:
                companies |= more
                profiles += found
                identity, person = pick(lead, profiles, companies, candidates | titles)
        except Exception:
            logging.exception("agent search failed for %s", lead["email"])

    return identity, person, companies, candidates
