# Lead research agent for HubSpot

The agent polls HubSpot through a Composio session, researches each new contact with Bright Data, checks that the LinkedIn profile belongs to the lead, writes a brief with Claude, and saves the results to HubSpot and Slack.

## Run it

You need Python 3.10 or later. The commands are for macOS and Linux shells. On Windows, use WSL.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

With uv, run `uv venv` and `uv pip install -r requirements.txt` instead.

Copy `.env.example` to `.env` and add your keys and settings. The scripts load it when they start, and variables already set in your shell take precedence:

```bash
cp .env.example .env
```

Then connect HubSpot and Slack and create the 5 `ai_*` contact properties:

```bash
python setup.py
```

To check the agent, create a test contact in HubSpot with a full name and a work email, wait about 10 seconds, and run 1 poll with `python agent.py --once`. If the first poll doesn't find the contact, run it again. Then start the poller:

```bash
python agent.py
```

To run from a scheduler instead, call `python agent.py --once` every 5 minutes, with a lock such as `flock -n` on Linux so that runs never overlap. For example, this crontab line, with `/path/to` replaced by the folder you cloned into:

```bash
*/5 * * * * cd /path/to/hubspot-lead-research-agent && flock -n /tmp/lead-agent.lock .venv/bin/python agent.py --once >> agent.log 2>&1
```

To measure the identity check on contacts you already know, fill a CSV with the columns in `known_contacts.example.csv` and run `python evaluate.py known_contacts.csv`.

## Files

- `setup.py` connects HubSpot and Slack through Composio and creates the HubSpot properties.
- `agent.py` polls for new contacts, marks them as in progress, runs the research, and writes the results.
- `webdata.py` wraps the Bright Data SERP API, Web Scraper API, Dataset Search API, and Web Unlocker.
- `identify.py` runs the search, the identity check, and the optional fallbacks.
- `search_agent.py` is the optional Claude search agent for leads the pipeline couldn't verify. It's imported only when `AGENT_SEARCH=on`.
- `verify.py` decides whether a LinkedIn profile belongs to the lead.
- `evaluate.py` measures the identity check on a CSV of contacts whose LinkedIn profiles you know.
- `brief.py` writes the brief with Claude.

You can also set `POLL_SECONDS` (default 300), `CLAUDE_MODEL` (default `claude-opus-5-5`), `BRIGHTDATA_DATASET_SEARCH=on` for the Dataset Search fallback, after you add funds to your Bright Data account, and `AGENT_SEARCH=on` for the Claude search agent, which spends Claude tokens on each lead it runs for.

## Handling lead data

The agent stores public data about people who contacted you, and it writes LinkedIn fields to HubSpot only for verified matches. Post briefs to the lead owner rather than a shared channel when you can, and follow the privacy rules that apply to your leads, such as the GDPR.
