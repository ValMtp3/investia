//go:build !linux

package sandboxrun

import "context"

// Hors Linux : fail-closed, aucune exécution.
func runPlatform(ctx context.Context, code string, o Opts) (Result, error) {
	return Result{}, ErrUnsupported
}

// ChildMain hors Linux : jamais appelé (le parent refuse avant), exit dur.
func ChildMain() {
	panic("sandboxrun child: Linux uniquement")
}

// LandlockABI hors Linux : 0 (indisponible).
func LandlockABI() int { return 0 }
