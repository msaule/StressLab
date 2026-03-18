# Universal Collapse Thresholds in Queue-Flow-Dependency Networks

## Abstract

Across 5,000 systems and 5 topology families, StressLab found that collapse risk accelerates sharply once baseline utilization enters a shared transition band around 0.10-0.19, with shared variance and recovery-lag warning signals appearing before failure across domains.

## Motivation

This flagship study uses StressLab as a discovery engine to test whether cross-domain operational networks share a common collapse onset regime as utilization and coupling rise, and whether warning signals generalize across domains.

## Experimental Design

- Systems: `5,000` synthetic systems
- Topology families: `5`
- Families: Hierarchical Supply, Market Microstructure, Random Queue, Scale-Free, Small-World
- Workflow per system: baseline simulation, minimum-shock failure search, worst-case search, collapse metric extraction, merged theory analysis
- Case-study layer: healthcare ED overload baseline vs collapse vs optimization

## Metrics

- Structural features: topology type, node and edge counts, clustering, path length, centralization, redundancy, coupling, utilization, slack, routing entropy, and centrality summaries.
- Outcome metrics: collapse probability, minimum shock to failure, worst-case damage, cascade size/depth/speed, recovery time, throughput loss, fragility index, resilience score, and bottleneck count.
- Early-warning metrics: variance increase, autocorrelation increase, and recovery lag.

## System Families

| topology_type | system_count |
| --- | --- |
| hierarchical_supply | 1000 |
| market_microstructure | 1000 |
| random_queue | 1000 |
| scale_free | 1000 |
| small_world | 1000 |

## Results

- Shared threshold band: `0.097` to `0.186` baseline utilization
- Median threshold: `0.152`

| topology_type | topology_label | critical_utilization | transition_low | transition_high | peak_slope | mean_collapse_probability |
| --- | --- | --- | --- | --- | --- | --- |
| scale_free | Scale-Free | 0.06182668683996517 | 0.0787143260219414 | 0.1807346400890889 | 8.504413906726976 | 0.24699999999999997 |
| random_queue | Random Queue | 0.09681778710645442 | 0.10404989952701504 | 0.14048919667606288 | 12.674950462061657 | 0.13699999999999998 |
| hierarchical_supply | Hierarchical Supply | 0.1521080299935587 | 0.1068691866007399 | 0.24975927340465467 | 9.125011212753456 | 0.5583333333333333 |
| small_world | Small-World | 0.18642351667459195 | 0.10329348797916599 | 0.20542789610906462 | 7.542121216193799 | 0.37799999999999995 |
| market_microstructure | Market Microstructure | 0.20211702581922594 | 0.13926454854210102 | 0.20812967301579025 | 7.2070307664308935 | 0.768 |

### Top Predictors

| feature | correlation | score |
| --- | --- | --- |
| capacity_slack | -0.7956387642365201 | 0.7956387642365201 |
| baseline_utilization | 0.7956387642365199 | 0.7956387642365199 |
| routing_entropy | 0.470095443466812 | 0.470095443466812 |
| average_degree | -0.2635922887556575 | 0.2635922887556575 |
| edge_count | -0.2411979901298805 | 0.2411979901298805 |
| clustering_coefficient | -0.2196088038077407 | 0.2196088038077407 |
| buffer_ratio | 0.1642164492648764 | 0.1642164492648764 |
| max_eigenvector | 0.1502273659595762 | 0.1502273659595762 |
| coupling_strength | -0.1405012744032533 | 0.1405012744032533 |
| node_count | -0.1213216334041833 | 0.1213216334041833 |

### Candidate Laws

| target | feature | model_type | coefficient | intercept | exponent | r2 | observations | formula | complexity | source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| collapse_probability | utilization+centralization_index | multivariate_linear | 3.919246428751345 | -0.1795355471240612 | 0.2941890631488335 | 0.6473968760258529 | 5000 | collapse_probability = -0.1795 + 3.9192 * utilization + 0.2942 * centralization_index | 85 | fragility |
| collapse_probability | capacity_slack+centralization_index | multivariate_linear | -3.919246428751348 | 3.739710881627288 | 0.2941890631488337 | 0.6473968760258529 | 5000 | collapse_probability = 3.7397 + -3.9192 * capacity_slack + 0.2942 * centralization_index | 88 | fragility |
| collapse_probability | utilization+redundancy_index | multivariate_linear | 3.952376662308021 | -0.1516764592738486 | 0.5436408372397812 | 0.6373169704155763 | 5000 | collapse_probability = -0.1517 + 3.9524 * utilization + 0.5436 * redundancy_index | 81 | fragility |
| collapse_probability | capacity_slack+redundancy_index | multivariate_linear | -3.952376662308033 | 3.800700203034185 | 0.5436408372397786 | 0.6373169704155763 | 5000 | collapse_probability = 3.8007 + -3.9524 * capacity_slack + 0.5436 * redundancy_index | 84 | fragility |
| collapse_probability | utilization+coupling_strength | multivariate_linear | 3.871861102363956 | 0.0289979116496555 | -0.3461746840379009 | 0.6361362926736568 | 5000 | collapse_probability = 0.0290 + 3.8719 * utilization + -0.3462 * coupling_strength | 82 | fragility |
| collapse_probability | capacity_slack+coupling_strength | multivariate_linear | -3.8718611023639578 | 3.9008590140136143 | -0.3461746840379007 | 0.6361362926736568 | 5000 | collapse_probability = 3.9009 + -3.8719 * capacity_slack + -0.3462 * coupling_strength | 86 | fragility |
| collapse_probability | utilization | log | 4.459317455936716 | -0.1247572870889743 |  | 0.6333733566019424 | 5000 | collapse_probability = -0.1248 + 4.4593 * log1p(utilization) | 60 | fragility |
| collapse_probability | utilization+routing_entropy | multivariate_linear | 3.8798327698195822 | -0.1069664882330593 | 0.0165178206021896 | 0.6330777332676719 | 5000 | collapse_probability = -0.1070 + 3.8798 * utilization + 0.0165 * routing_entropy | 80 | fragility |
| collapse_probability | capacity_slack+routing_entropy | multivariate_linear | -3.879832769819582 | 3.772866281586529 | 0.0165178206021865 | 0.6330777332676719 | 5000 | collapse_probability = 3.7729 + -3.8798 * capacity_slack + 0.0165 * routing_entropy | 83 | fragility |
| collapse_probability | utilization+capacity_slack | multivariate_linear | 2.5686460956331616 | 1.2360552262510012 | -1.332590869382157 | 0.6330410431558149 | 5000 | collapse_probability = 1.2361 + 2.5686 * utilization + -1.3326 * capacity_slack | 79 | fragility |

