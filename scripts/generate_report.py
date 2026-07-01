from __future__ import annotations

import argparse
import json
from pathlib import Path

from reliability_lab.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", default="reports/metrics.json")
    parser.add_argument("--out", default="reports/final_report.md")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--comparison", default="reports/cache_comparison.json")
    args = parser.parse_args()
    metrics = json.loads(Path(args.metrics).read_text(encoding="utf-8"))
    comparison = json.loads(Path(args.comparison).read_text(encoding="utf-8"))
    config = load_config(args.config)
    with_cache, without_cache = comparison["with_cache"], comparison["without_cache"]
    cb, cache = config.circuit_breaker, config.cache

    metric_rows = "\n".join(
        f"| {key} | {value} |" for key, value in metrics.items() if key != "scenarios"
    )
    descriptions = {item.name: item.description for item in config.scenarios}
    scenario_rows = "\n".join(
        f"| {name} | {descriptions.get(name, '')} | Status: {status}; aggregate circuit "
        f"opens: {metrics['circuit_open_count']} | {status.upper()} |"
        for name, status in metrics.get("scenarios", {}).items()
    )

    def delta(key: str) -> float:
        return round(float(with_cache[key]) - float(without_cache[key]), 6)

    report = f"""# Day 10 Reliability Final Report

## 1. Architecture summary

```text
User -> Gateway -> semantic cache -- hit --> response
                    |
                   miss
                    v
              primary circuit breaker -> primary provider
                    | open/failure
                    v
              backup circuit breaker  -> backup provider
                    | open/failure
                    v
              static degraded response
```

Each provider has an independent CLOSED/OPEN/HALF_OPEN breaker. Sensitive prompts bypass cache reads and writes; year or ID mismatches reject likely semantic false hits.

## 2. Configuration

| Setting | Value | Rationale |
|---|---:|---|
| primary fail rate | {config.providers[0].fail_rate} | Exercises fallback in the default workload. |
| backup fail rate | {config.providers[1].fail_rate} | Provides a substantially more reliable secondary route. |
| failure threshold | {cb.failure_threshold} | Opens quickly without reacting to one transient error. |
| reset timeout | {cb.reset_timeout_seconds}s | Bounds outage probing while preventing a retry storm. |
| success threshold | {cb.success_threshold} | One good probe restores this local simulated provider. |
| cache backend | {cache.backend} | Fast deterministic baseline; Redis is also implemented. |
| cache TTL | {cache.ttl_seconds}s | Limits staleness while retaining repeated test prompts. |
| similarity threshold | {cache.similarity_threshold} | Conservative matching plus a numeric mismatch guard. |
| requests per scenario | {config.load_test.requests} | Supports percentile and failure-path evidence. |
| random seed | 42 | Makes the simulation reproducible. |

## 3. SLO definitions

| SLI | Target | Actual | Met? |
|---|---:|---:|---|
| Availability | >= 99% | {metrics['availability']:.2%} | {'Yes' if metrics['availability'] >= .99 else 'No'} |
| P95 provider latency | < 2500 ms | {metrics['latency_p95_ms']} ms | {'Yes' if metrics['latency_p95_ms'] < 2500 else 'No'} |
| Fallback success rate | >= 95% | {metrics['fallback_success_rate']:.2%} | {'Yes' if metrics['fallback_success_rate'] >= .95 else 'No'} |
| Cache hit rate | >= 10% | {metrics['cache_hit_rate']:.2%} | {'Yes' if metrics['cache_hit_rate'] >= .10 else 'No'} |
| Recovery time | < 5000 ms | {metrics['recovery_time_ms']} | {'Yes' if metrics['recovery_time_ms'] is not None and metrics['recovery_time_ms'] < 5000 else 'Not observed'} |

## 4. Metrics

| Metric | Value |
|---|---:|
{metric_rows}

Results are aggregated across all scenarios. Per the lab contract, zero-latency cache hits are excluded from provider latency percentiles.

## 5. Cache comparison

Both runs use seed 42 and identical scenarios.

| Metric | Without cache | With cache | Delta |
|---|---:|---:|---:|
| latency_p50_ms | {without_cache['latency_p50_ms']} | {with_cache['latency_p50_ms']} | {delta('latency_p50_ms')} |
| latency_p95_ms | {without_cache['latency_p95_ms']} | {with_cache['latency_p95_ms']} | {delta('latency_p95_ms')} |
| estimated_cost | {without_cache['estimated_cost']} | {with_cache['estimated_cost']} | {delta('estimated_cost')} |
| cache_hit_rate | {without_cache['cache_hit_rate']} | {with_cache['cache_hit_rate']} | {delta('cache_hit_rate')} |

## 6. Redis shared cache

In-memory state is process-local, so replicas diverge and duplicate provider cost. `SharedRedisCache` stores a query/response hash under a deterministic key with server-side TTL, allowing all gateway replicas to observe the same entries.

Shared-state evidence is the passing `test_shared_state_across_instances` integration test. Reproduce it and inspect keys with:

```bash
docker compose up -d
pytest tests/test_redis_cache.py -v
docker compose exec redis redis-cli KEYS "rl:cache:*"
```

Test fixtures clean isolated prefixes, so an empty production-prefix result after tests is expected. Exact Redis reads are O(1); semantic lookup currently uses SCAN.

## 7. Chaos scenarios

| Scenario | Expected behavior | Observed behavior | Result |
|---|---|---|---|
{scenario_rows}

## 8. Failure analysis

Redis semantic lookup scans every cached key and calculates similarity locally. At high cardinality this increases latency and traffic. Before production, use a tenant-scoped vector index with bounded candidate retrieval and evaluate false-hit rate. Circuit state is process-local as well; coordinated state would stop multiple replicas probing an unhealthy provider simultaneously.

## 9. Next steps

1. Add concurrency tests and locking so HALF_OPEN permits a bounded number of probes.
2. Record end-to-end latency including cache hits and retain per-scenario metrics.
3. Add tenant isolation, Redis authentication/TLS, and automated cache-quality SLOs.
"""
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
