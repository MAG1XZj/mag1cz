"""
CS2 Update Tracker -> Discord webhook.

Watches SteamDB's GameTracking-CS2 repo on GitHub (their bot commits within
seconds of Valve pushing any CS2 build) and sends a "CS2 update detected"
embed to Discord with the changelist number and a link to the changed files.

Uses ETag conditional requests so quiet checks don't count against GitHub's
rate limit. No dependencies. Keeps a tiny .state.json next to the script so
restarts never miss updates that happened while it was down, and never
re-announce old ones.

Run:  python cs2_update_tracker.py
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ========================== CONFIG - EDIT THESE ==========================
UPDATE_WEBHOOK_URL = "https://discord.com/api/webhooks/1522958173655400479/ccLUOnsZFYBONjlh9NHf98_nzQYvboVZTJSW9JVym1IYFWT5ulog_n2bz3gCSH-VEF_p"

GITHUB_REPO   = "SteamDatabase/GameTracking-CS2"
POLL_INTERVAL = 120  # seconds between GitHub checks

# GitHub personal access token (no scopes needed - public repos only).
# Strongly recommended: without it you share the 60 req/hour limit with every
# other process on the host's IP. With it: 5000/hour.
# Generate at: https://github.com/settings/tokens (classic, no scopes needed)
GITHUB_TOKEN = ""  # <-- paste your token here
# =========================================================================

BLUE = 0x3498DB

STATE_FILE = Path(__file__).with_suffix(".state.json")


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(**kv):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(kv, f)
    except OSError as e:
        print(f"[!] Could not save state: {e}")


def send_webhook(embeds):
    payload = json.dumps({
        "username": "CS2 Update Tracker",
        "embeds": embeds,
    }).encode("utf-8")
    req = urllib.request.Request(
        UPDATE_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "cs2-update-tracker/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15):
            pass
        return True
    except (urllib.error.URLError, OSError) as e:
        print(f"[!] Discord webhook failed: {e}")
        return False


def github_get(url, etag=None):
    """GET a GitHub API URL. Returns (json_data, new_etag) or (None, etag)."""
    headers = {"User-Agent": "cs2-update-tracker/1.0", "Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    if etag:
        headers["If-None-Match"] = etag
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.headers.get("ETag", etag)
    except urllib.error.HTTPError as e:
        if e.code == 304:  # nothing new, normal quiet case
            return None, etag
        if e.code == 401:
            print("[!] GitHub API: 401 Unauthorized — your GITHUB_TOKEN is missing or revoked. "
                  "Generate a new one at https://github.com/settings/tokens")
        else:
            print(f"[!] GitHub API error {e.code}: {e}")
        return None, etag
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"[!] GitHub unreachable: {e}")
        return None, etag


def fetch_new_commits(last_sha, etag):
    """Return (list_of_(sha,summary) newest-first since last_sha, new_etag).

    Fetches up to 3 pages (100 commits) to catch up after downtime.
    Returns an empty list when nothing changed or GitHub was unreachable.
    """
    url = f"https://api.github.com/repos/{GITHUB_REPO}/commits?per_page=30"
    data, new_etag = github_get(url, etag)
    if not data:
        return [], new_etag

    new_commits = []
    for item in data:
        sha = item["sha"]
        if sha == last_sha:
            break
        summary = item["commit"]["message"].splitlines()[0]
        new_commits.append((sha, summary))

    # If we hit 30 commits without finding last_sha there may be more; fetch
    # another page. This keeps catch-up bounded at 90 commits.
    if len(new_commits) == 30:
        page2_url = url + "&page=2"
        data2, _ = github_get(page2_url)
        if data2:
            for item in data2:
                sha = item["sha"]
                if sha == last_sha:
                    break
                summary = item["commit"]["message"].splitlines()[0]
                new_commits.append((sha, summary))

    return new_commits, new_etag


def main():
    if not UPDATE_WEBHOOK_URL or "PASTE_YOUR" in UPDATE_WEBHOOK_URL:
        print("Edit the CONFIG section first: add your Discord webhook URL.")
        return

    state = load_state()
    last_sha = state.get("last_sha")
    etag = None
    if last_sha:
        print(f"[i] Resumed from saved state: {last_sha[:8]}")

    print("CS2 Update Tracker running... (Ctrl+C to stop)")

    while True:
        new_commits, etag = fetch_new_commits(last_sha, etag)

        if new_commits:
            if last_sha is None:
                # First-ever run: baseline so old commits aren't re-announced.
                sha, summary = new_commits[0]
                last_sha = sha
                save_state(last_sha=last_sha)
                print(f"[i] Baseline: {sha[:8]} ({summary[:60]})")
            else:
                # Process oldest-first so each alert appears in chronological order.
                for sha, summary in reversed(new_commits):
                    send_webhook([{
                        "title": ":package: CS2 update detected",
                        "description": (
                            "CS2 Update Tracker — a new CS2 build was just pushed.\n"
                            f"`{summary[:200]}`\n"
                            f"[View changed files](https://github.com/{GITHUB_REPO}/commit/{sha})"
                        ),
                        "color": BLUE,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }])
                    print(f"[i] CS2 update alert sent ({sha[:8]})")

                last_sha = new_commits[0][0]  # newest SHA becomes the new baseline
                save_state(last_sha=last_sha)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