### Heavy-Tail Evidence

| topology_type | topology_label | best_model | sample_size | alpha | log_likelihood_gap |
| --- | --- | --- | --- | --- | --- |
| market_microstructure | Market Microstructure | lognormal | 1000 | 1.472680649195278 | 467.4057858616893 |
| hierarchical_supply | Hierarchical Supply | lognormal | 1000 | 1.5109513730225914 | 434.8113270148406 |
| random_queue | Random Queue | lognormal | 1000 | 1.784196207156078 | 294.72924046057915 |
| small_world | Small-World | lognormal | 1000 | 1.6095585537903299 | 214.32966778204946 |
| scale_free | Scale-Free | lognormal | 998 | 1.840399592603935 | 129.07076545182554 |

### Early-Warning Separation

| metric | collapse_mean | stable_mean | fragile_mean | robust_mean | separation |
| --- | --- | --- | --- | --- | --- |
| variance_increase | 4535714.467388355 | 4147499.104934355 | 4573395.478210464 | 4101277.356138257 | 388215.3624540004 |
| recovery_lag | 3.3879345603271984 | 2.9113502935420743 | 3.22452 | 3.06428 | 0.4765842667851241 |
| autocorrelation_increase | -0.025525990241514966 | -0.018156768941789758 | -0.02247434167121234 | -0.021046294643498432 | -0.007369221299725209 |

## Key Findings

- Across 5,000 synthetic systems spanning 5 topology families, collapse risk rises sharply in a shared utilization band centered near 0.152, with the middle 50% of per-topology thresholds lying between 0.097 and 0.186.
- The transition is not identical across domains, but the threshold spread remains compact at 0.140 utilization points, which is consistent with a common collapse-onset regime rather than unrelated topology-specific behavior.
- Utilization is the dominant driver, while secondary structural variables such as capacity_slack, baseline_utilization, routing_entropy, average_degree materially shift how fast collapse accelerates near the threshold.
- Early-warning signals are shared across domains: collapse cases show about 1.09x higher variance growth and 1.16x longer recovery lag than stable cases.
- Cascade tails are broadly heavy-tailed, but in this run a lognormal tail model consistently fits better than a strict power law, suggesting multiplicative cascade growth rather than a single universal power-law exponent.
- The strongest interpretable law candidate from this run is: collapse_probability = -0.1795 + 3.9192 * utilization + 0.2942 * centralization_index.

## Figure Set

- `figures/collapse_probability_vs_utilization_overlay.png`: Collapse probability vs utilization with all topology families overlaid.
- `figures/fragility_heatmap_utilization_coupling.png`: Collapse risk heatmap across utilization and coupling bands.
- `figures/cascade_distribution_by_topology.png`: Cascade size survival curves on log-log axes by topology family.
- `figures/phase_transition_by_topology.png`: Per-topology collapse transition curves with estimated threshold markers.
- `figures/early_warning_signal_trends.png`: Shared early-warning signal trends across low- to high-fragility systems.
- `figures/feature_importance_and_laws.png`: Top collapse predictors alongside ranked symbolic/interpretable law candidates.
- `figures/healthcare_case_baseline_vs_collapse_vs_intervention.png`: Healthcare case study: baseline, collapse, and optimized response traces.
- `figures/flagship_main_result.png`: Multi-panel summary figure suitable for README or paper intro.

## Case Study Layer

- Healthcare case workspace: `runs\flagship_healthcare_case_workspace\2026-03-17_194529_994433_flagship_healthcare_case_study_batch`
- Baseline run: `runs\flagship_healthcare_case_workspace\2026-03-17_194529_994433_flagship_healthcare_case_study_batch\healthcare_baseline\2026-03-17_194530_013595_ed_basic_run`
- Collapse run: `runs\flagship_healthcare_case_workspace\2026-03-17_194529_994433_flagship_healthcare_case_study_batch\healthcare_worst_case\2026-03-17_194530_807946_ed_basic_worst_case`
- Optimized run: `runs\flagship_healthcare_case_workspace\2026-03-17_194529_994433_flagship_healthcare_case_study_batch\healthcare_optimize\2026-03-17_194532_747615_ed_basic_optimize`

## Limitations

- This study uses synthetic families plus one illustrative authored domain case, so the core claim is about structural regularities rather than calibrated forecasts for a specific real system.
- Utilization is the clearest universal driver in this run; coupling behaves more as a structural modifier than a stand-alone universal threshold axis.
- The heavy-tail evidence is strong and suggestive, but still coarse rather than a final statistical proof.

## Next Steps

- Repeat the study on larger networks and longer horizons.
- Add calibrated real-world parameterizations for healthcare, supply chains, and markets.
- Test whether the same transition band persists under domain-calibrated generators.