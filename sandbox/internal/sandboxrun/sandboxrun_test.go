package sandboxrun

import (
	"context"
	"errors"
	"runtime"
	"strings"
	"testing"
	"time"
)

// abiOK : vrai si le noyau a Landlock ABI v6 (run réel possible).
func abiOK() bool {
	return runtime.GOOS == "linux" && LandlockABI() >= 6
}

func TestRunHelloWorld(t *testing.T) {
	if !abiOK() {
		t.Skipf("Landlock ABI < 6 ou hors Linux (ABI=%d) : run réel skippé, fail-closed testé ailleurs", LandlockABI())
	}
	res, err := Run(context.Background(), "print('hello-sandbox')", Opts{Timeout: 10 * time.Second})
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if res.ExitCode != 0 {
		t.Fatalf("exit=%d stderr=%s", res.ExitCode, res.Stderr)
	}
	if !strings.Contains(res.Stdout, "hello-sandbox") {
		t.Fatalf("stdout inattendu: %q", res.Stdout)
	}
	if res.Backend != "sidecar-go" {
		t.Fatalf("backend=%q", res.Backend)
	}
}

func TestFailClosedSansABIv6(t *testing.T) {
	if abiOK() {
		t.Skip("ABI v6 présent ici")
	}
	_, err := Run(context.Background(), "print(1)", Opts{Timeout: time.Second})
	if !errors.Is(err, ErrUnsupported) {
		t.Fatalf("attendu ErrUnsupported (fail-closed), obtenu %v", err)
	}
}

func TestReseauRefuse(t *testing.T) {
	if !abiOK() {
		t.Skip("Landlock ABI < 6")
	}
	code := "import socket\nsocket.create_connection(('1.1.1.1', 443), timeout=3)\nprint('NON')"
	res, err := Run(context.Background(), code, Opts{Timeout: 15 * time.Second})
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if res.ExitCode == 0 || strings.Contains(res.Stdout, "NON") {
		t.Fatalf("le réseau aurait dû être refusé: exit=%d stdout=%q stderr=%q", res.ExitCode, res.Stdout, res.Stderr)
	}
}

func TestEcritureHorsTmpRefusee(t *testing.T) {
	if !abiOK() {
		t.Skip("Landlock ABI < 6")
	}
	code := "open('/etc/pwned','w').write('x')\nprint('NON')"
	res, err := Run(context.Background(), code, Opts{Timeout: 10 * time.Second})
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if res.ExitCode == 0 || strings.Contains(res.Stdout, "NON") {
		t.Fatalf("écriture hors tmpdir aurait dû être refusée: exit=%d stdout=%q stderr=%q", res.ExitCode, res.Stdout, res.Stderr)
	}
}

func TestTimeoutTueLeProcess(t *testing.T) {
	if !abiOK() {
		t.Skip("Landlock ABI < 6")
	}
	start := time.Now()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	res, err := Run(ctx, "while True: pass", Opts{Timeout: 2 * time.Second})
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if time.Since(start) > 10*time.Second {
		t.Fatalf("timeout non respecté (%s)", time.Since(start))
	}
	if res.ExitCode == 0 {
		t.Fatalf("la boucle infinie aurait dû être tuée: %+v", res)
	}
}

func TestCodeTropLongRefuse(t *testing.T) {
	_, err := Run(context.Background(), strings.Repeat("x", MaxCodeChars+1), Opts{})
	if err == nil {
		t.Fatal("code trop long doit être refusé avant exécution")
	}
}

// 24 (scan sécurité, CWE-400) : le timeout demandé par le client est clampé.
func TestClampTimeout(t *testing.T) {
	cases := []struct {
		in, want time.Duration
	}{
		{0, DefaultTimeout},
		{-5 * time.Second, DefaultTimeout},
		{500 * time.Millisecond, MinTimeout},
		{10 * time.Second, 10 * time.Second},
		{time.Hour, MaxTimeout},
	}
	for _, c := range cases {
		if got := ClampTimeout(c.in); got != c.want {
			t.Errorf("ClampTimeout(%v) = %v, want %v", c.in, got, c.want)
		}
	}
}
