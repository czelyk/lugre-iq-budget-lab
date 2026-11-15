# Pocket SDR acquisition replay

**Decision.** Keep OP76 as a sensitivity case. The lossless-only threshold crossing does not meet the independent protocol's robustness condition. Keep the recorder policy undecided.

The main case is OP76_0, at 960 ms, GPS PRN 32. The source capture, payload budget (1,670,310 bytes), and three recording policies match the pilot. The replay compresses and decompresses the lossless prefix and packs and unpacks the reduced-bit-depth and reduced-rate samples. It uses the original 8 Msps archive and a shared 4 Msps ground interface.

## Recorded outcomes

| Policy, GPS 32 | Packed bytes | Record length | Ratio to nominal threshold, group start 0 ms | Group start 5 ms |
| --- | ---: | ---: | ---: | ---: |
| Lossless | 1,670,310 | 320 ms | 1.0516, matched | 0.9354, matched |
| Low bit depth | 1,640,000 | 410 ms | 0.9463, matched | 0.9541, matched |
| Lower sample rate | 1,640,000 | 410 ms | 0.9365, matched | 0.9955, unmatched |

These ratios use Pocket SDR's C/A replica and FFT kernels with the pilot's per-Doppler-row normalization. The matched GPS 32 peak is 3,400 Hz at sample 760. The original lossless-only pass reproduced at the original grouping. Shifting the grouping and discarding incomplete blocks brought the lossless score below the threshold. A separate equal-dwell check kept 31 complete 10 ms blocks at both offsets. Both fell below the nominal threshold, with the same matched peak. The zero-offset 31-block value rounds to 1.000 at three decimals, but it is below the cutoff in the raw CSV.

The normalized replay found GPS 18 in the commissioning control and GPS 31 in every surface policy at both offsets. In OP23, lossless and both lossy policies gave matched passes for GPS 21 at 480 kB. The 60 ms raw option gave a matching peak below threshold. The conjugate-reversal control gave unmatched peaks below the threshold with row normalization. Conjugate reversal is an engineering check for this matched C/A alignment. It is not representative noise for false-alarm calibration.

The separately recorded, unmodified Pocket SDR executable is a stock 1 ms coherent diagnostic. It located GPS 18 in commissioning and the positive-control GPS 31 in the surface policies. It did not match the reference for weak GPS 32. The planned whole-grid normalization of the high-sensitivity harness also picked an incorrect frequency for the commissioning control. Its nominal passes therefore cannot establish the recording-policy decision. After observing that failure, the per-row version was executed as a sensitivity analysis, keeping both outputs. A 5 ms grouping shift had already been fixed in the [protocol](independent-protocol.md). The equal-dwell check was added to separate grouping changes from the number of complete blocks.

## Interpretation

Under one coherent grouping, a true peak can be reproduced across independent C/A and FFT implementations. Its pass/fail at the 1.67 MB budget is sensitive to the coherently processed portion and to the detector. Claiming a robust lossless advantage from this cut would overstate the evidence. The full receiver remains a separate comparison, and the same capture was reused. The threshold is theoretical and none of these tests measures tracking lock or an empirical false-alarm rate.

The next decision-changing result would hold the detector and its empirical false-alarm threshold fixed, then compare multiple withheld LuGRE captures against independent PRN/frequency references. The question is whether a codec changes a repeatable, externally matched acquisition or tracking result at equal bytes. Hardware throughput becomes relevant once that choice has support.

## Reproduction and outputs

- [Original protocol](independent-protocol.md)
- [Whole-grid table](../results/independent/acquisition.csv) and [stock CLI output](../results/independent/pocket_acq.log)
- [Per-row table](../results/independent/row-normalized/acquisition.csv)
- [Equal-dwell comparison](../results/independent/equal-dwell/acquisition.csv)
- [Original boundary observation](../results/pilot/op76_equal_boundary.csv)
- Environment: Windows, Python 3.12.10, NumPy 2.4.6, SciPy 1.18.0. Pocket SDR executable 0.22. Source revision 23c91c732365a3668d303656de95a36e7604b58a. The high-sensitivity experiment uses the upstream Python FFT path. [Pocket SDR](https://github.com/tomojitakasu/PocketSDR/tree/23c91c732365a3668d303656de95a36e7604b58a)
