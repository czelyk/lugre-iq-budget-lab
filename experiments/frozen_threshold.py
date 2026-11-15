"""Freeze a wrong-code score threshold, then test previously unused LuGRE recordings."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import zlib

import numpy as np
from scipy.fft import fft, ifft
from scipy.stats import gamma

from pocketsdr_replay import (
    Case, DOPPLERS, PERIOD, POCKET_COMMIT, RATE, ROOT, prepare_streams, read_capture,
    unpack_q4, resample_poly,
)

BUDGET = 960_000
CALIBRATION = ("OP2_0", "OP23_0", "OP38_0", "OP40_0")
# Digitized approximately from the external CAF figures. Delay units here are
# 4-Msps samples modulo 1 ms. These windows are for scoring, not search priors.
REFERENCES = {
    "OP32_0": ((6, -5150, 1375, 250),),
    "OP74_0": ((31, -5350, 2232, 250),),
    "OP78_0": ((12, -2160, 2092, 250),),
    "OP77_1": ((6, 20, 3390, 350), (14, 5260, 2419, 350)),
}
ALPHA = .05
CALIBRATION_CODES = 8
AUDIT_CODES = 4
CELLS = len(DOPPLERS) * PERIOD
SHIFTS = (0, 5)


def longest_lossless(raw):
    feasible = (
        ms for ms in range(10, 241, 10)
        if len(zlib.compress(raw[:ms * 8000], 9)) <= BUDGET
    )
    return max(feasible)


def streams_for(operation):
    iq, raw = read_capture(operation)
    # The shared pack/decode path is reused. Add raw from the same start.
    case = Case("validation", operation, 0, BUDGET, longest_lossless(raw), ())
    streams = prepare_streams(case, iq, raw)
    prefix = raw[:BUDGET]
    streams["raw"] = (prefix, resample_poly(unpack_q4(prefix), 1, 2))
    return streams


def code_bank(sdr_code, targets, decoys, seed):
    chips = sdr_code.gen_code("L1CA", 1)
    rng = np.random.default_rng(seed)
    code = {f"decoy-{k+1}": rng.permutation(chips) for k in range(decoys)}
    code.update({str(prn): sdr_code.gen_code("L1CA", prn) for prn, *_ in targets})
    bank = np.stack([sdr_code.gen_code_fft(c, .001, 0, RATE, PERIOD)
                     for c in code.values()])
    return tuple(code), bank


def search(stream, bank, workers, xp=np):
    is_cpu = xp is np
    bank = xp.asarray(bank)

    def forward(frame):
        if is_cpu:
            return fft(frame, axis=-1, workers=workers)
        return xp.fft.fft(frame, axis=-1)

    def inverse(frame):
        if is_cpu:
            return ifft(frame, axis=-1, workers=workers)
        return xp.fft.ifft(frame, axis=-1)

    blocks = (len(stream) - 5 * PERIOD) // (10 * PERIOD)
    data = xp.stack([xp.asarray(stream[s * PERIOD:(s + 10 * blocks) * PERIOD]).reshape(blocks, 10, PERIOD)
                     for s in SHIFTS])
    position = xp.arange(PERIOD)
    start_ms = xp.array(SHIFTS)[:, None] + 10 * xp.arange(blocks)
    sample_time = position / RATE
    millisecond = xp.arange(10) / 1000
    peaks = xp.zeros((len(bank), len(SHIFTS)))
    freq = xp.zeros_like(peaks, dtype=int)
    phase = xp.zeros_like(freq)
    for hz in DOPPLERS:
        epoch = xp.exp(-2j * np.pi * hz * millisecond).astype(np.complex64)
        carrier = xp.exp(-2j * np.pi * hz * sample_time).astype(np.complex64)
        if is_cpu:
            folded = np.einsum("sbmp,m->sbp", data, epoch)
        else:
            folded = (data * epoch[None, None, :, None]).sum(axis=2)
        spectra = forward(folded * carrier)
        drift = xp.rint(hz / 1_575_420_000 * RATE * start_ms / 1000).astype(int)
        indexes = (position - drift[..., None]) % PERIOD
        correlation = inverse(spectra[None, ...] * bank[:, None, None, :])
        power = correlation.real**2 + correlation.imag**2
        energies = xp.take_along_axis(power, indexes[None, ...], axis=-1).mean(axis=2)
        best = energies.argmax(axis=-1)
        normalized = energies.max(axis=-1) / energies.mean(axis=-1)
        improved = normalized > peaks
        peaks = xp.where(improved, normalized, peaks)
        freq = xp.where(improved, int(hz), freq)
        phase = xp.where(improved, best, phase)
    if not is_cpu:
        peaks, freq, phase = (xp.asnumpy(field) for field in (peaks, freq, phase))
    score = np.maximum(0, (-gamma.logsf(peaks, blocks, scale=1 / blocks)
                           - math.log(CELLS)) / math.log(10))
    return blocks, peaks, score, freq, phase


def fingerprint():
    protocol = ROOT / "docs" / "threshold-protocol.md"
    return hashlib.sha256(protocol.read_bytes() + Path(__file__).read_bytes()).hexdigest()


def reference_match(prn, hz, phase, targets):
    for target, expected_hz, expected_phase, tolerance in targets:
        if prn == str(target):
            delta = abs(int(phase) - expected_phase)
            return int(abs(int(hz) - expected_hz) <= tolerance and min(delta, PERIOD-delta) <= 16)
    return ""


def run(args):
    xp = np
    if args.backend == "cuda":
        import cupy as xp

    upstream = ROOT / ".cache" / "PocketSDR"
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"],
                                       text=True).strip()
    if revision != POCKET_COMMIT:
        raise ValueError(f"Unexpected Pocket SDR revision {revision}")
    sys.path.insert(0, str(upstream / "python"))
    import sdr_code

    args.output.mkdir(parents=True, exist_ok=True)
    frozen = args.output / "frozen_threshold.json"
    calibrating = args.stage == "calibration"
    if not calibrating:
        decision = json.loads(frozen.read_text(encoding="utf-8"))
        if decision["fingerprint"] != fingerprint() or decision["backend"] != args.backend:
            raise ValueError("Protocol or detector differs from the frozen calibration")
    inputs = CALIBRATION if calibrating else tuple(REFERENCES)
    seed = 20261115 if calibrating else 20261116
    decoys = CALIBRATION_CODES if calibrating else AUDIT_CODES
    filename = f"{args.stage}_scores.csv"
    trial_max = []
    with (args.output / filename).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(("operation", "policy", "code", "offset_ms", "actual_bytes",
                         "record_ms", "blocks", "peak_to_row_mean", "tail_score",
                         "doppler_hz", "delay_samples", "reference_match", "above_frozen"))
        for operation in inputs:
            targets = () if calibrating else REFERENCES[operation]
            labels, bank = code_bank(sdr_code, targets, decoys, seed)
            maxima = np.zeros(decoys)
            for policy, (payload, stream) in streams_for(operation).items():
                blocks, peak, score, freq, phase = search(stream, bank, args.workers, xp)
                maxima = np.maximum(maxima, score[:decoys].max(axis=1))
                for j, label in enumerate(labels):
                    for k, shift in enumerate(SHIFTS):
                        above = "" if calibrating else int(score[j,k] > decision["threshold"])
                        match = reference_match(label, freq[j,k], phase[j,k], targets)
                        writer.writerow((operation, policy, label, shift, len(payload),
                                         len(stream) // PERIOD, blocks, float(peak[j,k]),
                                         float(score[j,k]), freq[j,k], phase[j,k], match, above))
                f.flush()
                print(args.stage, operation, policy, len(payload), "bytes", flush=True)
            trial_max.extend((operation, labels[j], float(v)) for j, v in enumerate(maxima))
    with (args.output / f"{args.stage}_decoy_maxima.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.writer(f)
        writer.writerow(("operation", "code", "max_over_policies_offsets"))
        writer.writerows(trial_max)
    if calibrating:
        rank = math.ceil((len(trial_max) + 1) * (1 - ALPHA))
        threshold = sorted(t[2] for t in trial_max)[rank - 1]
        decision = dict(threshold=threshold, rank=rank, trials=len(trial_max),
                        alpha=ALPHA, calibration=list(inputs), fingerprint=fingerprint(),
                        sdr_revision=revision, backend=args.backend, backend_version=xp.__version__)
        frozen.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
        print("Frozen threshold", threshold, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("calibration","validation"))
    parser.add_argument("--output", type=Path, default=ROOT/"results"/"local"/"threshold")
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--workers", type=int, default=4)
    run(parser.parse_args())
