"""Performance + accuracy benchmarks for autoai-optimize.

Run directly:

    python benchmark.py            # full run, writes benchmark.md
    python benchmark.py --quick    # fewer repetitions for a faster smoke run
    python benchmark.py --accuracy # only the classifier-accuracy section

Methodology (see IMPROVEMENTS.md §3):
  * Each timing metric is repeated N times; we report mean / median / stdev,
    not a single measurement, so GC pauses and OS scheduling noise don't masquerade
    as signal.
  * Three payload tiers (small ~0.3KB, medium ~50KB, large ~500KB) because
    BeautifulSoup parsing cost scales with DOM size.
  * A no-middleware baseline (raw function-call overhead) makes the overhead
    percentage provable rather than implied.
  * A concurrency test exercises the LRU cache under a ThreadPoolExecutor to
    demonstrate the lock is not a bottleneck.
  * A rotating-pool throughput scenario simulates a realistic cache hit-rate
    near the eviction boundary instead of the best-case "same URL forever".
  * A classifier-accuracy section reports precision/recall/false-positive-rate
    against a labeled fixture set so the "never misclassify" claim is measured.
"""

from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from autoai_optimize.analyze.classifier import PageType, classify
from autoai_optimize.core import _CACHE, generate_jsonld, optimize_html

# ---------------------------------------------------------------------------
# Payload fixtures of varying size
# ---------------------------------------------------------------------------

SMALL_HTML = """\
<html>
  <head><title>My Awesome Product</title></head>
  <body>
    <!-- @ai-entity:product -->
    <h1 data-ai-field="name">Super Widget 3000</h1>
    <meta name="description" content="The best widget ever made." />
    <span>$199.99</span>
  </body>
</html>
"""


def _medium_html() -> str:
    """~50KB: a representative product page with nav/footer markup."""
    nav = '<nav><a href="/c/{i}">Category {i}</a></nav>\n' * 60
    body = (
        '<article><h2>Related item {i}</h2><p>Some description text for item {i}. '
        'It has details, specifications, and a price tag.</p></article>\n'
    ) * 40
    return f"""\
<!doctype html><html><head>
<title>Widget Pro</title>
<meta property="og:type" content="product">
<meta property="og:title" content="Widget Pro">
<meta name="description" content="Professional widget.">
</head><body>
{nav}
<main><h1>Widget Pro 3000</h1><p class="price">$99.99</p>
<button>Add to Cart</button></main>
{body}
<footer>{nav}</footer>
</body></html>
"""


def _large_html() -> str:
    """~500KB: a long article/blog page with heavy markup."""
    para = (
        '<p>This is paragraph {i} of a long-form article. It contains enough prose '
        'to stress the HTML parser the way a real blog or news page would. '
        'Search engines and AI crawlers see pages this large routinely.</p>\n'
    ) * 1500
    return f"""\
<!doctype html><html><head>
<title>Why Performance Matters</title>
<meta property="og:type" content="article">
<meta property="og:title" content="Why Performance Matters">
<meta name="author" content="AutoAI">
</head><body>
<article><h1>Why Performance Matters</h1>
<time datetime="2026-07-01T09:00:00Z">July 1, 2026</time>
{para}
</article></body></html>
"""


PAYLOADS = {
    "small (~0.3KB)": SMALL_HTML,
    "medium (~50KB)": _medium_html(),
    "large (~500KB)": _large_html(),
}


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

def _time_ms(func, repeats: int) -> list[float]:
    """Run `func` `repeats` times, returning per-run times in ms."""
    times: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        func()
        times.append((time.perf_counter() - start) * 1000)
    return times


def _stats(times: list[float]) -> dict[str, float]:
    return {
        "mean": statistics.mean(times),
        "median": statistics.median(times),
        "stdev": statistics.stdev(times) if len(times) > 1 else 0.0,
    }


def _fmt(value: float) -> str:
    return f"{value:.4f}" if value < 1 else f"{value:.2f}"


# ---------------------------------------------------------------------------
# Benchmark sections
# ---------------------------------------------------------------------------

