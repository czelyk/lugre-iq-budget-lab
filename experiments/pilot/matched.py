"""Follow-up: test a same-byte lossless competitor on independently reported PRNs."""
import csv
import sys
import zlib
import numpy as np
import pilot

REFS = {"OP2_0":(18,24), "OP23_0":(21,), "OP40_0":(25,), "OP76_0":(31,32)}
BUDGETS = (480_000, 960_000)

def encoded_sizes(raw):
    return {d: len(zlib.compress(raw[:d*8_000],9)) for d in range(10,241,10)}

def main():
    # A separate sensitivity check uses 50 Hz spacing, fixed for all policies.
    pilot.FREQ = np.arange(-20_000, 20_001, 50)
    operations = sys.argv[1:] or list(REFS)
    filename = f"matched_{operations[0]}.csv" if len(operations) == 1 else "matched_baselines.csv"
    with open(filename,"w",encoding="utf-8",newline="") as f:
        w=csv.writer(f)
        w.writerow(["operation","policy","budget_bytes","actual_bytes","duration_ms",
                    "PRN","doppler_hz","phase_at_4MSps","peak_mean","nominal_threshold",
                    "nominal_candidate"])
        for op in operations:
            prns = REFS[op]
            iq, raw = pilot.read_capture(op)
            sizes = encoded_sizes(raw)
            duration = tuple(max(d for d,s in sizes.items() if s<=budget)
                             for budget in BUDGETS)
            prepared = pilot.prepare(iq)
            variants = {
                "original": ("original", (60,120), BUDGETS),
                "lossless": ("original", duration, tuple(sizes[d] for d in duration)),
                "requantized": ("requantized",(120,240),BUDGETS),
                "lower_rate": ("lower_rate",(120,240),BUDGETS),
            }
            for policy,(key,durations,bytes_used) in variants.items():
                for prn,d,freq,phase,stat,cut,hit in pilot.acquire(prepared[key],prns,durations):
                    j=durations.index(d)
                    w.writerow([op,policy,BUDGETS[j],bytes_used[j],d,prn,freq,phase,
                                stat,cut,hit])
                f.flush()
                print(op, policy, "done",flush=True)

if __name__=="__main__":
    main()
