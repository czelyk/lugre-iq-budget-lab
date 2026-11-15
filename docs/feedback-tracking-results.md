# Centered Pocket SDR feedback replay

[Issue #2](https://github.com/czelyk/lugre-iq-budget-lab/issues/2) · [Frozen protocol](feedback-tracking-protocol.md)

The same first-10-ms I/Q mean removal was applied to each full decoded record. A published code/Doppler seed handed each stream to the pinned Pocket SDR Python channel. Carrier and code were updated by the stock FLL/DLL at one millisecond intervals. A separately measured correlation and guard criterion scored each 40 ms window. All prefixes kept the channel in the FLL pull-in interval. The code supplies a navigation initialization shim because navigation decoding is outside the experiment and the available Windows Python environment did not load the native FEC dependency. The replay exercised the NumPy correlator fallback.

## Flight results

The first scored 40 ms passed in **four of five captures for all three policies at every budget**. OP21 failed this first window across the three policies, even where some later windows passed. The fixed-horizon result was identical across lossless and low bit depth after equal centering.

At 960 kB, the initial consecutive time satisfying the criterion was:

| Flight recording | Raw | Lossless | Low bit depth |
| --- | ---: | ---: | ---: |
| OP32 GPS 6, lunar orbit | 80 ms | 120 ms | 120 ms |
| OP74 GPS 31, lunar surface | 80 ms | 160 ms | 200 ms |
| OP78 GPS 12, lunar surface | 80 ms | 160 ms | 200 ms |
| OP21 GPS 24, transfer | 0 ms | 0 ms | 0 ms |
| OP22 GPS 31, transfer | 40 ms | 40 ms | 40 ms |

OP74 and OP78 scored above the criterion in every complete window available to the lossless and low-bit records. In each of those two captures, the 40 ms difference at 960 kB came from the extra window made available by the longer prefix. On OP32 the extra low-bit record at 960 kB included a later passing window after an interruption. The initial consecutive duration stayed at 120 ms. On OP22 the common DC procedure reproduced the first-window parity.

[All policy results](../results/feedback-tracking/evaluation_summary.csv) · [All window measurements](../results/feedback-tracking/evaluation_windows.csv)

## Control results

- Sixteen noise-only calibration captures fixed the ratio cutoff at **1.8853240013**. In the eight disjoint synthetic noise captures, one passed the first 40 ms in some policy/budget cases and another passed a later isolated window. None sustained 80 ms from the start. Multiple policies and budgets reuse each waveform, so the counts are per capture. They establish neither a field false-alarm rate nor a reliable 40 ms lock declaration.
- All 27 policy/budget runs of the three signal-present controls passed the first window. On the corrected +500 Hz/s control, the 960 kB low-bit run passed every complete window after the excluded first 10 ms, for 200 ms total. In the final 170–210 ms window, the feedback estimated the known Doppler with **24.11 Hz** mean absolute error. Holding the initial seed would yield **94.75 Hz**. The separate fixed-frequency run also retained correlation in this synthetic waveform, so carrier-error improvement should not be read as unique lock retention.
- The first attempt at the ramp fixture used a linear phase exponent and thereby injected a *constant* +250 Hz offset. Its comparisons against ramp truth were invalid. The fixture was corrected to use a quadratic phase ramp and both frozen stages were rerun. The erroneous frequency-error columns are omitted from the retained diagnostic rows. The direct known-phase correlator independently checks the waveform without receiver feedback.

[Cutoff and calibration identity](../results/feedback-tracking/cutoff.json) · [Corrected ramp audit](../results/feedback-tracking/ramp_audit.csv) · [Discarded fixture diagnostics](../results/feedback-tracking/discarded_constant_offset_windows.csv)

## Decision

The additional low-bit observations passed the feedback criterion on the two stronger lunar-surface captures. The first common window stayed tied on all five captures, and extra low-bit samples did not extend the uninterrupted result on the weaker OP32 capture at 960 kB. A 40 ms pass still occurred in one noise-only control. This supports a bounded observation-length benefit, while leaving codec selection and a flight-tracker lock claim open. Independent lock evidence and a larger negative-control set would be necessary to use this endpoint for a hardware comparison.

Python 3.12.10, NumPy 2.4.6, SciPy 1.18.0, pinned Pocket SDR revision 23c91c732365a3668d303656de95a36e7604b58a. Download integrity is documented with the [LuGRE dataset instructions](../data/README.md).
