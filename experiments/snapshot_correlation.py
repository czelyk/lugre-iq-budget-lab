"""Measure reference-aided GPS L1 C/A correlation across a fixed I/Q byte budget."""
import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zlib

import numpy as np
from scipy.fft import fft, ifft
from scipy.signal import resample_poly

from pocketsdr_replay import (
    INPUT_RATE, PERIOD, POCKET_COMMIT, RATE, ROOT, pack_q2, pack_q4, quantize_2bit,
    read_capture, unpack_q2, unpack_q4,
)

BUDGETS = (480_000, 720_000, 960_000)
FREQUENCY_OFFSETS = np.arange(-350, 351, 50)
WINDOW_MS = 20
COHERENT_MS = 5
MIN_PHASE_GAP = 32
GPS_L1 = 1_575_420_000


@dataclass(frozen=True)
class Reference:
    operation: str
    prn: int
    doppler_hz: int
    delay_samples: int


# Approximate CAF values digitized from the external plots, modulo 1 ms.
FLIGHT = (
    Reference("OP32_0", 6, -5150, 1375),
    Reference("OP74_0", 31, -5350, 2232),
    Reference("OP78_0", 12, -2160, 2092),
    Reference("OP21_0", 24, 5630, 99),
    Reference("OP22_0", 31, 1900, 2403),
)
CONTROL = Reference("synthetic", 6, 1800, 700)


