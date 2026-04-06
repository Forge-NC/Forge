"""Dispatch batch break jobs — one per model to avoid timeout issues."""
import json
import sys
import time
import urllib.request
import ssl

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
FORGE_SERVER = "https://forge-nc.dev"
CTX = ssl.create_default_context()

ENDPOINTS = {
    "small": "saxvu76pwg997x",
    "medium": "qpaycqqpg23i1z",
    "large": "fderlpmi2u2v3p",
    "xxl": "ihpp1qyzlwu5i9",
}

def dispatch_model(endpoint_id, hf_repo, vllm_env=""):
    """Dispatch a single-model batch_break job."""
    payload = json.dumps({
        "input": {
            "order_id": f"batch-{hf_repo.replace('/', '-')[:40]}",
            "model_index": 0,
            "model_name": hf_repo.split("/")[-1],
            "model_id": hf_repo,
            "access_type": "batch_break",
            "models": [hf_repo],
            "forge_server": FORGE_SERVER,
            "webhook_secret": "batch_break",
            "vllm_env": vllm_env or "VLLM_MARLIN_USE_ATOMIC_ADD=1,TORCH_ALLOW_TF32_CUBLAS_OVERRIDE=1",
        },
    }).encode()

    req = urllib.request.Request(
        f"https://api.runpod.ai/v2/{endpoint_id}/run",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    resp = urllib.request.urlopen(req, context=CTX)
    return json.loads(resp.read())


def dispatch_tier(tier_name):
    """Dispatch all models for a given tier."""
    with open("batch_dispatch_lists.json") as f:
        lists = json.load(f)

    if tier_name not in lists:
        print(f"Unknown tier: {tier_name}")
        return

    tier = lists[tier_name]
    models = tier["models"]
    endpoint_id = ENDPOINTS.get(tier_name)
    if not endpoint_id:
        print(f"No endpoint for tier: {tier_name}")
        return

    print(f"Dispatching {len(models)} models to {tier_name} ({endpoint_id})")
    print()

    job_log = []
    for i, hf_repo in enumerate(models):
        result = dispatch_model(endpoint_id, hf_repo)
        status = result.get("status", "?")
        job_id = result.get("id", "?")
        print(f"  [{i+1}/{len(models)}] {status:12s} {job_id[:20]}  {hf_repo}")
        job_log.append({"job_id": job_id, "model": hf_repo, "tier": tier_name})

        if i < len(models) - 1:
            time.sleep(1)

    # Save job IDs for later result pulling
    log_file = f"batch_jobs_{tier_name}.json"
    with open(log_file, "w") as f:
        json.dump(job_log, f, indent=2)

    print(f"\nDone. {len(models)} jobs queued on {tier_name}.")
    print(f"Job IDs saved to {log_file}")
    print(f"Pull results: python pull_batch_results.py {tier_name}")


if __name__ == "__main__":
    tier = sys.argv[1] if len(sys.argv) > 1 else "small"
    dispatch_tier(tier)
