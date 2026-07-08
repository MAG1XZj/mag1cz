"""
CS2 Branch Watcher -> Discord webhook.

Watches CS2's Steam depot branches (via the steamcmd.net API, which mirrors
Steam's own app metadata). Unlike the GitHub update tracker - which only sees
builds AFTER they ship publicly - this sees every branch, including the
staging/beta branches Valve pushes builds to BEFORE release.

Alerts on:
  - a brand-new branch appearing        (strongest "something is coming" signal)
  - any branch getting a new build      (staging activity = update being prepared)
  - the public branch getting a new build (the release itself - redundant with
    the GitHub tracker, but independent of it)
  - a branch disappearing               (staging cleanup after release)

No dependencies. Keeps a tiny .state.json next to the script so restarts
never miss branch changes that happened while it was down, and never
re-announce existing branches.

Run:  python cs2_branch_watcher.py
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ========================== CONFIG - EDIT THESE ==========================
BRANCH_WEBHOOK_URL = "https://discord.com/api/webhooks/1523052885464846377/4akPpF1OV_xrxp-ZTJb_s_Hv-033n4BQlUAHBY-y58MMhk7beIcAwrDB9zD_LURMByRN"

APPID         = 730
POLL_INTERVAL = 300  # seconds; steamcmd.net is a free community API, be polite
# =========================================================================

TEAL, GOLD = 0x1ABC9C, 0xF1C40F

STATE_FILE = Path(__file__).with_suffix(".state.json")

_steam_fail_count = 0
_STEAM_FAIL_ALERT_THRESHOLD = 5  # alert to Discord after this many consecutive failures


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
        "username": "CS2 Branch Watcher",
        "embeds": embeds,
    }).encode("utf-8")
    req = urllib.request.Request(
        BRANCH_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "cs2-branch-watcher/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15):
            pass
        return True
    except (urllib.error.URLError, OSError) as e:
        print(f"[!] Discord webhook failed: {e}")
        return False


def fetch_branches():
    """Returns {branch_name: (buildid, timeupdated)} or None if unreachable."""
    global _steam_fail_count
    url = f"https://api.steamcmd.net/v1/info/{APPID}"
    req = urllib.request.Request(url, headers={"User-Agent": "cs2-branch-watcher/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _steam_fail_count = 0  # reset on success
    except (urllib.error.URLError, OSError, ValueError) as e:
        _steam_fail_count += 1
        print(f"[!] steamcmd.net unreachable (attempt {_steam_fail_count}): {e}")
        if _steam_fail_count == _STEAM_FAIL_ALERT_THRESHOLD:
            send_webhook([{
                "title": ":warning: CS2 Branch Watcher: Steam API unreachable",
                "description": (
                    f"steamcmd.net has been unreachable for "
                    f"{_steam_fail_count * POLL_INTERVAL // 60} minutes.\n"
                    "Branch change notifications are paused until it recovers."
                ),
                "color": 0xE74C3C,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }])
        return None

    branches = (data.get("data", {}).get(str(APPID), {})
                    .get("depots", {}).get("branches", {}))
    if not branches:
        return None
    result = {}
    for name, info in branches.items():
        result[name] = (str(info.get("buildid", "?")),
                        int(info.get("timeupdated", 0) or 0))
    return result


def embed(title, description, color):
    return {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main():
    if "PASTE_YOUR" in BRANCH_WEBHOOK_URL:
        print("Edit the CONFIG section first: add your Discord webhook URL.")
        return

    state = load_state()
    known = state.get("branches")  # {branch: [buildid, timeupdated]}
    if known:
        print(f"[i] Resumed from saved state: {len(known)} branches")

    print("CS2 Branch Watcher running... (Ctrl+C to stop)")

    while True:
        branches = fetch_branches()
        if branches:
            if known is None:
                known = branches
                save_state(branches=branches)
                print(f"[i] Baseline: {len(branches)} branches, "
                      f"public build {branches.get('public', ('?',))[0]}")
            else:
                embeds = []

                for name, (build, updated) in branches.items():
                    when = f"<t:{updated}:R>" if updated else "just now"
                    if name not in known:
                        embeds.append(embed(
                            ":new: New CS2 branch appeared",
                            f"Branch **`{name}`** just showed up with build `{build}` ({when}).",
                            GOLD,
                        ))
                        print(f"[i] New branch: {name} (build {build})")
                    elif known[name][0] != build:
                        if name == "public":
                            embeds.append(embed(
                                ":rocket: CS2 public build updated",
                                f"The **public** branch moved to build `{build}` ({when}) "
                                f"- an update just went live.\n"
                                f"Previous build: `{known[name][0]}`",
                                TEAL,
                            ))
                        else:
                            embeds.append(embed(
                                ":test_tube: CS2 staging branch updated",
                                f"Branch **`{name}`** moved to build `{build}` ({when}).\n"
                                f"Previous build: `{known[name][0]}`\n"
                                "Valve is staging a build - an update may be close.",
                                GOLD,
                            ))
                        print(f"[i] Branch updated: {name} -> build {build}")

                for name in known:
                    if name not in branches:
                        embeds.append(embed(
                            ":wastebasket: CS2 branch removed",
                            f"Branch **`{name}`** (last build `{known[name][0]}`) "
                            "is gone from the branch list.",
                            TEAL,
                        ))
                        print(f"[i] Branch removed: {name}")

                if embeds:
                    for i in range(0, len(embeds), 10):
                        send_webhook(embeds[i:i + 10])

                if branches != known:
                    save_state(branches=branches)
                known = branches

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
