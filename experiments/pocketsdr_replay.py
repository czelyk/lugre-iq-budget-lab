"""Replay actual packed LuGRE policies through Pocket SDR acquisition paths."""
import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import tempfile
import zlib

import numpy as np
from scipy.signal import resample_poly
from scipy.stats import gamma

ROOT = Path(__file__).resolve().parents[1]
POCKET_COMMIT = "23c91c732365a3668d303656de95a36e7604b58a"
sys.path.insert(0, str(ROOT / "experiments" / "pilot"))
from pilot import quantize_2bit, read_capture

INPUT_RATE = 8_000_000
RATE = 4_000_000
PERIOD = RATE // 1000
DOPPLERS = np.arange(-20_000, 20_001, 50)
LEVELS = np.array([-3, -1, 1, 3], dtype=np.float32)


@dataclass(frozen=True)
class Case:
    name: str
    operation: str
    start_ms: int
    budget: int
    lossless_ms: int
    prns: tuple[int, ...]


CASES = (
    Case("commissioning", "OP2_0", 0, 480_000, 60, (18,)),
    Case("orbit", "OP23_0", 0, 480_000, 100, (21,)),
    Case("surface", "OP76_0", 960, 1_670_310, 320, (31, 32)),
)
EXPECTED = {18: (-10_750, None), 21: (6150, 1445), 31: (-1900, None), 32: (3400, 760)}


def pack_q2(samples):
    i = np.searchsorted(LEVELS, samples.real).astype(np.uint8)
    q = np.searchsorted(LEVELS, samples.imag).astype(np.uint8)
    iq4 = i << 2 | q
    return (iq4[::2] << 4 | iq4[1::2]).tobytes()


def unpack_q2(payload):
    packed = np.frombuffer(payload, np.uint8)
    iq4 = np.empty(2 * len(packed), np.uint8)
    iq4[::2] = packed >> 4
    iq4[1::2] = packed & 15
    return LEVELS[iq4 >> 2] + 1j * LEVELS[iq4 & 3]


def pack_q4(samples):
    i = samples.real.astype(np.int8).view(np.uint8)
    q = samples.imag.astype(np.int8).view(np.uint8)
    return (i << 4 | (q & 15)).tobytes()


def unpack_q4(payload):
    packed = np.frombuffer(payload, np.uint8)
    i = (packed >> 4).astype(np.int8)
    q = (packed & 15).astype(np.int8)
    i[i >= 8] -= 16
    q[q >= 8] -= 16
    return i.astype(np.float32) + 1j * q.astype(np.float32)


def prepare_streams(case, iq, raw):
    start = case.start_ms * 8000
    duration_ms = case.budget // 4000 // 10 * 10
    n = duration_ms * 8000
    samples = iq[start:start + n]
    if len(samples) != n:
        raise ValueError(f"{case.operation} is too short")
    prefix = raw[start:start + case.lossless_ms * 8000]
    lossless = zlib.compress(prefix, 9)
    lowbit = pack_q2(quantize_2bit(samples))
    original = resample_poly(samples, 1, 2)
    lowrate = pack_q4(np.clip(np.rint(original.real), -8, 7) +
                      1j * np.clip(np.rint(original.imag), -8, 7))
    streams = {
        "lossless": (lossless, resample_poly(unpack_q4(zlib.decompress(lossless)), 1, 2)),
        "lowbit": (lowbit, resample_poly(unpack_q2(lowbit), 1, 2)),
        "lowrate": (lowrate, unpack_q4(lowrate)),
    }
    if case.name == "orbit":
        reference = raw[start:start + case.budget]
        streams["raw"] = (reference, resample_poly(unpack_q4(reference), 1, 2))
    if case.name == "commissioning":
        streams = {"raw": (prefix, resample_poly(unpack_q4(prefix), 1, 2))}
    if any(len(payload) > case.budget for payload, _ in streams.values()):
        raise ValueError(f"{case.name}: a payload exceeded its byte budget")
    return streams


