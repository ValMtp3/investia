//go:build linux

package sandboxrun

import (
	"unsafe"

	"golang.org/x/sys/unix"
)

// Filtre seccomp-bpf minimal, défense en profondeur derrière Landlock :
// bloque les syscalls d'échappement (mount, ptrace, bpf, modules, namespaces...)
// et socket() sauf AF_UNIX/AF_NETLINK. Action par défaut : ALLOW.
const (
	seccompRetAllow      uint32 = 0x7fff0000 // SECCOMP_RET_ALLOW
	seccompRetErrnoEPERM uint32 = 0x00050001 // SECCOMP_RET_ERRNO | EPERM

	bpfLDWABS = 0x00 // BPF_LD | BPF_W | BPF_ABS
	bpfJmpEq  = 0x10 // BPF_JMP | BPF_JEQ | BPF_K
	bpfJmpA   = 0x05 // BPF_JMP | BPF_JA
	bpfRetK   = 0x06 // BPF_RET | BPF_K
)

// seccomp_data : nr@0, arch@4, ip@8, args[0] low32@16, high32@20.
const offArgs0Low = 16

func bpfStmt(code uint16, jt, jf uint8, k uint32) unix.SockFilter {
	return unix.SockFilter{Code: code, Jt: jt, Jf: jf, K: k}
}

func bpfJumpEq(k uint32, jt, jf uint8) unix.SockFilter {
	return unix.SockFilter{Code: bpfJmpEq, Jt: jt, Jf: jf, K: k}
}

// blockedSyscalls : refusées (EPERM) quoi qu'il arrive.
var blockedSyscalls = []uint32{
	unix.SYS_MOUNT,
	unix.SYS_UMOUNT2,
	unix.SYS_PIVOT_ROOT,
	unix.SYS_PTRACE,
	unix.SYS_BPF,
	unix.SYS_KEXEC_LOAD,
	unix.SYS_KEXEC_FILE_LOAD,
	unix.SYS_REBOOT,
	unix.SYS_SWAPON,
	unix.SYS_SWAPOFF,
	unix.SYS_INIT_MODULE,
	unix.SYS_FINIT_MODULE,
	unix.SYS_DELETE_MODULE,
	unix.SYS_UNSHARE,
	unix.SYS_SETNS,
	unix.SYS_ACCT,
	unix.SYS_PROCESS_VM_READV,
	unix.SYS_PROCESS_VM_WRITEV,
}

// applySeccomp installe le filtre. socket() autorisé seulement en AF_UNIX (1)
// ou AF_NETLINK (16) — le réseau TCP est déjà refusé par Landlock ABI v6.
func applySeccomp() error {
	var prog []unix.SockFilter
	prog = append(prog, bpfStmt(bpfLDWABS, 0, 0, 0)) // A = nr (offset 0)
	// Bloc socket : 5 instructions, on le saute si nr != SYS_SOCKET.
	prog = append(prog, bpfJumpEq(unix.SYS_SOCKET, 0, 5))
	prog = append(prog, bpfStmt(bpfLDWABS, 0, 0, offArgs0Low)) // A = args[0] low32
	prog = append(prog, bpfJumpEq(unix.AF_UNIX, 2, 0))         // AF_UNIX -> RET ALLOW
	prog = append(prog, bpfJumpEq(unix.AF_NETLINK, 1, 0))      // AF_NETLINK -> RET ALLOW
	prog = append(prog, bpfStmt(bpfRetK, 0, 0, seccompRetErrnoEPERM))
	prog = append(prog, bpfStmt(bpfRetK, 0, 0, seccompRetAllow))
	// Syscalls bloquées : JEQ nr -> RET ERRNO (jt=0, jf=1 saute le RET si !=).
	for _, nr := range blockedSyscalls {
		prog = append(prog, bpfJumpEq(nr, 0, 1))
		prog = append(prog, bpfStmt(bpfRetK, 0, 0, seccompRetErrnoEPERM))
	}
	// default : ALLOW
	prog = append(prog, bpfStmt(bpfRetK, 0, 0, seccompRetAllow))

	fprog := unix.SockFprog{Len: uint16(len(prog)), Filter: &prog[0]}
	if err := unix.Prctl(unix.PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0); err != nil {
		return err
	}
	if _, _, errno := unix.Syscall(
		unix.SYS_PRCTL, unix.PR_SET_SECCOMP, unix.SECCOMP_MODE_FILTER,
		uintptr(unsafe.Pointer(&fprog)),
	); errno != 0 {
		return errno
	}
	return nil
}
