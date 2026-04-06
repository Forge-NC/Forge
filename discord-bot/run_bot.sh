#!/bin/bash
# Run the Forge NC Discord bot under cPanel Python app.
# Add as a cron job: * * * * * /home/forgenc/discord-bot/run_bot.sh
# Checks if bot is already running, starts it if not.

BOTDIR="/home/forgenc/discord-bot"
PIDFILE="$BOTDIR/bot.pid"
LOGFILE="$BOTDIR/bot.log"
PYTHON="/home/forgenc/virtualenv/discord-bot/3.9/bin/python3.9"

# Check if already running
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if kill -0 "$PID" 2>/dev/null; then
        exit 0  # Already running
    fi
    rm -f "$PIDFILE"
fi

# Start the bot
cd "$BOTDIR"
nohup "$PYTHON" bot.py >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
