# Forge Telemetry — Data Contract

## Opt-In Only

Telemetry is **disabled by default**. To enable:

```yaml
# ~/.forge/config.yaml
telemetry_enabled: true
```

## What We Collect

- **Machine ID** — random 12-character hex UUID, generated once and persisted locally in `~/.forge/machine_id`. Not derived from hostname or any user environment data.
- **Platform string** — `platform.platform()` (e.g., "Windows-11-10.0.26200-SP0")
- **Forge version** — hardcoded version string
- **GPU model, VRAM, driver version, CUDA version** — from `nvidia-smi`
- **CPU model, system RAM** — from OS APIs
- **Session metrics** — duration, turn count, aggregate token counts (input/output totals only)
- **Threat counts** — number of threats detected (not content)
- **Continuity grades** — letter grade (A-F) and numeric score
- **Reliability scores** — composite 0-100 score
- **Stress test results** — scenario names, pass/fail, durations, turn counts

## What We Explicitly DO NOT Collect

- File contents, paths, or filenames from user projects
- User prompts or assistant responses (always redacted in telemetry mode)
- IP addresses (server does not log them in profiles)
- Usernames, hostnames, or any PII
- Shell command text (redacted)
- Matched threat text (redacted)

## Redaction

Telemetry bundles use the same `AuditExporter` as `/export --redact`:
- Journal entries: user_intent, assistant_response, key_decisions → `[REDACTED]`
- Forensic events: file contents stripped, only paths/names/exit_codes retained
- Threat log: matched_text → `[REDACTED]`
- Shell commands: command text → `[REDACTED]`

## Retention

- Raw zip bundles: deleted after 90 days
- Machine profiles (aggregate metrics only): retained indefinitely

## Endpoint

Bundles are uploaded to `https://dirt-star.com/Forge/telemetry_receiver.php` via HTTPS POST.

## Authentication

- **Per-user token** (`telemetry_token` in config): takes priority, revocable server-side
- **Legacy shared key**: fallback when no per-user token is configured

## Size Limit

Bundles exceeding 512KB are silently dropped (not uploaded).
