# StressLab Demo Talk Track

StressLab is an open-source lab for systemic fragility in queue, flow, and dependency networks. The short story is that we used it to test 5,000 synthetic systems across five topology families and found a shared collapse transition band: once baseline utilization enters roughly the 0.10 to 0.19 range, collapse risk rises sharply across very different network classes.

The follow-up study matters because it makes that claim sharper. We held system size fixed, swept utilization and coupling in a controlled way, and found that coupling only shifts the threshold a little on average, but it cuts the failure margin a lot. So the clean takeaway is that collapse is primarily utilization-led, while coupling mostly determines how forgiving the system is once it is close to the cliff.

For the demo, I start with the main result figure, then the phase-transition and failure-margin figures, and then I switch to the healthcare case study to make the abstract result concrete. That sequence lets people see the science first, the operational meaning second, and the intervention story last.
