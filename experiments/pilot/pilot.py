"""Descriptive GPS L1 replay of the selected LuGRE L0 files."""
import csv
import hashlib
import os
import struct
from pathlib import Path
import sys
from zipfile import ZipFile
import zlib

import numpy as np
import scipy
from scipy.fft import fft, ifft
from scipy.signal import resample_poly
from scipy.stats import gamma

TAPS = [
    (2,6),(3,7),(4,8),(5,9),(1,9),(2,10),(1,8),(2,9),
    (3,10),(2,3),(3,4),(5,6),(6,7),(7,8),(8,9),(9,10),
    (1,4),(2,5),(3,6),(4,7),(5,8),(6,9),(1,3),(4,6),
    (5,7),(6,8),(7,9),(8,10),(1,6),(2,7),(3,8),(4,9),
]
FREQ = np.arange(-20_000, 20_001, 100)
RATE = 4_000_000
PERIOD = RATE // 1000
DURATIONS = {"original": (60, 120), "requantized": (60, 120, 240),
             "lower_rate": (120, 240)}


def archive_path():
    default = Path(__file__).resolve().parents[2] / "data" / "NASA-LuGRE-16411687.zip"
    return Path(os.environ.get("LUGRE_ARCHIVE", default))

def member(operation):
    with ZipFile(archive_path()) as archive:
        entry, = [v for v in archive.infolist()
                  if "IQS_L1" in v.filename and v.filename.endswith(f"{operation}.bin")]
        return entry.filename, archive.read(entry)


def read_capture(operation):
    name, data = member(operation)
    if data[:4] != b"qIQS":
        raise ValueError("Unexpected Qascom packet")
    _, count, _, kind, inversion, bits, rate, center, intermediate, _ = struct.unpack_from(
        "<d2IBHB4d", data, 10)
    packed = data[62:-3]
    if (count, kind, inversion, bits, rate, center, intermediate) != (
        len(packed), 1, 0, 4, 8_000_000, 1_575_420_000, 0
    ):
        raise ValueError("Unexpected snapshot parameters")
    raw = np.frombuffer(packed, dtype=np.uint8)
    i = (raw & 0xf0).view(np.int8) >> 4
    q = (raw << 4).view(np.int8) >> 4
    print(name, len(packed), hashlib.sha256(data).hexdigest(), flush=True)
    return i.astype(np.float32) + 1j*q.astype(np.float32), packed

def spectrum_for(prn):
    a, b = [1]*10, [1]*10
    first, second = TAPS[prn-1]
    chips = []
    for _ in range(1023):
        chips.append(1 - 2 * (a[-1] ^ b[first-1] ^ b[second-1]))
        a = [a[2] ^ a[9], *a[:-1]]
        b = [b[1] ^ b[2] ^ b[5] ^ b[7] ^ b[8] ^ b[9], *b[:-1]]
    code = np.array(chips, dtype=np.float32)[np.arange(PERIOD) * 1023 // PERIOD]
    return fft(code).conj()

def quantize_2bit(iq):
    def quantize_component(component):
        threshold = .98 * np.std(component[:80_000])
        magnitude = np.where(np.abs(component + .5) >= threshold, 3, 1)
        return np.where(component >= 0, magnitude, -magnitude).astype(np.float32)
    return quantize_component(iq.real) + 1j*quantize_component(iq.imag)


def prepare(iq):
    original = resample_poly(iq, 1, 2)
    requantized = resample_poly(quantize_2bit(iq), 1, 2)
    lower_rate = np.clip(np.rint(original.real), -8, 7) + 1j*np.clip(
        np.rint(original.imag), -8, 7)
    return dict(original=original, requantized=requantized, lower_rate=lower_rate)

def acquire(iq, prns, durations):
    blocks = max(durations)//10
    within_period = np.arange(PERIOD, dtype=np.float64) / RATE
    period_start = np.arange(blocks * 10, dtype=np.float64) / 1000
    iq = iq[:blocks * 10 * PERIOD].reshape(blocks * 10, PERIOD)
    replicas = np.stack([spectrum_for(prn) for prn in prns], axis=0)
    peak = np.zeros((len(prns),len(durations)))
    loc = np.zeros((len(prns),len(durations),2), dtype=int)
    idx = np.arange(PERIOD)
    for f in FREQ:
        carrier = np.exp(-2j*np.pi*f*within_period).astype(np.complex64)
        starts = np.exp(-2j*np.pi*f*period_start).astype(np.complex64)
        folded = (iq * starts[:,None]).reshape(blocks,10,PERIOD).sum(axis=1)
        folds = folded * carrier[None,:]
        corr = ifft(fft(folds, axis=-1)[None,:,:] * replicas[:,None,:], axis=-1)
        strength = corr.real**2 + corr.imag**2
        drift = np.rint(f / 1_575_420_000 * RATE * np.arange(blocks) / 100).astype(int)
        shifts = (idx[None,:] - drift[:,None]) % PERIOD
        accum = np.cumsum(np.take_along_axis(strength, shifts[None,:,:], axis=-1),axis=1)
        accum = accum[:,[d//10-1 for d in durations],:]
        phase = np.argmax(accum, axis=-1)
        score = np.max(accum, axis=-1) / np.mean(accum, axis=-1)
        better = score > peak
        peak[better] = score[better]
        loc[better] = np.stack([np.full_like(phase, f), phase],axis=-1)[better]
    for j, prn in enumerate(prns):
        for k, duration in enumerate(durations):
            dof = duration//10
            cut = gamma.isf(.001/(PERIOD*len(FREQ)), dof, scale=1/dof)
            freq, phase = loc[j,k]
            yield prn, duration, freq, phase, peak[j,k], cut, int(peak[j,k] >= cut)

def main():
    print(sys.version.split()[0], np.__version__, scipy.__version__, flush=True)
    operation = sys.argv[1]
    prns = tuple(map(int, sys.argv[2:])) or tuple(range(1, 33))
    iq, packed = read_capture(operation)
    sizes = {d:len(zlib.compress(packed[:d*8_000], 9)) for d in (60,120,240)}
    with open(f"{operation}.csv", "w", newline="", encoding="utf-8") as result:
        writer = csv.writer(result)
        writer.writerow(["operation", "policy", "PRN", "duration_ms", "doppler_hz",
                         "phase_at_4MSps", "peak_mean", "nominal_threshold",
                         "nominal_candidate", "raw_payload_bytes", "lossless_original_bytes"])
        for policy, stream in prepare(iq).items():
            for prn,d,f,p,stat,cut,hit in acquire(stream, prns, DURATIONS[policy]):
                size = (8_000 if policy=="original" else 4_000)*d
                writer.writerow([operation,policy,prn,d,f,p,stat,cut,hit,size,sizes[d]])
            result.flush()
            print(operation, policy, "done", flush=True)

if __name__ == "__main__":
    main()
