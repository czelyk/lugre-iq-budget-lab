"""Compare byte threshold for a weak, externally reported PRN in two later windows."""
import csv
import zlib

import numpy as np
import pilot

pilot.FREQ = np.arange(-20_000,20_001,50)
DURATIONS=tuple(range(60,401,20))

iq, raw = pilot.read_capture("OP76_0")
with open("op76_byte_curve.csv","w",newline="",encoding="utf-8") as f:
    writer=csv.writer(f)
    writer.writerow(["start_ms","duration_ms","policy","bytes","doppler_hz","phase",
                     "peak_mean","nominal_threshold","matching_peak"])
    for start in (960,1440):
        offset=start*8000
        # Each policy needs to work on an independently encodable input segment.
        data=pilot.prepare(iq[offset:offset+400*8000])
        phase_expect = 768 - round(3450 / 1_575_420_000 * 4_000_000 * start/1000)
        for policy, stream in data.items():
            for _, d, hz, phase, stat, cut, hit in pilot.acquire(stream,(32,),DURATIONS):
                matches = int(hit and abs(hz-3450)<=250 and abs(phase-phase_expect)<=8)
                size= (8000 if policy=="original" else 4000)*d
                writer.writerow([start,d,policy,size,hz,phase,stat,cut,matches])
                if policy=="original":
                    size=len(zlib.compress(raw[offset:offset+8000*d],9))
                    writer.writerow([start,d,"lossless",size,hz,phase,stat,cut,matches])
            f.flush()
            print(start,policy,"done",flush=True)
