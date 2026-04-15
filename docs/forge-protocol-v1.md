# Forge External Runner Protocol — v1

> **Status:** DRAFT — M0 specification, implementation in progress.
> **Canonical URL:** https://forge-nc.dev/protocol (once shipped)
> **Reference implementations:**
> - Python: `forge/external_runner_keys.py`
> - PHP: `server/includes/forge_crypto_v2.php`
> **Interop fixtures:** `tests/fixtures/external_runner_vectors.json`
> **Test suites:** `tests/test_external_runner_interop.py`, `server/tests/test_forge_crypto_v2.php`

## 1. Purpose

Forge Certified Audits and Deployment Assessments ordinarily run on forge-nc.dev's RunPod-hosted workers. For two use cases that cannot reach the public internet in the direction forge-nc.dev needs, the Forge External Runner Protocol defines a way for the customer to run the audit themselves while still producing a cryptographically verifiable, Origin-countersigned report that is indistinguishable in every meaningful way from a forge-hosted audit:

1. **Self-Hosted FCA** — An LLM creator runs Forge locally against their own model, requiring no transmission of model weights or endpoint credentials to forge-nc.dev.
2. **Deployment Assessment (in-VPC)** — A company integrating LLMs into a product runs a Forge-published Docker runner inside their own VPC to audit an internal endpoint that forge-nc.dev cannot reach from the public internet.

Both delivery modes use the same protocol. The difference is packaging (Forge CLI vs. Docker container) and the `runner_kind` field in the attestation envelope.

## 2. Threat Model

An adversary may:
- Observe any network traffic between the runner and forge-nc.dev.
- Gain read access to the runner's filesystem after a job completes.
- Gain read access to the distributed runner container image.
- Attempt to replay a bundle or report.
- Attempt to forge an audit report by constructing an envelope from scratch.

An adversary may NOT:
- Compromise the Origin seed (protected server-side + offline backup).
- Break Ed25519, SHA-512, HKDF-SHA512, or X25519 primitives.

The protocol's goal: a forged report or a replayed bundle produces signatures that fail to verify against the Origin public key, and therefore fails `server/verify_report.php` and the transparency log checks.

## 3. Primitives

| Primitive | Usage |
|---|---|
| **Ed25519** | Origin root signing, per-job child key signing, report signing |
| **HKDF-SHA512 (RFC 5869)** | Derivation of per-job child Ed25519 seeds from Origin seed |
| **X25519 sealed box** (libsodium `crypto_box_seal`) | Encryption of the runner bundle to the runner's one-time X25519 public key |
| **XSalsa20-Poly1305 (libsodium secretbox)** | Encryption of customer API keys at rest (existing infra, audit_crypto.php) |
| **SHA-512** | Scenario hash chain, target_hash, scenario_pack_hash |
| **SHA-512 HMAC** | Upload secret authentication of runner-to-server POSTs |
| **BLAKE2b** | Existing Origin-derived symmetric key derivation (audit_crypto.php); not changed |

## 4. Canonical JSON (`forge-cjson-v1`)

A deterministic JSON serialization used everywhere a signature or hash must be computed. Rules:

