# Additional LuGRE tracking replay

The frozen comparison found zero operations with additional continuous
passing windows supported by the full-resolution replay at any budget.
At 960 kB, one window common to both compressed policies passed in the
lossless and full-resolution streams and failed in the low-bit stream.
[Frozen protocol](tracking-recheck-protocol.md)

## Initial consecutive passing time

Each cell is in milliseconds after the 10 ms warm-up. The two compressed
policies had the same initial time at each of the three tested allowances.

| Operation and signal | Full 240 ms reference | Raw 480 / 720 / 960 kB | Lossless at all allowances | Two-bit at all allowances |
| --- | ---: | ---: | ---: | ---: |
| OP23_0 GPS 21 | 80 | 40 / 40 / 80 | 80 | 80 |
| OP76_0 GPS 32 from offset 960 ms | 40 | 40 / 40 / 40 | 40 | 40 |
| OP77_1 GPS 6 | 80 | 40 / 40 / 80 | 80 | 80 |
| OP77_1 GPS 14 | 0 | 0 / 0 / 0 | 0 | 0 |

At 960 kB OP76 used 180 ms in 939,527 lossless bytes and 240 ms in
960,000 low-bit bytes. At the 90 ms window the full and lossless scores
both reached 2.2181. The low-bit score reached 1.6670, below the
frozen 1.8853 cutoff. All three met the code and frequency guards there.
The window follows an interruption in the initial passing run, so it is
a loss in the common horizon with no change to initial continuity.
OP77 GPS 14 had a previously supported acquisition peak, but the
full-resolution seeded replay failed the initial tracking criterion.
The endpoint therefore supplies no useful evidence about encoding for
this target.

None of eight new signal-absent synthetic captures passed the first
window or reached 80 ms continuity under any tested policy or with
the full reference. These eight captures supply a control check. A
field false-alarm rate would require a representative independent corpus.

## Scope of the decision

The run excludes missing tracker outputs from passing windows. It
defines the common horizon from the stored record lengths so that a
tracker drop cannot masquerade as extra capture time. Added continuity
must lie within the initial passing run of both the low-bit and full
reference streams.

The follow-on gate failed at all three budgets. Against lossless zlib,
these replays provide no reason to prefer low-bit recording for the
seeded 80 ms criterion. The earlier longer-capture benefit on OP74
and OP78 remains an observation on those recordings. Four target
replays in three previously examined archive operations provide limited
coverage. The full-resolution replay uses the same receiver and
published peak seeds, so it provides an internal comparison. Independent
acquisition, carrier lock, and mission-level navigation remain outside
the measured endpoint.

## Reproduce

```sh
python tools/fetch_inputs.py
python experiments/tracking_recheck.py --check
```

The original cutoff is pinned by the feedback replay fingerprint.
Fresh outputs go under `results/local/tracking-recheck/`. The check
compares the reported metrics and LF-normalized CSV evidence against the
recorded run. [All windows](../results/tracking-recheck/windows.csv) ·
[Policy outcomes](../results/tracking-recheck/policies.csv) ·
[Paired outcomes](../results/tracking-recheck/pairs.csv) ·
[Summary and input identities](../results/tracking-recheck/summary.json)
