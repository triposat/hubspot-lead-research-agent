import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html import escape

from composio import Composio
from dotenv import load_dotenv

from brief import write_brief
from identify import identify
from verify import FREE_MAIL, company_key
from webdata import homepage_markdown

load_dotenv()  # read .env; variables already set in the shell take precedence

composio = Composio()
session = composio.sessions.create(
    user_id=os.environ["COMPOSIO_USER_ID"],
    toolkits=["hubspot", "slack"],
    # The session refuses any tool that isn't on these lists.
    tools={"hubspot": {"enable": ["HUBSPOT_SEARCH_CONTACTS_BY_CRITERIA", "HUBSPOT_UPDATE_CONTACT",
                                  "HUBSPOT_CREATE_NOTE"]},
           "slack": {"enable": ["SLACK_SEND_MESSAGE"]}},
)
CHANNEL = os.environ["SLACK_CHANNEL"]
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "300"))
# Only contacts created after this moment, so the first run doesn't research the whole CRM.
SINCE = datetime.fromisoformat(os.environ["RESEARCH_SINCE"])
FIELDS = ["email", "firstname", "lastname", "company", "jobtitle", "createdate"]


def tool(slug, **arguments):
    result = session.execute(slug, arguments=arguments)
    if result.error:
        raise RuntimeError(f"{slug}: {result.error}")
    return result.data


def new_contacts():
    """New contacts that have an email and that the agent hasn't marked yet."""
    since = int(SINCE.timestamp() * 1000)
    data = tool("HUBSPOT_SEARCH_CONTACTS_BY_CRITERIA", limit=100, properties=FIELDS,
                filterGroups=[{"filters": [
                    {"propertyName": "createdate", "operator": "GTE", "value": str(since)},
                    {"propertyName": "email", "operator": "HAS_PROPERTY"},
                    {"propertyName": "ai_identity_check", "operator": "NOT_HAS_PROPERTY"},
                ]}],
                sorts=[{"propertyName": "createdate", "direction": "ASCENDING"}])
    return data.get("results", [])


def set_fields(contact_id, fields):
    tool("HUBSPOT_UPDATE_CONTACT", contactId=contact_id, custom_properties=fields)


def run_job(contact):
    try:
        research_lead(contact["id"], contact["properties"])
    except Exception:  # mark it, so the lead is visible in HubSpot instead of lost
        logging.exception("research failed for contact %s", contact["id"])
        set_fields(contact["id"], {"ai_identity_check": "error"})


def main(once=False):
    logging.info("polling HubSpot every %s seconds for contacts created after %s",
                 POLL_SECONDS, SINCE)
    workers = ThreadPoolExecutor(max_workers=4)
    while True:
        try:
            for contact in new_contacts():
                # Mark it first: the next search skips any contact with ai_identity_check set.
                set_fields(contact["id"], {"ai_identity_check": "researching"})
                workers.submit(run_job, contact)
        except Exception:  # an unmarked contact waits for the next poll
            logging.exception("poll failed")
        if once:  # 1 poll per run, for a scheduler such as cron
            workers.shutdown(wait=True)
            return
        time.sleep(POLL_SECONDS)


