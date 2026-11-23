"""Replay centered LuGRE I/Q through the stock Pocket SDR FLL/DLL feedback channel."""
import argparse
import csv
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import numpy as np

from snapshot_correlation import (
    CONTROL, FLIGHT, GPS_L1, INPUT_RATE, PERIOD, POCKET_COMMIT, RATE, ROOT,
    encoded_policies, pack_q4, read_capture, synthesize, unpack_q4,
)

OFFSETS = (-256, -160, -80, 80, 160, 256)
WARM_UP_MS = 10
WINDOW_MS = 40
RAMP_HZ_PER_S = 500


def tracking_library():
    upstream = ROOT / ".cache" / "PocketSDR"
    revision = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != POCKET_COMMIT:
        raise ValueError(f"Expected Pocket SDR {POCKET_COMMIT}, got {revision}")
    source = upstream / "python"
    sys.path.insert(0, str(source))
    import sdr_code

    navigation = ModuleType("sdr_nav")
    navigation.nav_new = lambda _options: SimpleNamespace()
    navigation.nav_init = lambda _navigation: None

    def reject_decode(_channel):
        raise RuntimeError("Navigation decoding is outside this short tracking replay")

    navigation.nav_decode = reject_decode
    spec = spec_from_file_location("pocket_tracking", source / "sdr_ch.py")
    tracker = module_from_spec(spec)
    # The stock tracking code only uses these three navigation methods.
    with patch.dict(sys.modules, {"sdr_nav": navigation}):
        spec.loader.exec_module(tracker)
    return tracker, sdr_code


