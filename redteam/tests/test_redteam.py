"""Tests 23j : pipeline garak pinné — config, parse du rapport, générateur custom."""

import json
import sys
from pathlib import Path

import pytest

REDTEAM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REDTEAM_DIR))

from investia_generator import InvestiaGenerator  # noqa: E402
from run_redteam import LIVE_PROBES, load_conf, parse_report  # noqa: E402


def test_conf_pinned():
    conf = load_conf()
    assert conf["garak"]["version_pin"] == "0.17.1"
    assert conf["run"]["seed"] == 20261115
    assert set(LIVE_PROBES) <= set(conf["probes"])
    for probe in ("promptinject", "latentinjection", "dan"):
        assert probe in conf["probes"]


def test_parse_report(tmp_path: Path):
    report = tmp_path / "investia.report.jsonl"
    entries = [
        {"probe": "promptinject", "detector": "promptinject", "status": 1},
        {"probe": "dan", "detector": "dan", "status": 0},
        {"probe": "promptinject", "detector": "mitigation", "status": 1},
    ]
    report.write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8"
    )
    hitlog = tmp_path / "investia.hitlog.jsonl"
    hitlog.write_text(json.dumps({"hit": True}) + "\n", encoding="utf-8")
    stats = parse_report(report)
    assert stats["n_entries"] == 3
    assert stats["n_hits"] == 1
    assert stats["probes"] == ["dan", "promptinject"]


def test_parse_report_sans_hitlog(tmp_path: Path):
    report = tmp_path / "r.report.jsonl"
    report.write_text(json.dumps({"probe": "dan"}) + "\n", encoding="utf-8")
    stats = parse_report(report)
    assert stats["n_hits"] == 0
    assert stats["n_entries"] == 1


def test_investia_generator_avec_mock_llm():
    """Le générateur custom fait tourner le vrai harness (run_agent + garde-fous)."""
    from investia.evals.runner import EvalCase, MockLlm

    case = EvalCase(
        id="redteam",
        question="x",
        expected_tool=None,
        mock_tool_call=None,
        mock_final=(
            "## Thèse\nréponse mock\n## Risques\naucun\n## Confiance\n50\n"
            "## Sources\n- mock\n\nSimulation — pas un conseil financier."
        ),
    )
    gen = InvestiaGenerator(llm=MockLlm(case))
    from garak.attempt import Conversation, Message, Turn

    conv = Conversation(turns=[Turn(role="user", content=Message(text="sonde"))])
    out = gen._call_model(conv, generations_this_call=1)
    assert len(out) == 1
    assert out[0] is not None
    assert "réponse mock" in (out[0].text or "")


@pytest.mark.slow
def test_smoke_garak_hors_ligne(tmp_path: Path):
    """Smoke réel : garak tourne en test.Blank et produit un rapport (CI)."""
    from run_redteam import SMOKE_MODEL, SMOKE_PROBES, run_garak

    report = run_garak(SMOKE_MODEL, SMOKE_PROBES, tmp_path, seed=20261115)
    stats = parse_report(report)
    assert stats["n_entries"] >= 1
    assert any("test" in p for p in stats["probes"])
