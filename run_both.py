"""Runs the CS2 premier reminder, quest watcher, steam free-games bot
and the steam/cs2 maintenance monitor.

Point your host's startup command at this file:

    python3 -u run_both.py

Expected layout (edit SCRIPTS below if your folder names differ):

    run_both.py
    cs2_premier_reminder.py
    steam_cs2_maintenance_monitor.py   (config lives at the top of the file)
    cs2_update_tracker.py              (config lives at the top of the file)
    steam_update_tracker.py            (config lives at the top of the file)
    cs2_content_watcher.py             (config lives at the top of the file)
    cs2_branch_watcher.py              (config lives at the top of the file)
    requirements.txt                   (for the cs2 bot; the others need none)
    quest-watcher/quest_watcher.py     + its config.json
    steam-free-bot/steam_free_bot.py   + its config.json

Each script keeps its own working directory, so each one's
config.json / seen.json stay inside its folder.
If one crashes, it's restarted after 60s; the others keep running.
"""

import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent

SCRIPTS = [
    BASE / "cs2_premier_reminder.py",
    BASE / "steam_cs2_maintenance_monitor.py",
    BASE / "cs2_update_tracker.py",
    BASE / "steam_update_tracker.py",
    BASE / "cs2_content_watcher.py",
    BASE / "cs2_branch_watcher.py",
    BASE / "quest-watcher" / "quest_watcher.py",
    BASE / "steam-free-bot" / "steam_free_bot.py",
]

RESTART_DELAY = 60  # seconds before restarting a crashed script


def spawn(script):
    print(f"[run_both] starting {script.name}", flush=True)
    return subprocess.Popen([sys.executable, "-u", str(script)], cwd=script.parent)


def main():
    missing = [s for s in SCRIPTS if not s.exists()]
    if missing:
        for s in missing:
            print(f"[run_both] ERROR: {s} not found - fix the paths in SCRIPTS", flush=True)
        sys.exit(1)

    procs = {script: spawn(script) for script in SCRIPTS}

    # pending_restarts maps script -> earliest time to restart it.
    # This avoids blocking the whole loop with time.sleep(RESTART_DELAY).
    pending_restarts = {}

    try:
        while True:
            now = time.monotonic()

            # Fire any pending restarts whose delay has elapsed.
            for script, restart_at in list(pending_restarts.items()):
                if now >= restart_at:
                    procs[script] = spawn(script)
                    del pending_restarts[script]

            # Check for newly crashed processes.
            for script, proc in procs.items():
                if script in pending_restarts:
                    continue  # already queued for restart
                if proc.poll() is not None:
                    print(f"[run_both] {script.name} exited with code {proc.returncode}, "
                          f"restarting in {RESTART_DELAY}s", flush=True)
                    pending_restarts[script] = time.monotonic() + RESTART_DELAY

            time.sleep(5)
    except KeyboardInterrupt:
        for proc in procs.values():
            proc.terminate()


if __name__ == "__main__":
    main()