def benchmark_latency(reps: int) -> list[dict]:
    """Cold/warm/throughput per payload tier, plus a no-middleware baseline.

    The baseline measures the cost of calling a trivial function on the same
    HTML, so the middleware overhead is provable as a delta rather than implied.
    """
    _CACHE.clear()
    rows: list[dict] = []

    for label, html in PAYLOADS.items():
        # Clear cache so the first call is a true cold start.
        _CACHE.clear()

        # Baseline: a no-op call returning the html unchanged. This isolates
        # the overhead of optimize_html itself from "any function call".
        baseline_times = _time_ms(lambda h=html: _baseline_passthrough(h), reps)

        # Cold start: first parse/extraction/injection for this payload.
        # We bust the cache before each cold sample so every rep is cold.
        cold_times = []
        for _ in range(min(reps, 20)):  # cold is expensive; cap it
            _CACHE.clear()
            start = time.perf_counter()
            optimize_html(html, url="/products/widget")
            cold_times.append((time.perf_counter() - start) * 1000)

        # Warm start: cache is hot (identical input already processed once).
        optimize_html(html, url="/products/widget")  # prime the cache
        warm_times = _time_ms(
            lambda h=html: optimize_html(h, url="/products/widget"), reps
        )

        # Throughput over `reps` consecutive requests (all warm after first).
        through = _time_ms(
            lambda h=html: optimize_html(h, url="/products/widget"), reps
        )

        cold_s = _stats(cold_times)
        warm_s = _stats(warm_times)
        base_s = _stats(baseline_times)
        through_s = _stats(through)

        rows.append({
            "payload": label,
            "baseline_mean_ms": base_s["mean"],
            "cold_mean_ms": cold_s["mean"],
            "cold_median_ms": cold_s["median"],
            "cold_stdev_ms": cold_s["stdev"],
            "warm_mean_ms": warm_s["mean"],
            "warm_median_ms": warm_s["median"],
            "warm_stdev_ms": warm_s["stdev"],
            "throughput_mean_ms": through_s["mean"],
            "throughput_median_ms": through_s["median"],
            "overhead_vs_baseline_pct": (
                ((warm_s["mean"] - base_s["mean"]) / base_s["mean"] * 100)
                if base_s["mean"] > 0 else float("inf")
            ),
        })
    _CACHE.clear()
    return rows


def _baseline_passthrough(html: str) -> str:
    """Cheapest possible 'do nothing to the HTML' for baseline timing."""
    return html


