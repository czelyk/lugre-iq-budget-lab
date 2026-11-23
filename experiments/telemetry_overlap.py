"""Check whether LuGRE flight measurements can label archived GPS L1 snapshots."""

import argparse
from bisect import bisect_left
from collections import defaultdict
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import re
import sys
from struct import unpack_from
from xml.etree import ElementTree
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.fetch_inputs import ARCHIVE, CHECKSUM, ensure_archive

GPS_EPOCH = datetime(1980, 1, 6, tzinfo=UTC)
GPS_MINUS_UTC = timedelta(seconds=18)  # All observations are from Jan–Mar 2025.
CONTEXT_MARGIN = timedelta(seconds=1)  # One full published RAW cadence.
RAW_NAME = re.compile(r"_OP(\d+_\d+)\.txt$")
IQ_NAME = re.compile(r"IQS_L1_.*_\d+MS_._OP(\d+_\d+)\.(bin|sdrx)$")
RAW_LINE = re.compile(rb"rxTime: (\S+) measures: \[(.*)\]")
MEASUREMENT = re.compile(rb"svid: (\d+) [^\[\]]*?signalId: (\d+) fdRaw: (\S+)")
# These are the four frozen targets from tracking_recheck.py.
RECHECK_TARGETS = (("23_0", 0, 21), ("76_0", 960, 32), ("77_1", 0, 6), ("77_1", 0, 14))
RECHECK_LENGTH_MS = 240


def to_utc(gps_seconds):
    return GPS_EPOCH + timedelta(seconds=gps_seconds) - GPS_MINUS_UTC


