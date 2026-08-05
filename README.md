# Socius Connect room monitor

Checks connect.sociuswonen.nl every 5 minutes for any room whose listing
is no longer showing "No more spots available", and pings a Discord
channel when one opens up.

## Setup (~10 minutes)

### 1. Create a Discord webhook
In your Discord server: Server Settings → Integrations → Webhooks →
New Webhook → copy the Webhook URL.

### 2. Create a private GitHub repo
Push these files to a new **private** repository (private matters — your
credentials go in as secrets, but keep the repo itself private too).

```bash
cd socius-monitor
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

### 3. Add secrets
In the repo: Settings → Secrets and variables → Actions → New repository
secret. Add all three:

| Name | Value |
|---|---|
| `SOCIUS_EMAIL` | your Socius Connect login email |
| `SOCIUS_PASSWORD` | your Socius Connect password |
| `DISCORD_WEBHOOK_URL` | the webhook URL from step 1 |

### 4. Done
The workflow in `.github/workflows/monitor.yml` runs automatically every
5 minutes. You can also trigger it manually: Actions tab → "Socius room
monitor" → Run workflow.

## How it decides a room is "available"

Every room row on the offers page ends in an action button. When it's
taken, that button is disabled and reads "No more spots available". The
script looks for rows where that button is *not* disabled — that's a
claimable room. It remembers which rooms it already alerted on
(`state.json`, committed back to the repo after each run) so you get
pinged once per newly-available room, not every 5 minutes for the same
one.

## Notes / caveats

- This only watches the "Amsterdam" project section structure shown in
  the page I built it from. If Socius has more cities/projects, they
  should already be picked up too, since the script scans *all*
  `table.table-advanced` tables on the page — but worth checking the
  first Discord message matches what you expect.
- If Socius changes their site's HTML structure, the script will need
  updating.
- Respect their servers: every 5 minutes is already fairly frequent.
  Going faster risks looking like abuse and could get flagged.
- Keep the repo **private** since your login flows through GitHub
  Actions secrets (encrypted, but no reason to make the repo public).