def acquire(sdr_code, sdr_func, stream, prns, shift_ms, statistic):
    use = stream[shift_ms * PERIOD:]
    blocks = len(use) // (PERIOD * 10)
    data = use[:blocks * PERIOD * 10].reshape(blocks, 10, PERIOD)
    code_ffts = [sdr_code.gen_code_fft(sdr_code.gen_code("L1CA", prn), .001, 0, RATE, PERIOD)
                 for prn in prns]
    position = np.arange(PERIOD)[None, :]
    block_start_ms = shift_ms + 10 * np.arange(blocks)
    elapsed = np.arange(10) / 1000
    fast_time = np.arange(PERIOD) / RATE
    maxima = np.zeros(len(prns))
    mean_sums = np.zeros(len(prns))
    best = [None] * len(prns)
    for hz in DOPPLERS:
        epoch_carrier = np.exp(-2j * np.pi * hz * elapsed).astype(np.complex64)
        sample_carrier = np.exp(-2j * np.pi * hz * fast_time).astype(np.complex64)
        folded = np.einsum("bms,m->bs", data, epoch_carrier) * sample_carrier
        drift = np.rint(hz / 1_575_420_000 * RATE * block_start_ms / 1000).astype(int)
        indexes = (position - drift[:, None]) % PERIOD
        for j, code in enumerate(code_ffts):
            # Pocket SDR FFT correlator operates on the last axis. Normalize
            # its batch result per code period instead of per batch row count.
            correlation = sdr_func.corr_fft_(folded, code) * (blocks / PERIOD)
            power = np.abs(correlation) ** 2
            energies = np.take_along_axis(power, indexes, axis=1).mean(axis=0)
            phase = int(np.argmax(energies))
            row_mean = float(np.mean(energies))
            mean_sums[j] += row_mean
            score = float(energies[phase])
            if statistic == 'row':
                score /= row_mean
            if score > maxima[j]:
                maxima[j] = score
                best[j] = (int(hz), phase)
    threshold = gamma.isf(.001 / (PERIOD * len(DOPPLERS)), blocks, scale=1 / blocks)
    for prn, (hz, phase), maximum, mean_sum in zip(prns, best, maxima, mean_sums):
        metric = maximum if statistic == 'row' else maximum * len(DOPPLERS) / mean_sum
        expected_hz, expected_phase = EXPECTED[prn]
        match = abs(hz - expected_hz) <= 150 and (
            expected_phase is None or abs(phase - expected_phase) <= 8
        )
        yield prn, blocks, hz, phase, metric, threshold, int(metric >= threshold), int(match)


def run_cli(exe, stream, prns):
    with tempfile.TemporaryDirectory() as folder:
        iq_file = Path(folder) / "replay.cs16"
        cs16 = np.column_stack((stream.real, stream.imag)) * 1500.0
        np.rint(cs16).clip(-32768, 32767).astype("<i2").tofile(iq_file)
        # The CLI reads one extra C/A period after its integration interval.
        tint_ms = len(stream) // PERIOD - 1
        command = [str(exe), "-sig", "L1CA", "-fmt", "CS16", "-f", "4", "-d",
                   "0,20000", "-prn", ",".join(map(str, prns)),
                   "-tint", str(tint_ms), str(iq_file)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode or "PRN" not in result.stdout:
            raise RuntimeError(f"Pocket SDR returned no acquisition rows: {result.stderr}")
        return result.stdout.replace("\x1b[", "ANSI[")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pocketsdr", type=Path, default=ROOT / ".cache" / "PocketSDR")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "local" / "independent")
    parser.add_argument("--statistic", choices=("grid", "row"), default="grid")
    parser.add_argument("--skip-stock", action="store_true")
    parser.add_argument("--policy", choices=("raw", "lossless", "lowbit", "lowrate", "negative_reverse"))
    parser.add_argument("--equal-dwell", action="store_true",
                        help="Use the same number of complete 10 ms blocks for both shifts")
    parser.add_argument("--case", choices=[case.name for case in CASES])
    args = parser.parse_args()
    upstream = args.pocketsdr.resolve()
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"],
                                       text=True).strip()
    if revision != POCKET_COMMIT:
        raise ValueError(f"Expected Pocket SDR revision {POCKET_COMMIT}, got {revision}")
    sys.path.insert(0, str(upstream / "python"))
    import sdr_code
    import sdr_func

    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "acquisition.csv").open("w", newline="", encoding="utf-8") as table, (
        args.output / "pocket_acq.log"
    ).open("w", encoding="utf-8") as log:
        writer = csv.writer(table)
        writer.writerow(["case", "operation", "start_ms", "policy", "budget_bytes",
                         "actual_bytes", "duration_ms", "shift_ms", "prn", "coherent_blocks",
                         "doppler_hz", "phase_sample_4Msps", "metric", "nominal_threshold",
                         "nominal_pass", "reference_match"])
        log.write(f"Pocket SDR revision {revision}, statistic={args.statistic}\n")
        for case in CASES:
            if args.case is not None and args.case != case.name:
                continue
            streams = prepare_streams(case, *read_capture(case.operation))
            if case.name == "surface":
                payload, stream = streams["lossless"]
                streams["negative_reverse"] = (payload, np.conj(stream[::-1]).copy())
            if args.policy is not None and args.policy not in streams:
                raise ValueError(f"{case.name}: policy {args.policy!r} is unavailable")
            for policy, (payload, stream) in streams.items():
                if args.policy is not None and args.policy != policy:
                    continue
                prns = (32,) if policy == "negative_reverse" else case.prns
                log.write(f"\n{case.name} {policy} {len(payload)} bytes\n")
                if not args.skip_stock:
                    log.write(run_cli(upstream / "bin" / "pocket_acq.exe", stream, prns))
                log.flush()
                shared_samples = ((len(stream) - 5 * PERIOD) // (10 * PERIOD)) * (10 * PERIOD)
                for shift in (0, 5):
                    replay = stream[:shared_samples + shift * PERIOD] if args.equal_dwell else stream
                    for measurement in acquire(
                        sdr_code, sdr_func, replay, prns, shift, args.statistic
                    ):
                        writer.writerow([case.name, case.operation, case.start_ms, policy,
                                         case.budget, len(payload), len(stream) // PERIOD, shift,
                                         *measurement])
                table.flush()
                print(case.name, policy, "done", flush=True)


if __name__ == "__main__":
    main()
