# Forge External Runner

Customer-side audit runner for Forge Certified Audits (self-hosted) and Deployment Assessments (in-VPC). Runs inside a lean Python Docker container, executes the Forge Crucible Assurance Protocol against a target endpoint, and uploads a cryptographically signed report to forge-nc.dev.

**Image:** `ghcr.io/forge-nc/forge-external-runner:v1`
**Source:** `runner/` in this repo
**Protocol spec:** [`docs/forge-protocol-v1.md`](../docs/forge-protocol-v1.md)

## How it works

1. You purchase a Forge Certified Audit or Deployment Assessment.
2. At enrollment time, forge-nc.dev issues you a **sealed bundle** — an encrypted file that only the X25519 private key you generated at enrollment can open.
3. You run this container with the bundle mounted + your private key + the target endpoint's API key.
4. The container opens the bundle, runs the audit against your target, signs the report with a per-job child key derived from the Forge Origin seed, and uploads the signed report.
5. forge-nc.dev verifies the signature, Origin-countersigns, appends to a public transparency log, and returns a URL to your certified report.

## Prerequisites

- Docker 20.10+ (or Podman / containerd equivalent)
- Outbound HTTPS to `api.forge-nc.dev` (and the target endpoint, if external)
- A generated X25519 keypair (the enrollment flow returns one, or you can generate your own with `forge generate-runner-keypair`)

## Usage

```bash
docker run --rm \
  -e FORGE_TARGET_API_KEY="sk-your-api-key" \
  -v /secure/bundle.enc:/bundle/bundle.enc:ro \
  -v /secure/runner.key:/keys/runner.key:ro \
  ghcr.io/forge-nc/forge-external-runner:v1 \
  --bundle /bundle/bundle.enc \
  --runner-priv /keys/runner.key
```

Optional flags:
- `--target-url <url>` — override the endpoint URL from the bundle (useful when the internal DNS name differs from what was registered at purchase)
- `--verbose` / `-v` — verbose logging

## Verifying the image

The image is Sigstore-signed. Verify with `cosign`:

```bash
cosign verify \
  --certificate-identity-regexp 'https://github.com/Forge-NC/forge-external-runner' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/forge-nc/forge-external-runner:v1
```

The digest of the image published for the current protocol version is advertised in `https://forge-nc.dev/.well-known/forge-origin.json` under `runner_image_digest`.

## Security model

- The container runs as a non-root user (`forge`).
- The runner holds only: (a) the short-lived child signing seed from the bundle, (b) the upload secret from the bundle. It never sees the Origin seed.
- The child key is valid for 10 days from issuance. After that, any report signed with it is rejected by forge-nc.dev.
- Bundles are single-use. Once uploaded, the corresponding job_id is burned server-side.
- The runner's X25519 private key never leaves the host you run it on.
- Target endpoint credentials (`FORGE_TARGET_API_KEY`) are used only to make outbound requests to your endpoint and are not transmitted to forge-nc.dev.

## Troubleshooting

- **"envelope origin_envelope_sig did not verify"** — the bundle was tampered with in transit, or the Origin key was rotated after your bundle was issued. Contact support to re-issue.
- **"Bundle already downloaded"** — each bundle download URL is one-shot. Request a fresh bundle via the admin reissue flow.
- **"Upload rejected (429)"** — you've hit the per-job ingest rate limit (10 attempts per 10-day window). Contact support if you think this is in error.
- **"Upload rejected (409) — run_id already exists"** — the report was already ingested. Download the report from the URL returned by the successful ingest.

## License

Proprietary. © Forge NC (Forge Neural Cortex). All rights reserved.
