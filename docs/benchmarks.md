# Benchmarks

StressLab v0.1 includes a starter benchmark suite built from the three canonical examples:

- healthcare emergency department overload
- two-supplier supply chain with port congestion
- market liquidity withdrawal with venue delay

Run the suite with:

```bash
stresslab benchmark --suite starter
```

Outputs include:

- per-scenario metrics
- min-failure budgets and damage scores
- robust optimization summaries
- robust scenario-family counts and top coverage scores
- budgeted robust portfolio coverage rates
- fairness scores and fairness-aware intervention signals
- composite benchmark scores and leaderboard ranks
- a benchmark summary CSV
- a benchmark summary JSON artifact
- a benchmark markdown report
- a benchmark HTML report

The benchmark suite is intended as a reproducible smoke test and baseline comparison set rather than a final scientific benchmark corpus.
