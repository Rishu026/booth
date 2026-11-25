"""Issue #46: compare BOOTH's default ambiguity wording against an alternative,
passed through suffix=, on the questions of a finished run_example.py run.

Two arms, interleaved per question in random order:
  default_rerun  booth.check() with DEFAULT_SUFFIX (a second run, to measure
                 run-to-run noise against the original run)
  alt_wording    booth.check(suffix=ALT_SUFFIX): DEFAULT_SUFFIX with only the
                 ambiguity paragraph replaced

Both arms record result.interpretations and chosen_interpretation.

Usage: python suffix_experiment.py --model qwen3:8b --manifest output/manifest_qwen3-8b.json
Writes output/suffix_experiment.jsonl (use --resume to continue).
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_example as R  # noqa: E402

booth, core = R.booth, R.core

OLD_AMBIGUITY = """Set "ambiguous" to true if the question has more than one reasonable, \
meaningfully different answer depending on interpretation (different \
named entities sharing a name, different metrics like assets vs. \
market cap, different time periods, etc.). List those readings in \
"interpretations" (empty list if not ambiguous). If ambiguous, still \
answer under your best-guess interpretation, and name it in \
"chosen_interpretation"."""

NEW_AMBIGUITY = """Set "ambiguous" to true only if the question itself can reasonably \
be read in more than one way, and those readings lead to meaningfully \
different answers (different named entities sharing a name, different \
metrics like assets vs. market cap, different time periods, etc.). Do \
not mark a question ambiguous because a popular belief or misconception \
differs from the facts, because sources disagree, or because you are \
unsure which answer is right; express uncertainty through "confidence" \
instead. List the readings in "interpretations" (empty list if not \
ambiguous). If ambiguous, still answer under your best-guess \
interpretation, and name it in "chosen_interpretation"."""

if OLD_AMBIGUITY not in core.DEFAULT_SUFFIX:
    sys.exit("DEFAULT_SUFFIX ambiguity paragraph changed; update OLD_AMBIGUITY.")
ALT_SUFFIX = core.DEFAULT_SUFFIX.replace(OLD_AMBIGUITY, NEW_AMBIGUITY)
ARMS = {"default_rerun": None, "alt_wording": ALT_SUFFIX}


def run(arm, q, prov):
    prov.reset()
    t0 = time.perf_counter()
    res = booth.check(prov, q["base"], max_retries=booth.DEFAULT_MAX_RETRIES, suffix=ARMS[arm])
    last = res.attempts[-1] if res.attempts else None
    status = res.status
    raw_correct = R.grade(q, res.answer) if res.answer is not None else False
    if res.call_failed:
        outcome = "call_failed"
    elif status == booth.AMBIGUOUS:
        outcome = "ambiguous"
    elif status == booth.UNCERTAIN:
        outcome = "uncertain"
    else:
        outcome = "correct" if raw_correct else "incorrect"
    return {
        "qid": q["id"], "dataset": q["dataset"], "arm": arm,
        "status": status, "outcome": outcome, "predicted": res.answer,
        "reference": q["reference"], "raw_correct": raw_correct,
        "confidence": res.confidence, "n_attempts": res.n_attempts,
        "interpretations": res.interpretations,
        "chosen_interpretation": last.chosen_interpretation if last else None,
        "latency_s": time.perf_counter() - t0,
        "model_calls": prov.calls, "failed_calls": prov.failed_calls, "out_tokens": prov.out_tokens,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--manifest", default=str(HERE / "output" / "manifest.json"))
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--out", default=str(HERE / "output" / "suffix_experiment.jsonl"))
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    seed = manifest["seed"]
    prov = R.Provider(args.host, args.model, 0.0, seed, 1024, 300)
    prov("Reply with the single word: ready")  # warm-up

    out = Path(args.out)
    done = set()
    if args.resume and out.exists():
        done = {(r["qid"], r["arm"]) for r in map(json.loads, out.read_text().splitlines()) if r}
    elif out.exists():
        out.unlink()

    rng = random.Random(f"{seed}:suffix-experiment")
    order = manifest["questions"][:]
    rng.shuffle(order)
    with out.open("a") as fh:
        for i, q in enumerate(order, 1):
            arms = list(ARMS)
            rng.shuffle(arms)
            for arm in arms:
                if (q["id"], arm) in done:
                    continue
                fh.write(json.dumps(run(arm, q, prov)) + "\n")
                fh.flush()
            print(f"{i}/{len(order)} {q['id']}", file=sys.stderr)
    print(f"Wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
