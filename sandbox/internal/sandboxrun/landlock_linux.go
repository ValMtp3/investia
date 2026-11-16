//go:build linux

package sandboxrun

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"unsafe"

	"golang.org/x/sys/unix"
)

// Constantes Landlock non encore wrappées par x/sys (ABI stable).
const (
	landlockCreateRulesetVersion = 1 << 0 // LANDLOCK_CREATE_RULESET_VERSION
	landlockABIV6                = 6
)

// Masques d'accès FS gérés par le ruleset (deny par défaut hors règles).
const handledAccessFS = unix.LANDLOCK_ACCESS_FS_EXECUTE |
	unix.LANDLOCK_ACCESS_FS_WRITE_FILE |
	unix.LANDLOCK_ACCESS_FS_READ_FILE |
	unix.LANDLOCK_ACCESS_FS_READ_DIR |
	unix.LANDLOCK_ACCESS_FS_REMOVE_DIR |
	unix.LANDLOCK_ACCESS_FS_REMOVE_FILE |
	unix.LANDLOCK_ACCESS_FS_MAKE_CHAR |
	unix.LANDLOCK_ACCESS_FS_MAKE_DIR |
	unix.LANDLOCK_ACCESS_FS_MAKE_REG |
	unix.LANDLOCK_ACCESS_FS_MAKE_SOCK |
	unix.LANDLOCK_ACCESS_FS_MAKE_FIFO |
	unix.LANDLOCK_ACCESS_FS_MAKE_BLOCK |
	unix.LANDLOCK_ACCESS_FS_MAKE_SYM |
	unix.LANDLOCK_ACCESS_FS_REFER |
	unix.LANDLOCK_ACCESS_FS_TRUNCATE

// Réseau TCP géré (ABI v6) : sans règle NET_SERVICE, bind/connect sont refusés.
const handledAccessNet = unix.LANDLOCK_ACCESS_NET_BIND_TCP |
	unix.LANDLOCK_ACCESS_NET_CONNECT_TCP

const (
	fsReadExec = unix.LANDLOCK_ACCESS_FS_EXECUTE |
		unix.LANDLOCK_ACCESS_FS_READ_FILE |
		unix.LANDLOCK_ACCESS_FS_READ_DIR
	fsWriteTmp = unix.LANDLOCK_ACCESS_FS_WRITE_FILE |
		unix.LANDLOCK_ACCESS_FS_REMOVE_DIR |
		unix.LANDLOCK_ACCESS_FS_REMOVE_FILE |
		unix.LANDLOCK_ACCESS_FS_MAKE_CHAR |
		unix.LANDLOCK_ACCESS_FS_MAKE_DIR |
		unix.LANDLOCK_ACCESS_FS_MAKE_REG |
		unix.LANDLOCK_ACCESS_FS_MAKE_SOCK |
		unix.LANDLOCK_ACCESS_FS_MAKE_FIFO |
		unix.LANDLOCK_ACCESS_FS_MAKE_BLOCK |
		unix.LANDLOCK_ACCESS_FS_MAKE_SYM |
		unix.LANDLOCK_ACCESS_FS_TRUNCATE
)

// LandlockABI retourne la version ABI Landlock du noyau (0 si indisponible).
func LandlockABI() int {
	r, _, errno := unix.Syscall(
		unix.SYS_LANDLOCK_CREATE_RULESET, landlockCreateRulesetVersion, 0, 0,
	)
	if errno != 0 {
		return 0
	}
	return int(r)
}

func runPlatform(ctx context.Context, code string, o Opts) (Result, error) {
	_ = ctx
	if LandlockABI() < landlockABIV6 {
		// Fail-closed : sans Landlock ABI v6, pas de gestion réseau -> on refuse.
		return Result{}, ErrUnsupported
	}
	return runChild(ctx, code, o)
}

