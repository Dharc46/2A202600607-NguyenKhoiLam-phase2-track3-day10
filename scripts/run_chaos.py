from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from reliability_lab.chaos import load_queries, run_simulation
from reliability_lab.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--out", default="reports/metrics.json")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    config = load_config(args.config)
    queries = load_queries()
    random.seed(args.seed)
    metrics = run_simulation(config, queries)
    metrics.write_json(args.out)
    metrics.write_csv(Path(args.out).with_suffix(".csv"))

    random.seed(args.seed)
    without_cache = run_simulation(
        config.model_copy(update={"cache": config.cache.model_copy(update={"enabled": False})}),
        queries,
    )
    comparison = {
        "with_cache": metrics.to_report_dict(),
        "without_cache": without_cache.to_report_dict(),
    }
    comparison_path = Path(args.out).with_name("cache_comparison.json")
    comparison_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
