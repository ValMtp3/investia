package portfolio

import (
	"math"
	"testing"
)

const eps = 1e-9

func approx(a, b float64) bool { return math.Abs(a-b) < eps }

// Mêmes vecteurs que backend/tests/test_portfolio_calc.py.

func TestBuyUpdatesCashPositionAndFee(t *testing.T) {
	s, err := ApplyOrder(10_000.0, 0.0, 0.0, "buy", 10.0, 308.34)
	if err != nil {
		t.Fatal(err)
	}
	amount := 10 * 308.34
	fee := round2(amount * 0.001)
	if !approx(s.Fee, fee) || !approx(s.Cash, 10_000.0-amount-fee) || s.PositionQty != 10.0 || !approx(s.PositionAvg, 308.34) {
		t.Fatalf("état inattendu: %+v", s)
	}
	if !approx(s.Total(), s.Cash+10*308.34) {
		t.Fatalf("total inattendu: %v", s.Total())
	}
}

func TestBuyAveragesPriceOnExistingPosition(t *testing.T) {
	s, err := ApplyOrder(5_000.0, 10.0, 300.0, "buy", 10.0, 320.0)
	if err != nil {
		t.Fatal(err)
	}
	if !approx(s.PositionAvg, 310.0) || s.PositionQty != 20.0 {
		t.Fatalf("moyenne inattendue: %+v", s)
	}
}

func TestSellCreditsCashAndKeepsAvg(t *testing.T) {
	s, err := ApplyOrder(1_000.0, 10.0, 300.0, "sell", 4.0, 320.0)
	if err != nil {
		t.Fatal(err)
	}
	amount := 4 * 320.0
	fee := amount * 0.001
	if !approx(s.Cash, 1_000.0+amount-fee) || s.PositionQty != 6.0 || !approx(s.PositionAvg, 300.0) {
		t.Fatalf("vente inattendue: %+v", s)
	}
}

func TestBuyWithoutEnoughCashRaises(t *testing.T) {
	_, err := ApplyOrder(100.0, 0.0, 0.0, "buy", 10.0, 308.34)
	if err == nil {
		t.Fatal("attendu InsufficientFunds")
	}
}

func TestSellMoreThanPositionRaises(t *testing.T) {
	_, err := ApplyOrder(1_000.0, 2.0, 300.0, "sell", 5.0, 320.0)
	if err == nil {
		t.Fatal("attendu InsufficientFunds")
	}
}

func TestFractionalQuantitiesAllowed(t *testing.T) {
	s, err := ApplyOrder(10_000.0, 0.0, 0.0, "buy", 0.5, 308.34)
	if err != nil {
		t.Fatal(err)
	}
	if s.PositionQty != 0.5 {
		t.Fatalf("fraction inattendue: %+v", s)
	}
}
