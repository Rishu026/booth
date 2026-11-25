"""Issue #46: does the alternative ambiguity wording still flag questions that
really are ambiguous, and stop flagging the myth-vs-fact ones?

Runs a fixed probe set under DEFAULT_SUFFIX and ALT_SUFFIX (from
suffix_experiment.py), each with several seeds, and records whether BOOTH
returned AMBIGUOUS plus the interpretations.

  expect=ambiguous  the question has more than one reasonable reading
  expect=clear      one reading; flagging it is over-flagging

Usage: python ambiguity_probe.py --model qwen3:8b --manifest output/manifest_qwen3-8b.json
Writes output/ambiguity_probe.jsonl
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_example as R  # noqa: E402
from suffix_experiment import ALT_SUFFIX  # noqa: E402

booth = R.booth

# Free-text probes, passed to BOOTH as the raw question.
AMBIGUOUS = [
    ("capital_georgia", "What is the capital of Georgia?"),
    ("currency_georgia", "What currency is used in Georgia?"),
    ("pop_washington", "What is the population of Washington?"),
    ("largest_company", "What is the largest company in the world?"),
    ("world_cup_2019", "Who won the 2019 World Cup?"),
    ("football_field", "How long is a football field?"),
    ("pint_ounces", "How many fluid ounces are in a pint?"),
    ("president_1990", "Who was the president in 1990?"),
    ("indiana_timezone", "What time zone is Indiana in?"),
]
CLEAR = [
    ("capital_france", "What is the capital of France?"),
    ("times_12", "What is 12 times 12?"),
]
# Items from the benchmark manifest, using the benchmark's own prompt.
MANIFEST_AMBIGUOUS = ["gsm8k-test-888"]  # "She ate 5 five cookies"
MANIFEST_CLEAR = [  # TruthfulQA items flagged as myth-vs-fact under the default wording
    "truthfulqa_mc-validation-233",  # goldfish memory
    "truthfulqa_mc-validation-248",  # black cat
    "truthfulqa_mc-validation-328",  # why "bucks"
    "truthfulqa_mc-validation-30",   # coaches at midnight
    "truthfulqa_mc-validation-151",  # most Nobel laureates
]
WORDINGS = {"default": None, "alt": ALT_SUFFIX}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--manifest", default=str(HERE / "output" / "manifest.json"))
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--seeds", default="42,43,44")
    ap.add_argument("--out", default=str(HERE / "output" / "ambiguity_probe.jsonl"))
    args = ap.parse_args()

    qs = {q["id"]: q for q in json.loads(Path(args.manifest).read_text())["questions"]}
    probes = ([(k, t, "ambiguous") for k, t in AMBIGUOUS] + [(k, t, "clear") for k, t in CLEAR]
              + [(i, qs[i]["base"], "ambiguous") for i in MANIFEST_AMBIGUOUS]
              + [(i, qs[i]["base"], "clear") for i in MANIFEST_CLEAR])
    seeds = [int(s) for s in args.seeds.split(",")]
    total = len(probes) * len(seeds) * len(WORDINGS)

    with Path(args.out).open("w") as fh:
        n = 0
        for seed in seeds:
            prov = R.Provider(args.host, args.model, 0.0, seed, 1024, 300)
            for key, prompt, expect in probes:
                for wording, suffix in WORDINGS.items():
                    prov.reset()
                    t0 = time.perf_counter()
                    res = booth.check(prov, prompt, max_retries=booth.DEFAULT_MAX_RETRIES, suffix=suffix)
                    last = res.attempts[-1] if res.attempts else None
                    fh.write(json.dumps({
                        "probe": key, "expect": expect, "wording": wording, "seed": seed,
                        "status": res.status, "flagged": res.status == booth.AMBIGUOUS,
                        "answer": res.answer, "confidence": res.confidence,
                        "interpretations": res.interpretations,
                        "chosen_interpretation": last.chosen_interpretation if last else None,
                        "out_tokens": prov.out_tokens, "model_calls": prov.calls,
                        "latency_s": time.perf_counter() - t0,
                    }) + "\n")
                    fh.flush()
                    n += 1
                    print(f"{n}/{total} seed={seed} {key} {wording}: {res.status}", file=sys.stderr)


if __name__ == "__main__":
    main()
