"""Isolated Forge Judge inference — runs as its OWN process.

WHY a separate process: the weights-audit path tears down the model-under-test vLLM in the
SAME worker process, then needs the 24B judge. Loading + generating the judge in that same
process inherits a corrupted CUDA/NVML allocator state from the torn-down vLLM -> the canary
hit `RuntimeError: NVML_SUCCESS == r INTERNAL ASSERT FAILED (CUDACachingAllocator.cpp:1154)`
on the first generate(). Running here, in a fresh process, gives the judge a clean CUDA
context. handler._run_judge invokes this via subprocess and reads the result back.

Same loader as the validated eval stack: base 4-bit NF4 + trained LoRA adapter, distinct pad
token, left padding, deterministic greedy decode, B=1 vs B=8 self-check (correctness > speed).

Usage: python judge_subproc.py <input.json> <output.json>
  input.json : {base, adapter_url, fj_secret, prompts:[...], max_new_tokens?, max_len?}
  output.json: {status, generations:[...], batch_size, n}   (status: completed|failed)
"""
import glob
import io
import json
import os
import sys
import tarfile
import urllib.request


def run_judge(job_input: dict) -> dict:
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    # Reduce CUDA fragmentation so the 4-bit 24B fits cleanly on tight-VRAM tiers after the
    # model-under-test vLLM is reclaimed (the OOM error message itself recommends this). Set both
    # names: PyTorch 2.10 reads PYTORCH_ALLOC_CONF, older builds PYTORCH_CUDA_ALLOC_CONF.
    os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    base = job_input.get("base", "")
    adapter_url = job_input.get("adapter_url", "")
    fj_secret = job_input.get("fj_secret", "")
    prompts = job_input.get("prompts") or []
    max_new_tokens = int(job_input.get("max_new_tokens", 320))
    max_len = int(job_input.get("max_len", 4096))
    if not base or not adapter_url:
        return {"status": "failed", "error": "judge job requires 'base' and 'adapter_url'"}
    # stderr streams to the parent handler's Container log (handler runs us with stderr inherited),
    # so each milestone is visible live instead of the whole stage being a black box.
    print(f"[judge] subprocess start: {len(prompts)} cases, fetching adapter", file=sys.stderr, flush=True)

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from peft import PeftModel
    except Exception as exc:
        return {"status": "failed", "error": f"judge deps missing (peft/bitsandbytes): {exc}"}

    # fetch + extract the adapter (~150MB) from the operator's own server
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
            return {"status": "failed", "error": "adapter_config.json not found in adapter archive"}
        adapter_dir = os.path.dirname(cfgs[0])
        print("[judge] adapter fetched + extracted; loading 24B base (4-bit NF4)", file=sys.stderr, flush=True)
    except Exception as exc:
        return {"status": "failed", "error": f"adapter fetch/extract failed: {exc}"}

    try:
        # fix_mistral_regex=True: the Mistral-Small-24B tokenizer ships a known-bad regex that
        # otherwise tokenizes INCORRECTLY (transformers warns + says to set this). The judge base
        # is always Mistral-Small-24B, so pass it; fall back if an older transformers lacks the kwarg.
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
        return {"status": "failed", "error": f"judge model load failed: {exc}"}

    def _progress(msg):
        # stderr is inherited by the parent handler -> streams LIVE to the RunPod Container log,
        # so the judge stage is no longer a black box: we can see the batch decision + per-batch
        # rate and tell a slow B=1 fallback from a load hang from a real timeout.
        print(f"[judge] {msg}", file=sys.stderr, flush=True)

    _progress("model loaded (24B 4-bit NF4 + LoRA); starting scoring")

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
                _progress(f"{tag} batch {bi + 1}/{nb} (B={bs}) scored={base_done + min(s + bs, len(rws))}/{total}")
        return outs

    try:
        if not prompts:
            return {"status": "completed", "generations": [], "batch_size": 1, "n": 0}
        sample = prompts[:8]
        b1, b8 = _gen(sample, 1), _gen(sample, 8)
        bsz = 8 if b1 == b8 else 1
        _progress(f"batch-determinism self-check: B=1 {'==' if bsz == 8 else '!='} B=8 -> using B={bsz} "
                  f"for the remaining {max(0, len(prompts) - 8)} cases ({len(prompts)} total)")
        rest = _gen(prompts[8:], bsz, tag="main", base_done=8, total=len(prompts)) if len(prompts) > 8 else []
        gens = (b1 if bsz == 1 else b8) + rest
        _progress(f"scoring complete: {len(gens)}/{len(prompts)} generations at B={bsz}")
        return {"status": "completed", "generations": gens, "batch_size": bsz, "n": len(gens)}
    except Exception as exc:
        return {"status": "failed", "error": f"judge generation failed: {exc}"}


def main():
    if len(sys.argv) < 3:
        print("usage: judge_subproc.py <input.json> <output.json>", file=sys.stderr)
        sys.exit(2)
    in_path, out_path = sys.argv[1], sys.argv[2]
    try:
        job_input = json.load(open(in_path, encoding="utf-8"))
    except Exception as exc:
        json.dump({"status": "failed", "error": f"bad input json: {exc}"},
                  open(out_path, "w", encoding="utf-8"))
        return
    try:
        res = run_judge(job_input)
    except Exception as exc:
        res = {"status": "failed", "error": f"judge subprocess crashed: {exc}"}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f)


if __name__ == "__main__":
    main()
