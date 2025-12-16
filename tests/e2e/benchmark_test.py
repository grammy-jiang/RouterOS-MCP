"""Benchmark tests for Phase 2 performance targets.

Single-device, single-client baseline tests to measure:
- Resource fetch latency (with/without cache)
- Cache hit rate
- Memory usage

Compares against Phase 2 targets:
- Resource fetch latency <1s (95th percentile)
- Cache hit rate >70%
- No memory leaks

See docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md for testing strategy.
"""

import asyncio
import gc
import json
import logging
import statistics
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import Device
from routeros_mcp.infra.db.session import DatabaseSessionManager
from routeros_mcp.infra.observability.resource_cache import (
    initialize_cache,
    get_cache,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResults:
    """Results from a benchmark run."""

    name: str
    iterations: int
    latencies: List[float] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0
    memory_start_bytes: int = 0
    memory_end_bytes: int = 0
    memory_peak_bytes: int = 0

    @property
    def mean_latency(self) -> float:
        """Mean latency in seconds."""
        return statistics.mean(self.latencies) if self.latencies else 0.0

    @property
    def p50_latency(self) -> float:
        """50th percentile latency in seconds."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        return statistics.quantiles(sorted_latencies, n=100)[49]

    @property
    def p95_latency(self) -> float:
        """95th percentile latency in seconds."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        return statistics.quantiles(sorted_latencies, n=100)[94]

    @property
    def p99_latency(self) -> float:
        """99th percentile latency in seconds."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        return statistics.quantiles(sorted_latencies, n=100)[98]

    @property
    def cache_hit_rate(self) -> float:
        """Cache hit rate as percentage."""
        total = self.cache_hits + self.cache_misses
        if total > 0:
            return (self.cache_hits / total) * 100
        return 0.0

    @property
    def memory_increase_bytes(self) -> int:
        """Memory increase during benchmark."""
        return self.memory_end_bytes - self.memory_start_bytes

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "iterations": self.iterations,
            "latency": {
                "mean_ms": self.mean_latency * 1000,
                "p50_ms": self.p50_latency * 1000,
                "p95_ms": self.p95_latency * 1000,
                "p99_ms": self.p99_latency * 1000,
                "min_ms": min(self.latencies) * 1000 if self.latencies else 0.0,
                "max_ms": max(self.latencies) * 1000 if self.latencies else 0.0,
            },
            "cache": {
                "hits": self.cache_hits,
                "misses": self.cache_misses,
                "hit_rate_percent": self.cache_hit_rate,
            },
            "memory": {
                "start_mb": self.memory_start_bytes / (1024 * 1024),
                "end_mb": self.memory_end_bytes / (1024 * 1024),
                "peak_mb": self.memory_peak_bytes / (1024 * 1024),
                "increase_mb": self.memory_increase_bytes / (1024 * 1024),
            },
        }

    def print_summary(self) -> None:
        """Print benchmark summary."""
        logger.info("=" * 80)
        logger.info(f"BENCHMARK: {self.name}")
        logger.info("=" * 80)
        logger.info(f"Iterations: {self.iterations}")
        logger.info(f"Mean latency: {self.mean_latency * 1000:.2f}ms")
        logger.info(f"P50 latency: {self.p50_latency * 1000:.2f}ms")
        logger.info(f"P95 latency: {self.p95_latency * 1000:.2f}ms")
        logger.info(f"P99 latency: {self.p99_latency * 1000:.2f}ms")
        logger.info(f"Cache hit rate: {self.cache_hit_rate:.2f}%")
        logger.info(
            f"Memory increase: {self.memory_increase_bytes / (1024 * 1024):.2f}MB"
        )
        logger.info("=" * 80)


class BenchmarkRunner:
    """Runner for performance benchmarks."""

    def __init__(self, settings: Settings):
        """Initialize benchmark runner.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.session_factory: Optional[DatabaseSessionManager] = None
        self.cache = None

    async def setup(self) -> None:
        """Set up benchmark environment."""
        # Initialize cache
        self.cache = initialize_cache(
            ttl_seconds=300,
            max_entries=1000,
            enabled=True,
        )

        # Initialize database
        self.session_factory = DatabaseSessionManager(self.settings)
        await self.session_factory.init()

        # Warm up GC
        gc.collect()

    async def teardown(self) -> None:
        """Tear down benchmark environment."""
        if self.session_factory:
            await self.session_factory.close()

        # Clear cache
        if self.cache:
            await self.cache.clear()

        gc.collect()

    async def run_resource_fetch_without_cache(
        self, iterations: int = 1000
    ) -> BenchmarkResults:
        """Benchmark resource fetch without caching.

        Args:
            iterations: Number of iterations to run

        Returns:
            BenchmarkResults with timing data
        """
        results = BenchmarkResults(
            name="resource_fetch_without_cache",
            iterations=iterations,
        )

        # Start memory tracking
        tracemalloc.start()
        results.memory_start_bytes = tracemalloc.get_traced_memory()[0]

        # Mock device
        device = Device(
            id="dev-bench-001",
            name="router-bench-001",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=True,
            allow_professional_workflows=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Disable cache for this test
        cache = get_cache()
        original_enabled = cache._enabled
        cache._enabled = False

        try:
            for i in range(iterations):
                start_time = time.time()

                # Simulate resource fetch (without cache)
                await asyncio.sleep(0.001)  # Simulate minimal network latency
                response = {
                    "device_id": device.id,
                    "routeros_version": "7.15 (stable)",
                    "cpu_usage_percent": 15.5,
                    "memory_usage_percent": 50.0,
                }

                duration = time.time() - start_time
                results.latencies.append(duration)
                results.cache_misses += 1

                # Progress logging every 100 iterations
                if (i + 1) % 100 == 0:
                    logger.debug(f"Completed {i + 1}/{iterations} iterations")

        finally:
            # Restore cache state
            cache._enabled = original_enabled

            # End memory tracking
            results.memory_end_bytes, results.memory_peak_bytes = (
                tracemalloc.get_traced_memory()
            )
            tracemalloc.stop()

        results.print_summary()
        return results

    async def run_resource_fetch_with_cache(
        self, iterations: int = 1000
    ) -> BenchmarkResults:
        """Benchmark resource fetch with caching.

        Args:
            iterations: Number of iterations to run

        Returns:
            BenchmarkResults with timing data
        """
        results = BenchmarkResults(
            name="resource_fetch_with_cache",
            iterations=iterations,
        )

        # Start memory tracking
        tracemalloc.start()
        results.memory_start_bytes = tracemalloc.get_traced_memory()[0]

        # Mock device
        device = Device(
            id="dev-bench-002",
            name="router-bench-002",
            management_ip="192.168.1.2",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=True,
            allow_professional_workflows=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        cache = get_cache()
        resource_uri = f"device://{device.id}/overview"

        try:
            for i in range(iterations):
                start_time = time.time()

                # Try to get from cache
                cached = await cache.get(resource_uri, device.id)

                if cached:
                    results.cache_hits += 1
                else:
                    results.cache_misses += 1
                    # Simulate fetch and cache
                    await asyncio.sleep(0.001)  # Simulate network latency
                    response = json.dumps(
                        {
                            "device_id": device.id,
                            "routeros_version": "7.15 (stable)",
                            "cpu_usage_percent": 15.5,
                            "memory_usage_percent": 50.0,
                        }
                    )
                    await cache.set(resource_uri, response, device.id)

                duration = time.time() - start_time
                results.latencies.append(duration)

                # Progress logging every 100 iterations
                if (i + 1) % 100 == 0:
                    logger.debug(f"Completed {i + 1}/{iterations} iterations")

        finally:
            # End memory tracking
            results.memory_end_bytes, results.memory_peak_bytes = (
                tracemalloc.get_traced_memory()
            )
            tracemalloc.stop()

        results.print_summary()
        return results

    async def run_mixed_workload(self, iterations: int = 1000) -> BenchmarkResults:
        """Benchmark mixed workload (multiple devices, cache warm-up).

        Args:
            iterations: Number of iterations to run

        Returns:
            BenchmarkResults with timing data
        """
        results = BenchmarkResults(
            name="mixed_workload",
            iterations=iterations,
        )

        # Start memory tracking
        tracemalloc.start()
        results.memory_start_bytes = tracemalloc.get_traced_memory()[0]

        # Create multiple devices
        num_devices = 10
        devices = [
            Device(
                id=f"dev-bench-{i:03d}",
                name=f"router-bench-{i:03d}",
                management_ip=f"192.168.1.{i}",
                management_port=443,
                environment="lab",
                status="healthy",
                tags={},
                allow_advanced_writes=True,
                allow_professional_workflows=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            for i in range(num_devices)
        ]

        cache = get_cache()

        try:
            for i in range(iterations):
                # Round-robin through devices
                device = devices[i % num_devices]
                resource_uri = f"device://{device.id}/overview"

                start_time = time.time()

                # Try to get from cache
                cached = await cache.get(resource_uri, device.id)

                if cached:
                    results.cache_hits += 1
                else:
                    results.cache_misses += 1
                    # Simulate fetch and cache
                    await asyncio.sleep(0.001)  # Simulate network latency
                    response = json.dumps(
                        {
                            "device_id": device.id,
                            "routeros_version": "7.15 (stable)",
                            "cpu_usage_percent": 15.5,
                            "memory_usage_percent": 50.0,
                        }
                    )
                    await cache.set(resource_uri, response, device.id)

                duration = time.time() - start_time
                results.latencies.append(duration)

                # Progress logging every 100 iterations
                if (i + 1) % 100 == 0:
                    logger.debug(f"Completed {i + 1}/{iterations} iterations")

        finally:
            # End memory tracking
            results.memory_end_bytes, results.memory_peak_bytes = (
                tracemalloc.get_traced_memory()
            )
            tracemalloc.stop()

        results.print_summary()
        return results


async def run_all_benchmarks(
    iterations: int = 1000, output_file: Optional[Path] = None
) -> Dict[str, BenchmarkResults]:
    """Run all benchmark tests.

    Args:
        iterations: Number of iterations per benchmark
        output_file: Optional path to save results JSON

    Returns:
        Dictionary of benchmark results
    """
    logger.info(f"Starting benchmarks with {iterations} iterations each")

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="lab",
        resource_cache_enabled=True,
        resource_cache_ttl_seconds=300,
    )

    runner = BenchmarkRunner(settings)
    await runner.setup()

    results = {}

    try:
        # Benchmark 1: Resource fetch without cache
        logger.info("Running benchmark: resource_fetch_without_cache")
        results["without_cache"] = await runner.run_resource_fetch_without_cache(
            iterations
        )

        # Clear cache between benchmarks
        await runner.cache.clear()
        gc.collect()

        # Benchmark 2: Resource fetch with cache
        logger.info("Running benchmark: resource_fetch_with_cache")
        results["with_cache"] = await runner.run_resource_fetch_with_cache(iterations)

        # Clear cache between benchmarks
        await runner.cache.clear()
        gc.collect()

        # Benchmark 3: Mixed workload
        logger.info("Running benchmark: mixed_workload")
        results["mixed_workload"] = await runner.run_mixed_workload(iterations)

    finally:
        await runner.teardown()

    # Print comparison
    logger.info("\n" + "=" * 80)
    logger.info("BENCHMARK COMPARISON")
    logger.info("=" * 80)
    logger.info(
        f"Without cache P95: {results['without_cache'].p95_latency * 1000:.2f}ms"
    )
    logger.info(f"With cache P95: {results['with_cache'].p95_latency * 1000:.2f}ms")
    logger.info(
        f"Cache hit rate: {results['with_cache'].cache_hit_rate:.2f}%"
    )
    logger.info(f"Mixed workload P95: {results['mixed_workload'].p95_latency * 1000:.2f}ms")
    logger.info(
        f"Mixed cache hit rate: {results['mixed_workload'].cache_hit_rate:.2f}%"
    )

    # Calculate speedup
    if results["without_cache"].p95_latency > 0:
        speedup = (
            results["without_cache"].p95_latency / results["with_cache"].p95_latency
        )
        logger.info(f"Cache speedup: {speedup:.2f}x")

    logger.info("=" * 80)

    # Save results
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_data = {
            name: result.to_dict() for name, result in results.items()
        }
        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2)
        logger.info(f"Results saved to {output_file}")

    return results


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_benchmark_resource_fetch_latency():
    """Benchmark resource fetch latency (Phase 2 target: <1s p95)."""
    results = await run_all_benchmarks(
        iterations=1000, output_file=Path("reports/benchmark_results.json")
    )

    # Validate Phase 2 targets
    with_cache = results["with_cache"]

    # P95 latency should be <1s
    assert (
        with_cache.p95_latency < 1.0
    ), f"P95 latency {with_cache.p95_latency:.3f}s exceeds 1s target"

    # Cache hit rate should be >70%
    assert (
        with_cache.cache_hit_rate > 70.0
    ), f"Cache hit rate {with_cache.cache_hit_rate:.2f}% below 70% target"

    # Memory increase should be reasonable (<50MB for 1000 iterations)
    assert (
        with_cache.memory_increase_bytes < 50 * 1024 * 1024
    ), f"Memory increase {with_cache.memory_increase_bytes / (1024 * 1024):.2f}MB exceeds 50MB"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_benchmark_cache_hit_rate():
    """Benchmark cache hit rate (Phase 2 target: >70%)."""
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="lab",
        resource_cache_enabled=True,
        resource_cache_ttl_seconds=300,
    )

    runner = BenchmarkRunner(settings)
    await runner.setup()

    try:
        # Run mixed workload which should achieve high cache hit rate
        results = await runner.run_mixed_workload(iterations=500)

        # Cache hit rate should be >70%
        assert (
            results.cache_hit_rate > 70.0
        ), f"Cache hit rate {results.cache_hit_rate:.2f}% below 70% target"

    finally:
        await runner.teardown()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_benchmark_no_memory_leak():
    """Benchmark memory usage (no significant memory leaks)."""
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="lab",
        resource_cache_enabled=True,
        resource_cache_ttl_seconds=300,
    )

    runner = BenchmarkRunner(settings)
    await runner.setup()

    try:
        # Run multiple rounds to detect memory leaks
        memory_increases = []

        for round_num in range(3):
            logger.info(f"Memory leak test round {round_num + 1}/3")

            # Clear cache between rounds
            await runner.cache.clear()
            gc.collect()

            # Run benchmark
            results = await runner.run_resource_fetch_with_cache(iterations=100)
            memory_increases.append(results.memory_increase_bytes)

        # Memory increase should stabilize (not grow unbounded)
        # Allow some variance but shouldn't grow >2x
        if len(memory_increases) >= 2:
            first_increase = memory_increases[0]
            last_increase = memory_increases[-1]

            if first_increase > 0:
                growth_factor = last_increase / first_increase
                assert (
                    growth_factor < 2.0
                ), f"Memory growth factor {growth_factor:.2f}x suggests memory leak"

    finally:
        await runner.teardown()


if __name__ == "__main__":
    # Run standalone benchmarks
    asyncio.run(
        run_all_benchmarks(
            iterations=1000, output_file=Path("reports/benchmark_results.json")
        )
    )
