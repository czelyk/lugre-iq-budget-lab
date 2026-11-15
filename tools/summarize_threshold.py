"""Summarize the frozen acquisition decisions and independently check the tables."""
import argparse
import csv
import json
from pathlib import Path


def rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def report(folder):
    frozen = json.loads((folder/"frozen_threshold.json").read_text(encoding="utf-8"))
    cal = rows(folder/"calibration_decoy_maxima.csv")
    audit = rows(folder/"validation_decoy_maxima.csv")
    scores = rows(folder/"validation_scores.csv")
    threshold = frozen["threshold"]
    assert sorted(float(r["max_over_policies_offsets"]) for r in cal)[frozen["rank"]-1] == threshold
    assert len(cal) == frozen["trials"] and len(audit) == 16
    print(f"Frozen score {threshold:.6f}. Audit exceedances "
          f"{sum(float(r['max_over_policies_offsets']) > threshold for r in audit)}/{len(audit)}.")
    fields = ("operation", "prn", "policy", "bytes", "record_ms", "pass_offset_0",
              "pass_offset_5", "pass_both")
    groups = {}
    for row in scores:
        assert int(row["actual_bytes"]) <= 960_000
        assert int(row["above_frozen"]) == int(float(row["tail_score"]) > threshold)
        if row["reference_match"]:
            key = (row["operation"], row["code"], row["policy"])
            offsets = groups.setdefault(key, {})
            offsets[int(row["offset_ms"])] = row
    with (folder/"target_decisions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        for key, offsets in groups.items():
            assert set(offsets) == {0,5}
            a,b = offsets[0], offsets[5]
            assert a["blocks"] == b["blocks"]
            passes = [int(r["reference_match"]) and int(r["above_frozen"]) for r in (a,b)]
            decision = (*key, a["actual_bytes"], a["record_ms"], *passes, int(all(passes)))
            writer.writerow(decision)
            print(*decision)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    report(parser.parse_args().folder)