// ChildMain : point d'entrée du helper child. Applique rlimits + Landlock +
// seccomp sur soi-même, puis exec python. Ne retourne jamais (exec ou exit).
func ChildMain() {
	code := os.Getenv(envSBCode)
	workdir := os.Getenv(envSBWorkdir)
	python := os.Getenv(envSBPython)
	if code == "" || workdir == "" || python == "" {
		fmt.Fprintln(os.Stderr, "[sidecar child] env incomplet")
		os.Exit(126)
	}
	applyRlimits(
		os.Getenv(envSBCPU), os.Getenv(envSBMem),
		os.Getenv(envSBNOFile), os.Getenv(envSBFSize),
	)
	// no_new_privs : requis par Landlock restrict_self et seccomp.
	if err := unix.Prctl(unix.PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0); err != nil {
		fmt.Fprintf(os.Stderr, "[sidecar child] no_new_privs: %v\n", err)
		os.Exit(125)
	}
	if err := applyLandlock(workdir); err != nil {
		fmt.Fprintf(os.Stderr, "[sidecar child] landlock: %v\n", err)
		os.Exit(125)
	}
	if err := applySeccomp(); err != nil {
		fmt.Fprintf(os.Stderr, "[sidecar child] seccomp: %v\n", err)
		os.Exit(125)
	}
	_ = os.Chdir(workdir)
	env := []string{"PATH=/usr/local/bin:/usr/bin:/bin", "LANG=C.UTF-8", "HOME=" + workdir, "TMPDIR=" + workdir}
	err := unix.Exec(python, []string{"python", "-I", "-c", code}, env)
	fmt.Fprintf(os.Stderr, "[sidecar child] exec: %v\n", err)
	os.Exit(127)
}

func applyRlimits(cpuS, memB, nofile, fsize string) {
	set := func(res int, val uint64) {
		_ = unix.Setrlimit(res, &unix.Rlimit{Cur: val, Max: val})
	}
	if v, err := strconv.ParseUint(cpuS, 10, 64); err == nil {
		set(unix.RLIMIT_CPU, v)
	}
	if v, err := strconv.ParseUint(memB, 10, 64); err == nil {
		set(unix.RLIMIT_AS, v)
	}
	if v, err := strconv.ParseUint(nofile, 10, 64); err == nil {
		set(unix.RLIMIT_NOFILE, v)
	}
	if v, err := strconv.ParseUint(fsize, 10, 64); err == nil {
		set(unix.RLIMIT_FSIZE, v)
	}
	_ = unix.Setrlimit(unix.RLIMIT_NPROC, &unix.Rlimit{Cur: 64, Max: 64})
	_ = unix.Setrlimit(unix.RLIMIT_CORE, &unix.Rlimit{Cur: 0, Max: 0})
}

// applyLandlock : deny par défaut, lecture/exec sur le système, écriture
// uniquement dans workdir, aucun bind/connect TCP (ABI v6, deny-all réseau).
func applyLandlock(workdir string) error {
	attr := unix.LandlockRulesetAttr{
		Handled_access_fs:  handledAccessFS,
		Handled_access_net: handledAccessNet,
	}
	fd, _, errno := unix.Syscall(
		unix.SYS_LANDLOCK_CREATE_RULESET,
		uintptr(unsafe.Pointer(&attr)),
		unsafe.Sizeof(attr),
		0,
	)
	if errno != 0 {
		return fmt.Errorf("create_ruleset: %w", errno)
	}
	rulesetFD := int(fd)
	defer unix.Close(rulesetFD)

	addPath := func(path string, access uint64) error {
		p, err := unix.Open(path, unix.O_PATH|unix.O_CLOEXEC, 0)
		if err != nil {
			return fmt.Errorf("open %s: %w", path, err)
		}
		defer unix.Close(p)
		rule := unix.LandlockPathBeneathAttr{Allowed_access: access, Parent_fd: int32(p)}
		_, _, errno := unix.Syscall(
			unix.SYS_LANDLOCK_ADD_RULE, uintptr(rulesetFD),
			landlockRulePathBeneath, uintptr(unsafe.Pointer(&rule)),
		)
		if errno != 0 {
			return fmt.Errorf("add_rule %s: %w", path, errno)
		}
		return nil
	}
	for _, p := range []string{"/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc", "/dev"} {
		if err := addPath(p, fsReadExec); err != nil {
			return err
		}
	}
	if err := addPath(workdir, fsWriteTmp|fsReadExec); err != nil {
		return err
	}
	// Aucun port autorisé : aucune règle NET_SERVICE -> tout le TCP est refusé.
	_, _, errno = unix.Syscall(unix.SYS_LANDLOCK_RESTRICT_SELF, uintptr(rulesetFD), 0, 0)
	if errno != 0 {
		return fmt.Errorf("restrict_self: %w", errno)
	}
	return nil
}

const landlockRulePathBeneath = 1 // LANDLOCK_RULE_PATH_BENEATH
