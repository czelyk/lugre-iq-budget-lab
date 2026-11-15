import csv
import numpy as np
import pilot

pilot.FREQ=np.arange(-20_000,20_001,50)
iq,_=pilot.read_capture("OP76_0")
stream=pilot.prepare(iq)["original"]
with open("op76_reference.csv","w",newline="",encoding="utf-8") as f:
 w=csv.writer(f)
 w.writerow(["start_ms","PRN","duration_ms","doppler_hz","phase_at_4MSps",
             "peak_mean","nominal_threshold","nominal_candidate"])
 for start in (0,480):
  for row in pilot.acquire(stream[start*pilot.PERIOD:],(31,32),(480,)):
   print(start,row,flush=True)
   w.writerow([start,*row])
