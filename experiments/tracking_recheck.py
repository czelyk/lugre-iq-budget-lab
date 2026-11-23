"""Test frozen feedback continuity on additional LuGRE snapshots."""

import argparse
import csv
import hashlib
from itertools import chain
import json
from pathlib import Path
import platform

import numpy as np
import scipy
from scipy.signal import resample_poly

from feedback_tracking import WARM_UP_MS, WINDOW_MS, fingerprint, tracking_library, tracking_windows
from snapshot_correlation import (
    BUDGETS, CONTROL, INPUT_RATE, POCKET_COMMIT, ROOT, Reference, encoded_policies,
    read_capture, synthesize,
)

SEGMENT_MS = 240
SAMPLES_PER_MS = INPUT_RATE // 1000
ARCHIVE = ROOT / "results" / "tracking-recheck"
CALIBRATION = ROOT / "results" / "feedback-tracking" / "cutoff.json"
TARGETS = (
    (Reference("OP23_0", 21, 6150, 1445), 0),
    (Reference("OP76_0", 32, 3400, 760), 960),
    (Reference("OP77_1", 6, 20, 3390), 0),
    (Reference("OP77_1", 14, 5260, 2419), 0),
)
NEGATIVE_SEEDS = range(9100, 9108)
MIN_CONTINUITY_MS = 80


def flight_cases():
    captures = {}
    for reference, offset_ms in TARGETS:
        if reference.operation not in captures:
            captures[reference.operation] = read_capture(reference.operation)
        iq, raw = captures[reference.operation]
        start = offset_ms * SAMPLES_PER_MS
        stop = start + SEGMENT_MS * SAMPLES_PER_MS
        if stop > len(raw):
            raise ValueError(f"{reference.operation} is too short for the frozen segment")
        yield "flight", reference.operation, offset_ms, reference, iq[start:stop], raw[start:stop]


def score_windows(tracker, reference, stream, cutoff):
    rows = []
    for start, score, guard, _, code_error, frequency_error, *_ in tracking_windows(
            tracker, reference, stream, None):
        rows.append({"start_ms": start, "score": score, "inside_guard": guard,
                     "max_code_error_samples": code_error, "max_frequency_error_hz": frequency_error,
                     "pass": int(score > cutoff and guard)})
    return rows


def initial_duration(rows):
    count = 0
    for row in rows:
        if not row["pass"]:
            break
        count += 1
    return count * WINDOW_MS


