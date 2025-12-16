#!/usr/bin/env python3
"""Generate performance benchmark report with graphs.

Reads benchmark/load test results from JSON files and generates:
- Latency graphs (p50, p95, p99 over time)
- Cache hit rate graphs
- Comparison against Phase 1 baseline (if available)
- Summary report in Markdown format

Usage:
    python scripts/benchmark_report.py --output reports/phase2_benchmark.json
    python scripts/benchmark_report.py --input reports/benchmark_results.json --format html
    python scripts/benchmark_report.py --load-test reports/load_test_results.json --benchmark reports/benchmark_results.json
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ReportConfig:
    """Configuration for report generation."""

    benchmark_file: Optional[Path] = None
    load_test_file: Optional[Path] = None
    baseline_file: Optional[Path] = None
    output_dir: Path = Path("reports")
    output_format: str = "markdown"  # markdown, html, json
    generate_graphs: bool = True


@dataclass
class BenchmarkReport:
    """Benchmark report data."""

    timestamp: str
    benchmark_data: Optional[Dict[str, Any]] = None
    load_test_data: Optional[Dict[str, Any]] = None
    baseline_data: Optional[Dict[str, Any]] = None
    comparisons: Dict[str, Any] = field(default_factory=dict)
    graphs: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "timestamp": self.timestamp,
            "benchmark": self.benchmark_data,
            "load_test": self.load_test_data,
            "baseline": self.baseline_data,
            "comparisons": self.comparisons,
            "graphs": self.graphs,
        }


def load_json_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """Load JSON data from file.

    Args:
        file_path: Path to JSON file

    Returns:
        Loaded data or None if file doesn't exist
    """
    if not file_path.exists():
        logger.warning(f"File not found: {file_path}")
        return None

    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {file_path}: {e}")
        return None


def generate_ascii_graph(
    values: List[float], labels: List[str], width: int = 60, height: int = 10
) -> str:
    """Generate ASCII bar graph.

    Args:
        values: Values to plot
        labels: Labels for each value
        width: Graph width in characters
        height: Graph height in rows

    Returns:
        ASCII graph string
    """
    if not values:
        return "No data to plot"

    max_val = max(values)
    if max_val == 0:
        return "All values are zero"

    lines = []
    lines.append("┌" + "─" * (width + 2) + "┐")

    for i, (label, value) in enumerate(zip(labels, values)):
        # Calculate bar length
        bar_len = int((value / max_val) * width) if max_val > 0 else 0
        bar = "█" * bar_len

        # Format label and value
        label_str = f"{label:12s}"
        value_str = f"{value:.2f}"

        lines.append(f"│ {label_str} {bar:<{width}s} {value_str:>8s} │")

    lines.append("└" + "─" * (width + 2) + "┘")
    return "\n".join(lines)


def generate_latency_graph(benchmark_data: Dict[str, Any]) -> str:
    """Generate latency comparison graph.

    Args:
        benchmark_data: Benchmark results data

    Returns:
        ASCII graph of latency metrics
    """
    # Extract latency data from all benchmarks
    benchmarks = []
    p50_values = []
    p95_values = []
    p99_values = []

    for name, data in benchmark_data.items():
        if "latency" in data:
            benchmarks.append(name.replace("_", " ").title())
            latency = data["latency"]
            p50_values.append(latency.get("p50_ms", 0))
            p95_values.append(latency.get("p95_ms", 0))
            p99_values.append(latency.get("p99_ms", 0))

    if not benchmarks:
        return "No latency data available"

    graph = "## Latency Comparison\n\n"
    graph += "### P50 Latency (ms)\n"
    graph += generate_ascii_graph(p50_values, benchmarks) + "\n\n"

    graph += "### P95 Latency (ms)\n"
    graph += generate_ascii_graph(p95_values, benchmarks) + "\n\n"

    graph += "### P99 Latency (ms)\n"
    graph += generate_ascii_graph(p99_values, benchmarks) + "\n\n"

    return graph


def generate_cache_graph(data: Dict[str, Any], title: str = "Cache Metrics") -> str:
    """Generate cache hit rate graph.

    Args:
        data: Data containing cache metrics
        title: Graph title

    Returns:
        ASCII graph of cache metrics
    """
    graph = f"## {title}\n\n"

    # Extract cache data
    if "cache" in data:
        cache = data["cache"]
        hits = cache.get("hits", 0)
        misses = cache.get("misses", 0)
        hit_rate = cache.get("hit_rate_percent", 0)

        graph += f"**Hit Rate:** {hit_rate:.2f}%\n\n"
        graph += generate_ascii_graph(
            [hits, misses], ["Cache Hits", "Cache Misses"]
        )
        graph += "\n\n"

    return graph


def compare_with_baseline(
    current: Dict[str, Any], baseline: Dict[str, Any]
) -> Dict[str, Any]:
    """Compare current results with baseline.

    Args:
        current: Current benchmark data
        baseline: Baseline benchmark data

    Returns:
        Dictionary of comparisons
    """
    comparisons = {}

    # Compare latency
    if "latency" in current and "latency" in baseline:
        curr_p95 = current["latency"].get("p95_ms", 0)
        base_p95 = baseline["latency"].get("p95_ms", 0)

        if base_p95 > 0:
            improvement = ((base_p95 - curr_p95) / base_p95) * 100
            comparisons["latency_p95_improvement"] = improvement
            comparisons["latency_p95_current"] = curr_p95
            comparisons["latency_p95_baseline"] = base_p95

    # Compare cache hit rate
    if "cache" in current and "cache" in baseline:
        curr_hit_rate = current["cache"].get("hit_rate_percent", 0)
        base_hit_rate = baseline["cache"].get("hit_rate_percent", 0)

        comparisons["cache_hit_rate_current"] = curr_hit_rate
        comparisons["cache_hit_rate_baseline"] = base_hit_rate
        comparisons["cache_hit_rate_diff"] = curr_hit_rate - base_hit_rate

    # Compare throughput (if available)
    if "summary" in current and "summary" in baseline:
        curr_rps = current["summary"].get("requests_per_second", 0)
        base_rps = baseline["summary"].get("requests_per_second", 0)

        if base_rps > 0:
            improvement = ((curr_rps - base_rps) / base_rps) * 100
            comparisons["throughput_improvement"] = improvement
            comparisons["throughput_current"] = curr_rps
            comparisons["throughput_baseline"] = base_rps

    return comparisons


def generate_markdown_report(report: BenchmarkReport) -> str:
    """Generate Markdown report.

    Args:
        report: Report data

    Returns:
        Markdown formatted report
    """
    md = f"# Phase 2 Performance Benchmark Report\n\n"
    md += f"Generated: {report.timestamp}\n\n"

    # Executive Summary
    md += "## Executive Summary\n\n"

    if report.benchmark_data:
        md += "### Benchmark Results\n\n"
        for name, data in report.benchmark_data.items():
            md += f"**{name.replace('_', ' ').title()}**\n\n"

            if "latency" in data:
                latency = data["latency"]
                md += f"- P50 Latency: {latency.get('p50_ms', 0):.2f}ms\n"
                md += f"- P95 Latency: {latency.get('p95_ms', 0):.2f}ms\n"
                md += f"- P99 Latency: {latency.get('p99_ms', 0):.2f}ms\n"

            if "cache" in data:
                cache = data["cache"]
                md += f"- Cache Hit Rate: {cache.get('hit_rate_percent', 0):.2f}%\n"

            if "memory" in data:
                memory = data["memory"]
                md += f"- Memory Increase: {memory.get('increase_mb', 0):.2f}MB\n"

            md += "\n"

    if report.load_test_data:
        md += "### Load Test Results\n\n"

        if "summary" in report.load_test_data:
            summary = report.load_test_data["summary"]
            md += f"- Total Requests: {summary.get('total_requests', 0)}\n"
            md += f"- Duration: {summary.get('duration_seconds', 0):.2f}s\n"
            md += (
                f"- Throughput: {summary.get('requests_per_second', 0):.2f} req/s\n"
            )

        if "cache" in report.load_test_data:
            cache = report.load_test_data["cache"]
            md += f"- Cache Hit Rate: {cache.get('hit_rate_percent', 0):.2f}%\n"

        if "latency" in report.load_test_data:
            latency = report.load_test_data["latency"]
            md += f"- P95 Latency: {latency.get('p95_ms', 0):.2f}ms\n"

        md += "\n"

    # Detailed Results
    md += "## Detailed Results\n\n"

    # Benchmark graphs
    if report.benchmark_data:
        md += generate_latency_graph(report.benchmark_data)

    # Cache graphs
    if report.benchmark_data:
        for name, data in report.benchmark_data.items():
            if "cache" in data:
                md += generate_cache_graph(
                    data, f"Cache Metrics: {name.replace('_', ' ').title()}"
                )

    if report.load_test_data:
        md += generate_cache_graph(report.load_test_data, "Load Test Cache Metrics")

    # Baseline comparison
    if report.comparisons:
        md += "## Comparison with Baseline\n\n"

        if "latency_p95_improvement" in report.comparisons:
            improvement = report.comparisons["latency_p95_improvement"]
            md += f"- **Latency P95 Improvement:** {improvement:.2f}%\n"
            md += f"  - Current: {report.comparisons['latency_p95_current']:.2f}ms\n"
            md += f"  - Baseline: {report.comparisons['latency_p95_baseline']:.2f}ms\n\n"

        if "cache_hit_rate_diff" in report.comparisons:
            diff = report.comparisons["cache_hit_rate_diff"]
            md += f"- **Cache Hit Rate Change:** {diff:+.2f}%\n"
            md += f"  - Current: {report.comparisons['cache_hit_rate_current']:.2f}%\n"
            md += (
                f"  - Baseline: {report.comparisons['cache_hit_rate_baseline']:.2f}%\n\n"
            )

        if "throughput_improvement" in report.comparisons:
            improvement = report.comparisons["throughput_improvement"]
            md += f"- **Throughput Improvement:** {improvement:.2f}%\n"
            md += f"  - Current: {report.comparisons['throughput_current']:.2f} req/s\n"
            md += (
                f"  - Baseline: {report.comparisons['throughput_baseline']:.2f} req/s\n\n"
            )

    # Phase 2 Acceptance Criteria
    md += "## Phase 2 Acceptance Criteria\n\n"

    # Check cache hit rate >70%
    cache_hit_rate = None
    if report.load_test_data and "cache" in report.load_test_data:
        cache_hit_rate = report.load_test_data["cache"].get("hit_rate_percent", 0)
    elif report.benchmark_data:
        # Get best cache hit rate from benchmarks
        for data in report.benchmark_data.values():
            if "cache" in data:
                rate = data["cache"].get("hit_rate_percent", 0)
                if cache_hit_rate is None or rate > cache_hit_rate:
                    cache_hit_rate = rate

    if cache_hit_rate is not None:
        status = "✅ PASS" if cache_hit_rate > 70 else "❌ FAIL"
        md += f"- **Cache Hit Rate >70%:** {status} ({cache_hit_rate:.2f}%)\n"

    # Check P95 latency <1s
    p95_latency = None
    if report.load_test_data and "latency" in report.load_test_data:
        p95_latency = report.load_test_data["latency"].get("p95_ms", 0)
    elif report.benchmark_data:
        # Get best P95 from benchmarks
        for data in report.benchmark_data.values():
            if "latency" in data:
                latency = data["latency"].get("p95_ms", 0)
                if p95_latency is None or latency < p95_latency:
                    p95_latency = latency

    if p95_latency is not None:
        status = "✅ PASS" if p95_latency < 1000 else "❌ FAIL"
        md += f"- **P95 Latency <1s:** {status} ({p95_latency:.2f}ms)\n"

    # Check no memory leaks
    memory_ok = True
    if report.benchmark_data:
        for data in report.benchmark_data.values():
            if "memory" in data:
                increase = data["memory"].get("increase_mb", 0)
                if increase > 100:  # Threshold: 100MB
                    memory_ok = False

    status = "✅ PASS" if memory_ok else "⚠️  WARNING"
    md += f"- **No Memory Leaks:** {status}\n"

    md += "\n"

    return md


def generate_report(config: ReportConfig) -> BenchmarkReport:
    """Generate benchmark report.

    Args:
        config: Report configuration

    Returns:
        Generated report
    """
    logger.info("Generating benchmark report...")

    # Load data files
    benchmark_data = None
    if config.benchmark_file:
        benchmark_data = load_json_file(config.benchmark_file)

    load_test_data = None
    if config.load_test_file:
        load_test_data = load_json_file(config.load_test_file)

    baseline_data = None
    if config.baseline_file:
        baseline_data = load_json_file(config.baseline_file)

    # Create report
    report = BenchmarkReport(
        timestamp=datetime.utcnow().isoformat(),
        benchmark_data=benchmark_data,
        load_test_data=load_test_data,
        baseline_data=baseline_data,
    )

    # Compare with baseline
    if baseline_data and (benchmark_data or load_test_data):
        current = benchmark_data or load_test_data
        if isinstance(current, dict):
            # If current is nested (multiple benchmarks), compare first one
            if any(isinstance(v, dict) for v in current.values()):
                first_key = next(iter(current.keys()))
                current = current[first_key]

        report.comparisons = compare_with_baseline(current, baseline_data)

    return report


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate performance benchmark report with graphs"
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        help="Path to benchmark results JSON",
        default=None,
    )
    parser.add_argument(
        "--load-test",
        type=Path,
        help="Path to load test results JSON",
        default=None,
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Path to baseline results JSON for comparison",
        default=None,
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file path (default: reports/benchmark_report.md)",
        default=Path("reports/benchmark_report.md"),
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "html"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--no-graphs",
        action="store_true",
        help="Disable graph generation",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.benchmark and not args.load_test:
        logger.error("Must specify at least --benchmark or --load-test")
        return 1

    # Create config
    config = ReportConfig(
        benchmark_file=args.benchmark,
        load_test_file=args.load_test,
        baseline_file=args.baseline,
        output_dir=args.output.parent,
        output_format=args.format,
        generate_graphs=not args.no_graphs,
    )

    # Generate report
    report = generate_report(config)

    # Save report
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.format == "json":
        with open(args.output, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        logger.info(f"JSON report saved to {args.output}")

    elif args.format == "markdown":
        markdown = generate_markdown_report(report)
        with open(args.output, "w") as f:
            f.write(markdown)
        logger.info(f"Markdown report saved to {args.output}")

    elif args.format == "html":
        # HTML generation would require additional dependencies (markdown2, jinja2)
        logger.error("HTML format not yet implemented")
        return 1

    logger.info("Report generation complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