def tracking_windows(tracker, ref, stream, ramp):
    stream = stream - np.mean(stream[:10 * PERIOD])
    channel = tracker.ch_new("L1CA", ref.prn, RATE, 0)
    first_off = len(channel.trk.pos)
    channel.trk.pos.extend(OFFSETS)
    tracker.start_track(channel, ref.doppler_hz, ref.delay_samples / RATE, 40.0)
    correlations, frequencies, phases = [], [], []
    for ms in range(len(stream) // PERIOD - 1):
        tracker.ch_update(channel, ms / 1000, stream, ms * PERIOD)
        if channel.state != "LOCK":
            break
        correlations.append(np.concatenate((channel.trk.C[:1], channel.trk.C[first_off:])))
        frequencies.append(channel.fd)
        phases.append(channel.coff * RATE)
    correlation = np.array(correlations)
    frequencies = np.array(frequencies)
    phases = np.array(phases)
    for start in range(WARM_UP_MS, len(correlations) - WINDOW_MS + 1, WINDOW_MS):
        stop = start + WINDOW_MS
        prompt_and_off = correlation[start:stop].reshape(8, 5, 1 + len(OFFSETS))
        energy = (np.abs(prompt_and_off.sum(axis=1)) ** 2).sum(axis=0)
        score = float(energy[0] / energy[1:].mean())
        epoch_seconds = np.arange(start, stop) / 1000
        fd = frequencies[start:stop]
        predicted_code = ref.delay_samples - RATE * ref.doppler_hz / GPS_L1 * epoch_seconds
        code_error = (phases[start:stop] - predicted_code + PERIOD / 2) % PERIOD - PERIOD / 2
        code_max = float(np.max(np.abs(code_error)))
        fd_max = float(np.max(np.abs(fd - ref.doppler_hz)))
        if ramp is None:
            mean_error, fixed_error = "", ""
        else:
            truth = CONTROL.doppler_hz + ramp * epoch_seconds
            mean_error = float(np.mean(np.abs(fd - truth)))
            fixed_error = float(np.mean(np.abs(ref.doppler_hz - truth)))
        yield start, score, int(code_max <= 8 and fd_max <= 500), float(np.median(fd)), (
            code_max
        ), fd_max, mean_error, fixed_error


def ramp_control(sdr_code):
    iq, _ = synthesize(sdr_code, 7202, 40)
    t = np.arange(len(iq)) / INPUT_RATE
    # Phase is the integral of the required frequency ramp.
    phase_cycles = 0.5 * RAMP_HZ_PER_S * t**2
    iq *= np.exp(2j * np.pi * phase_cycles).astype(np.complex64)
    real = np.clip(np.rint(iq.real), -8, 7)
    imag = np.clip(np.rint(iq.imag), -8, 7)
    raw = pack_q4(real + 1j * imag)
    return unpack_q4(raw), raw


def cases(stage, sdr_code):
    if stage == "calibration":
        for seed in range(7100, 7116):
            yield "null_calibration", str(seed), CONTROL, None, *synthesize(sdr_code, seed)
        return
    for seed in range(8100, 8108):
        yield "null_audit", str(seed), CONTROL, None, *synthesize(sdr_code, seed)
    for seed, cn0 in ((8200, 40), (8201, 35)):
        yield f"positive_{cn0}", str(seed), CONTROL, 0, *synthesize(sdr_code, seed, cn0)
    yield "positive_ramp", "7202", CONTROL, RAMP_HZ_PER_S, *ramp_control(sdr_code)
    for ref in FLIGHT:
        yield "flight", ref.operation, ref, None, *read_capture(ref.operation)


def fingerprint():
    files = (Path(__file__), ROOT/"docs"/"feedback-tracking-protocol.md",
             ROOT/"experiments"/"snapshot_correlation.py",
             ROOT/"experiments"/"pocketsdr_replay.py", ROOT/"experiments"/"pilot"/"pilot.py")
    data = b"".join(path.read_bytes().replace(b"\r\n", b"\n") for path in files)
    return hashlib.sha256(data).hexdigest()


def run(stage, out):
    tracker, sdr_code = tracking_library()
    out.mkdir(parents=True, exist_ok=True)
    path = out / "cutoff.json"
    cutoff = None
    if stage == "evaluation":
        freeze = json.loads(path.read_text(encoding="utf-8"))
        if freeze["fingerprint"] != fingerprint():
            raise ValueError("Tracker or protocol differs from the frozen calibration.")
        cutoff = freeze["cutoff"]
    maxima = {}
    with (out / f"{stage}_windows.csv").open("w", newline="", encoding="utf-8") as data, (
        out / f"{stage}_summary.csv"
    ).open("w", newline="", encoding="utf-8") as summary:
        window_rows = csv.writer(data)
        outcome_rows = csv.writer(summary)
        fields = ("kind","case","budget_bytes","policy","encoded_bytes","record_ms")
        window_rows.writerow(fields + ("start_ms","score","inside_guard","median_doppler_hz",
                                       "max_code_delta_samples","max_doppler_delta_hz",
                                       "tracking_mae_hz","fixed_seed_mae_hz","pass"))
        outcome_rows.writerow(fields + ("max_score","first_40ms_pass","initial_passing_ms",
                                        "available_ms","passing_windows"))
        for kind, case, ref, ramp, iq, raw in cases(stage,sdr_code):
            cache = {}
            max_score = 0.0
            for budget, policy, size, duration, stream in encoded_policies(iq,raw):
                key = policy, duration
                if key not in cache:
                    cache[key] = list(tracking_windows(tracker,ref,stream,ramp))
                windows = cache[key]
                peak = max((window[1] for window in windows), default=0.0)
                max_score = max(max_score, peak)
                prefix = (kind,case,budget,policy,size,duration)
                flags = []
                for window in windows:
                    passed = "" if cutoff is None else int(window[1] > cutoff and window[2])
                    flags.append(passed)
                    window_rows.writerow(prefix + window + (passed,))
                outcome = ("","","","")
                if cutoff is not None:
                    duration_ms = next((i for i,p in enumerate(flags) if not p),len(flags))*WINDOW_MS
                    outcome = (int(bool(flags) and flags[0]),duration_ms,len(flags)*WINDOW_MS,sum(flags))
                outcome_rows.writerow(prefix + (peak,) + outcome)
            maxima[case] = max_score
            data.flush()
            summary.flush()
            print(stage,kind,case,f"max={max_score:.3f}",flush=True)
    if cutoff is None:
        frozen = dict(cutoff=max(maxima.values()), maxima=maxima, fingerprint=fingerprint(),
                      pocket_sdr=POCKET_COMMIT)
        path.write_text(json.dumps(frozen,indent=2)+"\n",encoding="utf-8")
        print("Frozen cutoff",frozen["cutoff"],flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",choices=("calibration","evaluation"))
    parser.add_argument("--output",type=Path,default=ROOT/"results"/"local"/"feedback-tracking")
    arguments = parser.parse_args()
    run(arguments.stage,arguments.output)
