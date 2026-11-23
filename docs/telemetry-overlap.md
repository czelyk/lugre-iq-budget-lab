# Can LuGRE flight telemetry validate snapshot Doppler?

The tracking recheck found no extra initial continuity for two-bit recording over lossless zlib. The remaining decision was whether longer two-bit captures produce more usable GPS L1 C/A Doppler measurements at the same byte budget. Before processing either format again, this audit checked for independent onboard Doppler during the I/Q captures.

## Method

The audit used the publisher's verified LuGRE.zip archive (Zenodo v1). It read the start time, sample count, and sample rate from each L1 I/Q packet header. The SDRX start time agreed with the binary to within 0.876 ms on all 20 captures. OP40_0 has 300 ms in its binary filename and 400 ms in its SDRX filename. The binary header specifies 3,200,329 samples at 8 MHz, so the audit uses a duration of approximately 400.041 ms.

The audit searched all 21 TLM_RAW text products across the mission. It checked the first timestamp of each text product against the paired binary. The receiver interface document in the archive identifies rxTime as GPS time during the mission, signalId 0 as GPS L1 C/A, and fdRaw as the tracking-loop Doppler in Hz. Both packet timestamps and telemetry epochs were converted to UTC with the 18 s GPS–UTC offset for the mission dates.

The primary test requires a telemetry timestamp in the half-open I/Q interval. As a sensitivity check, the audit also searched one full published RAW cadence (1 s) before and after each interval. That wider search checks for nearby context. It cannot independently validate a subsecond Doppler estimate. For the four latest replay targets, the search also required the same GPS PRN and used the exact 240 ms replay intervals.

[LuGRE data archive, product handbook and receiver interface document](https://zenodo.org/records/16411687) · [NASA summary of the data products and cadence](https://www.gps.gov/sites/default/files/2026-04/Parker%202026-04_CGSIC_NASA_v1.0.pdf)

## Result

Across 355,206 RAW message epochs, 189,917 contained at least one GPS L1 C/A measurement. None of the 20 L1 I/Q captures contained a RAW epoch or had one within 1 s. The closest was OP22_0, with a GPS L1 C/A measurement epoch 140.868 s before the start of the I/Q capture. The search covered all RAW products, including those from other operation IDs.

| Replay target | Closest same-PRN RAW measurement relative to the replay window | Source operation |
| --- | ---: | --- |
| OP23_0, GPS 21 | 19 days 22 h 54 min before | OP9_0 |
| OP76_0, GPS 32 | 29 min 22 s after | OP76_0 |
| OP77_1, GPS 6 | 11 h 22 min 29 s before | OP76_0 |
| OP77_1, GPS 14 | 12 h 7 min 44 s before | OP76_0 |

The public erratum for OP23_0 corrects the apparent overlap in the archived operation table. In the actual TLM_RAW file the last message is 141.595 s before the I/Q capture. The nearest RAW epoch with any GPS L1 C/A measurement is approximately 771 s before it. [Published erratum](https://zenodo.org/records/16411687) · [Recorded audit output](../results/telemetry-overlap/overlap.json)

## Decision

Close the two-bit-versus-lossless superiority claim as an IAC candidate on this evidence. A different-epoch measurement reflects changing satellite geometry and receiver conditions. An ephemeris and spacecraft trajectory can produce a geometric Doppler prediction, as the LuGRE snapshot study already demonstrated. It cannot independently show that a specific weak signal was tracked during the capture. Full-resolution replay remains a useful paired control, with the same signal realization and receiver algorithm. The earlier replay using that control provided no extra initial continuity for two-bit recording.

The Doppler pilot therefore did not run and the audit places no new bound on Doppler error. New work on this hypothesis would require independently labelled, time-aligned captures or a controlled recording with known input Doppler.

[LuGRE snapshot study, Section III-D](https://arxiv.org/html/2601.06081v2#S3.SS4) · [Additional tracking replay](tracking-recheck-results.md)

## Reproduce

Run with Python 3.12 from the repository root. The script uses the standard library and verifies the public archive checksum. It reuses the local ZIP or downloads it if absent.

```sh
python experiments/telemetry_overlap.py --check
```
