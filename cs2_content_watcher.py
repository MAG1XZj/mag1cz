"""
CS2 Content Watcher -> Discord webhook.

Digs into each new GameTracking-CS2 commit (the same repo the update tracker
watches) and scans the actual diffs for interesting content:

  - new cases / capsules        ("CSGO_crate_*" strings, incl. charm packs)
  - new weapon skins            ("PaintKit_*_Tag" strings)
  - new stickers                ("StickerKit_*" strings)
  - new charms                  ("keychain_*" strings)
  - new collections             ("CSGO_set_*" strings - armory/map collections)
  - new music kits / agents     ("CSGO_musickit_*" / "CSGO_CustomPlayer_*")
  - event hints                 (changed files whose names mention majors,
                                 operations, events, tournaments, armory, ...)

New items go to the content webhook; event hints go to their own events
webhook. Only sends when it actually finds something - plain updates that
add no content stay silent (the update tracker already announces those).

No dependencies. Keeps a tiny .state.json next to the script so restarts
never miss updates that happened while it was down, and never re-announce
old ones.

Run:  python cs2_content_watcher.py
"""

import json
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ========================== CONFIG - EDIT THESE ==========================
CONTENT_WEBHOOK_URL = "https://discord.com/api/webhooks/1522987358192930877/_weP8bJvbJw11vuo6Rub8HmmQEaPJKj26We1aYyliXzjAioefoaC3W5ngm9vIjo6uTJ3"  # new cases/skins/stickers/...
EVENTS_WEBHOOK_URL  = "https://discord.com/api/webhooks/1522986538689102038/8QiEkaCvgWYoNYcnDAvabJBP6ADFW1p6tmtlL_QVlXg9dnNJJf1vIM72MWGUQ9jtA4ek"  # event hints

GITHUB_REPO   = "SteamDatabase/GameTracking-CS2"
POLL_INTERVAL = 120  # seconds between GitHub checks

# GitHub personal access token (no scopes needed - public repos only).
# Strongly recommended: without it you share the 60 req/hour limit with every
# other process on the host's IP. With it: 5000/hour.
# Generate at: https://github.com/settings/tokens (classic, no scopes needed)
GITHUB_TOKEN = ""  # <-- paste your token here
# =========================================================================

GOLD = 0xF1C40F

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


EVENT_HINT_KEYWORDS = ("major", "operation", "battlepass", "tournament",
                       "event", "season", "pickem", "armory", "xpshop")

ENGLISH_STRINGS = "game/csgo/pak01_dir/resource/csgo_english.txt"
ITEMS_GAME = "game/csgo/pak01_dir/scripts/items/items_game.txt"