1. Object keys sorted lexicographically at every level.
2. UTF-8 output, no BOM.
3. No whitespace between tokens. Separators: `,` and `:`.
4. Strings encoded without unnecessary backslash escapes (matches Python's `json.dumps(..., ensure_ascii=False)`).
5. Integers emitted as `123`; finite floats whose value is integer emit as `1.0`; other floats fall back to the language's default representation. (Envelopes do not currently contain floats.)
6. Booleans `true` / `false`; `null` as-is; arrays as `[a,b,c]` in source order (NOT sorted).

**Reference implementations:**
- Python: `forge.external_runner_keys._canonical_json` (uses `json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')`)
- PHP: `Forge\Crypto\forge_canonical_json` in `server/includes/forge_crypto_v2.php`

Golden vectors for canonical JSON are in `tests/fixtures/external_runner_vectors.json` under `canonical_json_cases`.

## 5. HKDF Child Key Derivation

For each paid audit order assigned to the external-runner delivery path, the server derives a per-job Ed25519 keypair.

Inputs:
- `origin_seed`: 32 raw bytes (the Origin Ed25519 seed)
- `job_id`: the job identifier, UTF-8 string
- `issued_at`: unix timestamp when the job is enrolled

HKDF inputs:
- `IKM = origin_seed[:32]`
- `salt = b"forge-external-runner-salt-v1"` (bytes of ASCII string)
- `info = b"forge-external-runner-v1|" + job_id.encode("utf-8") + b"|" + str(issued_at).encode("ascii")`
- `length = 32`

HKDF output becomes the child Ed25519 seed. Its keypair is the child signing key. Under these rules, the same inputs always produce the same keypair — enabling server-side verification without storing child keys.

Golden vectors: `tests/fixtures/external_runner_vectors.json` under `hkdf_cases`.

## 6. Attestation Envelope

The envelope is a JSON object that accompanies every external-runner report. Fields:

| Field | Type | Description |
|---|---|---|
| `scheme` | string | `"forge-external-runner-v1"` |
| `job_id` | string | Unique job identifier |
| `order_id` | string | Forge NC order this job fulfills (`aud_...` style) |
| `passport_id` | string | Buyer's passport (`pp_...` style) |
| `runner_kind` | string | `"self-hosted-fca"` or `"deployment-assessment-vpc"` |
| `target_hash` | string | SHA-512 hex of `endpoint_url + ":" + model_id` — binds the key to a specific audit target |
| `scenario_pack_version` | int | `ASSURANCE_PROTOCOL_VERSION` at issuance time |
| `scenario_pack_hash` | string | SHA-512 hex of the canonical scenario pack content |
| `issued_at` | int | Unix timestamp |
| `expires_at` | int | `issued_at + 10 days` |
| `child_key_name` | string | Human-readable: `"Origin-External-{job_id}"` |
| `child_pub_b64` | string | Base64-encoded raw 32-byte child Ed25519 public key |
| `origin_pub_b64` | string | Base64-encoded raw 32-byte Origin root public key |
| `kdf` | string | `"HKDF-SHA512"` |
| `kdf_salt` | string | `"forge-external-runner-salt-v1"` |
| `kdf_info_prefix` | string | `"forge-external-runner-v1"` |
| `origin_envelope_sig` | string | Ed25519 signature over `forge_canonical_json(envelope_without_sig_field)`, base64-encoded |

Envelope without `origin_envelope_sig` is serialized via `forge-cjson-v1` and signed with the Origin seed. The resulting signature is appended as `origin_envelope_sig`.

## 7. Envelope Verification

Verifiers (server ingest, offline verifier libraries, third parties with the Origin pubkey) must check ALL of:

1. `scheme` equals `"forge-external-runner-v1"`.
2. `now_ts >= issued_at - 60` (clock skew tolerance).
3. `now_ts <= expires_at`.
4. `job_id NOT IN revocation_list` (if revocation list is available).
5. `origin_envelope_sig` verifies over `forge_canonical_json(envelope_minus_sig)` using `origin_pub_b64`.
6. Re-derive child pubkey via §5 using `(origin_seed, job_id, issued_at)`; must equal `child_pub_b64` in the envelope.

Any failure → envelope is rejected. Report carrying a rejected envelope is not certified.

Note: Verifiers that do not possess the `origin_seed` can still perform checks 1–5 using only the Origin public key (treat the HKDF check as assumed-server-correct). Full check 6 requires the seed and runs server-side.

## 8. Sealed Bundle

A sealed bundle is the opaque file the server delivers to the customer's runner. It contains the child private seed and job metadata, encrypted to a one-time X25519 public key the customer generates at enrollment. Only the holder of the corresponding X25519 private key (the runner) can open it.

Bundle format (serialized to file at `bundle_v1.forge.enc`):

```
magic     : 12 bytes  "FORGEBUNDLE\x01"
version   :  1 byte   0x01
runner_pk : 32 bytes  runner's X25519 public key (as provided at enroll)
sealed_ct : N bytes   output of libsodium crypto_box_seal(plaintext, runner_pk)
```

`plaintext` is the canonical JSON of:

```json
{
  "envelope": <full Attestation Envelope, including origin_envelope_sig>,
  "child_priv_seed_b64": "<base64 of 32-byte child Ed25519 seed>",
  "upload_url": "https://api.forge-nc.dev/api/v1/external/ingest",
  "upload_secret_b64": "<base64 of 32-byte HMAC key>",
  "scenario_pack": { ... embedded scenarios ... },
  "origin_pubkey_b64": "<base64 of 32-byte Origin root public key>",
  "single_use_nonce": "<base64 of 16-byte nonce>",
  "issued_at": <unix ts>
}
```

Bundles are one-shot: the server records `single_use_nonce` at enroll time and refuses any re-use. The plaintext also carries the runner's upload secret — a symmetric HMAC key used to authenticate the runner's POST to the ingest endpoint (separate from the child signing key, so upload auth and report signing use different keys).

## 9. Report

The runner produces a standard Forge assurance report using the existing `forge/break_runner.py` + `forge/assurance_report.py` pipeline, with two changes:

1. The report's `pub_key_b64` and `signature` fields use the **child** key (not the runner's machine key).
2. The `_verification.external_envelope` block attaches the full Attestation Envelope from §6.

