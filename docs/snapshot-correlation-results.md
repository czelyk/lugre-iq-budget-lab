# Sustained I/Q correlation after a reference-aided handoff

[Issue #1](https://github.com/czelyk/lugre-iq-budget-lab/issues/1) · [Frozen protocol](snapshot-correlation-protocol.md)

The pilot compared the same capture prefix at each of three packed I/Q payload allowances. The score asks whether consecutive 20 ms windows keep a strong local correlation near an independent code/Doppler seed. Each window repeats a bounded local search. The experiment does not exercise receiver feedback loops, navigation-data decoding, or unaided acquisition.

## Recorded result

The 16 synthetic null recordings fixed the cutoff at **4.2167286873**. Both signal-present controls passed the 40 ms common horizon in every policy/budget combination (18/18). In the separate eight-record null audit, one noise-only recording crossed the cutoff for an isolated 20 ms window. None passed two consecutive windows at the start of the test horizon. These synthetic controls give a sanity check on the endpoint, with no measured field false-alarm rate.

At 960 kB, the initial consecutive passing duration after the excluded first 20 ms was:

| Capture | Raw | Lossless | Low bit depth |
| --- | ---: | ---: | ---: |
| OP21 GPS 24, transfer | 100 ms | 180 ms | 220 ms |
| OP22 GPS 31, transfer | 0 ms | 0 ms | 220 ms |
| OP32 GPS 6, lunar orbit | 0 ms | 0 ms | 20 ms |
| OP74 GPS 31, lunar surface | 100 ms | 160 ms | 220 ms |
| OP78 GPS 12, lunar surface | 100 ms | 160 ms | 220 ms |

At 480 and 720 kB, the same qualitative pattern held. In OP21, OP74, and OP78, all three policies passed the common 40 ms horizon and all complete windows available to them kept passing. The duration differences on those captures came from how much of the prefix fit in the byte allowance. OP32 never passed the common horizon under any policy. Its single 20 ms result deserves the same caution as an isolated noise score.

[All window scores](../results/snapshot-correlation/evaluation_windows.csv) · [Policy outcomes across all budgets](../results/snapshot-correlation/evaluation_summary.csv) · [Calibrated cutoff](../results/snapshot-correlation/cutoff.json)

## Equal-duration DC diagnostic

The uncentered OP22 short-horizon result also changed between policies, even with the same time interval. A follow-up compared identical 60 ms prefixes. Estimate the complex mean from the first 10 ms of each decoded stream, subtract it, then rescore the 20 and 40 ms starting windows with the same cutoff. This diagnostic was added after the main results and kept separate.

| OP22 input | Score at 20 ms start | Score at 40 ms start | Both pass |
| --- | ---: | ---: | --- |
| Lossless, uncentered | 2.520 | 7.256 | No |
| Lossless, centered | 13.456 | 14.530 | Yes |
| Low bit depth, uncentered | 13.271 | 14.167 | Yes |
| Low bit depth, centered | 13.199 | 14.259 | Yes |

The lossless OP22 early-horizon result became equivalent by the binary endpoint after a simple receive-side correction. Neither OP32 path passed both windows in the diagnostic. The same eight noise controls were repeated on the 60 ms interval. None passed the two-window check in either centering setting. The cutoff is inherited from the frozen experiment. This follow-up does not calibrate real RF interference.

**Decision.** Reduced bit depth retained more usable time at equal bytes in the current replay. The difference in passing duration on three captures follows from record length, while the apparent short-horizon improvement on OP22 depends on receiver preprocessing. These data support longer-record utility in the tested captures. A hardware choice would need a fair centered lossless comparison over the full recording and a receiver that actually maintains lock. The synthetic controls and single mission give limited evidence for rare false detections and generalization.

[Equal-duration diagnostic](../results/snapshot-correlation/centering_check.csv) · [External reference for OP22](https://destevez.net/wp-content/uploads/2025/12/OP22_G31.png)
