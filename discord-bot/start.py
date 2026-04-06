"""Start the bot as a background daemon."""
import subprocess
import sys
import os

bot_dir = os.path.dirname(os.path.abspath(__file__))
bot_py = os.path.join(bot_dir, "bot.py")
log_file = os.path.join(bot_dir, "bot.log")
pid_file = os.path.join(bot_dir, "bot.pid")

# Check if already running
if os.path.exists(pid_file):
    try:
        pid = int(open(pid_file).read().strip())
        os.kill(pid, 0)  # Check if process exists
        print(f"Bot already running (PID {pid})")
        sys.exit(0)
    except (OSError, ValueError):
        os.remove(pid_file)

# Start bot in background
with open(log_file, "a") as log:
    proc = subprocess.Popen(
        [sys.executable, bot_py],
        cwd=bot_dir,
        stdout=log,
        stderr=log,
        start_new_session=True,
    )

with open(pid_file, "w") as f:
    f.write(str(proc.pid))

print(f"Bot started (PID {proc.pid})")
