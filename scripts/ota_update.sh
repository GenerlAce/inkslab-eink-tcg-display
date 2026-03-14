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
    # Pass values via env vars to avoid shell injection into Python strings
    _STAGE="$stage" _MSG="$message" _ERR="$error" _SF="$STATUS_FILE" \
    python3 -c "
import json, time, os
json.dump({
    'stage': os.environ['_STAGE'],
    'message': os.environ['_MSG'],
    'error': os.environ['_ERR'],
    'timestamp': int(time.time())
}, open(os.environ['_SF'], 'w'))
" 2>/dev/null || echo "{\"stage\":\"update\",\"message\":\"Working...\",\"error\":\"\",\"timestamp\":$(date +%s)}" > "$STATUS_FILE"
}

cleanup() {
    rm -f "$LOCK_FILE"
}
trap cleanup EXIT

# Prevent concurrent updates
if [ -f "$LOCK_FILE" ]; then
    OLD_PID=$(cat "$LOCK_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        write_status "error" "Another update is already running" "true"
        exit 1
    fi
    rm -f "$LOCK_FILE"
fi
echo $$ > "$LOCK_FILE"

cd "$SCRIPT_DIR" || {
    write_status "error" "Failed to cd to project directory" "true"
    exit 1
}

# Fix "dubious ownership" error — service runs as root but repo is owned by pi
git config --global --add safe.directory "$SCRIPT_DIR" 2>/dev/null

# Auto-detect the default branch (main or master)
BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
if [ -z "$BRANCH" ]; then
    if git rev-parse --verify origin/main >/dev/null 2>&1; then
        BRANCH="main"
    else
        BRANCH="master"
    fi
fi

# Stage 1: Fetch
write_status "fetching" "Checking for updates..." ""
if ! timeout 60 git fetch origin 2>&1; then
    write_status "error" "Failed to fetch from remote. Check internet connection." "true"
    exit 1
fi

# Stage 2: Pull
write_status "pulling" "Downloading update..." ""
if ! timeout 120 git pull origin "$BRANCH" 2>&1; then
    write_status "pulling" "Pull failed, resetting to remote..." ""
    if ! git reset --hard "origin/$BRANCH" 2>&1; then
        write_status "error" "Failed to update. Manual intervention needed." "true"
        exit 1
    fi
fi

# Stage 2.5: Update service files if they changed
write_status "pulling" "Updating service files..." ""
if [ -f "$SCRIPT_DIR/inkslab.service" ]; then
    cp "$SCRIPT_DIR/inkslab.service" /etc/systemd/system/inkslab.service 2>/dev/null
fi
if [ -f "$SCRIPT_DIR/inkslab_web.service" ]; then
    cp "$SCRIPT_DIR/inkslab_web.service" /etc/systemd/system/inkslab_web.service 2>/dev/null
fi
systemctl daemon-reload 2>/dev/null

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
