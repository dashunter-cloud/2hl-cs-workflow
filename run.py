"""Single entry point: runs the full pipeline 5 times.

Usage:
    python run.py            # 5 representative runs on the full sample
    python run.py --once     # 1 run only (for fast iteration)
    python run.py --runs 3   # custom run count

Each run produces outputs/run_<id>/*.json with all stage outputs.
A cost_summary.json aggregates across runs.
"""
import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # picks up ANTHROPIC_API_KEY from .env

from src.pipeline import run_pipeline  # noqa: E402
from src.telemetry import Telemetry  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5,
                    help="number of end-to-end runs (default 5)")
    ap.add_argument("--once", action="store_true",
                    help="single run, equivalent to --runs 1")
    ap.add_argument("--sample-accounts", type=int, default=None,
                    help="limit accounts per run (default: all)")
    args = ap.parse_args()

    if "ANTHROPIC_API_KEY" not in os.environ:
        raise SystemExit("ANTHROPIC_API_KEY not set. Copy .env.example -> .env "
                         "and add your key, or export it in your shell.")

    n = 1 if args.once else args.runs
    outputs_root = Path("outputs")
    outputs_root.mkdir(exist_ok=True)
    telemetry_path = outputs_root / "telemetry.jsonl"
    # Fresh telemetry per invocation
    if telemetry_path.exists():
        telemetry_path.unlink()

    run_summaries = []
    for i in range(1, n + 1):
        rid = f"{i:02d}"
        run_summaries.append(run_pipeline(
            rid,
            sample_accounts=args.sample_accounts,
            output_dir=outputs_root / f"run_{rid}",
            telemetry_path=telemetry_path,
        ))

    # Aggregate across all runs
    all_tel = Telemetry(telemetry_path)
    # rehydrate calls from disk
    if telemetry_path.exists():
        for line in telemetry_path.read_text().splitlines():
            d = json.loads(line)
            from src.telemetry import StageCall
            all_tel.calls.append(StageCall(**d))
    overall = all_tel.summary()
    runs_count = len(run_summaries)
    avg_cost_per_run = overall["total_cost_usd"] / runs_count if runs_count else 0
    final = {
        "runs": runs_count,
        "total_cost_usd_across_runs": overall["total_cost_usd"],
        "avg_cost_per_end_to_end_run_usd": avg_cost_per_run,
        "by_stage": overall["by_stage"],
        "run_summaries": run_summaries,
    }
    (outputs_root / "cost_summary.json").write_text(json.dumps(final, indent=2))
    print("\n=== AGGREGATE COST SUMMARY ===")
    print(f"Runs: {runs_count}")
    print(f"Total cost: ${overall['total_cost_usd']:.4f}")
    print(f"Avg cost per end-to-end run: ${avg_cost_per_run:.4f}")
    print(f"By stage:")
    for stage, s in overall["by_stage"].items():
        print(f"  {stage:25s} calls={s['calls']:3d}  total=${s['total_cost_usd']:.4f}  "
              f"avg=${s['avg_cost_per_call_usd']:.5f}  "
              f"in={s['avg_in_tokens']:.0f} out={s['avg_out_tokens']:.0f}")


if __name__ == "__main__":
    main()
