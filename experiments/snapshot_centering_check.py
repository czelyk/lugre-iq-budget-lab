"""Check whether simple receive-side centering explains shared-horizon differences."""
import argparse
import csv
import json
from itertools import chain
from pathlib import Path
import sys

from snapshot_correlation import (
    CONTROL, FLIGHT, PERIOD, ROOT, Correlator, encoded_policies, fingerprint,
    read_capture, synthesize,
)


def compare(out, sdr_code):
    frozen = json.loads((out/"cutoff.json").read_text(encoding="utf-8"))
    if frozen["fingerprint"] != fingerprint():
        raise ValueError("The initial score and threshold differ from this checkout")
    threshold = frozen["cutoff"]
    flight = ((r.operation, r, *read_capture(r.operation)) for r in FLIGHT
              if r.operation in {"OP22_0","OP32_0"})
    noise = ((f"noise-{n}", CONTROL, *synthesize(sdr_code, n)) for n in range(6100,6108))
    with (out/"centering_check.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("case","policy","centering","dc_i","dc_q","score_20ms","score_40ms",
                         "passes_both"))
        for case, ref, iq, raw in chain(flight,noise):
            correlator = Correlator(ref,sdr_code)
            for budget, policy, _, _, stream in encoded_policies(iq,raw):
                if budget != 480_000 or policy == "raw":
                    continue
                ms60 = stream[:60*PERIOD]
                dc = ms60[:10*PERIOD].mean()
                for use in (False,True):
                    centered = ms60 - dc if use else ms60
                    scores = [w[3] for w in correlator.windows(centered)][1:]
                    writer.writerow((case,policy,int(use),dc.real,dc.imag,*scores,
                                     int(all(s > threshold for s in scores))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"results"/"local"/"snapshot-correlation")
    args = parser.parse_args()
    sys.path.insert(0,str(ROOT/".cache"/"PocketSDR"/"python"))
    import sdr_code
    compare(args.output,sdr_code)
