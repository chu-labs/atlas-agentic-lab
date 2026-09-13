import time

from atlas_agents import authority
from atlas_agents.scout import THRESHOLDS, Cluster, sig_label


def test_thresholds_are_loud_for_crashes():
    assert THRESHOLDS["crash"] == 1
    assert THRESHOLDS["business_rule"] > 1


def test_cluster_recent_and_impact():
    c = Cluster("x")
    now = time.time()
    c.events = [{"_received": now, "customer_impact": 10}, {"_received": now - 10_000, "customer_impact": 99}]
    assert len(c.recent) == 1
    assert c.impact == 10


def test_sig_label_is_stable_and_short():
    assert sig_label("/api/x:ValueError") == sig_label("/api/x:ValueError")
    assert len(sig_label("a")) == 12


def test_every_agent_def_loads_and_none_can_merge():
    for n in ("scout", "forge", "sentinel", "conductor", "watchtower"):
        assert authority.load(n).can("can_merge") is False


def test_claude_final_json_parses_trailing_object():
    from atlas_agents.claude_code import Run

    r = Run(result='Some prose {"nested": {"a": 1}} more prose {"decision": "fix", "plan": ["x"]}')
    assert r.final_json() == {"decision": "fix", "plan": ["x"]}
    assert Run(result="no json here").final_json() is None


def test_forge_slug():
    from atlas_agents.forge import slug

    assert slug("Renewal window drops policies due exactly 30 days out") == "renewal-window-drops-policies-due-exactl"


def test_cluster_key_groups_same_frame_across_endpoints():
    from atlas_agents.scout import cluster_key

    stack = 'File "/app/atlas/api/routes.py", line 133, in building_risk\n  File "/app/atlas/domain/risk.py", line 27, in claims_pillar\nZeroDivisionError'
    a = cluster_key({"kind": "crash", "error_type": "ZeroDivisionError", "endpoint": "/api/buildings/{id}/risk", "stack": stack})
    b = cluster_key({"kind": "crash", "error_type": "ZeroDivisionError", "endpoint": "/api/policies/{n}/quote", "stack": stack})
    assert a == b == "ZeroDivisionError@atlas/domain/risk.py:claims_pillar"
    assert cluster_key({"kind": "business_rule", "message": "quote.expired_policy: ATL-1 expired"}) == "rule:quote.expired_policy"
    assert cluster_key({"kind": "performance", "endpoint": "/api/policies"}) == "slow:/api/policies"


def test_board_move_steps_forward(monkeypatch):
    from atlas_agents.board import Board

    b = Board.__new__(Board)
    calls = []
    monkeypatch.setattr(b, "get", lambda key: {"status": "Backlog"})
    monkeypatch.setattr(b, "transition", lambda key, status: calls.append(status) or {"status": status})
    b.move("ATLAS-1", "In Progress")
    assert calls == ["Triage", "In Progress"]
    calls.clear()
    monkeypatch.setattr(b, "get", lambda key: {"status": "In Review"})
    b.move("ATLAS-1", "In Progress")
    assert calls == ["In Progress"]


def test_extract_json_tolerates_fences_and_prose():
    from atlas_agents.llm import _extract_json

    assert _extract_json('Here you go:\n```json\n{"a": 1, "b": {"c": [1,2]}}\n```\nthanks') == {"a": 1, "b": {"c": [1, 2]}}
    assert _extract_json("no json at all") is None
