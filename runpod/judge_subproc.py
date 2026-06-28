"""Isolated Forge Judge inference — runs as its OWN process.

WHY a separate process: the weights-audit path tears down the model-under-test vLLM in the
SAME worker process, then needs the 24B judge. Loading + generating the judge in that same
process inherits a corrupted CUDA/NVML allocator state from the torn-down vLLM -> the canary
hit `RuntimeError: NVML_SUCCESS == r INTERNAL ASSERT FAILED (CUDACachingAllocator.cpp:1154)`
on the first generate(). Running here, in a fresh process, gives the judge a clean CUDA
context. handler._run_judge invokes this via subprocess and reads the result back.

Same loader as the validated eval stack: base 4-bit NF4 + trained LoRA adapter, distinct pad
token, left padding, deterministic greedy decode, B=1 vs B=8 self-check (correctness > speed).

OBSERVABILITY: every milestone prints to stderr (the handler streams stderr to its logger ->
Container log AND server/Intelligence-tab log, live) AND is written to a progress sidecar JSON
(argv[3]) that is rewritten after every batch. The sidecar is the durable record: it survives a
timeout-kill (the streamed lines die with the Container log) and rides home in the delivered
report's diagnostics, so we can always tell a slow B=1 fallback from a load failure from an OOM
from a timeout — without the inaccessible Container log.

Usage: python judge_subproc.py <input.json> <output.json> [<progress.json>]
  input.json   : {base, adapter_url, fj_secret, prompts:[...], max_new_tokens?, max_len?}
  output.json  : {status, generations:[...], batch_size, n, diag:{...}}   (status: completed|failed)
  progress.json: live diag dict, rewritten each step (optional but the handler always passes it)
"""
import glob
import io
import json
import os
import sys
import tarfile
import time
import traceback
import urllib.request