Server ingest:
1. Runs §7 envelope verification. Fails → 400.
2. Verifies `signature` against `child_pub_b64` using standard Ed25519 detached verification. Fails → 400.
3. Verifies hash chain (scenario entries' `prev_hash` + `entry_hash`) — same rules as existing `assurance_verify.php`.
4. Rejects duplicate `run_id`.
5. Appends an Origin countersignature under `_verification.origin_signature` — covers `{run_id, machine_signature: report.signature, machine_pub_key_b64: report.pub_key_b64, pass_rate, model, scenarios_run, certified_at, certified_by}` per existing audit_orchestrator `_origin_certify_report()` semantics.
6. Appends a leaf to the transparency log (see §10).
7. Stores at `server/data/assurance/reports/{run_id}.json`.

The final artifact has three distinct signatures:
- **child**: inside `signature` (the audit was run under the scoped child key)
- **origin (envelope)**: inside `_verification.external_envelope.origin_envelope_sig` (Origin authorized this job)
- **origin (countersign)**: inside `_verification.origin_signature` (Origin certifies the final report)

All three must verify for the report to be considered valid.

## 10. Transparency Log

Every accepted ingestion appends a leaf to an append-only log. Leaf format:

```json
{
  "leaf_index": <int, monotonically increasing from 0>,
  "ingested_at": <unix ts>,
  "envelope_hash": "<sha512 hex of canonical JSON of envelope>",
  "report_dsse_hash": "<sha512 hex of report JSON bytes as stored>",
  "run_id": "<run_id>",
  "order_id": "<order_id>",
  "passport_id": "<passport_id>",
  "origin_certified": true
}
```

Leaves form a Merkle tree using SHA-512 of the canonical-JSON-encoded leaf. A **Signed Tree Head** (STH) contains:

```json
{
  "tree_size": <int>,
  "root_hash": "<sha512 hex>",
  "timestamp": <unix ts>,
  "log_version": 1
}
```

STH is signed by the Origin key and published at `/.well-known/forge-transparency-sth.json` (and archived per timestamp for historical proofs). STH issuance is triggered on each new leaf append.

Inclusion proofs are served at `/api/v1/external/inclusion_proof?run_id=...`.

## 11. Revocation

Revocations are recorded in an append-only JSON file at `server/data/external_revocations.json`. Each entry:

```json
{
  "seq": <int>,
  "revoked_at": <unix ts>,
  "job_id": "<job_id>",
  "reason": "<string>",
  "approved_by": "<email of Origin-role approver>"
}
```

Two-person approval:
- A non-Origin admin clicks "Revoke" → creates a `pending_approval` record.
- An Origin-role user approves or rejects. Only on approve does the revocation get appended.

The full file is served (Origin-signed summary) at `/.well-known/forge-revocations.json` for third-party verifiers to consult.

## 12. Well-Known Discovery

Three static (server-updated) files under `/.well-known/`:

- `/.well-known/forge-origin.json` — Origin public key, protocol version, URLs for the other two endpoints, runner image digest to pull from GHCR.
- `/.well-known/forge-revocations.json` — Origin-signed revocation list (see §11).
- `/.well-known/forge-transparency-sth.json` — latest Signed Tree Head (see §10).

These are the entry points for any verifier, in any language, to bootstrap offline verification of a Forge Certified Audit report.

## 13. Test Vectors

See `tests/fixtures/external_runner_vectors.json`. Any implementation that claims Forge Protocol v1 compliance must produce:

1. Byte-identical HKDF outputs for the `hkdf_cases` inputs.
2. Byte-identical canonical JSON for the `canonical_json_cases` inputs.
3. Envelope verification results that match Python and PHP reference implementations exactly.

Test vector origin seed is 32 bytes of `0x11`. **This is a deterministic test value, not a real key. Do not use it.**

## 14. Versioning

`forge-external-runner-v1` is this protocol. Any breaking change to the envelope schema, canonical JSON rules, HKDF inputs, or verification semantics requires a new version string (e.g., `forge-external-runner-v2`). Old versions continue to verify as long as the Origin key they reference remains valid.

## 15. Reference Files

| Path | Purpose |
|---|---|
| `forge/external_runner_keys.py` | Python reference implementation |
| `server/includes/forge_crypto_v2.php` | PHP reference implementation |
| `tests/fixtures/external_runner_vectors.json` | Shared golden vectors |
| `tests/test_external_runner_interop.py` | Python parity test suite |
| `server/tests/test_forge_crypto_v2.php` | PHP parity test suite |
| `docs/forge-protocol-v1.md` | This document |