def benchmark_concurrency(reps: int) -> dict:
    """Exercise the LRU cache under concurrent threads.

    Demonstrates the lock is not a bottleneck: per-request time under load
    should be on the same order as single-threaded warm hits.
    """
    _CACHE.clear()
    html = SMALL_HTML
    optimize_html(html, url="/products/widget")  # prime cache

    errors = []
    n_workers = 8
    calls_per_worker = max(reps // n_workers, 50)

    def worker() -> None:
        try:
            for _ in range(calls_per_worker):
                optimize_html(html, url="/products/widget")
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        list(pool.map(lambda _: worker(), range(n_workers)))
    elapsed = time.perf_counter() - start

    total_calls = n_workers * calls_per_worker
    per_call_ms = (elapsed / total_calls) * 1000
    _CACHE.clear()
    return {
        "workers": n_workers,
        "calls_per_worker": calls_per_worker,
        "total_calls": total_calls,
        "wall_time_s": elapsed,
        "per_call_ms": per_call_ms,
        "errors": errors,
    }


def benchmark_rotating_pool(reps: int) -> dict:
    """Throughput against a rotating pool of distinct pages.

    Unlike the best-case 'same URL forever' throughput, this simulates a
    realistic working set (e.g. 200 unique pages, 1000 total requests) near
    the LRU max_size=1024 eviction boundary, so behavior under churn is visible.
    """
    _CACHE.clear()
    pool_size = 200
    pages = [
        (f'<html><head><title>P{i}</title></head><body>'
         f'<h1>Product {i}</h1><p class="price">${i}.99</p></body></html>',
         f"/products/p{i}")
        for i in range(pool_size)
    ]
    total_requests = max(reps, 1000)

    start = time.perf_counter()
    for i in range(total_requests):
        html, url = pages[i % pool_size]
        optimize_html(html, url=url)
    elapsed = time.perf_counter() - start

    hit_rate = (total_requests - pool_size) / total_requests  # first pass misses
    result = {
        "pool_size": pool_size,
        "total_requests": total_requests,
        "wall_time_s": elapsed,
        "per_call_ms": (elapsed / total_requests) * 1000,
        "estimated_cache_hit_rate_pct": hit_rate * 100,
    }
    _CACHE.clear()
    return result


# ---------------------------------------------------------------------------
# Classifier accuracy (IMPROVEMENTS.md §3.6) — precision/recall/FP-rate
# ---------------------------------------------------------------------------

# Labeled fixtures: (url_path, html, expected_page_type).
# Includes deliberate non-matches (admin/404/login) to test false positives.
ACCURACY_FIXTURES: list[tuple[str, str, PageType]] = [
    # --- Products (positive) ---
    ("/products/widget-x",
     '<meta property="og:type" content="product"><h1>Widget</h1><p>$19.99</p>',
     PageType.PRODUCT),
    ("/shop/item-42",
     '<html><body><h1>Item</h1><p>$5.00</p></body></html>',
     PageType.PRODUCT),
    ("/p/abc",
     '<html><body><h1>Buy me</h1><span itemprop="price" content="9.99">$9.99</span></body></html>',
     PageType.PRODUCT),
    # --- Articles (positive) ---
    ("/blog/how-to-test",
     '<meta property="og:type" content="article">',
     PageType.ARTICLE),
    ("/news/today",
     '<html><body><article><h1>News</h1></article></body></html>',
     PageType.ARTICLE),
    ("/post/123",
     '<html><body><article><time datetime="2026-01-01">x</time></article></body></html>',
     PageType.ARTICLE),
    # --- Unknowns (must NOT be classified as Product/Article) ---
    ("/admin/dashboard",
     '<html><body><h1>Admin Panel</h1></body></html>',
     PageType.UNKNOWN),
    ("/login",
     '<html><body><form><input name="user"></form></body></html>',
     PageType.UNKNOWN),
    ("/node_modules/react/index.js",
     '<html><body>module.exports = {};</body></html>',
     PageType.UNKNOWN),
    ("/",
     '<html><body><h1>Welcome</h1><p>Home page.</p></body></html>',
     PageType.UNKNOWN),
    ("/404",
     '<html><body><h1>Not Found</h1></body></html>',
     PageType.UNKNOWN),
]


def benchmark_accuracy() -> dict:
    """Measure classifier precision/recall/false-positive-rate.

    For each labeled fixture we run the real classify() and compare the
    predicted PageType to the expected one, restricted to {ARTICLE, PRODUCT,
    UNKNOWN} since Profile is scored separately and not emitted by classify().
    """
    tp = fp = fn = tn = 0  # treating UNKNOWN as the negative class

    per_case: list[dict] = []
    for path, html, expected in ACCURACY_FIXTURES:
        soup = BeautifulSoup(html, "html.parser")
        predicted = classify(path, soup).page_type
        expected_positive = expected != PageType.UNKNOWN
        predicted_positive = predicted != PageType.UNKNOWN

        if expected_positive and predicted_positive:
            tp += 1
        elif not expected_positive and predicted_positive:
            fp += 1
        elif expected_positive and not predicted_positive:
            fn += 1
        else:
            tn += 1

        per_case.append({
            "path": path,
            "expected": expected.value,
            "predicted": predicted.value,
            "correct": (predicted == expected),
        })

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    fp_rate = fp / (fp + tn) if (fp + tn) else 0.0
    accuracy = (tp + tn) / len(ACCURACY_FIXTURES)

    return {
        "total": len(ACCURACY_FIXTURES),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "accuracy_pct": accuracy * 100,
        "precision": precision,
        "recall": recall,
        "false_positive_rate": fp_rate,
        "per_case": per_case,
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def render_markdown(
    latency_rows: list[dict],
    concurrency: dict,
    rotating: dict,
    accuracy: dict,
) -> str:
    lines: list[str] = []
    lines.append("# AutoAI-Optimize Performance & Accuracy Benchmark\n")
    lines.append(
        "Methodology: each timing metric is repeated and reported as "
        "mean/median/stdev (not a single measurement). Three payload tiers are "
        "tested because parsing cost scales with DOM size. A no-middleware "
        "baseline makes overhead provable. Concurrency and rotating-pool "
        "sections exercise the LRU cache under realistic load. A labeled "
        "fixture set measures classifier precision/recall/false-positive-rate.\n"
    )

    lines.append("## 1. Latency by payload tier\n")
    lines.append("| Payload | Baseline (ms) | Cold mean (ms) | Warm mean (ms) | Warm median (ms) | Warm stdev | Throughput mean (ms) | Overhead vs baseline |")
    lines.append("|---------|---------------|----------------|----------------|------------------|------------|----------------------|----------------------|")
    for r in latency_rows:
        lines.append(
            f"| {r['payload']} | {_fmt(r['baseline_mean_ms'])} | "
            f"{_fmt(r['cold_mean_ms'])} | {_fmt(r['warm_mean_ms'])} | "
            f"{_fmt(r['warm_median_ms'])} | {_fmt(r['warm_stdev_ms'])} | "
            f"{_fmt(r['throughput_mean_ms'])} | {r['overhead_vs_baseline_pct']:.1f}% |"
        )
    lines.append("")
    lines.append(
        "> Overhead vs baseline = how much slower a warm cache hit is than a "
        "no-op function call returning the same HTML. Cold-start cost reflects "
        "BeautifulSoup parsing + extraction + injection.\n"
    )

    lines.append("## 2. Concurrency (ThreadPoolExecutor on LRU cache)\n")
    lines.append(f"- Workers: **{concurrency['workers']}**")
    lines.append(f"- Total concurrent calls: **{concurrency['total_calls']}**")
    lines.append(f"- Wall time: **{concurrency['wall_time_s']:.3f} s**")
    lines.append(f"- Per-call (warm, contended): **{_fmt(concurrency['per_call_ms'])} ms**")
    lines.append(f"- Errors: **{len(concurrency['errors'])}**\n")

    lines.append("## 3. Rotating-pool throughput (realistic cache hit-rate)\n")
    lines.append(f"- Distinct pages in pool: **{rotating['pool_size']}**")
    lines.append(f"- Total requests: **{rotating['total_requests']}**")
    lines.append(f"- Estimated cache hit rate: **{rotating['estimated_cache_hit_rate_pct']:.1f}%**")
    lines.append(f"- Per-call average: **{_fmt(rotating['per_call_ms'])} ms**\n")

    lines.append("## 4. Classifier accuracy (labeled fixtures)\n")
    lines.append(f"- Fixtures: **{accuracy['total']}**")
    lines.append(f"- Accuracy: **{accuracy['accuracy_pct']:.1f}%**")
    lines.append(f"- Precision: **{accuracy['precision']:.3f}**")
    lines.append(f"- Recall: **{accuracy['recall']:.3f}**")
    lines.append(f"- False-positive rate: **{accuracy['false_positive_rate']:.3f}**")
    lines.append(
        f"- Confusion: TP={accuracy['true_positive']} "
        f"FP={accuracy['false_positive']} "
        f"FN={accuracy['false_negative']} "
        f"TN={accuracy['true_negative']}\n"
    )
    lines.append("| Path | Expected | Predicted | Correct |")
    lines.append("|------|----------|-----------|---------|")
    for c in accuracy["per_case"]:
        mark = "✅" if c["correct"] else "❌"
        lines.append(f"| `{c['path']}` | {c['expected']} | {c['predicted']} | {mark} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="autoai-optimize benchmark")
    parser.add_argument("--quick", action="store_true",
                        help="fewer repetitions for a fast smoke run")
    parser.add_argument("--accuracy", action="store_true",
                        help="run only the classifier-accuracy section")
    args = parser.parse_args()

    reps = 50 if args.quick else 100

    if args.accuracy:
        acc = benchmark_accuracy()
        print(json.dumps(acc, indent=2))
        return

    print("Running latency benchmarks (this may take a moment)...")
    latency = benchmark_latency(reps)
    print("Running concurrency benchmark...")
    conc = benchmark_concurrency(reps)
    print("Running rotating-pool benchmark...")
    rot = benchmark_rotating_pool(reps)
    print("Running classifier-accuracy benchmark...")
    acc = benchmark_accuracy()

    md = render_markdown(latency, conc, rot, acc)
    with open("benchmark.md", "w", encoding="utf-8") as f:
        f.write(md)

    # Also dump raw numbers as JSON for programmatic consumption / CI gating.
    with open("benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "latency": latency,
            "concurrency": conc,
            "rotating_pool": rot,
            "accuracy": acc,
        }, f, indent=2)

    print("Benchmark complete. Wrote benchmark.md and benchmark_results.json.")
    print(f"\nClassifier accuracy: {acc['accuracy_pct']:.1f}%  "
          f"(precision={acc['precision']:.3f}, recall={acc['recall']:.3f}, "
          f"FP-rate={acc['false_positive_rate']:.3f})")
    small_warm = next((r for r in latency if "small" in r["payload"]), {})
    if small_warm:
        print(f"Small-payload warm cache hit: {small_warm['warm_mean_ms']:.4f} ms "
              f"(median {small_warm['warm_median_ms']:.4f} ms)")


if __name__ == "__main__":
    main()