def run_judge(job_input: dict, prog_path: str = "") -> dict:
    t0 = time.monotonic()
    prompts = job_input.get("prompts") or []
    diag = {"phase": "start", "n_prompts": len(prompts), "scored": 0}

    def save():
        if prog_path:
            try:
                with open(prog_path, "w", encoding="utf-8") as pf:
                    json.dump(diag, pf)
            except Exception:
                pass

    def emit(msg):
        # stderr -> handler log pump -> Container log + server/Intelligence-tab log (live).
        print(f"[judge] {msg}", file=sys.stderr, flush=True)

    def fail(stage, exc):
        diag["phase"] = "failed:" + stage
        diag["error"] = f"{type(exc).__name__}: {exc}"
        diag["traceback"] = traceback.format_exc()[-2500:]
        diag["elapsed_s"] = round(time.monotonic() - t0, 1)
        save()
        emit(f"FAILED at {stage}: {type(exc).__name__}: {exc}")
        return {"status": "failed", "error": f"judge {stage} failed: {exc}", "diag": diag}

    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    # Reduce CUDA fragmentation so the 4-bit 24B fits cleanly on tight-VRAM tiers after the
    # model-under-test vLLM is reclaimed. Set both names (PyTorch 2.10 reads PYTORCH_ALLOC_CONF).
    os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    base = job_input.get("base", "")
    adapter_url = job_input.get("adapter_url", "")
    fj_secret = job_input.get("fj_secret", "")
    max_new_tokens = int(job_input.get("max_new_tokens", 320))
    max_len = int(job_input.get("max_len", 4096))
    diag["max_new_tokens"] = max_new_tokens
    diag["max_len"] = max_len
    if not base or not adapter_url:
        return fail("config", ValueError("judge job requires 'base' and 'adapter_url'"))
    emit(f"subprocess start: {len(prompts)} cases")
    diag["phase"] = "imports"
    save()

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from peft import PeftModel
    except Exception as exc:
        return fail("deps", exc)

    try:
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            diag["gpu"] = torch.cuda.get_device_name(0)
            diag["vram_total_gb"] = round(total / 1e9, 1)
            diag["vram_free_gb_pre"] = round(free / 1e9, 1)
            emit(f"device: {diag['gpu']} vram_free={diag['vram_free_gb_pre']}/{diag['vram_total_gb']}GB")
        else:
            diag["gpu"] = "NONE (cuda not available)"
            emit("WARNING: torch.cuda.is_available() == False")
    except Exception:
        pass
    diag["phase"] = "fetch_adapter"
    save()

    # fetch + extract the adapter (~150MB) from the operator's own server
    t = time.monotonic()
    try:
        _hdrs = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}   # Cloudflare 403s the default urllib UA
        if fj_secret:
            _hdrs["X-FJ-Secret"] = fj_secret
        req = urllib.request.Request(adapter_url, headers=_hdrs)
        data = urllib.request.urlopen(req, timeout=600).read()
        adir = "/tmp/fj_judge_adapter"
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            tf.extractall(adir)
        cfgs = glob.glob(os.path.join(adir, "**", "adapter_config.json"), recursive=True)
        if not cfgs:
            return fail("adapter_fetch", FileNotFoundError("adapter_config.json not in archive"))
        adapter_dir = os.path.dirname(cfgs[0])
    except Exception as exc:
        return fail("adapter_fetch", exc)
    diag["adapter_fetch_s"] = round(time.monotonic() - t, 1)
    diag["adapter_bytes"] = len(data)
    emit(f"adapter fetched + extracted ({diag['adapter_bytes']} bytes, {diag['adapter_fetch_s']}s); loading 24B 4-bit NF4")
    diag["phase"] = "load_model"
    save()

    t = time.monotonic()
    try:
        # fix_mistral_regex=True: the Mistral-Small-24B tokenizer ships a known-bad regex.
        try:
            tok = AutoTokenizer.from_pretrained(base, fix_mistral_regex=True)
        except TypeError:
            tok = AutoTokenizer.from_pretrained(base)
        tok.pad_token = tok.unk_token if tok.unk_token is not None else tok.eos_token
        tok.padding_side = "left"
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                 bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
        base_model = AutoModelForCausalLM.from_pretrained(
            base, quantization_config=bnb, device_map="cuda", dtype=torch.bfloat16)
        model = PeftModel.from_pretrained(base_model, adapter_dir)
        model.eval()
    except Exception as exc:
        return fail("model_load", exc)
    diag["model_load_s"] = round(time.monotonic() - t, 1)
    try:
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            diag["vram_free_gb_post_load"] = round(free / 1e9, 1)
    except Exception:
        pass
    emit(f"model loaded ({diag['model_load_s']}s, vram_free_post={diag.get('vram_free_gb_post_load','?')}GB); scoring")
    diag["phase"] = "selfcheck"
    save()

    def _gen(rws, bs, tag=None, base_done=0, total=0):
        outs = []
        nb = (len(rws) + bs - 1) // bs
        for bi, s in enumerate(range(0, len(rws), bs)):
            chunk = rws[s:s + bs]
            rendered = [tok.apply_chat_template([{"role": "user", "content": p}],
                                                tokenize=False, add_generation_prompt=True) for p in chunk]
            enc = tok(rendered, return_tensors="pt", padding=True, truncation=True,
                      max_length=max_len).to(model.device)
            with torch.no_grad():
                out = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False,
                                     pad_token_id=tok.pad_token_id)
            outs.extend(tok.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True))
            if tag:
                done = base_done + min(s + bs, len(rws))
                diag["scored"] = done
                diag["batch_size"] = bs
                save()
                emit(f"{tag} batch {bi + 1}/{nb} (B={bs}) scored={done}/{total} "
                     f"elapsed={round(time.monotonic() - t0)}s")
        return outs

    try:
        if not prompts:
            diag["phase"] = "completed"
            save()
            return {"status": "completed", "generations": [], "batch_size": 1, "n": 0, "diag": diag}
        sample = prompts[:8]
        ts = time.monotonic()
        b1, b8 = _gen(sample, 1), _gen(sample, 8)
        diag["selfcheck_s"] = round(time.monotonic() - ts, 1)
        bsz = 8 if b1 == b8 else 1
        diag["b1_eq_b8"] = (b1 == b8)
        diag["batch_size"] = bsz
        emit(f"self-check: B=1 {'==' if bsz == 8 else '!='} B=8 -> B={bsz} ({diag['selfcheck_s']}s); "
             f"scoring remaining {max(0, len(prompts) - 8)} of {len(prompts)}")
        diag["phase"] = "scoring"
        save()
        ts = time.monotonic()
        rest = _gen(prompts[8:], bsz, tag="main", base_done=8, total=len(prompts)) if len(prompts) > 8 else []
        gens = (b1 if bsz == 1 else b8) + rest
        diag["scoring_s"] = round(time.monotonic() - ts, 1)
        diag["n_generated"] = len(gens)
        diag["n_empty"] = sum(1 for g in gens if not (g or "").strip())
        diag["elapsed_s"] = round(time.monotonic() - t0, 1)
        diag["phase"] = "completed"
        save()
        emit(f"scoring complete: {len(gens)}/{len(prompts)} at B={bsz}, "
             f"{diag['n_empty']} empty, total {diag['elapsed_s']}s")
        return {"status": "completed", "generations": gens, "batch_size": bsz,
                "n": len(gens), "diag": diag}
    except Exception as exc:
        return fail("generation", exc)


def main():
    if len(sys.argv) < 3:
        print("usage: judge_subproc.py <input.json> <output.json> [<progress.json>]", file=sys.stderr)
        sys.exit(2)
    in_path, out_path = sys.argv[1], sys.argv[2]
    prog_path = sys.argv[3] if len(sys.argv) >= 4 else ""
    try:
        job_input = json.load(open(in_path, encoding="utf-8"))
    except Exception as exc:
        json.dump({"status": "failed", "error": f"bad input json: {exc}"},
                  open(out_path, "w", encoding="utf-8"))
        return
    try:
        res = run_judge(job_input, prog_path)
    except Exception as exc:
        res = {"status": "failed", "error": f"judge subprocess crashed: {exc}",
               "diag": {"traceback": traceback.format_exc()[-2500:]}}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f)


if __name__ == "__main__":
    main()
