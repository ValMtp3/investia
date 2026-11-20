// Sidecar de sandboxing Investia (23i) : serveur HTTP stdlib sur unix socket.
//
// POST /run {"code", "timeout_s", "max_output_chars"} -> 200 Result JSON
// 503 si l'isolation noyau est indisponible (fail-closed, AUCUNE exécution).
//
// Le binaire est statique (CGO_ENABLED=0) et ré-execute lui-même la
// sous-commande "__child" qui applique Landlock + seccomp avant exec python.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net"
	"net/http"
	"os"
	"time"

	"investia/sandbox/internal/sandboxrun"
)

const (
	envSock     = "INVESTIA_SANDBOX_SOCK"
	defaultSock = "/run/investia/sandbox.sock"
	// 24 (scan sécurité, CWE-400) : borne dure du body JSON — un client du
	// socket ne peut pas pousser un corps arbitrairement gros en mémoire.
	maxBodyBytes = 64 * 1024
)

type runRequest struct {
	Code           string  `json:"code"`
	TimeoutSeconds float64 `json:"timeout_s"`
	MaxOutputChars int     `json:"max_output_chars"`
}

type errorResponse struct {
	Error string `json:"error"`
}

func main() {
	log.SetPrefix("[investia-sidecar] ")
	if len(os.Args) > 1 && os.Args[1] == "__child" {
		sandboxrun.ChildMain() // n'exécute jamais python hors Linux : panic contrôlé
		return
	}
	sock := os.Getenv(envSock)
	if sock == "" {
		sock = defaultSock
	}
	_ = os.Remove(sock) // socket mort d'un run précédent
	listener, err := net.Listen("unix", sock)
	if err != nil {
		log.Fatalf("listen %s: %v", sock, err)
	}
	_ = os.Chmod(sock, 0o660)
	log.Printf("écoute sur %s (Landlock ABI=%d, fail-closed si < 6)", sock, sandboxrun.LandlockABI())

	mux := http.NewServeMux()
	mux.HandleFunc("POST /run", handleRun)
	server := &http.Server{Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	if err := server.Serve(listener); err != nil {
		log.Fatalf("serve: %v", err)
	}
}

func handleRun(w http.ResponseWriter, r *http.Request) {
	// 24 (CWE-400) : body borné avant le moindre parse JSON.
	r.Body = http.MaxBytesReader(w, r.Body, maxBodyBytes)
	var req runRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, errorResponse{"JSON invalide: " + err.Error()})
		return
	}
	if req.Code == "" {
		writeJSON(w, http.StatusBadRequest, errorResponse{"code vide"})
		return
	}
	if len(req.Code) > sandboxrun.MaxCodeChars {
		writeJSON(w, http.StatusBadRequest, errorResponse{"code trop long"})
		return
	}
	// 24 (CWE-400) : le timeout demandé par le client est borné [1 s, 60 s].
	timeout := sandboxrun.ClampTimeout(time.Duration(req.TimeoutSeconds * float64(time.Second)))
	ctx, cancel := context.WithTimeout(r.Context(), timeout+5*time.Second)
	defer cancel()

	res, err := sandboxrun.Run(ctx, req.Code, sandboxrun.Opts{
		Timeout:        timeout,
		MaxOutputChars: req.MaxOutputChars,
	})
	if errors.Is(err, sandboxrun.ErrUnsupported) {
		// Fail-closed : AUCUNE exécution sans isolation noyau.
		writeJSON(w, http.StatusServiceUnavailable, errorResponse{
			Error: "isolation noyau indisponible (Linux >= 6.12, Landlock ABI v6 requis) — exécution refusée",
		})
		return
	}
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, errorResponse{err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, res)
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
