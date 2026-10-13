import re
import unicodedata

FREE_MAIL = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com",
             "yahoo.com", "icloud.com", "proton.me", "protonmail.com"}


def _tokens(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split()


SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "edu"}
# A company name that is only a generic word, such as "Company", is not evidence on its own.
GENERIC = {"company", "group", "labs", "solutions", "systems", "software", "technologies",
           "global", "holdings", "partners", "ventures", "studio", "digital", "services"}


def _label(domain):
    parts = (domain or "").lower().removeprefix("www.").split(".")
    if len(parts) >= 3 and parts[-2] in SECOND_LEVEL and len(parts[-1]) == 2:
        return parts[-3]  # acme.co.uk -> acme, not co
    return parts[-2] if len(parts) >= 2 else parts[0]


def name_matches(first, last, profile_name):
    have = set(_tokens(profile_name))
    want_first, want_last = _tokens(first), _tokens(last)
    return bool(want_first and want_last) and want_first[0] in have and want_last[-1] in have


def company_matches(email_domain, company_site, company_name):
    # The LinkedIn website field can hold a campaign short link, and some
    # profiles show a company name with no page link, so use the company name instead.
    label = _label(email_domain)
    if company_site and _label(company_site) == label:
        return True
    words = _tokens(company_name)
    squashed, domain = "".join(words), "".join(_tokens(email_domain.replace(".", " ")))
    # A whole word or the whole name must match, so meta.com doesn't match "Metabase".
    return len(label) >= 4 and len(squashed) >= 4 and squashed not in GENERIC and (
        label in words or squashed == domain or squashed in label)


def title_matches(email_domain, company_name, title, person=""):
    # Only distinctive names (5+ letters) count, and a "former" role never does.
    if re.search(r"\b(ex|former|formerly|prev|previously)\b", title or "", re.I):
        return False
    name = set(_tokens(person))  # the person's own name isn't company evidence
    words = "".join(t for t in _tokens(title) if t not in name)
    keys = (_label(email_domain), "".join(_tokens(company_name)))
    return any(len(key) >= 5 and key in words for key in keys)


def check_identity(lead, profile, company, title=""):
    """verified | job_change | unverified | no_match"""
    if not name_matches(lead["first"], lead["last"], profile.get("name")):
        return "no_match"
    domain = lead["email"].rsplit("@", 1)[-1].lower()
    if domain in FREE_MAIL:
        return "unverified"
    current = profile.get("current_company_name")
    link = (profile.get("current_company") or {}).get("link") or ""
    if current and "/school/" not in link:
        site = (company or {}).get("website_simplified")
        return "verified" if company_matches(domain, site, current) else "job_change"
    # No usable current company on the profile, so check the search result title.
    person = f"{lead['first']} {lead['last']}"
    return "verified" if title_matches(domain, lead.get("company"), title, person) else "unverified"


RANK = {"verified": 0, "job_change": 1, "unverified": 2}


def pick(lead, profiles, companies_by_url, titles=None):
    """Best profile first. Two same-name profiles can both pass, so
    the one with more followers comes first."""
    ranked = []
    for p in profiles:
        link = ((p.get("current_company") or {}).get("link") or "").split("?")[0]
        title = (titles or {}).get((p.get("input") or {}).get("url"), "")
        v = check_identity(lead, p, companies_by_url.get(company_key(link)), title)
        if v != "no_match":
            ranked.append((RANK[v], -(p.get("followers") or 0), v, p))
    ranked.sort(key=lambda s: s[:2])
    return (ranked[0][2], ranked[0][3]) if ranked else ("no_match", None)


def company_key(url):
    m = re.search(r"linkedin\.com/company/([^/?#]+)", url or "")
    return m.group(1).lower() if m else None
