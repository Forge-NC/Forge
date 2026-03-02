# Forge — Power User Testing Checklist

10 minutes to install, run, and report back. Thanks for testing.

## Prerequisites

- **Python 3.10+** — check with `python --version`
- **Ollama** — install from https://ollama.com, make sure it's running (`ollama list`)
- **GPU** — 8GB+ VRAM recommended (works on CPU, just slower)
- **Windows 10/11 or Linux**

## Step 1: Install (2 min)

```bash
cd Forge
python install.py
```

The installer will:
1. Create a Python virtual environment
2. Install all dependencies
3. Check voice input availability
4. Ask if you want to enable anonymous telemetry (recommended — helps us improve)
5. Create a desktop shortcut

## Step 2: Launch (30 sec)

```bash
# Console mode (default)
.venv/Scripts/forge          # Windows
.venv/bin/forge              # Linux

# Or use the desktop shortcut "Forge NC" for the GUI dashboard
```

On first run, Forge will:
- Create `~/.forge/` config directory
- Detect your Ollama installation
- Offer to pull `qwen2.5-coder:14b` if not already installed (~9GB)

## Step 3: Try a Task (3 min)

Give Forge something to do in a real project directory:

```
> Review this codebase and suggest improvements
> Write a function that parses CSV files with error handling
> Find all TODO comments in this project
```

Try a few turns of conversation. Notice the context management — it handles long sessions automatically.

## Step 4: Explore Commands (2 min)

```
/help           — see all 45 commands
/context        — check context window usage
/continuity     — see context quality grade (A-F)
/billing        — token usage this session
/safety         — current safety level
/theme          — try different color themes (midnight, dracula, cyberpunk, matrix...)
/dashboard      — open the HUD overlay
```

## Step 5: Export Audit Bundle (30 sec)

```
/export
```

This creates a zip at `~/.forge/exports/` containing your full session audit. If you opted into telemetry, this also auto-uploads on exit.

To manually upload:
```
/export --upload
```

## Step 6: Run Stress Test (5 min)

```bash
cd Forge
.venv/Scripts/python scripts/run_live_stress.py --live --smoke -n 1
```

This runs 3 scenarios (crash recovery, malicious repo, repair loop) against your real Ollama. Takes ~5 minutes.

View results:
```bash
.venv/Scripts/python scripts/view_stress_results.py
```

## Reporting Issues

When reporting a bug or friction point, include:
1. What you were doing
2. What happened vs what you expected
3. Your `/export` bundle (if possible) — it contains the full session trace

## Telemetry

If you enabled telemetry during install, Forge sends a redacted summary at the end of each session:
- Session duration, turn count, model name
- Token counts (input/output/cached)
- Threat detection counts (no content)
- Continuity grade, platform, Forge version

**No user prompts or AI responses are sent** (unless you disable redaction in Settings > Telemetry).

Change anytime: Settings > Telemetry tab, or edit `~/.forge/config.yaml`:
```yaml
telemetry_enabled: true    # or false to disable
telemetry_redact: true     # or false for full data
```

## Known Issues

- Voice input requires extra deps: `pip install forge[voice]`
- First model pull (~9GB) takes a while on slow connections
- GUI terminal effects may flicker on older GPUs

## Quick Reference

| Action | Command |
|--------|---------|
| Quit | `/quit` or Ctrl+C |
| Save session | `/save mysession` |
| Load session | `/load mysession` |
| Switch model | `/model qwen2.5-coder:3b` |
| Export audit | `/export` |
| Upload audit | `/export --upload` |
| Run stress test | `python scripts/run_live_stress.py --live --smoke -n 1` |
