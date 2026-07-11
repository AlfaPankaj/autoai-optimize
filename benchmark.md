# AutoAI-Optimize Performance & Accuracy Benchmark

Methodology: each timing metric is repeated and reported as mean/median/stdev (not a single measurement). Three payload tiers are tested because parsing cost scales with DOM size. A no-middleware baseline makes overhead provable. Concurrency and rotating-pool sections exercise the LRU cache under realistic load. A labeled fixture set measures classifier precision/recall/false-positive-rate.

## 1. Latency by payload tier

| Payload | Baseline (ms) | Cold mean (ms) | Warm mean (ms) | Warm median (ms) | Warm stdev | Throughput mean (ms) | Overhead vs baseline |
|---------|---------------|----------------|----------------|------------------|------------|----------------------|----------------------|
| small (~0.3KB) | 0.0001 | 1.01 | 0.0028 | 0.0028 | 0.0003 | 0.0028 | 2293.2% |
| medium (~50KB) | 0.0001 | 17.02 | 0.0148 | 0.0147 | 0.0004 | 0.0147 | 14103.8% |
| large (~500KB) | 0.0001 | 85.09 | 0.3501 | 0.3475 | 0.0110 | 0.3448 | 336548.4% |

> Overhead vs baseline = how much slower a warm cache hit is than a no-op function call returning the same HTML. Cold-start cost reflects BeautifulSoup parsing + extraction + injection.

## 2. Concurrency (ThreadPoolExecutor on LRU cache)

- Workers: **8**
- Total concurrent calls: **400**
- Wall time: **0.005 s**
- Per-call (warm, contended): **0.0120 ms**
- Errors: **0**

## 3. Rotating-pool throughput (realistic cache hit-rate)

- Distinct pages in pool: **200**
- Total requests: **1000**
- Estimated cache hit rate: **80.0%**
- Per-call average: **0.1209 ms**

## 4. Classifier accuracy (labeled fixtures)

- Fixtures: **11**
- Accuracy: **100.0%**
- Precision: **1.000**
- Recall: **1.000**
- False-positive rate: **0.000**
- Confusion: TP=6 FP=0 FN=0 TN=5

| Path | Expected | Predicted | Correct |
|------|----------|-----------|---------|
| `/products/widget-x` | Product | Product | ✅ |
| `/shop/item-42` | Product | Product | ✅ |
| `/p/abc` | Product | Product | ✅ |
| `/blog/how-to-test` | Article | Article | ✅ |
| `/news/today` | Article | Article | ✅ |
| `/post/123` | Article | Article | ✅ |
| `/admin/dashboard` | Unknown | Unknown | ✅ |
| `/login` | Unknown | Unknown | ✅ |
| `/node_modules/react/index.js` | Unknown | Unknown | ✅ |
| `/` | Unknown | Unknown | ✅ |
| `/404` | Unknown | Unknown | ✅ |
