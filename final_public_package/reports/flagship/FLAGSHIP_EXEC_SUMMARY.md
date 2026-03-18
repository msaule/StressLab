# StressLab Flagship Study Executive Summary

Across 5,000 systems and 5 topology families, StressLab found that collapse risk accelerates sharply once baseline utilization enters a shared transition band around 0.10-0.19, with shared variance and recovery-lag warning signals appearing before failure across domains.

## Key Findings

- Across 5,000 synthetic systems spanning 5 topology families, collapse risk rises sharply in a shared utilization band centered near 0.152, with the middle 50% of per-topology thresholds lying between 0.097 and 0.186.
- The transition is not identical across domains, but the threshold spread remains compact at 0.140 utilization points, which is consistent with a common collapse-onset regime rather than unrelated topology-specific behavior.
- Utilization is the dominant driver, while secondary structural variables such as capacity_slack, baseline_utilization, routing_entropy, average_degree materially shift how fast collapse accelerates near the threshold.
- Early-warning signals are shared across domains: collapse cases show about 1.09x higher variance growth and 1.16x longer recovery lag than stable cases.
- Cascade tails are broadly heavy-tailed, but in this run a lognormal tail model consistently fits better than a strict power law, suggesting multiplicative cascade growth rather than a single universal power-law exponent.
- The strongest interpretable law candidate from this run is: collapse_probability = -0.1795 + 3.9192 * utilization + 0.2942 * centralization_index.