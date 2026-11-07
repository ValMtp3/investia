"""Benchmark P7 (étape 6.3) : apply_order en Python vs Go, même boucle.

Lance N itérations côté Python (investia.portfolio.calc.apply_order) et côté
Go (binaire compilé comparisons/go/cmd/bench), produit bench_results.json.
"""

import json
import subprocess
import time
from pathlib import Path

from investia.portfolio.calc import apply_order

HERE = Path(__file__).resolve().parent
GO_DIR = HERE / "go"
RESULTS = HERE / "bench_results.json"
N = 1_000_000


def bench_python(n: int) -> dict:
    cash, qty, avg = 1e12, 0.0, 0.0
    start = time.perf_counter()
    for i in range(n):
        price = 300.0 + (i % 100) * 0.5
        st = apply_order(
            cash=cash,
            position_qty=qty,
            position_avg=avg,
            side="buy",
            quantity=1.0,
            price_eur=price,
        )
        cash, qty, avg = st.cash, st.position_qty, st.position_avg
    elapsed = time.perf_counter() - start
    return {
        "iterations": n,
        "total_ms": round(elapsed * 1000, 3),
        "ns_per_op": round(elapsed * 1e9 / n, 1),
    }


def bench_go(n: int) -> dict:
    subprocess.run(
        ["go", "build", "-o", str(HERE / "bench_go_bin"), "./cmd/bench"],
        cwd=GO_DIR,
        check=True,
    )
    out = subprocess.run(
        [str(HERE / "bench_go_bin"), str(n)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout.strip())


def main() -> None:
    py = bench_python(N)
    go = bench_go(N)
    results = {
        "component": "portfolio.calc.apply_order (P7)",
        "iterations": N,
        "python": py,
        "go": go,
        "speedup": round(py["ns_per_op"] / go["ns_per_op"], 1),
    }
    RESULTS.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
