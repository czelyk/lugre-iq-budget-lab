# Tracking replay on additional LuGRE recordings

Test three archive operations absent from the centered feedback experiment.
These operations were already examined in acquisition work. Their feedback
outcomes are new, while the recordings are familiar.

| Operation | Origin within capture | GPS PRN | External Doppler (Hz) | Code offset at 4 Msps |
| --- | ---: | ---: | ---: | ---: |
| OP23_0 | 0 ms | 21 | 6150 | 1445 |
| OP76_0 | 960 ms | 32 | 3400 | 760 |
| OP77_1 | 0 ms | 6 | 20 | 3390 |
| OP77_1 | 0 ms | 14 | 5260 | 2419 |

Reuse the external seeds from the [independent acquisition protocol](independent-protocol.md)
and [threshold protocol](threshold-protocol.md). OP77_1 supplies two targets in
one capture, with weaker prior evidence for PRN 6. Do not search or tune the
seeds after evaluation. Treat the independent CAF peaks as acquisition evidence.
They do not supply continuous tracking truth.

Give raw, lossless zlib and two-bit I/Q the existing payload allowances of
480,000, 720,000 and 960,000 bytes. Reuse the original packed encoders,
prefix rounding, resampling, DC estimate, seeded FLL/DLL feedback channel
and correlation guards. Pin the previous calibration by its existing
fingerprint. Evaluate the full unmodified 240 ms segment as a reference
at the same seed, outside the byte-budget comparison. Run eight new
signal-absent synthetic captures with seeds 9100 through 9107 at all
allowances and at full length. The calibration and detector stay frozen.

An experimental continuity result requires two consecutive passing 40 ms
windows starting at 10 ms. A supported added window must also pass in the
full-resolution reference at the corresponding time. Report each policy's
first-window result, initial consecutive passing time, and any window where
low-bit and lossless disagree within their common observation horizon.
An extra passing window with equivalent common windows demonstrates a
benefit from longer capture duration. This cannot establish independent
lock, position or a field false-alarm rate.

To support follow-on work, require full-reference-supported extra
continuity on at least two distinct operations at the same allowance,
with no loss of a full-reference-supported passing common window at that
allowance and no false 80 ms continuity in the new controls. Count
operations, rather than PRNs or repeated allowances, as distinct
recordings. Report the observations even if this gate fails.

[LuGRE archive](https://zenodo.org/records/16411687) ·
[External peak analysis](https://destevez.net/2025/12/first-analysis-of-the-lunar-gnss-receiver-experiment-data/)