def compare(policies, full):
    low, low_ms = policies["lowbit"]
    lossless, lossless_ms = policies["lossless"]
    reference_passes = {row["start_ms"] for row in full if row["pass"]}
    low_by_start = {row["start_ms"]: row["pass"] for row in low}
    lossless_by_start = {row["start_ms"]: row["pass"] for row in lossless}
    # Each tracked epoch needs one further millisecond in the input buffer.
    lossless_starts = set(range(WARM_UP_MS, lossless_ms - WINDOW_MS, WINDOW_MS))
    common = lossless_starts & set(range(WARM_UP_MS, low_ms - WINDOW_MS, WINDOW_MS))
    both_durations = {policy: initial_duration(rows) for policy, (rows, _) in policies.items()}
    full_initial_ms = initial_duration(full)
    full_initial = {row["start_ms"] for row in full[:full_initial_ms // WINDOW_MS]}
    extra = [row["start_ms"] for row in low[:both_durations["lowbit"] // WINDOW_MS]
             if row["start_ms"] not in lossless_starts and row["start_ms"] in full_initial]
    common_losses = sorted(start for start in common
                           if lossless_by_start.get(start, 0) > low_by_start.get(start, 0))
    common_gains = sorted(start for start in common
                          if low_by_start.get(start, 0) > lossless_by_start.get(start, 0))
    return {
        "full_initial_ms": full_initial_ms,
        "raw_initial_ms": both_durations["raw"], "lossless_initial_ms": both_durations["lossless"],
        "lowbit_initial_ms": both_durations["lowbit"],
        "supported_extra_window_starts_ms": " ".join(map(str, extra)),
        "common_window_loss_starts_ms": " ".join(map(str, common_losses)),
        "supported_common_window_loss_starts_ms": " ".join(
            str(start) for start in common_losses if start in reference_passes),
        "common_window_gain_starts_ms": " ".join(map(str, common_gains)),
        "supported_extra_continuity": int(bool(extra) and both_durations["lowbit"] >= MIN_CONTINUITY_MS
                                           and full_initial_ms >= MIN_CONTINUITY_MS),
    }


def run():
    frozen = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    if frozen["fingerprint"] != fingerprint() or frozen["pocket_sdr"] != POCKET_COMMIT:
        raise ValueError("The original tracker inputs do not match the frozen calibration")
    cutoff = frozen["cutoff"]
    tracker, code = tracking_library()
    windows, results, pairs, inputs = [], [], [], []
    negatives = (("null", str(seed), 0, CONTROL, *synthesize(code, seed)) for seed in NEGATIVE_SEEDS)
    for kind, case, offset, reference, iq, raw in chain(flight_cases(), negatives):
        prefix = {"kind": kind, "case": case, "offset_ms": offset, "prn": reference.prn}
        inputs.append({**prefix, "segment_sha256": hashlib.sha256(raw).hexdigest()})
        cache = {}
        full = score_windows(tracker, reference, resample_poly(iq, 1, 2), cutoff)
        budgets = {budget: {} for budget in BUDGETS}
        streams = chain(((0, "full", len(raw), SEGMENT_MS, None),), encoded_policies(iq, raw))
        for budget, policy, size, duration, stream in streams:
            if duration * SAMPLES_PER_MS > len(raw):
                raise ValueError("Declared duration exceeds the input segment")
            if policy == "full":
                scores = full
            else:
                key = policy, duration
                if key not in cache:
                    cache[key] = score_windows(tracker, reference, stream, cutoff)
                scores = cache[key]
                budgets[budget][policy] = scores, duration
            row = {**prefix, "budget_bytes": budget, "policy": policy,
                   "encoded_bytes": size, "record_ms": duration}
            windows.extend({**row, **score} for score in scores)
            results.append({**row, "first_pass": int(bool(scores) and scores[0]["pass"]),
                            "initial_ms": initial_duration(scores),
                            "available_windows": len(scores)})
        for budget, policies in budgets.items():
            pairs.append({**prefix, "budget_bytes": budget, **compare(policies, full)})
        print(kind, case, reference.prn, "full initial ms", initial_duration(full), flush=True)

    false_continuity = sorted({row["case"] for row in results
                               if row["kind"] == "null" and row["initial_ms"] >= MIN_CONTINUITY_MS})
    false_first = sorted({row["case"] for row in results if row["kind"] == "null" and row["first_pass"]})
    summary = {"cutoff": cutoff, "calibration_fingerprint": frozen["fingerprint"],
               "pocket_sdr": POCKET_COMMIT, "python": platform.python_version(),
               "numpy": np.__version__, "scipy": scipy.__version__, "inputs": inputs,
               "null_captures_passing_first_window": false_first,
               "null_captures_with_80ms_continuity": false_continuity, "by_budget": {}}
    for budget in BUDGETS:
        subset = [row for row in pairs if row["budget_bytes"] == budget and row["kind"] == "flight"]
        operations = sorted({row["case"] for row in subset if row["supported_extra_continuity"]})
        regressions = sum(bool(row["supported_common_window_loss_starts_ms"]) for row in subset)
        summary["by_budget"][str(budget)] = {
            "operations_with_supported_added_continuity": operations,
            "targets_with_common_window_loss": regressions,
            "gate_met": len(operations) >= 2 and regressions == 0 and not false_continuity,
        }
    return summary, windows, results, pairs


def write_table(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/local/tracking-recheck")
    parser.add_argument("--check", action="store_true", help="Check recorded outcome and CSV hashes")
    args = parser.parse_args()
    if args.output.resolve() == ARCHIVE.resolve():
        parser.error("Use a separate output directory to preserve recorded evidence")
    summary, windows, results, pairs = run()
    args.output.mkdir(parents=True, exist_ok=True)
    files = ("windows.csv", "policies.csv", "pairs.csv")
    for name, rows in zip(files, (windows, results, pairs), strict=True):
        write_table(args.output / name, rows)
    summary["csv_sha256"] = {name: hashlib.sha256((args.output / name).read_bytes()).hexdigest()
                             for name in files}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                              encoding="utf-8", newline="\n")
    if args.check:
        expected = json.loads((ARCHIVE / "summary.json").read_text(encoding="utf-8"))
        for field in summary.keys() - {"python"}:
            if summary[field] != expected[field]:
                raise RuntimeError(f"Archived result differs in {field}")
        print("Archived tracking replay reproduced.")
    print(json.dumps(summary["by_budget"], indent=2))


if __name__ == "__main__":
    main()
