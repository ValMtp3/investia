// Package sandboxrun exécute du code Python non fiable dans une sandbox noyau
// (Landlock + seccomp-bpf + rlimits), fail-closed.
//
// 23i : le sidecar délègue chaque run à un process helper (ré-exec de soi-même,
// sous-commande "__child") qui applique Landlock/seccomp/rlimits sur lui-même
// puis exec python. Sans Landlock ABI v6 (Linux >= 6.12) : ErrUnsupported,
// AUCUNE exécution (fail-closed).
package sandboxrun

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"syscall"
	"time"
)

// ErrUnsupported : isolation noyau indisponible (hors Linux, ou Landlock ABI < 6).
// Fail-closed : l'appelant doit refuser l'exécution, jamais dégrader.
var ErrUnsupported = errors.New("sandboxrun: isolation noyau indisponible (Linux >= 6.12, Landlock ABI v6 requis)")

// Passerelles parent -> child (le code passe par env, < 128 Ko par var).
const (
	childArg     = "__child"
	envSBCode    = "INVESTIA_SB_CODE"
	envSBWorkdir = "INVESTIA_SB_WORKDIR"
	envSBPython  = "INVESTIA_SB_PYTHON"
	envSBCPU     = "INVESTIA_SB_CPU"
	envSBMem     = "INVESTIA_SB_MEM"
	envSBNOFile  = "INVESTIA_SB_NOFILE"
	envSBFSize   = "INVESTIA_SB_FSIZE"
)

const (
	// MaxCodeChars : borne dure côté sidecar (le pre-check Python 13c filtre avant).
	MaxCodeChars = 10_000
	// MaxOutputChars par défaut, tronqué par le parent.
	DefaultMaxOutputChars = 20_000
	DefaultTimeout        = 10 * time.Second
	// 24 (scan sécurité, CWE-400) : bornes du timeout demandé par le client.
	MinTimeout = 1 * time.Second
	MaxTimeout = 60 * time.Second
)

// ClampTimeout borne un timeout demandé : <= 0 -> défaut, puis [MinTimeout, MaxTimeout].
func ClampTimeout(d time.Duration) time.Duration {
	if d <= 0 {
		return DefaultTimeout
	}
	if d < MinTimeout {
		return MinTimeout
	}
	if d > MaxTimeout {
		return MaxTimeout
	}
	return d
}

// Opts : limites d'un run.
type Opts struct {
	Timeout        time.Duration
	MaxOutputChars int
	CPUSeconds     uint64
	MemoryBytes    uint64
	MaxOpenFiles   uint64
	MaxFileBytes   uint64
	PythonBin      string // défaut : python3 du PATH (résolu par le parent)
}

func (o *Opts) withDefaults() Opts {
	out := *o
	if out.Timeout <= 0 {
		out.Timeout = DefaultTimeout
	}
	if out.MaxOutputChars <= 0 {
		out.MaxOutputChars = DefaultMaxOutputChars
	}
	if out.CPUSeconds == 0 {
		out.CPUSeconds = 10
	}
	if out.MemoryBytes == 0 {
		out.MemoryBytes = 512 * 1024 * 1024
	}
	if out.MaxOpenFiles == 0 {
		out.MaxOpenFiles = 64
	}
	if out.MaxFileBytes == 0 {
		out.MaxFileBytes = 10 * 1024 * 1024
	}
	if out.PythonBin == "" {
		out.PythonBin = "python3"
	}
	return out
}

// Result : sortie d'un run sandboxé.
type Result struct {
	ExitCode  int    `json:"exit_code"`
	Stdout    string `json:"stdout"`
	Stderr    string `json:"stderr"`
	Truncated bool   `json:"truncated"`
	Backend   string `json:"backend"`
}

// Run exécute code dans la sandbox. ctx dépassé -> process tué (groupe), Timeout true.
func Run(ctx context.Context, code string, opts Opts) (Result, error) {
	if len(code) > MaxCodeChars {
		return Result{}, fmt.Errorf("code trop long (%d > %d car.)", len(code), MaxCodeChars)
	}
	return runPlatform(ctx, code, opts.withDefaults())
}

// runChild : orchestre le helper child (défini par plateforme).
func runChild(ctx context.Context, code string, o Opts) (Result, error) {
	tmpdir, err := os.MkdirTemp("", "investia-sb-")
	if err != nil {
		return Result{}, err
	}
	defer os.RemoveAll(tmpdir)

	pythonPath, err := exec.LookPath(o.PythonBin)
	if err != nil {
		return Result{}, fmt.Errorf("python introuvable: %w", err)
	}
	self, err := os.Executable()
	if err != nil {
		return Result{}, err
	}

	cmd := exec.CommandContext(ctx, self, childArg)
	cmd.Dir = tmpdir
	cmd.Env = []string{
		"PATH=/usr/local/bin:/usr/bin:/bin",
		"LANG=C.UTF-8",
		"HOME=" + tmpdir,
		"TMPDIR=" + tmpdir,
		envSBCode + "=" + code,
		envSBWorkdir + "=" + tmpdir,
		envSBPython + "=" + pythonPath,
		envSBCPU + "=" + fmt.Sprint(o.CPUSeconds),
		envSBMem + "=" + fmt.Sprint(o.MemoryBytes),
		envSBNOFile + "=" + fmt.Sprint(o.MaxOpenFiles),
		envSBFSize + "=" + fmt.Sprint(o.MaxFileBytes),
	}
	// Groupe de process dédié : le timeout tue tout le arbre.
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return Result{}, err
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return Result{}, err
	}
	if err := cmd.Start(); err != nil {
		return Result{}, err
	}
	outC := make(chan []byte, 1)
	errC := make(chan []byte, 1)
	go func() { b, _ := readAll(stdout, o.MaxOutputChars); outC <- b }()
	go func() { b, _ := readAll(stderr, o.MaxOutputChars); errC <- b }()

	waitC := make(chan error, 1)
	go func() { waitC <- cmd.Wait() }()
	timedOut := false
	select {
	case err := <-waitC:
		_ = err // exit code géré ci-dessous
	case <-ctx.Done():
		timedOut = true
		if cmd.Process != nil {
			// 24 (scan sécurité, CWE-400) : tue le process direct (setsid
			// éventuel du child le mettrait hors du groupe) puis tout le groupe.
			_ = syscall.Kill(cmd.Process.Pid, syscall.SIGKILL)
			_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		}
		<-waitC
	}
	out, errB := <-outC, <-errC
	res := Result{
		ExitCode:  exitCode(cmd, timedOut),
		Stdout:    string(out),
		Stderr:    string(errB),
		Truncated: len(out) >= o.MaxOutputChars || len(errB) >= o.MaxOutputChars,
		Backend:   "sidecar-go",
	}
	if timedOut {
		res.Stderr += fmt.Sprintf("\n[sidecar] timeout après %s (processus tué)", o.Timeout)
		res.ExitCode = -1
	}
	return res, nil
}

func exitCode(cmd *exec.Cmd, timedOut bool) int {
	if timedOut {
		return -1
	}
	if cmd.ProcessState == nil {
		return -1
	}
	return cmd.ProcessState.ExitCode()
}

func readAll(r interface{ Read([]byte) (int, error) }, limit int) ([]byte, error) {
	buf := make([]byte, 0, 4096)
	tmp := make([]byte, 4096)
	for len(buf) < limit {
		n, err := r.Read(tmp)
		if n > 0 {
			buf = append(buf, tmp[:n]...)
		}
		if err != nil {
			break
		}
	}
	return buf, nil
}