def send_webhook(url, embeds, username):
    payload = json.dumps({
        "username": username,
        "embeds": embeds,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "cs2-content-watcher/1.0"},
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
    headers = {"User-Agent": "cs2-content-watcher/1.0", "Accept": "application/vnd.github+json"}
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
    """Return (list_of_sha newest-first since last_sha, new_etag).

    Fetches up to 2 pages (60 commits) to catch up after downtime.
    """
    url = f"https://api.github.com/repos/{GITHUB_REPO}/commits?per_page=30"
    data, new_etag = github_get(url, etag)
    if not data:
        return [], new_etag

    new_shas = []
    for item in data:
        sha = item["sha"]
        if sha == last_sha:
            break
        new_shas.append(sha)

    if len(new_shas) == 30:
        page2_url = url + "&page=2"
        data2, _ = github_get(page2_url)
        if data2:
            for item in data2:
                sha = item["sha"]
                if sha == last_sha:
                    break
                new_shas.append(sha)

    return new_shas, new_etag


def added_lines(patch):
    if not patch:
        return []
    return [l[1:] for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++")]


def scan_commit(sha):
    """Fetch one commit's diffs and extract new content + event hints."""
    detail, _ = github_get(f"https://api.github.com/repos/{GITHUB_REPO}/commits/{sha}")
    if detail is None:
        return None

    findings = {"cases": [], "skins": [], "stickers": [], "charms": [],
                "collections": [], "music": [], "agents": [], "hints": []}

    for f in detail.get("files", []):
        name = f.get("filename", "")
        lower = name.lower()

        if any(k in lower for k in EVENT_HINT_KEYWORDS):
            findings["hints"].append(name)

        if name == ENGLISH_STRINGS:
            for line in added_lines(f.get("patch")):
                m = re.search(r'"CSGO_crate_(?!.*_desc)[\w]+"\s+"([^"]+)"', line)
                if m:
                    findings["cases"].append(m.group(1))
                    continue
                m = re.search(r'"PaintKit_[\w]+_Tag"\s+"([^"]+)"', line)
                if m:
                    findings["skins"].append(m.group(1))
                    continue
                m = re.search(r'"StickerKit_(?!desc_)[\w]+"\s+"([^"]+)"', line)
                if m:
                    findings["stickers"].append(m.group(1))
                    continue
                m = re.search(r'"keychain_(?!.*_desc)[\w]+"\s+"([^"]+)"', line)
                if m:
                    findings["charms"].append(m.group(1))
                    continue
                m = re.search(r'"CSGO_set_(?!.*_desc)[\w]+"\s+"([^"]+)"', line)
                if m:
                    findings["collections"].append(m.group(1))
                    continue
                m = re.search(r'"CSGO_musickit_[\w]+"\s+"([^"]+)"', line)
                if m:
                    findings["music"].append(m.group(1))
                    continue
                m = re.search(r'"CSGO_CustomPlayer_[\w]+"\s+"([^"]+)"', line)
                if m:
                    findings["agents"].append(m.group(1))

        elif name == ITEMS_GAME and f.get("patch") is None and f.get("additions", 0) > 0:
            findings["hints"].append("items_game.txt changed (+%d lines, diff too "
                                     "large to scan)" % f.get("additions", 0))

    for key in findings:
        findings[key] = list(dict.fromkeys(findings[key]))
    return findings


def field(name, items, limit=12):
    shown = items[:limit]
    extra = len(items) - len(shown)
    value = "\n".join(f"• {i}" for i in shown)
    if extra > 0:
        value += f"\n… and {extra} more"
    return {"name": f"{name} ({len(items)})", "value": value[:1024], "inline": False}


def build_content_embed(sha, findings):
    fields = []
    if findings["cases"]:
        fields.append(field(":package: New cases / capsules", findings["cases"]))
    if findings["skins"]:
        fields.append(field(":gun: New skins", findings["skins"]))
    if findings["stickers"]:
        fields.append(field(":label: New stickers", findings["stickers"]))
    if findings["charms"]:
        fields.append(field(":key: New charms", findings["charms"]))
    if findings["collections"]:
        fields.append(field(":art: New collections", findings["collections"]))
    if findings["music"]:
        fields.append(field(":musical_note: New music kits", findings["music"]))
    if findings["agents"]:
        fields.append(field(":detective: New agents", findings["agents"]))
    if not fields:
        return None
    return {
        "title": ":sparkles: New CS2 content detected",
        "description": f"[View the full diff](https://github.com/{GITHUB_REPO}/commit/{sha})",
        "fields": fields[:10],
        "color": GOLD,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_events_embed(sha, findings):
    if not findings["hints"]:
        return None
    return {
        "title": "CS2 event hints detected",
        "description": f"[View the full diff](https://github.com/{GITHUB_REPO}/commit/{sha})",
        "fields": [field("Changed files", findings["hints"], limit=6)],
        "color": GOLD,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main():
    if "PASTE_YOUR" in CONTENT_WEBHOOK_URL + EVENTS_WEBHOOK_URL:
        print("Edit the CONFIG section first: add your Discord webhook URLs.")
        return

    state = load_state()
    last_sha = state.get("last_sha")
    etag = None
    if last_sha:
        print(f"[i] Resumed from saved state: {last_sha[:8]}")

    print("CS2 Content Watcher running... (Ctrl+C to stop)")

    while True:
        new_shas, etag = fetch_new_commits(last_sha, etag)

        if new_shas:
            if last_sha is None:
                last_sha = new_shas[0]
                save_state(last_sha=last_sha)
                print(f"[i] Baseline: {last_sha[:8]}")
            else:
                # Process oldest-first so Discord gets alerts in order.
                for sha in reversed(new_shas):
                    findings = scan_commit(sha)
                    if findings is not None:
                        content = build_content_embed(sha, findings)
                        if content:
                            send_webhook(CONTENT_WEBHOOK_URL, [content], "CS2 Content Watcher")
                            print(f"[i] Content alert sent ({sha[:8]})")
                        events = build_events_embed(sha, findings)
                        if events:
                            send_webhook(EVENTS_WEBHOOK_URL, [events], "CS2 Event Watcher")
                            print(f"[i] Event hints alert sent ({sha[:8]})")
                        if not content and not events:
                            print(f"[i] Update {sha[:8]} contained no new content, staying silent")

                last_sha = new_shas[0]
                save_state(last_sha=last_sha)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
