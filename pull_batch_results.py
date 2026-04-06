"""Pull completed batch break results from RunPod and upload reports to server."""
import json
import sys
import os
import ssl
import urllib.request
import base64
import subprocess

API_KEY = os.environ.get("RUNPOD_API_KEY", "")
SFTP_KEY = os.path.expanduser("~/.ssh/forge_server_key_dec")
SERVER = "forgenc@107.161.23.171"
REMOTE_DIR = "/home/forgenc/public_html/data/assurance/reports"
CTX = ssl.create_default_context()

ENDPOINTS = {
    "small": "saxvu76pwg997x",
    "medium": "qpaycqqpg23i1z",
    "large": "fderlpmi2u2v3p",
    "xxl": "ihpp1qyzlwu5i9",
}


def get_job_status(endpoint_id, job_id):
    req = urllib.request.Request(
        f"https://api.runpod.ai/v2/{endpoint_id}/status/{job_id}",
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    resp = urllib.request.urlopen(req, context=CTX)
    return json.loads(resp.read())


def save_and_upload_report(report_b64, label=""):
    """Decode base64 report, save locally, upload via SFTP."""
    report_json = base64.b64decode(report_b64)
    report = json.loads(report_json)
    run_id = report.get("run_id", "unknown")
    model = report.get("model", "unknown")

    # Save locally
    local_dir = os.path.join(os.path.dirname(__file__), "batch_reports")
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, f"{run_id}.json")
    with open(local_path, "w", encoding="utf-8") as f:
        json.dump(report, f)

    # Upload via SFTP
    sftp_cmd = f'put {local_path} {REMOTE_DIR}/{run_id}.json'
    result = subprocess.run(
        ["sftp", "-i", SFTP_KEY, "-o", "StrictHostKeyChecking=no", "-b", "-", SERVER],
        input=sftp_cmd.encode(),
        capture_output=True,
    )
    ok = result.returncode == 0
    status = "uploaded" if ok else "SFTP FAILED"
    print(f"  {status}: {run_id} ({model}) {label}")
    return ok


def pull_tier(tier_name, job_ids=None):
    """Pull results for a tier. If job_ids provided, check those. Otherwise scan."""
    endpoint_id = ENDPOINTS.get(tier_name)
    if not endpoint_id:
        print(f"Unknown tier: {tier_name}")
        return

    if not job_ids:
        print(f"No job IDs provided for {tier_name}. Pass job IDs as arguments.")
        print("Usage: python pull_batch_results.py <tier> <job_id1> <job_id2> ...")
        return

    uploaded = 0
    failed = 0
    skipped = 0

    for job_id in job_ids:
        job_id = job_id.strip()
        if not job_id:
            continue

        try:
            data = get_job_status(endpoint_id, job_id)
        except Exception as e:
            print(f"  ERROR fetching {job_id}: {e}")
            failed += 1
            continue

        status = data.get("status", "?")
        if status != "COMPLETED":
            print(f"  SKIP {job_id}: {status}")
            if data.get("error"):
                print(f"    Error: {data['error'][:200]}")
            skipped += 1
            continue

        output = data.get("output", {})
        results = output.get("results", [])

        if not results:
            # Single model job — check for report_b64 directly
            for key in ["break_report_b64", "assure_report_b64"]:
                if output.get(key):
                    save_and_upload_report(output[key], key)
                    uploaded += 1
        else:
            # Batch results
            for r in results:
                if r.get("status") != "completed":
                    print(f"  SKIP model {r.get('model','?')}: {r.get('status','?')}")
                    if r.get("error"):
                        print(f"    Error: {r['error'][:200]}")
                    skipped += 1
                    continue

                for key in ["report_b64"]:
                    if r.get(key):
                        save_and_upload_report(r[key], r.get("model", ""))
                        uploaded += 1

    print(f"\nDone: {uploaded} uploaded, {failed} errors, {skipped} skipped")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pull_batch_results.py <tier> [job_id1 job_id2 ...]")
        print("       python pull_batch_results.py small          (reads from batch_jobs_small.json)")
        print("       python pull_batch_results.py small abc123   (specific job IDs)")
        sys.exit(1)

    tier = sys.argv[1]

    if len(sys.argv) > 2:
        job_ids = sys.argv[2:]
    else:
        # Read from saved job log
        log_file = f"batch_jobs_{tier}.json"
        if os.path.exists(log_file):
            with open(log_file) as f:
                jobs = json.load(f)
            job_ids = [j["job_id"] for j in jobs]
            print(f"Loaded {len(job_ids)} job IDs from {log_file}")
        else:
            print(f"No {log_file} found. Pass job IDs as arguments.")
            sys.exit(1)

    pull_tier(tier, job_ids)
