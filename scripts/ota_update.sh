#!/bin/bash
# InkSlab OTA Update Script
# Runs detached from the web process so it survives service restarts.
# Writes progress to /tmp/inkslab_update_status.json at each stage.

STATUS_FILE="/tmp/inkslab_update_status.json"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

write_status() {
    local stage="$1"
    local message="$2"
    local error="$3"
    echo "{\"stage\":\"$stage\",\"message\":\"$message\",\"error\":\"$error\",\"timestamp\":$(date +%s)}" > "$STATUS_FILE"
}

cd "$SCRIPT_DIR" || {
    write_status "error" "Failed to cd to project directory" "true"
    exit 1
}

# Stage 1: Fetch
write_status "fetching" "Checking for updates..." ""
if ! git fetch origin 2>&1; then
    write_status "error" "Failed to fetch from remote. Check internet connection." "true"
    exit 1
fi

# Stage 2: Pull
write_status "pulling" "Downloading update..." ""
if ! git pull origin master 2>&1; then
    # Fallback: hard reset
    write_status "pulling" "Pull failed, resetting to remote..." ""
    if ! git reset --hard origin/master 2>&1; then
        write_status "error" "Failed to update. Manual intervention needed." "true"
        exit 1
    fi
fi

# Stage 3: Restart display daemon
write_status "restarting_display" "Restarting display service..." ""
sudo systemctl restart inkslab 2>&1 || true

# Stage 4: Pre-restart web — write status before we kill ourselves
write_status "restarting_web" "Restarting web dashboard... Reconnecting shortly." ""
sleep 1

# Stage 5: Restart web dashboard (this kills the Flask process, but we're detached)
sudo systemctl restart inkslab_web 2>&1 || true

# Wait for web to come back up
sleep 3

# Stage 6: Complete
write_status "complete" "Update complete! Page will reload." ""