def encoded_policies(iq, raw):
    # A prefix can be encoded once and reused at all three allowances.
    raw_per_ms = INPUT_RATE // 1000
    lossless = {d: zlib.compress(raw[:d * raw_per_ms], 9) for d in range(10, 241, 10)}
    for budget in BUDGETS:
        lowbit_ms = min(240, budget // (raw_per_ms * 5) * 10)
        raw_ms = min(240, budget // (raw_per_ms * 10) * 10)
        lossless_ms = max(d for d, payload in lossless.items() if len(payload) <= budget)
        bit_payload = pack_q2(quantize_2bit(iq[:lowbit_ms * raw_per_ms]))
        payloads = {
            "raw": (raw[:raw_ms * raw_per_ms], raw_ms),
            "lossless": (lossless[lossless_ms], lossless_ms),
            "lowbit": (bit_payload, lowbit_ms),
        }
        for name, (payload, length) in payloads.items():
            if len(payload) > budget:
                raise ValueError(f"{name} exceeded {budget} bytes")
            if name == "lowbit":
                decoded = unpack_q2(payload)
            elif name == "lossless":
                decoded = unpack_q4(zlib.decompress(payload))
            else:
                decoded = unpack_q4(payload)
            yield budget, name, len(payload), length, resample_poly(decoded, 1, 2)


def synthesize(sdr_code, seed, cn0=None):
    rng = np.random.default_rng(seed)
    n = 240 * INPUT_RATE // 1000
    index = np.arange(n, dtype=np.float64)
    time = index / INPUT_RATE
    noise_std = 2.0
    i = rng.normal(0, noise_std, n).astype(np.float32)
    q = rng.normal(0, noise_std, n).astype(np.float32)
    signal = (i + 1j * q) + 0.20 * np.exp(2j * np.pi * 420_000 * time).astype(np.complex64)
    if cn0 is not None:
        chips = sdr_code.gen_code("L1CA", CONTROL.prn)
        delay = CONTROL.delay_samples / RATE
        chip_time = ((time - delay) * (1 + CONTROL.doppler_hz / GPS_L1) * 1_023_000)
        spreading = chips[np.floor(chip_time).astype(np.int64) % 1023]
        symbols = rng.choice((-1, 1), size=13)[(index.astype(int) // (INPUT_RATE // 50))]
        amplitude = np.sqrt(2 * noise_std**2 * 10**(cn0 / 10) / INPUT_RATE)
        signal += amplitude * spreading * symbols * np.exp(2j * np.pi * CONTROL.doppler_hz * time)
    packed = pack_q4(np.clip(np.rint(signal.real), -8, 7) + 1j * np.clip(np.rint(signal.imag), -8, 7))
    return unpack_q4(packed), packed


class Correlator:
    def __init__(self, reference, sdr_code):
        self.reference = reference
        self.frequencies = reference.doppler_hz + FREQUENCY_OFFSETS
        self.samples = np.arange(PERIOD)
        self.code_fft = sdr_code.gen_code_fft(
            sdr_code.gen_code("L1CA", reference.prn), .001, 0, RATE, PERIOD
        )
        cycles = self.frequencies[:, None] * np.arange(COHERENT_MS) / 1000
        time_cycles = self.frequencies[:, None] * self.samples / RATE
        self.millisecond_carrier = np.exp(-2j * np.pi * cycles).astype(np.complex64)
        self.sample_carrier = np.exp(-2j * np.pi * time_cycles).astype(np.complex64)
        self.local = (reference.delay_samples + np.arange(-8, 9)) % PERIOD
        self.off_reference = (
            (self.samples - reference.delay_samples + PERIOD // 2) % PERIOD - PERIOD // 2
        )
        self.off_reference = abs(self.off_reference) > MIN_PHASE_GAP

    def windows(self, stream):
        per_window = WINDOW_MS * PERIOD
        for start in range(0, len(stream) - per_window + 1, per_window):
            ms = start // PERIOD
            signal = stream[start:start + per_window].reshape(
                WINDOW_MS // COHERENT_MS, COHERENT_MS, PERIOD
            )
            folds = np.einsum("bmq,fm->fbq", signal, self.millisecond_carrier)
            folds *= self.sample_carrier[:, None, :]
            correlations = ifft(fft(folds, axis=-1) * self.code_fft, axis=-1)
            power = correlations.real**2 + correlations.imag**2
            block_start = (ms + COHERENT_MS * np.arange(WINDOW_MS // COHERENT_MS)) / 1000
            walk = np.rint(self.frequencies[:, None] / GPS_L1 * RATE * block_start).astype(int)
            index = (self.samples - walk[:, :, None]) % PERIOD
            energies = np.take_along_axis(power, index, axis=-1).mean(axis=1)
            local = energies[:, self.local] / energies[:, self.off_reference].mean(axis=1)[:, None]
            f, phase = np.unravel_index(local.argmax(), local.shape)
            yield ms, int(self.frequencies[f]), int(self.local[phase]), float(local[f, phase])


def captures(stage, sdr_code):
    if stage == "calibration":
        for seed in range(5100, 5116):
            yield "noise_calibration", str(seed), CONTROL, *synthesize(sdr_code, seed)
        return
    for seed in range(6100, 6108):
        yield "noise_audit", str(seed), CONTROL, *synthesize(sdr_code, seed)
    for seed, cn0 in ((6200, 40), (6201, 35)):
        yield f"positive_{cn0}dBHz", str(seed), CONTROL, *synthesize(sdr_code, seed, cn0)
    for reference in FLIGHT:
        yield "flight", reference.operation, reference, *read_capture(reference.operation)


def fingerprint():
    protocol = ROOT / "docs" / "snapshot-correlation-protocol.md"
    digest = hashlib.sha256()
    for path in (protocol, Path(__file__), ROOT / "experiments" / "pocketsdr_replay.py",
                 ROOT / "experiments" / "pilot" / "pilot.py"):
        # Ignore checkout newline conversion, but preserve substantive edits.
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def endpoints(windows, cutoff):
    post = [v for v in windows if v[0] >= WINDOW_MS]
    passes = [v[3] > cutoff for v in post]
    first_miss = next((i for i, passed in enumerate(passes) if not passed), len(passes))
    return int(len(passes) >= 2 and all(passes[:2])), WINDOW_MS * first_miss, WINDOW_MS * len(passes)


def run(stage, out, sdr_code):
    out.mkdir(parents=True, exist_ok=True)
    fixed = out / "cutoff.json"
    if stage == "evaluation":
        decision = json.loads(fixed.read_text(encoding="utf-8"))
        if decision["fingerprint"] != fingerprint():
            raise ValueError("The tracking detector or protocol differs from the calibration.")
        threshold = decision["cutoff"]
    else:
        threshold = None
    maxima = {}
    with (out / f"{stage}_windows.csv").open("w", newline="", encoding="utf-8") as samples, (
        out / f"{stage}_summary.csv"
    ).open("w", newline="", encoding="utf-8") as summaries:
        detailed = csv.writer(samples)
        summary = csv.writer(summaries)
        fields = ["kind","case","prn","budget_bytes","policy","encoded_bytes","record_ms"]
        detailed.writerow(fields + ["window_start_ms","doppler_hz","delay_samples","score","pass"])
        summary.writerow(fields + ["post_warmup_max_score","fixed_40ms_pass",
                                   "initial_passing_ms","available_ms"])
        for kind, case, reference, iq, raw in captures(stage, sdr_code):
            correlator = Correlator(reference, sdr_code)
            measured = {}
            case_max = 0.0
            for budget, policy, size, length, stream in encoded_policies(iq, raw):
                key = policy, length
                if key not in measured:
                    measured[key] = list(correlator.windows(stream))
                windows = measured[key]
                row = [kind,case,reference.prn,budget,policy,size,length]
                peak = max(w[3] for w in windows if w[0] >= WINDOW_MS)
                case_max = max(case_max, peak)
                for window in windows:
                    passed = "" if threshold is None or window[0] < WINDOW_MS else int(window[3] > threshold)
                    detailed.writerow(row + list(window) + [passed])
                detail = ["", "", ""] if threshold is None else list(endpoints(windows, threshold))
                summary.writerow(row + [peak] + detail)
            maxima[case] = case_max
            print(stage, kind, case, f"max={case_max:.3f}", flush=True)
    if threshold is None:
        fixed.write_text(json.dumps(dict(cutoff=max(maxima.values()), trial_maxima=maxima,
                                        fingerprint=fingerprint(), pocket_sdr=POCKET_COMMIT),
                                    indent=2) + "\n", encoding="utf-8")
        print("Frozen cutoff", max(maxima.values()), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("calibration","evaluation"))
    parser.add_argument("--output", type=Path, default=ROOT/"results"/"local"/"snapshot-correlation")
    args = parser.parse_args()
    pocket = ROOT / ".cache" / "PocketSDR"
    revision = subprocess.check_output(["git","-C",str(pocket),"rev-parse","HEAD"], text=True).strip()
    if revision != POCKET_COMMIT:
        raise ValueError(f"Expected Pocket SDR {POCKET_COMMIT}, got {revision}")
    sys.path.insert(0, str(pocket/"python"))
    import sdr_code
    run(args.stage, args.output, sdr_code)


if __name__ == "__main__":
    main()
