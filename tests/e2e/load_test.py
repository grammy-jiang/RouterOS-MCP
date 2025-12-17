"""Load test for Phase 2 features.

Simulates 100 devices and 10 concurrent clients with a realistic workload mix:
- 70% resource fetches (device overview, health, config)
- 20% tool calls (system overview, interface list, etc.)
- 10% subscriptions (health monitoring)

Runs for 5 minutes and collects performance metrics including:
- Latency (p50, p95, p99)
- Cache hit rate
- Throughput (requests/second)
- Error rate

See docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md for testing strategy.
"""

import asyncio
import json
import logging
import os
import random
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

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
class LatencyMetrics:
    """Latency statistics."""

    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    mean: float = 0.0
    min: float = 0.0
    max: float = 0.0


@dataclass
class LoadTestMetrics:
    """Metrics collected during load test."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    latencies: list[float] = field(default_factory=list)
    error_types: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    start_time: float | None = None
    end_time: float | None = None

    @property
    def duration_seconds(self) -> float:
        """Total test duration in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0

    @property
    def requests_per_second(self) -> float:
        """Throughput in requests per second."""
        if self.duration_seconds > 0:
            return self.total_requests / self.duration_seconds
        return 0.0

    @property
    def cache_hit_rate(self) -> float:
        """Cache hit rate as percentage."""
        total_cache_ops = self.cache_hits + self.cache_misses
        if total_cache_ops > 0:
            return (self.cache_hits / total_cache_ops) * 100
        return 0.0

    @property
    def error_rate(self) -> float:
        """Error rate as percentage."""
        if self.total_requests > 0:
            return (self.failed_requests / self.total_requests) * 100
        return 0.0

    def get_latency_metrics(self) -> LatencyMetrics:
        """Calculate latency percentiles."""
        if not self.latencies:
            return LatencyMetrics()

        sorted_latencies = sorted(self.latencies)
        return LatencyMetrics(
            p50=statistics.quantiles(sorted_latencies, n=100)[49],
            p95=statistics.quantiles(sorted_latencies, n=100)[94],
            p99=statistics.quantiles(sorted_latencies, n=100)[98],
            mean=statistics.mean(sorted_latencies),
            min=min(sorted_latencies),
            max=max(sorted_latencies),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        latency = self.get_latency_metrics()
        return {
            "summary": {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "duration_seconds": self.duration_seconds,
                "requests_per_second": self.requests_per_second,
            },
            "cache": {
                "hits": self.cache_hits,
                "misses": self.cache_misses,
                "hit_rate_percent": self.cache_hit_rate,
            },
            "latency": {
                "p50_ms": latency.p50 * 1000,
                "p95_ms": latency.p95 * 1000,
                "p99_ms": latency.p99 * 1000,
                "mean_ms": latency.mean * 1000,
                "min_ms": latency.min * 1000,
                "max_ms": latency.max * 1000,
            },
            "errors": {
                "error_rate_percent": self.error_rate,
                "error_types": dict(self.error_types),
            },
        }


class MockDeviceFactory:
    """Factory for creating mock devices and RouterOS responses."""

    def __init__(self, num_devices: int = 100):
        """Initialize mock device factory.

        Args:
            num_devices: Number of mock devices to create
        """
        self.num_devices = num_devices
        self.devices: list[Device] = []
        self._create_devices()

    def _create_devices(self) -> None:
        """Create mock devices."""
        for i in range(self.num_devices):
            device = Device(
                id=f"dev-load-{i:03d}",
                name=f"router-load-{i:03d}",
                management_ip=f"192.168.{i // 256}.{i % 256}",
                management_port=443,
                environment="lab",
                status="healthy",
                tags={"test": "load-test"},
                allow_advanced_writes=True,
                allow_professional_workflows=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            self.devices.append(device)

    def get_device(self, device_id: str) -> Device | None:
        """Get device by ID."""
        for device in self.devices:
            if device.id == device_id:
                return device
        return None

    def get_random_device(self) -> Device:
        """Get a random device."""
        return random.choice(self.devices)

    def create_system_overview_response(self, device: Device) -> dict[str, Any]:
        """Create mock system overview response."""
        return {
            "routeros_version": "7.15 (stable)",
            "architecture": "x86",
            "board_name": "CHR",
            "cpu_model": "QEMU Virtual CPU",
            "cpu_count": 2,
            "cpu_usage_percent": 15.5,
            "memory_total_bytes": 536870912,  # 512MB
            "memory_free_bytes": 268435456,  # 256MB
            "memory_usage_percent": 50.0,
            "uptime_seconds": 86400,
            "identity": device.name,
        }

    def create_health_response(self, device: Device) -> dict[str, Any]:
        """Create mock health check response."""
        return {
            "status": "healthy",
            "last_check_timestamp": datetime.utcnow().isoformat(),
            "metrics": {
                "cpu_usage": 15.5,
                "memory_usage": 50.0,
                "uptime_seconds": 86400,
            },
        }


class ConcurrentClient:
    """Simulates a concurrent MCP client making requests."""

    def __init__(
        self,
        client_id: int,
        device_factory: MockDeviceFactory,
        session_factory: DatabaseSessionManager,
        settings: Settings,
        metrics: LoadTestMetrics,
    ):
        """Initialize concurrent client.

        Args:
            client_id: Client identifier
            device_factory: Mock device factory
            session_factory: Database session factory
            settings: Application settings
            metrics: Shared metrics object
        """
        self.client_id = client_id
        self.device_factory = device_factory
        self.session_factory = session_factory
        self.settings = settings
        self.metrics = metrics
        self.running = False

    async def _make_resource_fetch(self) -> None:
        """Make a resource fetch request (70% of workload)."""
        device = self.device_factory.get_random_device()
        resource_uri = f"device://{device.id}/overview"

        start_time = time.time()
        try:
            # Get cache instance
            cache = get_cache()

            # Try to get from cache
            cached = await cache.get(resource_uri, device.id)
            if cached:
                self.metrics.cache_hits += 1
            else:
                self.metrics.cache_misses += 1
                # Simulate fetching from RouterOS
                await asyncio.sleep(0.01)  # Simulate network latency
                response = json.dumps(self.device_factory.create_system_overview_response(device))
                await cache.set(resource_uri, response, device.id)

            self.metrics.successful_requests += 1
        except Exception as e:
            self.metrics.failed_requests += 1
            self.metrics.error_types[type(e).__name__] += 1
            logger.error(f"Resource fetch failed: {e}")
        finally:
            duration = time.time() - start_time
            self.metrics.latencies.append(duration)
            self.metrics.total_requests += 1

    async def _make_tool_call(self) -> None:
        """Make a tool call request (20% of workload)."""
        self.device_factory.get_random_device()

        start_time = time.time()
        try:
            # Simulate tool call with some processing time
            await asyncio.sleep(0.02)  # Simulate tool execution
            self.metrics.successful_requests += 1
        except Exception as e:
            self.metrics.failed_requests += 1
            self.metrics.error_types[type(e).__name__] += 1
            logger.error(f"Tool call failed: {e}")
        finally:
            duration = time.time() - start_time
            self.metrics.latencies.append(duration)
            self.metrics.total_requests += 1

    async def _make_subscription(self) -> None:
        """Make a subscription request (10% of workload)."""
        self.device_factory.get_random_device()

        start_time = time.time()
        try:
            # Simulate subscription setup
            await asyncio.sleep(0.005)  # Minimal overhead
            self.metrics.successful_requests += 1
        except Exception as e:
            self.metrics.failed_requests += 1
            self.metrics.error_types[type(e).__name__] += 1
            logger.error(f"Subscription failed: {e}")
        finally:
            duration = time.time() - start_time
            self.metrics.latencies.append(duration)
            self.metrics.total_requests += 1

    async def run(self, duration_seconds: int = 300) -> None:
        """Run client workload for specified duration.

        Args:
            duration_seconds: Duration to run in seconds (default 5 minutes)
        """
        self.running = True
        end_time = time.time() + duration_seconds

        logger.info(f"Client {self.client_id} starting workload")

        while self.running and time.time() < end_time:
            # Select workload type based on distribution
            rand = random.random()

            if rand < 0.70:
                # 70% resource fetches
                await self._make_resource_fetch()
            elif rand < 0.90:
                # 20% tool calls
                await self._make_tool_call()
            else:
                # 10% subscriptions
                await self._make_subscription()

            # Small delay between requests (10-50ms)
            await asyncio.sleep(random.uniform(0.01, 0.05))

        logger.info(f"Client {self.client_id} finished workload")

    def stop(self) -> None:
        """Stop client workload."""
        self.running = False


async def run_load_test(
    num_devices: int = 100,
    num_clients: int = 10,
    duration_seconds: int = 300,
    output_file: Path | None = None,
) -> LoadTestMetrics:
    """Run load test with concurrent clients.

    Args:
        num_devices: Number of mock devices
        num_clients: Number of concurrent clients
        duration_seconds: Test duration in seconds
        output_file: Optional path to save metrics JSON

    Returns:
        LoadTestMetrics with collected data
    """
    logger.info(
        f"Starting load test: {num_devices} devices, {num_clients} clients, "
        f"{duration_seconds}s duration"
    )

    # Initialize cache with Phase 2 settings
    cache = initialize_cache(
        ttl_seconds=300,  # 5 minute TTL
        max_entries=1000,  # Support 1000 cached entries
        enabled=True,
    )

    # Create mock device factory
    device_factory = MockDeviceFactory(num_devices=num_devices)

    # Create in-memory database session (for testing)
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="lab",
        resource_cache_enabled=True,
        resource_cache_ttl_seconds=300,
    )
    session_factory = DatabaseSessionManager(settings)
    await session_factory.init()

    # Create metrics collector
    metrics = LoadTestMetrics()
    metrics.start_time = time.time()

    # Create concurrent clients
    clients: list[ConcurrentClient] = []
    for i in range(num_clients):
        client = ConcurrentClient(
            client_id=i,
            device_factory=device_factory,
            session_factory=session_factory,
            settings=settings,
            metrics=metrics,
        )
        clients.append(client)

    # Run all clients concurrently
    try:
        tasks = [client.run(duration_seconds) for client in clients]
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Load test interrupted, stopping clients...")
        for client in clients:
            client.stop()
    finally:
        metrics.end_time = time.time()

        # Get final cache stats
        cache_stats = await cache.get_stats()
        logger.info(f"Final cache stats: {cache_stats}")

        # Close database
        await session_factory.close()

    # Log summary
    logger.info("=" * 80)
    logger.info("LOAD TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Duration: {metrics.duration_seconds:.2f}s")
    logger.info(f"Total requests: {metrics.total_requests}")
    logger.info(f"Successful: {metrics.successful_requests}")
    logger.info(f"Failed: {metrics.failed_requests}")
    logger.info(f"Throughput: {metrics.requests_per_second:.2f} req/s")
    logger.info(f"Cache hit rate: {metrics.cache_hit_rate:.2f}%")
    logger.info(f"Error rate: {metrics.error_rate:.2f}%")

    latency = metrics.get_latency_metrics()
    logger.info(f"Latency p50: {latency.p50 * 1000:.2f}ms")
    logger.info(f"Latency p95: {latency.p95 * 1000:.2f}ms")
    logger.info(f"Latency p99: {latency.p99 * 1000:.2f}ms")
    logger.info("=" * 80)

    # Save to file if specified
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(metrics.to_dict(), f, indent=2)
        logger.info(f"Metrics saved to {output_file}")

    return metrics


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.skipif(
    os.getenv("RUN_LONG_LOAD_TEST") != "1",
    reason="5-minute load test disabled by default; set RUN_LONG_LOAD_TEST=1 to enable",
)
async def test_load_test_5_minutes():
    """Run 5-minute load test with 100 devices and 10 clients."""
    metrics = await run_load_test(
        num_devices=100,
        num_clients=10,
        duration_seconds=300,  # 5 minutes
        output_file=Path("reports/load_test_5min.json"),
    )

    # Validate acceptance criteria
    assert metrics.total_requests > 0, "No requests were made"
    assert metrics.error_rate < 5.0, f"Error rate {metrics.error_rate:.2f}% exceeds 5%"

    # Cache hit rate should be >70% (Phase 2 target)
    assert metrics.cache_hit_rate > 70.0, f"Cache hit rate {metrics.cache_hit_rate:.2f}% below 70%"

    # Latency p95 should be <1s (Phase 2 target)
    latency = metrics.get_latency_metrics()
    assert latency.p95 < 1.0, f"P95 latency {latency.p95:.3f}s exceeds 1s"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_load_test_quick():
    """Quick load test (30 seconds) for CI/development."""
    metrics = await run_load_test(
        num_devices=20,
        num_clients=5,
        duration_seconds=30,  # 30 seconds
        output_file=Path("reports/load_test_quick.json"),
    )

    # Basic validation
    assert metrics.total_requests > 0, "No requests were made"
    assert metrics.error_rate < 10.0, f"Error rate {metrics.error_rate:.2f}% exceeds 10%"


if __name__ == "__main__":
    # Run standalone load test
    asyncio.run(
        run_load_test(
            num_devices=100,
            num_clients=10,
            duration_seconds=300,
            output_file=Path("reports/load_test_results.json"),
        )
    )