def research_lead(contact_id, c):
    lead = {"first": c.get("firstname") or "", "last": c.get("lastname") or "",
            "email": c["email"], "company": c.get("company"), "title": c.get("jobtitle")}
    domain = lead["email"].rsplit("@", 1)[-1].lower()

    with ThreadPoolExecutor(max_workers=1) as pool:
        site = pool.submit(homepage_markdown, domain) if domain not in FREE_MAIL else None
        identity, person, companies, candidates = identify(lead, domain)
        try:
            homepage = site.result() if site else ""
        except Exception:  # a missing homepage shouldn't stop the brief
            homepage = ""

    company = companies.get(company_key(((person or {}).get("current_company") or {}).get("link")))
    research = {"identity_check": identity, "homepage_markdown": homepage}
    if identity == "verified":
        # Public profiles can omit the job title, so pass the search result title too.
        research |= {"linkedin": slim_profile(person), "company_linkedin": slim_company(company),
                     "search_result_title": candidates.get(person["input"]["url"], "")}
    elif identity == "job_change":
        # Same name, different company: a job change or a different person. Share only the employer.
        research["same_name_profile_company"] = person.get("current_company_name")
    brief = write_brief(lead, research)

    fields = {"ai_identity_check": identity, "ai_brief_headline": brief.headline}
    if identity == "verified":
        fields |= {"ai_linkedin_url": person["input"]["url"],
                   "ai_current_company": person.get("current_company_name") or "",
                   "ai_company_size": (company or {}).get("company_size") or ""}
    set_fields(contact_id, fields)
    tool("HUBSPOT_CREATE_NOTE", hs_timestamp=int(time.time() * 1000),
         hs_note_body=note(brief, identity), associations=[{"to": {"id": contact_id}, "types": [
             {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]}])
    tool("SLACK_SEND_MESSAGE", channel=CHANNEL, markdown_text=render(lead, brief, identity))
    logging.info("contact %s: %s", contact_id, identity)


def slim_profile(p):
    if not p:
        return None
    return {"name": p.get("name"), "position": p.get("position"),
            "current_company": p.get("current_company_name"), "city": p.get("city"),
            "about": (p.get("about") or "")[:600], "followers": p.get("followers"),
            "recent_posts": [{"title": x.get("title"), "date": x.get("created_at")}
                             for x in (p.get("posts") or [])[:3]],
            "url": p.get("url")}


def slim_company(c):
    if not c:
        return None
    return {"name": c.get("name"), "website": c.get("website_simplified"),
            "size": c.get("company_size"), "industry": c.get("industries"),
            "headquarters": c.get("headquarters"), "about": (c.get("about") or "")[:600],
            "recent_updates": [{"date": u.get("date"), "text": (u.get("text") or "")[:200]}
                               for u in (c.get("updates") or [])[:3]]}


def confidence(brief, identity):
    return brief.confidence if identity == "verified" else "low"


def note(brief, identity):
    items = lambda xs: "".join(f"<li>{escape(x)}</li>" for x in xs) or "<li>none</li>"
    return (f"<p><strong>{escape(brief.headline)}</strong></p>"
            f"<p>Talking points:</p><ul>{items(brief.talking_points)}</ul>"
            f"<p>Company: {escape(brief.company_snapshot)}</p>"
            f"<p>Watch out:</p><ul>{items(brief.watch_outs)}</ul>"
            f"<p><em>Identity check: {identity}. "
            f"Confidence: {confidence(brief, identity)}.</em></p>")


def render(lead, brief, identity):
    def esc(text):  # Slack reads <...> as mentions and links, and [text](url) hides a link's target
        return str(text).replace("<", "").replace(">", "").replace("](", "] (")
    points = "\n".join(f"- {esc(p)}" for p in brief.talking_points)
    watch = "\n".join(f"- {esc(w)}" for w in brief.watch_outs) or "- none"
    # Code format, so Slack doesn't turn the address into a mailto link
    email = esc(lead["email"]).replace("`", "")
    return (f"**New lead: {esc(lead['first'])} {esc(lead['last'])}** (`{email}`)\n"
            f"{esc(brief.headline)}\n\n**Talking points**\n{points}\n\n"
            f"**Company:** {esc(brief.company_snapshot)}\n\n**Watch out**\n{watch}\n\n"
            f"_Identity check: {identity}. Confidence: {confidence(brief, identity)}._")


if __name__ == "__main__":
    # force=True, because importing composio already configures the root logger
    logging.basicConfig(level=logging.INFO, force=True)
    for name in ("httpx", "httpx2"):  # skip one line per API request
        logging.getLogger(name).setLevel(logging.WARNING)
    main(once="--once" in sys.argv)
