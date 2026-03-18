# StressLab Master Key Findings

## Threshold Result

- Across 5,000 synthetic systems and five topology families, collapse risk accelerated sharply once baseline utilization entered a shared transition band around 0.10 to 0.19.
- The median estimated threshold across families was 0.152.
- The result varied by topology, but the band remained compact enough to support a common collapse-onset regime rather than five unrelated stories.

## Coupling Result

- The controlled follow-up sweep over 2,700 fixed-size synthetic systems showed that coupling only modestly shifts the threshold itself.
- The mean high-versus-low coupling threshold shift was 0.008 utilization points.
- The largest absolute threshold shift observed was 0.023 utilization points.
- Coupling mattered more as a failure-margin variable than as a threshold-placement variable.

## Early Warning Result

- Collapse cases showed about 1.09x higher variance growth than stable cases.
- Collapse cases showed about 1.16x longer recovery lag than stable cases.
- Autocorrelation was directionally interesting but less stable than variance growth and recovery lag.
- The most portable early-warning story in the current data is that systems become noisier and slower to recover before they fail.

## Cascade Tail Result

- Cascade sizes were clearly heavy-tailed across topology families.
- In coarse tail-model comparisons, lognormal fits outperformed strict power-law fits.
- The evidence supports multiplicative cascade growth, but not a strong claim that one universal power-law exponent governs all domains.

## Healthcare Validation Result

- In the healthcare follow-up family, collapse turned on around a 0.98x arrival multiplier.
- Collapse was effectively saturated by about 1.20x arrival intensity.
- That makes the synthetic result more believable operationally: the utilization cliff appears in a more intuitive, domain-readable setting too.

## Bottom Line

- Across domains, collapse thresholds are primarily utilization-led.
- Coupling mainly narrows the failure margin rather than moving the threshold much.
