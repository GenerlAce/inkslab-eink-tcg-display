#!/bin/bash
# InkSlab OTA Update Script
# Runs detached from the web process so it survives service restarts.
# Writes progress to /tmp/inkslab_update_status.json at each stage.

STATUS_FILE="/tmp/inkslab_update_status.json"
LOCK_FILE="/tmp/inkslab_update.lock"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

write_status() {
    local stage="$1"
    local message="$2"
    local error="$3"
    # Use Python for safe JSON output (avoids broken JSON from special chars)
    python3 -c "
import json, time
json.dump({'stage': '$stage', 'message': '''$message''', 'error': '''$error''', 'timestamp': int(time.time())}, open('$STATUS_FILE', 'w'))
" 2>/dev/null || echo "{\"stage\":\"$stage\",\"message\":\"Update in progress\",\"error\":\"$error\",\"timestamp\":$(date +%s)}" > "$STATUS_FILE"
}

cleanup() {
    rm -f "$LOCK_FILE"
}
trap cleanup EXIT

# Prevent concurrent updates
if [ -f "$LOCK_FILE" ]; then
    # Check if the locking process is still alive
    OLD_PID=$(cat "$LOCK_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        write_status "error" "Another update is already running" "true"
        exit 1
    fi
    # Stale lock, remove it
    rm -f "$LOCK_FILE"
fi
echo $$ > "$LOCK_FILE"

cd "$SCRIPT_DIR" || {
    write_status "error" "Failed to cd to project directory" "true"
    exit 1
}

# Auto-detect the default branch (main or master)
BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
if [ -z "$BRANCH" ]; then
    # Fallback: check which branch exists on the remote
    if git rev-parse --verify origin/main >/dev/null 2>&1; then
        BRANCH="main"
    else
        BRANCH="master"
    fi
fi

# Stage 1: Fetch
write_status "fetching" "Checking for updates..." ""
if ! git fetch origin 2>&1; then
    write_status "error" "Failed to fetch from remote. Check internet connection." "true"
    exit 1
fi

# Stage 2: Pull
write_status "pulling" "Downloading update..." ""
if ! git pull origin "$BRANCH" 2>&1; then
    # Fallback: hard reset
    write_status "pulling" "Pull failed, resetting to remote..." ""
    if ! git reset --hard "origin/$BRANCH" 2>&1; then
        write_status "error" "Failed to update. Manual intervention needed." "true"
        exit 1
    fi
fi

# Stage 3: Restart display daemon
write_status "restarting_display" "Restarting display service..." ""
if ! sudo systemctl restart inkslab 2>&1; then
    write_status "error" "Display service restart failed. Try rebooting." "true"
    exit 1
fi

# Stage 4: Pre-restart web — write status before we kill ourselves
write_status "restarting_web" "Restarting web dashboard... Reconnecting shortly." ""
sleep 1

# Stage 5: Restart web dashboard (this kills the Flask process, but we're detached)
if ! sudo systemctl restart inkslab_web 2>&1; then
    write_status "error" "Web service restart failed. Try rebooting." "true"
    exit 1
fi

# Wait for web to come back up
sleep 3

# Stage 6: Complete
write_status "complete" "Update complete! Page will reload." ""