def load_captures(archive):
    metadata_by_operation = {}
    binaries_by_operation = {}
    for member in sorted(archive.namelist()):
        match = IQ_NAME.fullmatch(Path(member).name)
        if match:
            operation, extension = match.groups()
            members = metadata_by_operation if extension == "sdrx" else binaries_by_operation
            if operation in members:
                raise ValueError(f"Multiple L1 {extension} files for {operation}")
            members[operation] = member
    if metadata_by_operation.keys() != binaries_by_operation.keys():
        raise ValueError("The L1 metadata and binary operation lists differ")

    captures = {}
    for operation, member in binaries_by_operation.items():
        metadata_member = metadata_by_operation[operation]
        metadata = ElementTree.fromstring(archive.read(metadata_member))
        metadata_start = datetime.fromisoformat(metadata.findtext("{*}session/{*}toa"))
        with archive.open(member) as source:
            header = source.read(62)
        gps_seconds, count, _, _, _, bits, rate, _, _, _ = unpack_from("<d2IBHB4d", header, 10)
        if (not header.startswith(b"qIQS") or bits not in (4, 8) or rate <= 0
                or archive.getinfo(member).file_size != 65 + count * bits // 4):
            raise ValueError(f"Unexpected I/Q packet layout in {member}")
        start = to_utc(gps_seconds)
        offset = (metadata_start - start).total_seconds()
        if abs(offset) > 0.001:
            raise ValueError(f"I/Q packet and SDRX timestamps differ by more than 1 ms in {member}")
        end = start + timedelta(seconds=count / rate)
        captures[operation] = (member, start, end, offset)
    return captures


def load_raw_timelines(archive):
    """Index the RAW message epochs and the actual GPS L1 C/A tracking measurements."""
    epochs = []
    gps_l1 = []
    by_prn = defaultdict(list)
    raw_members = []
    target_prns = {prn for _, _, prn in RECHECK_TARGETS}
    for member in sorted(archive.namelist()):
        if "/TLM/TLM_RAW_" not in member or not member.endswith(".txt"):
            continue
        operation = RAW_NAME.search(member)[1]
        raw_members.append(member)
        with archive.open(member.removesuffix(".txt") + ".bin") as binary:
            first_packet_gps = unpack_from("<d", binary.read(18), 10)[0]
        with archive.open(member) as source:
            for line_number, line in enumerate(source):
                match = RAW_LINE.search(line)
                if match is None:
                    if line.strip():
                        raise ValueError(f"Unrecognized RAW line in {member}")
                    continue
                gps_seconds = float(match[1])
                if line_number == 0 and abs(gps_seconds - first_packet_gps) > 0.00001:
                    raise ValueError(f"First RAW text and packet timestamps differ in {member}")
                utc = to_utc(gps_seconds)
                epochs.append((utc, operation))
                matches = MEASUREMENT.findall(match[2])
                if len(matches) != match[2].count(b"svid:"):
                    raise ValueError(f"Unrecognized RAW measurement in {member} at {gps_seconds}")
                l1_signals = [(int(prn), float(doppler)) for prn, signal, doppler in matches if signal == b"0"]
                if l1_signals:
                    gps_l1.append((utc, operation))
                for prn, doppler in l1_signals:
                    if prn in target_prns:
                        by_prn[prn].append((utc, operation, doppler))
    return raw_members, sorted(epochs), sorted(gps_l1), {
        prn: sorted(rows) for prn, rows in by_prn.items()
    }


def coverage(timeline, start, end):
    first = bisect_left(timeline, (start,))
    stop = bisect_left(timeline, (end,))
    near_start = bisect_left(timeline, (start - CONTEXT_MARGIN,))
    near_end = bisect_left(timeline, (end + CONTEXT_MARGIN + timedelta(microseconds=1),))
    candidates = timeline[max(first - 1, 0):first + 1]
    result = {"inside": stop - first, "within_1_s_including_inside": near_end - near_start, "nearest": None}
    if candidates:
        def signed_gap(row):
            utc = row[0]
            boundary = start if utc < start else end
            if start <= utc < end:
                return 0.0
            return (utc - boundary).total_seconds()

        nearest = min(candidates, key=lambda row: abs(signed_gap(row)))
        result["nearest"] = {
            "utc": nearest[0].isoformat(),
            "operation": nearest[1],
            "gap_to_window_s": signed_gap(nearest),
        }
        if len(nearest) == 3:
            result["nearest"]["doppler_hz"] = nearest[2]
    return result


def audit(archive_path):
    with ZipFile(archive_path) as archive:
        captures = load_captures(archive)
        members, epochs, gps_l1, by_prn = load_raw_timelines(archive)
    if not captures or not epochs or not gps_l1:
        raise ValueError("Missing I/Q metadata or usable RAW messages")

    windows = []
    for operation, (member, start, end, offset) in captures.items():
        windows.append({
            "operation": operation, "member": member, "start_utc": start.isoformat(), "end_utc": end.isoformat(),
            "sdrx_minus_packet_start_s": offset,
            "any_raw_epoch": coverage(epochs, start, end),
            "gps_l1_ca_epoch": coverage(gps_l1, start, end),
        })
    targets = []
    for operation, offset_ms, prn in RECHECK_TARGETS:
        _, start, capture_end, _ = captures[operation]
        start += timedelta(milliseconds=offset_ms)
        end = start + timedelta(milliseconds=RECHECK_LENGTH_MS)
        if end > capture_end:
            raise ValueError(f"Recheck window outside capture for {operation}")
        targets.append({
            "operation": operation, "gps_prn": prn, "start_utc": start.isoformat(), "end_utc": end.isoformat(),
            "same_prn_raw": coverage(by_prn.get(prn, []), start, end),
        })
    return {
        "archive_md5": CHECKSUM,
        "raw_member_count": len(members),
        "raw_members": members,
        "raw_epoch_count": len(epochs),
        "gps_l1_ca_epoch_count": len(gps_l1),
        "l1_captures": windows,
        "tracking_recheck_targets": targets,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare with the saved JSON without writing files.")
    parser.add_argument("--out", type=Path, default=ROOT / "results/local/telemetry-overlap/overlap.json")
    options = parser.parse_args()
    ensure_archive()
    report = audit(Path(os.environ.get("LUGRE_ARCHIVE", ARCHIVE)))
    if options.check:
        recorded = ROOT / "results/telemetry-overlap/overlap.json"
        if report != json.loads(recorded.read_text(encoding="utf-8")):
            raise SystemExit("Recorded overlap results differ.")
        print("Recorded overlap results verified.")
    else:
        options.out.parent.mkdir(parents=True, exist_ok=True)
        options.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
