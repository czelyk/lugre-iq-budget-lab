"""Audit the known chirp after the frozen tracker diverged on the ramp control."""
import argparse
import csv
from pathlib import Path
from unittest.mock import patch

import numpy as np

from feedback_tracking import (
    CONTROL, GPS_L1, OFFSETS, PERIOD, RATE, RAMP_HZ_PER_S, ROOT, ramp_control,
    tracking_library, tracking_windows,
)
from snapshot_correlation import encoded_policies


def oracle_scores(stream, sdr_code):
    """Correlate against the known injected phase and a fixed-rate ablation."""
    data = stream - np.mean(stream[:10 * PERIOD])
    chips = sdr_code.gen_code("L1CA", CONTROL.prn)
    lag_samples = CONTROL.delay_samples + np.array((0, *OFFSETS))
    times = np.arange(len(data)) / RATE
    delays = lag_samples[:, None] / RATE
    chip_time = (times - delays) * (1 + CONTROL.doppler_hz / GPS_L1) * 1_023_000
    replica = chips[np.floor(chip_time).astype(int) % 1023]
    for start in range(10, len(data) // PERIOD - 40 + 1, 40):
        indexes = slice(start * PERIOD, (start + 40) * PERIOD)
        t = times[indexes]
        fd = CONTROL.doppler_hz + RAMP_HZ_PER_S * t
        for mode, slope in (("injected_phase", RAMP_HZ_PER_S), ("oracle_fixed", 0)):
            cycles = CONTROL.doppler_hz * t + 0.5 * slope * t**2
            baseband = data[indexes] * np.exp(-2j * np.pi * cycles)
            taps = (replica[:, indexes] * baseband).reshape(len(lag_samples),8,-1).sum(axis=2)
            energy = (abs(taps) ** 2).sum(axis=1)
            estimate = CONTROL.doppler_hz + slope * t
            yield mode, start, float(np.mean(estimate)), float(np.mean(fd)), (
                float(energy[0] / energy[1:].mean())
            ), float(np.mean(abs(estimate-fd)))


def audit(out):
    tracker, sdr_code = tracking_library()
    iq, raw = ramp_control(sdr_code)
    out.mkdir(parents=True, exist_ok=True)
    with (out/"ramp_audit.csv").open("w",newline="",encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(("policy","method","window_start_ms","window_length_ms",
                         "doppler_hz","truth_at_midpoint_hz","score","ramp_mae_hz"))
        for budget, policy, _, _, stream in encoded_policies(iq,raw):
            if budget != 960_000:
                continue
            for mode, start, hz, truth, score, mae in oracle_scores(stream, sdr_code):
                writer.writerow((policy,mode,start,40,hz,truth,score,mae))
            for mode in ("feedback","fixed_frequency"):
                loop = tracker.FLL if mode == "feedback" else lambda _channel: None
                with patch.object(tracker,"FLL",loop):
                    for start, score, _, fd, _, _, mae, _ in tracking_windows(
                        tracker, CONTROL, stream, RAMP_HZ_PER_S
                    ):
                        expected = CONTROL.doppler_hz + RAMP_HZ_PER_S * (start+19.5) / 1000
                        writer.writerow((policy,mode,start,40,fd,expected,score,mae))


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"results"/"local"/"feedback-tracking")
    audit(parser.parse_args().output)
