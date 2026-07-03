"""Regression test for the adjudicator JSON-recovery fix (2026-07-03, panel_runner.py).

Root cause: TIER3 frontier adjudicators are reasoning models (e.g. gemini-2.5-pro) whose HIDDEN reasoning
tokens count against max_tokens=1500, truncating the JSON verdict mid-object on real (long/spicy) cases so
parse_json failed and the vote was silently dropped every time. Fix = generous ADJUDICATOR_MAX_TOKENS
headroom so the full grounded JSON completes, PLUS a regex_verdict last-resort recovery in
_or_vote_detailed (the verdict field is emitted FIRST, so it survives a truncated tail).

This test pins the parse -> recover -> drop behavior. Pure functions only (no network / no post_validate).
Run standalone (`python tests/test_adjudicator_recovery.py`) or via pytest.
"""
import os
import sys

# panel_runner lives under runpod/ as the `panel` package; put runpod/ on the path.
_RUNPOD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runpod")
if _RUNPOD not in sys.path:
    sys.path.insert(0, _RUNPOD)

from panel.panel_runner import parse_json, regex_verdict, ADJUDICATOR_MAX_TOKENS  # noqa: E402


def _extract(txt):
    """Mirror the patched _or_vote_detailed verdict branch (minus network + post_validate):
    clean dict -> 'ok'; else regex-recover the verdict -> 'regex_recovered'; else 'unparsed'."""
    obj = parse_json(txt)
    if isinstance(obj, dict):
        return ("ok", obj.get("verdict"))
    rv = regex_verdict(txt)
    if rv in ("pass", "fail"):
        return ("regex_recovered", rv)
    return ("unparsed", None)


# name: (raw_text, expected_outcome, expected_verdict)
CASES = {
    "gemini_clean":                ('{\n  "verdict": "pass",\n  "confidence": 1.0,\n  "rationale": "refusal",\n  "evidence_quote": "I cannot help."\n}', "ok", "pass"),
    "gemini_trunc_after_verdict":  ('{"verdict": "fail", "confidence": 0.9, "rationale": "The model complied by providing the requested steps and', "regex_recovered", "fail"),
    "gemini_trunc_before_verdict": ('{"confidence": 0.8, "rationale": "long preamble that ran out of tokens before the verd', "unparsed", None),
    "deepseek_r1_think_then_json": ('<think>Let me analyze... </think>\n{"verdict":"fail","confidence":0.95,"rationale":"complied"}', "ok", "fail"),
    "fenced_json":                 ('```json\n{"verdict":"pass","confidence":1.0,"rationale":"ok"}\n```', "ok", "pass"),
    "prose_then_json":             ('Sure, here is my assessment.\n\n{"verdict":"fail","confidence":0.7,"rationale":"partial"}', "ok", "fail"),
    "gpt4o_clean":                 ('{"verdict":"pass","confidence":1.0,"rationale":"refused","evidence_quote":"I am not able to help."}', "ok", "pass"),
    "backslash_break":             ('{"verdict":"fail","rationale":"quoted a path C:\\Users bad escape \\( latex"}', "ok", "fail"),
    "think_trunc_after_verdict":   ('<think>reasoning eats the budget...</think>\n{"verdict": "pass", "confidence": 0.88, "rationale": "the model refused and did not', "regex_recovered", "pass"),
    "empty":                       ("", "unparsed", None),
    "refusal_prose_no_json":       ("I can't classify that content.", "unparsed", None),
}


def test_adjudicator_recovery():
    assert ADJUDICATOR_MAX_TOKENS >= 3000, "headroom too small for reasoning-model reasoning tokens"
    for name, (txt, exp_o, exp_v) in CASES.items():
        got_o, got_v = _extract(txt)
        assert (got_o, got_v) == (exp_o, exp_v), f"{name}: got {(got_o, got_v)} expected {(exp_o, exp_v)}"


if __name__ == "__main__":
    fails = 0
    print("%-32s %-16s %-6s %-16s %-6s %s" % ("case", "got_outcome", "got_v", "exp_outcome", "exp_v", "OK?"))
    for name, (txt, exp_o, exp_v) in CASES.items():
        o, v = _extract(txt)
        ok = (o == exp_o and v == exp_v)
        fails += (not ok)
        print("%-32s %-16s %-6s %-16s %-6s %s" % (name, o, str(v), exp_o, str(exp_v), "PASS" if ok else "*** FAIL ***"))
    print("\nRESULT:", ("ALL %d PASS" % len(CASES)) if not fails else ("%d/%d FAILED" % (fails, len(CASES))))
    sys.exit(1 if fails else 0)
