// Bench P7 : boucle de N apply_order, affiche le temps total en ms.
package main

import (
	"fmt"
	"os"
	"strconv"
	"time"

	"investia-comparisons/go/portfolio"
)

func main() {
	n := 1_000_000
	if len(os.Args) > 1 {
		if v, err := strconv.Atoi(os.Args[1]); err == nil {
			n = v
		}
	}
	cash, qty, avg := 1e12, 0.0, 0.0
	start := time.Now()
	for i := 0; i < n; i++ {
		price := 300.0 + float64(i%100)*0.5
		st, err := portfolio.ApplyOrder(cash, qty, avg, "buy", 1.0, price)
		if err != nil {
			panic(err)
		}
		cash, qty, avg = st.Cash, st.PositionQty, st.PositionAvg
	}
	elapsed := time.Since(start)
	fmt.Printf("{\"iterations\": %d, \"total_ms\": %.3f, \"ns_per_op\": %.1f}\n", n, float64(elapsed.Milliseconds())+float64(elapsed.Microseconds()%1000)/1000.0, float64(elapsed.Nanoseconds())/float64(n))
}
