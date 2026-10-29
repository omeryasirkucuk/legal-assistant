"""Run the golden question set and report grounding, coverage, length, cost and latency.

    uv run python -m legal_api.evaluation.golden [--only ID ...] [--concurrency 3]

Each run writes the full answers and metrics to var/eval/<timestamp>.jsonl.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime

from legal_api import llm
from legal_api.agent.answer import AnswerResult, answer
from legal_api.config import REPO_ROOT
from legal_api.evaluation.coverage import grade_coverage

QUESTIONS = REPO_ROOT / "eval" / "golden" / "questions.jsonl"
OUT_DIR = REPO_ROOT / "var" / "eval"


async def metrics(item: dict, result: AnswerResult) -> dict:
    answers = list(result.answers.values())
    grading = llm.Usage()
    text = result.text
    covered = await grade_coverage(item["question"], text, item["must_cover"], grading)
    cited = {k for a in answers if a.found for s in a.segments for k in s.keys}
    return {
        "id": item["id"],
        "expect": item["expect"],
        "atoms": len(answers),
        "found": sum(a.found and a.grounded for a in answers),
        "ungrounded": len(result.ungrounded),
        "coverage": f"{sum(covered)}/{len(covered)}" if covered else "-",
        "covered": covered,
        "short_chars": len(text),
        "branches": [b.label for b in result.branches],
        "cited": len(cited),
        "cost_usd": round(result.usage.cost_usd, 4),
        "cost_by_step": result.usage.by_purpose(),
        "eval_cost_usd": round(grading.cost_usd, 4),
        "seconds": result.timings.get("total_s", 0.0),
        "timings": result.timings,
        "answer": text,
        "sources": [f"[{e.key}] {e.citation}" for e in result.ledger if e.key in cited],
    }


def _passed(m: dict) -> bool:
    return all(m["covered"]) and m["ungrounded"] == 0


async def run(only: list[str], concurrency: int, max_usd: float) -> None:
    items = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    items = [i for i in items if not only or i["id"] in only]
    gate = asyncio.Semaphore(concurrency)
    spent = 0.0

    async def one(item: dict) -> dict | None:
        nonlocal spent
        async with gate:
            if spent >= max_usd:
                print(f"  skipped {item['id']}: budget {max_usd} $ reached", flush=True)
                return None
            m = await metrics(item, await answer(item["question"]))
            spent += m["cost_usd"] + m["eval_cost_usd"]
            print(f"  done {m['id']}: {m['seconds']}s ${m['cost_usd']} cov {m['coverage']}",
                  flush=True)
            return m

    results = [r for r in await asyncio.gather(*(one(i) for i in items)) if r]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{datetime.now(UTC):%Y%m%dT%H%M%S}.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n",
                   encoding="utf-8")

    print(f"\n{'id':<12}{'pass':<6}{'cov':<6}{'atoms':<7}{'found':<7}{'ungr':<6}"
          f"{'chars':<7}{'sec':<7}{'$':<7}")
    for m in results:
        print(f"{m['id']:<12}{'yes' if _passed(m) else 'NO':<6}{m['coverage']:<6}"
              f"{m['atoms']:<7}{m['found']:<7}{m['ungrounded']:<6}{m['short_chars']:<7}"
              f"{m['seconds']:<7}{m['cost_usd']:<7}")
    points = [c for m in results for c in m["covered"]]
    seconds = sorted(m["seconds"] for m in results)
    print(f"\npassed {sum(_passed(m) for m in results)}/{len(results)}; "
          f"coverage {sum(points)}/{len(points)}; "
          f"median {seconds[len(seconds) // 2]}s; "
          f"answers ${sum(m['cost_usd'] for m in results):.2f} + "
          f"grading ${sum(m['eval_cost_usd'] for m in results):.2f}")
    steps: dict[str, float] = {}
    for m in results:
        for step, row in m["cost_by_step"].items():
            steps[step] = steps.get(step, 0.0) + row["usd"]
    print("cost by step: " + ", ".join(f"{k} ${v:.3f}" for k, v in steps.items()))
    print(f"details: {out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--max-usd", type=float, default=0.5,
                        help="stop starting new questions once this much has been spent")
    args = parser.parse_args()
    asyncio.run(run(args.only, args.concurrency, args.max_usd))


if __name__ == "__main__":
    main()
