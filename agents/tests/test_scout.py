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
