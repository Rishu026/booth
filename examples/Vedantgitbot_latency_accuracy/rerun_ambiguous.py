"""Re-run AMBIGUOUS rows from a finished run_example.py run and record
result.interpretations / chosen_interpretation (issue #46).

Usage: python rerun_ambiguous.py <example_dir> <model>
Writes <example_dir>/output/ambiguous_interpretations.jsonl
"""
import json
import sys
from pathlib import Path

ex = Path(sys.argv[1]).resolve()
model = sys.argv[2]
sys.path.insert(0, str(ex))
import run_example as R  # noqa: E402
booth, core = R.booth, R.core

out = ex / "output"
manifest = json.loads((out / "manifest.json").read_text())
qs = {q["id"]: q for q in manifest["questions"]}
rows = [json.loads(l) for l in (out / "results.jsonl").read_text().splitlines() if l.strip()]
amb = [r for r in rows if r["status"] == "AMBIGUOUS"]
print(f"{len(amb)} AMBIGUOUS rows to re-run", file=sys.stderr)

prov = R.Provider("http://localhost:11434", model, 0.0, manifest["seed"], 1024, 300)
dest = out / "ambiguous_interpretations.jsonl"
with dest.open("w") as fh:
    for i, r in enumerate(amb, 1):
        q = qs[r["qid"]]
        fn = R.ReasonFirst(prov) if r["arm"] == "booth_reason" else prov
        res = booth.check(fn, q["base"], max_retries=booth.DEFAULT_MAX_RETRIES)
        last = res.attempts[-1] if res.attempts else None
        rec = {
            "qid": r["qid"], "dataset": r["dataset"], "arm": r["arm"],
            "question": q["question"], "choices": q.get("choices"),
            "reference": q["reference"],
            "orig_status": r["status"], "orig_answer": r["predicted"],
            "rerun_status": res.status, "rerun_answer": res.answer,
            "reproduced": res.status == r["status"] and res.answer == r["predicted"],
            "raw_correct": R.grade(q, res.answer) if res.answer is not None else False,
            "confidence": res.confidence,
            "interpretations": res.interpretations,
            "chosen_interpretation": last.chosen_interpretation if last else None,
        }
        fh.write(json.dumps(rec) + "\n")
        fh.flush()
        print(f"{i}/{len(amb)} {r['qid']} {r['arm']} reproduced={rec['reproduced']}", file=sys.stderr)
print(f"Wrote {dest}", file=sys.stderr)
