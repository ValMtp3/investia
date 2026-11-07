// Package portfolio : réécriture Go du calcul de portefeuille simulé
// (P7, étape 6.3) — fidèle à backend/src/investia/portfolio/calc.py (D35).
package portfolio

import (
	"fmt"
	"math"
)

// FeeRate : frais proportionnels 0,1 % (D35).
const FeeRate = 0.001

// InsufficientFunds : cash insuffisant (buy) ou position insuffisante (sell).
type InsufficientFunds struct{ Msg string }

func (e *InsufficientFunds) Error() string { return e.Msg }

// State : état du portefeuille après un ordre.
type State struct {
	Cash         float64
	PositionQty  float64
	PositionAvg  float64
	Fee          float64
}

// Total : valeur totale (cash + position au prix moyen).
func (s State) Total() float64 { return s.Cash + s.PositionQty*s.PositionAvg }

// round2 arrondit à 2 décimales comme Python round(x, 2).
func round2(x float64) float64 { return math.Round(x*100) / 100 }

// ApplyOrder applique un ordre simulé (dernier prix connu + frais 0,1 %).
func ApplyOrder(cash, positionQty, positionAvg float64, side string, quantity, priceEur float64) (State, error) {
	if quantity <= 0 {
		return State{}, fmt.Errorf("quantité invalide")
	}
	if priceEur <= 0 {
		return State{}, fmt.Errorf("prix invalide")
	}
	amount := priceEur * quantity
	fee := round2(amount * FeeRate)
	switch side {
	case "buy":
		if cash < amount+fee {
			return State{}, &InsufficientFunds{Msg: fmt.Sprintf("cash %.2f insuffisant pour %.2f (montant + frais)", cash, amount+fee)}
		}
		newQty := positionQty + quantity
		newAvg := 0.0
		if newQty != 0 {
			newAvg = (positionQty*positionAvg + quantity*priceEur) / newQty
		}
		return State{Cash: cash - amount - fee, PositionQty: newQty, PositionAvg: newAvg, Fee: fee}, nil
	case "sell":
		if positionQty < quantity {
			return State{}, &InsufficientFunds{Msg: fmt.Sprintf("position %.2f insuffisante pour vendre %.2f", positionQty, quantity)}
		}
		return State{Cash: cash + amount - fee, PositionQty: positionQty - quantity, PositionAvg: positionAvg, Fee: fee}, nil
	default:
		return State{}, fmt.Errorf("side inconnu : %s", side)
	}
}
