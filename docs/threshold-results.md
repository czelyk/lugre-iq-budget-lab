# Frozen-threshold replay on unused LuGRE captures

**Decision.** At a 960,000-byte payload allowance, the lossless and low-bit policies preserved a matched weak orbit signal on OP32. Lossless and reduced bit depth tied on all tested targets. Only one of the three primary captures showed any difference between policies. The result supports a narrow case study and leaves the recorder policy open.

## Experiment

Four earlier recordings supplied 32 shuffled-code maxima. Each maximum includes all four policies and both time offsets. The threshold was frozen at **3.4896763658910444** on the duration-adjusted score before scoring held-out targets. None of the 16 new shuffled-code maxima on the held-out captures exceeded the cutoff. These are correlated surrogate trials on four captures. They give no operational false-alarm rate.

A target counted only when the same policy passed the frozen threshold and matched the external Doppler and code delay at both 0 and 5 ms offsets. Both offsets used an equal number of complete coherent blocks within each policy. The budgets apply to encoded I/Q payload bytes. Packet headers, codec throughput, and receiver tracking are outside the experiment.

| Held-out capture | GPS PRN | Raw | Lossless | Low bit depth | Low sample rate |
| --- | ---: | --- | --- | --- | --- |
| OP32, lunar orbit | 6 | Miss | Pass | Pass | Miss |
| OP74, lunar surface | 31 | Pass | Pass | Pass | Pass |
| OP78_0, lunar surface | 12 | Pass | Pass | Pass | Pass |
| OP77_1, exploratory surface | 6 | Miss | Miss | Miss | Miss |
| OP77_1, exploratory surface | 14 | Pass | Pass | Pass | Pass |

On OP32, both successful encodings returned **−5,150 Hz** and code phase **1,374–1,375 samples** at 4 Msps. The lossless payload was 951,014 bytes for 180 ms. The 240 ms low-bit payload used 960,000 bytes. The two misses still found the same external peak in the code/Doppler search. Their scores fell below the frozen threshold. The low-rate policy delivered 240 ms and still missed. This shows that added duration alone did not determine the result in this recording.

| OP32 policy | Payload bytes | Recorded ms | Score at 0 ms | Score at 5 ms |
| --- | ---: | ---: | ---: | ---: |
| Raw | 960,000 | 120 | 0.000 | 0.362 |
| Lossless | 951,014 | 180 | 3.640 | 3.779 |
| Low bit depth | 960,000 | 240 | 4.565 | 7.500 |
| Low sample rate | 960,000 | 240 | 2.819 | 3.256 |

## Limits and decision

The two passing OP32 treatments share a positive result and differ in recording length, quantization and subsequent processing. The experiment compares complete policies. It cannot attribute the difference to a single parameter. Neither candidate encoding recovered a target that the other missed. The exploratory OP77_1 PRN 6 miss represents an evaluated weak target, with the external author's weaker evidence retained in the [protocol](threshold-protocol.md). Five targets across four captures cannot settle generalization.

This satisfies the next held-out replay step. It does not satisfy the planned repeatability criterion across more than one primary capture. A further test that could change the decision would compare lossless and low-bit at several preassigned budgets against a tracking or sustained-correlation endpoint on additional independent recordings. If suitable ground truth is unavailable, fixture development alone would leave the ambiguity open.

## Reproduction and provenance

- [Frozen protocol](threshold-protocol.md) · [Calibration score and fingerprint](../results/threshold/frozen_threshold.json) · [All calibration scores](../results/threshold/calibration_scores.csv)
- [All validation scores](../results/threshold/validation_scores.csv) · [Target decisions](../results/threshold/target_decisions.csv) · [Held-out decoy maxima](../results/threshold/validation_decoy_maxima.csv)
- The full run used CuPy 14.2.0, CUDA 12.8 component wheels, Python 3.12.10, NumPy 2.4.6 and SciPy 1.18.0. An independent CPU evaluation of all 32 calibration maxima produced the same threshold. The largest absolute score difference was 0.00000629. [CPU maxima](../results/threshold/cpu_calibration_decoy_maxima.csv)
- External reference for each acquisition. [OP32/G06](https://destevez.net/wp-content/uploads/2025/12/OP32_G06.png) · [OP74/G31](https://destevez.net/wp-content/uploads/2025/12/OP74_G31.png) · [OP78_0/G12](https://destevez.net/wp-content/uploads/2025/12/OP78_0_G12.png) · [OP77_1/G06](https://destevez.net/wp-content/uploads/2025/12/OP77_1_G06.png) · [OP77_1/G14](https://destevez.net/wp-content/uploads/2025/12/OP77_1_G14.png) · [Source analysis](https://destevez.net/2025/12/first-analysis-of-the-lunar-gnss-receiver-experiment-data/)
