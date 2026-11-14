"""Tests de l'export dataset depuis les traces (spec 14b) — TDD avant le code."""

import hashlib
import json

from investia.evals.export_traces import export_dataset


class FakeTraceStore:
    def __init__(self, runs):
        self._runs = runs

    async def list_runs(self, limit=50):
        return [{"id": rid, **run} for rid, run in list(self._runs.items())[:limit]]

    async def get_run(self, run_id):
        return {
            "run": {"id": run_id, **self._runs[run_id]},
            "steps": [{"kind": "tool_call"}, {"kind": "guardrail"}],
            "spans": [],
        }


def _store():
    return FakeTraceStore(
        {
            "run-ok": {
                "question": "prix AAPL ?",
                "status": "ok",
                "model": "gpt-6-luna",
                "turns": 2,
                "total_cost_cents": 0.02,
                "created_at": "2026-11-14T10:00:00+00:00",
            },
            "run-ko": {
                "question": "ordre risqué ?",
                "status": "blocked",
                "model": "gpt-6-luna",
                "turns": 3,
                "total_cost_cents": 0.05,
                "created_at": "2026-11-14T11:00:00+00:00",
            },
        }
    )


async def test_export_ne_garde_que_les_statuts_demandes(tmp_path):
    out = tmp_path / "ds.jsonl"
    info = await export_dataset(_store(), out, statuses=("blocked", "max_turns"))
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["id"] == "run-ko"
    assert entry["status"] == "blocked"
    assert entry["step_kinds"] == ["tool_call", "guardrail"]
    assert info["count"] == 1
    # hash SHA-256 juste à côté du fichier
    sha_file = tmp_path / "ds.jsonl.sha256"
    assert (
        sha_file.read_text(encoding="utf-8").strip()
        == hashlib.sha256(out.read_bytes()).hexdigest()
    )


async def test_export_deterministe_et_trie_par_date_desc(tmp_path):
    out1 = tmp_path / "a.jsonl"
    out2 = tmp_path / "b.jsonl"
    info1 = await export_dataset(_store(), out1)
    info2 = await export_dataset(_store(), out2)
    assert out1.read_bytes() == out2.read_bytes()
    assert info1["sha256"] == info2["sha256"]
    assert info1["count"] == 2
    # tri created_at desc : run-ko (11h) avant run-ok (10h)
    first = json.loads(out1.read_text(encoding="utf-8").splitlines()[0])
    assert first["id"] == "run-ko"


async def test_export_sans_filtre_garde_tout(tmp_path):
    out = tmp_path / "all.jsonl"
    info = await export_dataset(_store(), out)
    assert info["count"] == 2
