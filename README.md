# Lead research agent for HubSpot

Researches each new HubSpot lead, checks that the LinkedIn profile it finds belongs to that person, and sends the rep a short brief in Slack. It uses Composio for HubSpot and Slack, Bright Data for the LinkedIn and web data, and Claude for the brief.

## Requirements

- Python 3.10 or later. On Windows, use WSL.
- A HubSpot account. The free CRM works.
- A Composio project and API key.
- A Bright Data API key and 2 zones, one for the SERP API and one for Web Unlocker.
- An Anthropic API key.
- A Slack channel for the briefs. The Slack account you connect must be a member of it.

## Install

```bash
git clone https://github.com/triposat/hubspot-lead-research-agent
cd hubspot-lead-research-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

With uv, use `uv venv` and `uv pip install -r requirements.txt` instead.

## Configure

Add your keys and settings to `.env`. Set `RESEARCH_SINCE` to the current time in UTC, so the agent skips contacts created before you start it. The scripts load `.env` when they start, and variables set in your shell take precedence.

If a Bright Data zone uses an IP allowlist, add the IP of the machine that runs the agent.

Optional settings:

| Variable | Default | What it does |
|---|---|---|
| `POLL_SECONDS` | `300` | How often the agent checks HubSpot for new contacts |
| `CLAUDE_MODEL` | `claude-opus-5-5` | The model that writes the brief |
| `BRIGHTDATA_DATASET_SEARCH` | `off` | `on` adds a Dataset Search fallback. Needs funds in your Bright Data account |
| `AGENT_SEARCH` | `off` | `on` adds a Claude search agent for leads the first search misses. Uses more Claude tokens |

## Connect HubSpot and Slack

```bash
python connect.py
```

The script prints a Composio link for HubSpot and one for Slack. Approve both and press Enter. It then creates the 5 `ai_*` contact properties in HubSpot.

## Run

Test with one contact first. Create a contact in HubSpot with a full name and a work email, wait a few seconds, and run a single poll:

```bash
python agent.py --once
```

The brief appears in Slack and as a note on the contact. If the poll doesn't find the contact yet, run it again. Then start the agent:

```bash
python agent.py
```

To run it from cron instead, poll every 5 minutes with a lock so that runs don't overlap. Replace `/path/to` with the folder you cloned into:

```bash
*/5 * * * * cd /path/to/hubspot-lead-research-agent && flock -n /tmp/lead-agent.lock .venv/bin/python agent.py --once >> agent.log 2>&1
```

## What the agent writes to HubSpot

Each new contact gets an `ai_identity_check` value:

- **`researching`** means the research is still running. If the value stays after a crash, clear it to retry.
- **`verified`** means the name and company matched a LinkedIn profile, so the LinkedIn fields are set.
- **`job_change`** means a profile with the same name lists another company. Confirm whether the lead changed jobs or it's a different person.
- **`unverified`** means there was no company to check against, because the lead used a personal email domain or the profile lists no current company.
- **`no_match`** means no LinkedIn profile with the lead's name was found, or the contact has no full name.
- **`error`** means the research didn't finish, and the terminal log shows why. For `ip_forbidden`, add this machine's IP to the zone's allowlist, then clear the field to retry.

## Check accuracy

`evaluate.py` runs the identity check on contacts whose LinkedIn profiles you already know. Put 20 to 50 of them in a CSV with the columns in `known_contacts.example.csv`, then run:

```bash
python evaluate.py known_contacts.csv
```

`test_verify.py` tests the matching rules offline, with no API keys. Run it after you change `verify.py`:

```bash
python -m unittest test_verify.py
```

## Files

| File | What it does |
|---|---|
| `connect.py` | Connects HubSpot and Slack through Composio and creates the HubSpot properties |
| `agent.py` | Polls for new contacts, runs the research, and writes the results |
| `identify.py` | Runs the LinkedIn search, the identity check, and the optional fallbacks |
| `verify.py` | Decides whether a LinkedIn profile belongs to the lead |
| `webdata.py` | Calls the Bright Data SERP API, Web Scraper API, Dataset Search API, and Web Unlocker |
| `brief.py` | Writes the brief with Claude |
| `search_agent.py` | The optional Claude search agent, loaded only when `AGENT_SEARCH=on` |
| `evaluate.py` | Measures the identity check on contacts you know |
| `test_verify.py` | Offline tests for `verify.py` |

## Lead data

The agent stores public data about people who contacted you, and it writes LinkedIn fields to HubSpot only for verified matches. Post briefs to the lead owner rather than a shared channel when you can, and follow the privacy rules that apply to your leads, such as the GDPR.

## License

MIT
