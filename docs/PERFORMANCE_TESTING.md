# Phase 2 Performance Testing Guide

This guide documents how to run and interpret Phase 2 performance tests and benchmarks.

## Overview

Phase 2 introduces comprehensive performance testing to validate caching improvements:

- **Load Tests**: Simulate realistic workloads with 100 devices and 10 concurrent clients
- **Benchmarks**: Measure baseline performance metrics for single-device scenarios
- **Reports**: Generate visualizations and comparisons against targets

## Performance Targets (Phase 2)

Phase 2 acceptance criteria:

| Metric | Target | Description |
|--------|--------|-------------|
| **Cache Hit Rate** | >70% | Percentage of requests served from cache |
| **P95 Latency** | <1s | 95th percentile resource fetch latency |
| **Throughput** | >100 req/s | Requests per second with 10 concurrent clients |
| **Memory** | <50MB/1000 req | Memory increase per 1000 requests |
| **Error Rate** | <5% | Percentage of failed requests |

## Running Tests

### Quick Validation (30 seconds)

For rapid feedback during development:

```bash
# Quick load test (30 seconds, 20 devices, 5 clients)
pytest tests/e2e/load_test.py::test_load_test_quick -v

# Quick benchmark (single device, 1000 iterations)
pytest tests/e2e/benchmark_test.py::test_benchmark_resource_fetch_latency -v
```

**Expected output:**
- Load test: ~100-200 requests in 30 seconds
- Benchmark: P95 latency <1s, cache hit rate >70%

### Full Load Test (5 minutes)

For comprehensive validation before release:

```bash
# Run as pytest
pytest tests/e2e/load_test.py::test_load_test_5_minutes -v

# Or run standalone
python tests/e2e/load_test.py
```

**Expected output:**
```
Client 0 starting workload
Client 1 starting workload
...
Client 0 finished workload
Client 1 finished workload
...
================================================================================
LOAD TEST SUMMARY
================================================================================
Duration: 300.12s
Total requests: 15234
Successful: 15234
Failed: 0
Throughput: 50.77 req/s
Cache hit rate: 85.23%
Error rate: 0.00%
Latency p50: 12.45ms
Latency p95: 45.67ms
Latency p99: 89.12ms
================================================================================
```

### Full Benchmarks

Run all benchmark scenarios:

```bash
# Run all benchmarks
pytest tests/e2e/benchmark_test.py -v

# Or run standalone
python tests/e2e/benchmark_test.py
```

**Scenarios tested:**
1. **Without Cache**: Baseline performance with caching disabled
2. **With Cache**: Performance with caching enabled (warmup + steady state)
3. **Mixed Workload**: Multiple devices with realistic access patterns

**Expected output:**
```
================================================================================
BENCHMARK: resource_fetch_without_cache
================================================================================
Iterations: 1000
Mean latency: 1.23ms
P50 latency: 1.15ms
P95 latency: 2.34ms
P99 latency: 3.45ms
Cache hit rate: 0.00%
Memory increase: 2.34MB
================================================================================

================================================================================
BENCHMARK: resource_fetch_with_cache
================================================================================
Iterations: 1000
Mean latency: 0.45ms
P50 latency: 0.12ms
P95 latency: 0.89ms
P99 latency: 1.23ms
Cache hit rate: 85.67%
Memory increase: 3.12MB
================================================================================

================================================================================
BENCHMARK COMPARISON
================================================================================
Without cache P95: 2.34ms
With cache P95: 0.89ms
Cache hit rate: 85.67%
Mixed workload P95: 1.12ms
Mixed cache hit rate: 78.45%
Cache speedup: 2.63x
================================================================================
```

## Generating Reports

### Basic Report

Generate report from test results:

```bash
# From benchmark results
python scripts/benchmark_report.py \
    --benchmark reports/benchmark_results.json \
    --output reports/phase2_benchmark.md

# From load test results
python scripts/benchmark_report.py \
    --load-test reports/load_test_results.json \
    --output reports/phase2_load_test.md

# Combined report
python scripts/benchmark_report.py \
    --benchmark reports/benchmark_results.json \
    --load-test reports/load_test_results.json \
    --output reports/phase2_combined.md
```

### Comparison with Baseline

Compare Phase 2 against Phase 1 baseline:

```bash
python scripts/benchmark_report.py \
    --benchmark reports/benchmark_results.json \
    --baseline reports/phase1_baseline.json \
    --output reports/phase2_vs_phase1.md
```

### Example Report Output

```markdown
# Phase 2 Performance Benchmark Report

Generated: 2025-12-16T14:20:00.000000

## Executive Summary

### Benchmark Results

**Resource Fetch With Cache**

- P50 Latency: 0.12ms
- P95 Latency: 0.89ms
- P99 Latency: 1.23ms
- Cache Hit Rate: 85.67%
- Memory Increase: 3.12MB

### Load Test Results

- Total Requests: 15234
- Duration: 300.12s
- Throughput: 50.77 req/s
- Cache Hit Rate: 85.23%
- P95 Latency: 45.67ms

## Detailed Results

## Latency Comparison

### P50 Latency (ms)
┌────────────────────────────────────────────────────────────────┐
│ Without Cache ████████████████████████████████████████     1.15 │
│ With Cache    ████                                          0.12 │
│ Mixed Workload████████                                      0.45 │
└────────────────────────────────────────────────────────────────┘

### P95 Latency (ms)
┌────────────────────────────────────────────────────────────────┐
│ Without Cache ████████████████████████████████████████     2.34 │
│ With Cache    ████████████                                  0.89 │
│ Mixed Workload███████████████                               1.12 │
└────────────────────────────────────────────────────────────────┘

## Cache Metrics: Resource Fetch With Cache

**Hit Rate:** 85.67%

┌────────────────────────────────────────────────────────────────┐
│ Cache Hits    ██████████████████████████████████████████  856.70│
│ Cache Misses  ██████                                      143.30│
└────────────────────────────────────────────────────────────────┘

## Comparison with Baseline

- **Latency P95 Improvement:** 62.00%
  - Current: 0.89ms
  - Baseline: 2.34ms

- **Cache Hit Rate Change:** +15.67%
  - Current: 85.67%
  - Baseline: 70.00%

- **Throughput Improvement:** 45.23%
  - Current: 50.77 req/s
  - Baseline: 34.95 req/s

## Phase 2 Acceptance Criteria

- **Cache Hit Rate >70%:** ✅ PASS (85.67%)
- **P95 Latency <1s:** ✅ PASS (0.89ms)
- **No Memory Leaks:** ✅ PASS
```

