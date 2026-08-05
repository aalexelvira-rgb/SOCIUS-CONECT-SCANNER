#!/usr/bin/env python3
"""
Socius Connect room-availability monitor.

Logs into connect.sociuswonen.nl, checks the "Current offers" page for any
living space whose action button is NOT the disabled "No more spots
available" state, and sends a Discord webhook notification when a *new*
available room is found (so you don't get re-notified for the same room
on every run).

State (which rooms we've already alerted on) is stored in state.json next
to this script. In the GitHub Actions setup, that file is committed back
to the repo after every run so state persists between scheduled runs.
"""

import json
import os
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://connect.sociuswonen.nl"
LOGIN_URL = f"{BASE_URL}/account/do_login"
OFFERS_URL = f"{BASE_URL}/kamer_vinden/aanbod/overzicht/"

STATE_FILE = Path(__file__).parent / "state.json"

# --- Credentials & webhook come from environment variables ---
# Never hardcode these. Set them as GitHub Actions secrets (see README).
EMAIL = os.environ.get("SOCIUS_EMAIL")
PASSWORD = os.environ.get("SOCIUS_PASSWORD")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}


def load_state() -> set:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text()))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def save_state(seen: set) -> None:
    STATE_FILE.write_text(json.dumps(sorted(seen), indent=2))


def login(session: requests.Session) -> None:
    if not EMAIL or not PASSWORD:
        sys.exit("ERROR: SOCIUS_EMAIL and SOCIUS_PASSWORD environment variables must be set.")

    # Grab the login page first so we pick up any session/CSRF cookies
    session.get(f"{BASE_URL}/account/login", headers=HEADERS, timeout=20)

    resp = session.post(
        LOGIN_URL,
        data={
            "email": EMAIL,
            "password": PASSWORD,
            "submit_login": "Inloggen",
        },
        headers=HEADERS,
        timeout=20,
    )
    resp.raise_for_status()

    # A failed login re-renders the login form. A successful one redirects
    # (or returns content from the offers page). We do a sanity check below
    # once we fetch the offers page instead of trusting this response alone.


def fetch_offers_html(session: requests.Session) -> str:
    resp = session.get(OFFERS_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_available_rooms(html: str):
    """
    Returns a list of dicts for every room row whose action cell does NOT
    contain a 'disabled' button (i.e. it's actually claimable/registerable).
    Each dict has a stable-ish id plus the details worth putting in a
    notification.
    """
    soup = BeautifulSoup(html, "html.parser")
    available = []

    # Every project's room table has this class combo
    tables = soup.select("table.table-advanced")

    for table in tables:
        headers = [th.get_text(strip=True) for th in table.select("thead th")]

        for row in table.select("tbody tr"):
            cells = row.find_all("td")
            if not cells:
                continue

            action_cell = cells[-1]
            action_link = action_cell.find("a")

            is_disabled = (
                action_link is None
                or "disabled" in action_link.get("class", [])
            )
            if is_disabled:
                continue  # this room is not actually available

            # Build a readable record from whatever columns exist
            values = [c.get_text(strip=True) for c in cells[:-1]]
            record = dict(zip(headers, values))
            action_text = action_link.get_text(strip=True)
            action_href = action_link.get("href", "")

            # A reasonably stable identifier: living space "Number" column
            # if present, else a hash of the row text
            room_id = record.get("Number") or record.get("Nummer")
            if not room_id:
                room_id = str(abs(hash(tuple(values))))

            record["_id"] = room_id
            record["_action_text"] = action_text
            record["_action_href"] = action_href
            available.append(record)

    return available


def notify_discord(room: dict) -> None:
    if not DISCORD_WEBHOOK_URL:
        print("WARNING: DISCORD_WEBHOOK_URL not set, skipping notification. Room:", room)
        return

    lines = [f"**Room available!** ({room.get('_action_text', 'Open')})"]
    for key, value in room.items():
        if key.startswith("_"):
            continue
        lines.append(f"**{key}:** {value}")
    if room.get("_action_href"):
        href = room["_action_href"]
        if href.startswith("/"):
            href = BASE_URL + href
        lines.append(f"[Open listing]({href})")
    else:
        lines.append(f"[Open offers page]({OFFERS_URL})")

    payload = {"content": "\n".join(lines)}
    resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=20)
    resp.raise_for_status()


def main():
    session = requests.Session()
    login(session)
    html = fetch_offers_html(session)

    if "Log in" in html and "frmLogin" in html:
        sys.exit("ERROR: Login appears to have failed (landed back on login page). "
                 "Check SOCIUS_EMAIL / SOCIUS_PASSWORD secrets.")

    available_rooms = parse_available_rooms(html)
    seen = load_state()

    current_ids = {room["_id"] for room in available_rooms}
    new_rooms = [room for room in available_rooms if room["_id"] not in seen]

    for room in new_rooms:
        print("New available room found:", room)
        notify_discord(room)

    if not new_rooms:
        print(f"No new available rooms. ({len(available_rooms)} currently available, "
              f"{len(seen)} previously known.)")

    # Update state: keep only rooms that are still actually listed as
    # available, so if a room disappears and later reappears we notify again.
    save_state(current_ids)


if __name__ == "__main__":
    main()
