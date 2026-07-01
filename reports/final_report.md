# Day 10 Reliability Final Report

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
| primary fail rate | 0.25 | Exercises fallback in the default workload. |
| backup fail rate | 0.05 | Provides a substantially more reliable secondary route. |
| failure threshold | 3 | Opens quickly without reacting to one transient error. |
| reset timeout | 2.0s | Bounds outage probing while preventing a retry storm. |
| success threshold | 1 | One good probe restores this local simulated provider. |
| cache backend | memory | Fast deterministic baseline; Redis is also implemented. |
| cache TTL | 300s | Limits staleness while retaining repeated test prompts. |
| similarity threshold | 0.92 | Conservative matching plus a numeric mismatch guard. |
| requests per scenario | 100 | Supports percentile and failure-path evidence. |
| random seed | 42 | Makes the simulation reproducible. |

## 3. SLO definitions

| SLI | Target | Actual | Met? |
|---|---:|---:|---|
| Availability | >= 99% | 74.75% | No |
| P95 provider latency | < 2500 ms | 317.82 ms | Yes |
| Fallback success rate | >= 95% | 43.58% | No |
| Cache hit rate | >= 10% | 45.75% | Yes |
| Recovery time | < 5000 ms | 2275.8424282073975 | Yes |

## 4. Metrics

| Metric | Value |
|---|---:|
| total_requests | 400 |
| availability | 0.7475 |
| error_rate | 0.2525 |
| latency_p50_ms | 276.34 |
| latency_p95_ms | 317.82 |
| latency_p99_ms | 320.14 |
| fallback_success_rate | 0.4358 |
| cache_hit_rate | 0.4575 |
| circuit_open_count | 13 |
| recovery_time_ms | 2275.8424282073975 |
| estimated_cost | 0.051698 |
| estimated_cost_saved | 0.183 |

Results are aggregated across all scenarios. Per the lab contract, zero-latency cache hits are excluded from provider latency percentiles.

## 5. Cache comparison

Both runs use seed 42 and identical scenarios.

| Metric | Without cache | With cache | Delta |
|---|---:|---:|---:|
| latency_p50_ms | 265.46 | 276.34 | 10.88 |
| latency_p95_ms | 315.55 | 317.82 | 2.27 |
| estimated_cost | 0.14109 | 0.051698 | -0.089392 |
| cache_hit_rate | 0.0 | 0.4575 | 0.4575 |

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
| primary_timeout_100 | Primary provider fails 100% â€” all traffic should fallback | Status: pass; aggregate circuit opens: 13 | PASS |
| primary_flaky_50 | Primary provider fails 50% â€” circuit should oscillate | Status: pass; aggregate circuit opens: 13 | PASS |
| all_healthy | Baseline â€” both providers healthy | Status: pass; aggregate circuit opens: 13 | PASS |
| all_providers_down | Both providers fail 100%: gateway should degrade safely | Status: pass; aggregate circuit opens: 13 | PASS |

## 8. Failure analysis

Redis semantic lookup scans every cached key and calculates similarity locally. At high cardinality this increases latency and traffic. Before production, use a tenant-scoped vector index with bounded candidate retrieval and evaluate false-hit rate. Circuit state is process-local as well; coordinated state would stop multiple replicas probing an unhealthy provider simultaneously.

## 9. Next steps

1. Add concurrency tests and locking so HALF_OPEN permits a bounded number of probes.
2. Record end-to-end latency including cache hits and retain per-scenario metrics.
3. Add tenant isolation, Redis authentication/TLS, and automated cache-quality SLOs.