## Interpreting Results

### Cache Hit Rate

**Target:** >70%

- **85%+**: Excellent caching performance
- **70-85%**: Good caching, meets targets
- **50-70%**: Acceptable but below target
- **<50%**: Poor caching, investigate TTL settings or access patterns

**Common issues:**
- Low hit rate: TTL too short, cache size too small, or cold cache
- Very high hit rate (>95%): May indicate unrealistic test patterns

### Latency Percentiles

**Targets:** P95 <1s

- **P50 (Median)**: Typical user experience
- **P95**: 95% of requests complete within this time
- **P99**: Worst-case for most users

**Good ranges:**
- P50: <50ms (with cache), <200ms (without cache)
- P95: <200ms (with cache), <1s (without cache)
- P99: <500ms (with cache), <2s (without cache)

**Common issues:**
- High variance (P99 >> P95): Investigate outliers, GC pauses, or network issues
- All percentiles high: Check network latency, RouterOS load, or resource contention

### Throughput

**Target:** >100 req/s (10 concurrent clients)

- **100+ req/s**: Meets target for Phase 2
- **50-100 req/s**: Acceptable but may need optimization
- **<50 req/s**: Below expectations, investigate bottlenecks

**Scaling expectations:**
- Single client: ~20-30 req/s
- 10 clients: ~100-150 req/s
- 100 clients: ~500-1000 req/s (requires load balancing)

### Memory Usage

**Target:** <50MB increase per 1000 requests

- **<20MB**: Excellent memory efficiency
- **20-50MB**: Good, meets targets
- **50-100MB**: Acceptable but watch for leaks
- **>100MB**: Investigate memory leaks or excessive caching

**Validation:**
```bash
# Run memory leak detection
pytest tests/e2e/benchmark_test.py::test_benchmark_no_memory_leak -v
```

## Troubleshooting

### Low Cache Hit Rate

**Check cache configuration:**
```python
# In config/lab.yaml
resource_cache_enabled: true
resource_cache_ttl_seconds: 300  # 5 minutes
resource_cache_max_entries: 1000
```

**Verify cache is initialized:**
```bash
# Look for this log line
ResourceCache initialized: enabled=True, ttl=300s, max_entries=1000
```

**Increase TTL if appropriate:**
- Lab environment: 300-900s (5-15 minutes)
- Production: 60-300s (1-5 minutes) depending on data volatility

### High Latency

**Check network latency to RouterOS devices:**
```bash
# Ping RouterOS management IP
ping -c 10 192.168.1.1

# Expected: <10ms on LAN, <50ms over WAN
```

**Check RouterOS CPU load:**
- Target: <30% average, <70% peak
- High CPU (>80%): Reduce polling frequency or optimize queries

**Check database performance:**
- SQLite: Consider PostgreSQL for production
- Add indexes for frequently queried fields
- Monitor query execution time

### Low Throughput

**Check concurrency limits:**
```python
# In mcp/server.py
MAX_CONCURRENT_REQUESTS = 100  # Increase if needed
```

**Check RouterOS connection limits:**
- REST API: Default 20 concurrent connections
- Increase in RouterOS: /ip service set www-ssl max-sessions=50

**Check database connection pool:**
```python
# In config
database_pool_size: 20  # PostgreSQL only
database_max_overflow: 40
```

### Memory Leaks

**Run memory profiler:**
```bash
# Enable tracemalloc in benchmark
python tests/e2e/benchmark_test.py

# Check Memory increase column in output
# Should be <50MB for 1000 iterations
```

**Common causes:**
- Unclosed database sessions
- Growing cache without eviction
- Event loop not properly closed
- Large objects kept in memory

## CI Integration

Add to GitHub Actions workflow:

```yaml
- name: Run Performance Tests
  run: |
    pytest tests/e2e/benchmark_test.py -v
    pytest tests/e2e/load_test.py::test_load_test_quick -v

- name: Generate Performance Report
  if: always()
  run: |
    python scripts/benchmark_report.py \
      --benchmark reports/benchmark_results.json \
      --output reports/benchmark_report.md
```

## Best Practices

1. **Establish baseline**: Run tests on clean environment before changes
2. **Compare consistently**: Use same test parameters for comparisons
3. **Multiple runs**: Average results from 3-5 runs for reliability
4. **Monitor trends**: Track metrics over time, not just snapshots
5. **Test realistic scenarios**: Use workload mixes similar to production
6. **Warm up cache**: Run warm-up phase before measuring steady state
7. **Document changes**: Note any config changes that affect results

## References

- [Testing Strategy](../docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md)
- [Observability](../docs/08-observability-logging-metrics-and-diagnostics.md)
- [Resource Caching](../routeros_mcp/infra/observability/resource_cache.py)
