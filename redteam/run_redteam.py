"""Lance garak (scanner NVIDIA pinné) et parse son rapport — étape 23j.

Usage :
    uv run python run_redteam.py --smoke   # hors-ligne, test.Blank (CI, sans clés)
    uv run python run_redteam.py --live    # vrai scan : générateur investia, VPS only

Exit 0 si garak a tourné et le rapport est produit/parsé, 1 sinon.
Le jugement sur les hits se fait en revue humaine du rapport (garak ne fail
pas sur les hits) — voir README.md.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

REDTEAM_DIR = Path(__file__).resolve().parent
CONF_PATH = REDTEAM_DIR / "garak.conf.yaml"

# Probes du vrai scan (voir garak.conf.yaml pour la justification).
LIVE_PROBES = [
    "promptinject",
    "latentinjection",
    "dan",
    "encoding",
    "packagehallucination",
]
SMOKE_MODEL = "test.Blank"  # générateur hors-ligne garak, zéro clé
SMOKE_PROBES = ["test.Test"]


def load_conf() -> dict:
    conf = yaml.safe_load(CONF_PATH.read_text(encoding="utf-8"))
    assert conf["garak"]["version_pin"] == "0.17.1", "pin garak drifté"
    return conf


def run_garak(model_type: str, probes: list[str], out_dir: Path, seed: int) -> Path:
    """Lance `python -m garak` (config pinnée) et retourne le rapport JSONL."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # garak 0.17 : -S = spec unifié ; le rapport se écrit dans run.report_dir
    # (garak.conf.yaml) avec --report_prefix. -r sert à convertir, on ne l'utilise pas.
    spec = ",".join(f"probes.{p}" for p in probes)
    cmd = [
        sys.executable,
        "-m",
        "garak",
        "--config",
        str(CONF_PATH),
        "-m",
        model_type,
        "-S",
        spec,
        "--seed",
        str(seed),
        "--report_prefix",
        "investia",
        "--narrow_output",
    ]
    proc = subprocess.run(cmd, cwd=REDTEAM_DIR, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout[-3000:], file=sys.stderr)
        print(proc.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"garak a échoué (exit {proc.returncode})")
    # garak 0.17 écrit le rapport dans $XDG_DATA_HOME/garak/garak_runs/ (fallback local)
    xdg = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    candidates = [out_dir, xdg / "garak" / "garak_runs"]
    for candidate in candidates:
        reports = sorted(candidate.glob("investia*.report.jsonl"))
        if reports:
            return reports[-1]
    raise SystemExit(f"aucun rapport investia*.report.jsonl dans {candidates}")


def parse_report(report_path: Path) -> dict:
    """Parse le rapport garak (JSONL) + le hitlog : stats par probe et hits."""
    entries = [
        json.loads(line)
        for line in report_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    probes_seen = sorted({str(e.get("probe", "?")) for e in entries})
    hitlog = report_path.with_name(
        report_path.name.replace(".report.jsonl", ".hitlog.jsonl")
    )
    n_hits = 0
    if hitlog.exists():
        n_hits = sum(
            1
            for line in hitlog.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return {
        "report": str(report_path),
        "n_entries": len(entries),
        "n_hits": n_hits,
        "probes": probes_seen,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lance garak et parse le rapport (23j)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--smoke", action="store_true", help="hors-ligne test.Blank (CI)"
    )
    group.add_argument("--live", action="store_true", help="vrai scan, VPS seulement")
    args = parser.parse_args(argv)
    conf = load_conf()
    seed = int(conf["run"]["seed"])
    if args.smoke:
        report = run_garak(SMOKE_MODEL, SMOKE_PROBES, REDTEAM_DIR / "garak_runs", seed)
    else:
        report = run_garak("investia", LIVE_PROBES, REDTEAM_DIR / "garak_runs", seed)
    stats = parse_report(report)
    print(
        f"OK : {stats['n_entries']} entrées, {stats['n_hits']} hits, "
        f"probes={stats['probes']} — rapport : {stats['report']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
