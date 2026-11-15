# LuGRE I/Q Budget Lab

A research prototype for comparing raw GNSS recording policies under the same downlink byte budget. It replays real L1 I/Q captures from NASA and ASI's Lunar GNSS Receiver Experiment (LuGRE) and measures whether quantization, reduced sample rate, or lossless encoding changes the ground receiver's GPS L1 C/A acquisition decision.

**Latest result:** At 960 kB, lossless and low-bit-depth recording both preserved a weak lunar-orbit target that the raw and lower-rate policies missed. The two leading policies tied on all five targets. Only one of three primary captures separated any policies. [Frozen-threshold results](docs/threshold-results.md)

[Previous Pocket SDR independent replay](docs/independent-replay.md)
The repository contains recorded pilot results and a follow-up acquisition replay using a pinned Pocket SDR revision. This is an offline, digital replay. It does not measure physical recorder throughput, RF re-quantization, navigation fixes, or flight readiness.

## Reproduce on Windows

Run these PowerShell commands from the project root with Python 3.12 and Git installed.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools/fetch_inputs.py
.\.venv\Scripts\python.exe -B experiments/pocketsdr_replay.py
```

The download is 256 MB for the public capture archive, plus an ignored Pocket SDR checkout. If the archive is already present, copy it to `data/NASA-LuGRE-16411687.zip` before running the fetch script. Generated outputs land in `results/local/independent`. Use `--case surface` for just the boundary experiment. The two diagnostics discussed in the follow-up can be reproduced separately:

```powershell
.\.venv\Scripts\python.exe -B experiments/pocketsdr_replay.py --statistic row --skip-stock --output results/local/row-normalized
.\.venv\Scripts\python.exe -B experiments/pocketsdr_replay.py --case surface --policy lossless --statistic row --equal-dwell --skip-stock --output results/local/equal-dwell
```

To repeat the original pilot without changing the recorded CSVs:

```powershell
New-Item -ItemType Directory -Force results/local/pilot | Out-Null
Push-Location results/local/pilot
try {
    & ../../../.venv/Scripts/python.exe -B ../../../experiments/pilot/pilot.py OP76_0 31 32
    & ../../../.venv/Scripts/python.exe -B ../../../experiments/pilot/matched.py OP76_0
    & ../../../.venv/Scripts/python.exe -B ../../../experiments/pilot/op76_equal_boundary.py
} finally {
    Pop-Location
}
```

## Reproduce the frozen-threshold comparison

Run calibration first and validation second in the same output directory. Use a fresh output directory for any detector or protocol change.

```powershell
.\.venv\Scripts\python.exe -B experiments/frozen_threshold.py calibration
.\.venv\Scripts\python.exe -B experiments/frozen_threshold.py validation
.\.venv\Scripts\python.exe -B tools/summarize_threshold.py results/local/threshold
```

The CPU is the default. The optional `--backend cuda` requires a working CuPy/CUDA installation and must be used for both stages. The threshold is based on shuffled-code surrogates in four calibration captures. [Protocol](docs/threshold-protocol.md)

## Repository map

| Path | Contents |
| --- | --- |
| [experiments/pilot](experiments/pilot) | Initial acquisition comparison, reference cuts and byte-budget checks |
| [experiments/pocketsdr_replay.py](experiments/pocketsdr_replay.py) | Packed policy replay using the stock Pocket SDR CLI and a separate high-sensitivity harness |
| [results/pilot](results/pilot) | Preserved CSV results from the initial investigation |
| [results/independent](results/independent) | Recorded CSV and stock receiver output from the follow-up |
| [results/threshold](results/threshold) | Frozen calibration, unused-capture replay, and wrong-code audit |
| [docs](docs) | Prior art, experiment design and interpretation |
| [data](data) | Source, license and archive integrity instructions |

## Sources

- Parker et al., *GNSS Reception at the Moon: First Results of the Lunar GNSS Receiver Experiment*. [Paper](https://doi.org/10.33012/NAVI.756)
- NASA and ASI, *Lunar GNSS Receiver Experiment (LuGRE) Mission Data*. [Dataset](https://zenodo.org/records/16411687)
- Sciacca et al., *First Multi-Constellation Observations of Navigation Satellite Signals in the Lunar Domain by Post-Processing L1/L5 IQ Snapshots*. [Open preprint](https://arxiv.org/html/2601.06081v2)
- T. Takasu, *Pocket SDR*. The checkout stays outside the tracked project and retains its upstream license. [Pinned source](https://github.com/tomojitakasu/PocketSDR/tree/23c91c732365a3668d303656de95a36e7604b58a)
