# StressLab Master Narrative

## What StressLab Is

StressLab is an open-source research and decision platform for systemic fragility. It models queue, flow, and dependency networks, stresses them under realistic disruptions, and measures how collapse emerges, propagates, and can be mitigated.

The project began as a resilience-testing engine. It is now also a discovery engine: a way to generate large families of synthetic systems, run controlled stress campaigns across them, and search for general laws of collapse rather than only studying one handcrafted scenario at a time.

## Why This Problem Matters

Hospitals, supply chains, logistics networks, and fragmented markets all fail through a related set of mechanisms. Demand rises, capacity saturates, buffers deplete, routing options narrow, and local overload becomes network-wide damage. Teams often talk about those systems as if they are domain-specific and incomparable. The core question behind StressLab is whether that is actually true.

If the same collapse dynamics recur across very different systems, then resilience planning can move from anecdotal scenario analysis toward something closer to a scientific discipline. That is the ambition behind the work.

## What We Tested

StressLab ran two connected studies.

### Study 1: Cross-Domain Flagship Discovery

- 5,000 synthetic systems
- 5 topology families
- 1,000 systems each for random queue, scale-free, small-world, hierarchical supply, and market microstructure networks
- Baseline simulation, minimum-shock failure search, worst-case search, collapse metric extraction, theory analysis, and research reporting for every system

The flagship study asked whether very different queue-flow-dependency systems show a shared collapse onset band as utilization and coupling rise, and whether early warning signals generalize across topology families.

### Study 2: Controlled Threshold Follow-Up

- 2,700 fixed-size synthetic systems
- 144 healthcare family variants
- Fixed-size factorial sweep over utilization and coupling
- Healthcare referral-family validation sweep over arrival intensity and coupling modes

The follow-up study tested the hardest part of the flagship claim: whether coupling meaningfully moves the threshold itself, or whether utilization is the primary driver and coupling mostly changes how much disturbance the system can absorb before failing.

## The Flagship Result

The flagship study found a clear shared collapse transition band across topology families. Collapse risk accelerated sharply once baseline utilization entered roughly the 0.10 to 0.19 range, with a median estimated threshold of 0.152 across the five synthetic families.

That result matters because the families were structurally different. Scale-free graphs reached their critical point earliest, market microstructure graphs latest, and the others fell between them. Even with that variation, the threshold spread remained compact enough to support a common utilization-led collapse regime rather than five unrelated topology-specific stories.

The same run also showed shared early warning structure. Collapse cases exhibited about 1.09x higher variance growth and 1.16x longer recovery lag than stable cases. Cascade tails were clearly heavy-tailed, but the best coarse fit was lognormal rather than strict power law, which points toward multiplicative cascade growth rather than a universal single exponent.

## How the Follow-Up Sharpened the Claim

The flagship result could still be misread as "utilization and coupling jointly define one universal threshold." The controlled follow-up made that claim more precise.

In the controlled sweep, the threshold stayed primarily utilization-led. Higher coupling shifted the critical point only modestly on average: 0.008 utilization points between high and low coupling regimes, with the largest absolute shift at 0.023.

But coupling still mattered operationally. Across the controlled synthetic grid, higher coupling reduced the minimum shock-to-failure margin by about 39.2% on average. In plain terms, tighter coupling did not move the cliff very far, but it made systems easier to push over once they were near it.

That distinction is important. It changes the interpretation from "coupling determines where collapse starts" to "utilization determines where collapse starts, while coupling determines how forgiving the system is once it is close."

## The Final Claim

Across domains, collapse thresholds are primarily utilization-led; coupling mainly narrows the failure margin rather than moving the threshold much.

That is the strongest defensible claim supported by both studies together.

## Why It Matters for Real Systems

This result is practical, not just theoretical.

- For operators, it suggests that the first-order question is how close the system is to its utilization cliff.
- For planners, it suggests that redundancy, rerouting, and decoupling matter because they preserve shock margin, not because they necessarily relocate the threshold by a large amount.
- For monitoring, it suggests that variance growth and recovery lag are more portable early-warning signals than any single domain-specific rule of thumb.

The healthcare family validation makes the synthetic result easier to trust. In that family, collapse turned on around a 0.98x arrival multiplier and was essentially saturated by 1.20x. The operational units differ, but the same story appears: a narrow transition, a visible cliff, and warning signals that sharpen before failure.

## Limitations

- The strongest result is cross-domain and structural, not a calibrated forecast for a specific real organization.
- The synthetic generators are broad and useful, but still stylized.
- Heavy-tail evidence is strong and consistent, but the current result favors lognormal tails over a final universal power-law claim.
- Coupling was studied in an interpretable way, not exhaustively. There are richer notions of coupling than the single operational measure used here.

## Why This Is a Meaningful Research Result

The studies do not show that every network collapses at exactly the same utilization. They show something more credible and more useful: very different network families appear to share a narrow collapse-onset regime, and the main axis of that regime is utilization, not arbitrary domain detail.

That is a meaningful scientific and engineering claim. It is strong enough to anchor the public narrative of the repository, strong enough for a portfolio centerpiece, and strong enough to motivate a more formal paper.

## Next Research Step

The next step should be a calibrated extension, not another broad synthetic sweep. The most valuable follow-up would be one real domain family with externally grounded parameters, plus a controlled intervention study that tests whether maintaining shock margin below the utilization cliff outperforms threshold-shifting strategies in practice.
