import os

from composio import Composio
from dotenv import load_dotenv

load_dotenv()  # read .env; variables already set in the shell take precedence

FIELDS = {"ai_identity_check": "AI identity check", "ai_brief_headline": "AI brief headline",
          "ai_linkedin_url": "AI LinkedIn URL", "ai_current_company": "AI current company",
          "ai_company_size": "AI company size"}

session = Composio().sessions.create(user_id=os.environ["COMPOSIO_USER_ID"],
                                     toolkits=["hubspot", "slack"])
for toolkit in ("hubspot", "slack"):
    print(toolkit, session.authorize(toolkit).redirect_url)
input("Approve both links, then press Enter to create the HubSpot properties.")

result = session.execute("HUBSPOT_CREATE_BATCH_OF_PROPERTIES", arguments={
    "objectType": "contacts",
    "inputs": [{"name": name, "label": label, "type": "string", "fieldType": "text",
                "groupName": "contactinformation"} for name, label in FIELDS.items()]})
if result.error:
    raise SystemExit(result.error)
print("created:", [p["name"] for p in result.data.get("results", [])])
for error in result.data.get("errors", []):  # a second run reports each property as existing
    print(error["message"])
