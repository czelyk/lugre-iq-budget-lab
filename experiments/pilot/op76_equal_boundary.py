"""Close the duration gap at the first lossless detection's actual byte budget."""
import csv
import zlib
import numpy as np
import pilot

start_ms = 960
pilot.FREQ = np.arange(-20_000, 20_001, 50)
iq, raw = pilot.read_capture("OP76_0")
offset = start_ms * 8000
budget = len(zlib.compress(raw[offset:offset+320*8000], 9))
frames_ms = budget // 4000 // 10 * 10
variants = pilot.prepare(iq[offset:offset+frames_ms*8000])
with open("op76_equal_boundary.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["policy", "budget_bytes", "duration_ms", "actual_bytes", "PRN",
                     "doppler_hz", "phase_at_4MSps", "peak_mean", "nominal_threshold",
                     "nominal_candidate"])
    for policy in ("requantized", "lower_rate"):
        for prn,d,hz,phase,stat,cut,hit in pilot.acquire(variants[policy], (32,), (frames_ms,)):
            row = [policy,budget,d,d*4000,prn,hz,phase,stat,cut,hit]
            print(row,flush=True)
            writer.writerow(row)
        f.flush()
