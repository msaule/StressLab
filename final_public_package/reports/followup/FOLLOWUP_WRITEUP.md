# Follow-up Study: Controlled Utilization-Coupling Sweep

## Abstract

In the controlled follow-up sweep over 2,700 fixed-size synthetic systems plus 144 healthcare variants, StressLab found that the collapse threshold stays primarily utilization-led, while higher coupling shifts it only modestly on average (0.008 utilization points) but reduces the shock margin to failure by about 39.2%.

## Design

- Synthetic controlled systems: `2,700`
- Healthcare validation variants: `144`
- Synthetic design held node count fixed and swept utilization targets plus coupling regimes.
- Healthcare design swept arrival intensity and dependency-routing coupling modes on the ED example family.

## Key Findings

- In the controlled synthetic study, the utilization threshold remains the main driver of collapse, with a median controlled threshold near 0.252.
- Changing coupling shifts the threshold, but only modestly on average: the mean high-minus-low coupling shift is 0.008 utilization points, with the largest absolute shift at 0.023.
- Higher coupling still matters operationally because it shrinks the minimum shock-to-failure margin by about 39.2% on average across the controlled synthetic grid.
- That follow-up result weakens any claim that raw coupling alone sets the universal threshold; coupling acts more like a modifier on a utilization-led transition and a reducer of failure margin.
- The healthcare validation family shows the same qualitative shape in operational terms: collapse turns on around a 0.98x arrival multiplier and is essentially saturated by 1.20x, which supports the portability of the utilization-threshold result beyond purely synthetic systems.

## Controlled Threshold Table

        topology_type        topology_label coupling_regime  critical_utilization  peak_slope  mean_collapse_probability              feature
  hierarchical_supply   Hierarchical Supply            high              0.300335    0.702000                   0.990942 baseline_utilization
  hierarchical_supply   Hierarchical Supply             low              0.298518    1.144623                   0.981884 baseline_utilization
  hierarchical_supply   Hierarchical Supply          medium              0.299785    0.651805                   0.990942 baseline_utilization
market_microstructure Market Microstructure            high              0.224785    3.710919                   0.949028 baseline_utilization
market_microstructure Market Microstructure             low              0.218241    2.772881                   0.939559 baseline_utilization
market_microstructure Market Microstructure          medium              0.224300    3.344989                   0.947052 baseline_utilization
         random_queue          Random Queue            high              0.312077    8.162967                   0.671525 baseline_utilization
         random_queue          Random Queue             low              0.289177    8.321307                   0.577652 baseline_utilization
         random_queue          Random Queue          medium              0.283908   11.551908                   0.655138 baseline_utilization
           scale_free            Scale-Free            high              0.222352    3.968597                   0.941041 baseline_utilization
           scale_free            Scale-Free             low              0.223129    4.762140                   0.935688 baseline_utilization
           scale_free            Scale-Free          medium              0.225859    3.619356                   0.939312 baseline_utilization
          small_world           Small-World            high              0.254477    8.817547                   0.833004 baseline_utilization
          small_world           Small-World             low              0.245826   11.230795                   0.805254 baseline_utilization
          small_world           Small-World          medium              0.251937   10.976767                   0.839015 baseline_utilization

## Healthcare Threshold Table

      topology_type       topology_label coupling_regime  critical_utilization  peak_slope  mean_collapse_probability     feature
healthcare_referral Healthcare ED Family            high                 0.975    3.333333                   0.694444 util_target
healthcare_referral Healthcare ED Family             low                 0.975    3.333333                   0.694444 util_target
healthcare_referral Healthcare ED Family          medium                 0.975    3.888889                   0.701389 util_target

## Threshold Shift Table

        topology_type        topology_label  low_threshold  medium_threshold  high_threshold  threshold_shift
           scale_free            Scale-Free       0.223129          0.225859        0.222352        -0.000778
  hierarchical_supply   Hierarchical Supply       0.298518          0.299785        0.300335         0.001816
market_microstructure Market Microstructure       0.218241          0.224300        0.224785         0.006544
          small_world           Small-World       0.245826          0.251937        0.254477         0.008650
         random_queue          Random Queue       0.289177          0.283908        0.312077         0.022900

## Failure Shock Margin Shift

        topology_type        topology_label  mean_pct_change_high_vs_low  median_low_budget  median_high_budget
  hierarchical_supply   Hierarchical Supply                    -0.921638           0.000000            0.000000
market_microstructure Market Microstructure                    -0.510785           0.000000            0.000000
           scale_free            Scale-Free                    -0.279359           0.055910            0.040342
         random_queue          Random Queue                    -0.260210           0.636697            0.445645
          small_world           Small-World                     0.011982           0.237774            0.212637

## Figures

- `figures/controlled_threshold_by_coupling.png`: Controlled synthetic collapse curves by topology and coupling regime.
- `figures/threshold_shift_by_coupling.png`: Estimated threshold shifts between low and high coupling regimes.
- `figures/failure_shock_budget_margin.png`: How higher coupling changes the minimum shock required to trigger failure.
- `figures/healthcare_family_threshold.png`: Healthcare ED family collapse curves under utilization and dependency coupling sweeps.
- `figures/followup_main_result.png`: Multi-panel summary of the controlled follow-up study.