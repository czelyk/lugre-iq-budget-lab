import csv
import heapq
from collections import Counter
import pilot

# Fixed Huffman code lengths learned on the first 10 ms from the positive control.
def code_lengths(counts):
    q = [(counts.get(b,0)+1, b, b) for b in range(256)]
    heapq.heapify(q)
    for order in range(256,511):
        a, _, left = heapq.heappop(q)
        b, _, right = heapq.heappop(q)
        heapq.heappush(q, (a+b,order,(left,right)))
    def visit(node, depth):
        if isinstance(node,int):
            yield node, depth
        else:
            for child in node:
                yield from visit(child,depth+1)
    return dict(visit(q[0][2],0))

_, prefix = pilot.read_capture("OP2_0")
lengths = code_lengths(Counter(prefix[:80_000]))
with open("static_huffman_size.csv","w",encoding="utf-8",newline="") as f:
    w=csv.writer(f)
    w.writerow(["operation","budget_bytes","max_duration_ms","encoded_bytes","codebook_bytes","format"])
    for op in ("OP2_0","OP23_0","OP38_0","OP40_0","OP76_0"):
        _, raw = pilot.read_capture(op)
        sizes = {d:256+(7+sum(lengths[b]*n for b,n in Counter(raw[:d*8000]).items()))//8
                 for d in range(10,241,10)}
        for budget in (480000,960000):
            d=max(d for d,s in sizes.items() if s<=budget)
            w.writerow([op,budget,d,sizes[d],256,"analytical canonical lengths; no encoding timed"])
            print(op,budget,d,sizes[d],flush=True)
