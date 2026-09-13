from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mission import ops
from mission.state import State, normalise

from .script import T0, ev


class FakeECS:
    def __init__(self, running=1, desired=1):
        self.running, self.desired = running, desired

    def describe_services(self, cluster, services):
        return {"services": [
            {"serviceName": n, "status": "ACTIVE", "desiredCount": self.desired, "runningCount": self.running, "pendingCount": 0,
             "taskDefinition": f"td/{n}:7", "deployments": [{"status": "PRIMARY", "rolloutState": "COMPLETED", "createdAt": "x", "updatedAt": "y"}]}
            for n in services]}

    def describe_task_definition(self, taskDefinition):
        return {"taskDefinition": {"containerDefinitions": [{"image": f"123.dkr.ecr/atlas/{taskDefinition.split('/')[1].split(':')[0]}:abc1234"}]}}


class FakeELB:
    def __init__(self, unhealthy=0, only="atlas-platform"):
        self.unhealthy, self.only = unhealthy, only  # unhealthy targets only behind `only`'s target group

    def describe_target_groups(self):
        return {"TargetGroups": [{"TargetGroupName": f"atlas-agentic-lab-{n}", "TargetGroupArn": f"arn:aws:elasticloadbalancing:ap-southeast-2:1:targetgroup/atlas-agentic-lab-{n}/abc"} for n in ops.SERVICES]}

    def describe_load_balancers(self):
        return {"LoadBalancers": [{"LoadBalancerName": "atlas-agentic-lab", "LoadBalancerArn": "arn:aws:elasticloadbalancing:ap-southeast-2:1:loadbalancer/app/atlas-agentic-lab/def"}]}

    def describe_target_health(self, TargetGroupArn):
        n = self.unhealthy if (self.only is None or self.only in TargetGroupArn) else 0
        return {"TargetHealthDescriptions": [{"TargetHealth": {"State": "healthy"}}] + [{"TargetHealth": {"State": "unhealthy"}}] * n}


class FakeCW:
    def __init__(self, e5=0, p95=0.2, unh=0):
        self.e5, self.p95, self.unh = e5, p95, unh

    def get_metric_data(self, MetricDataQueries, StartTime, EndTime, ScanBy):
        assert ScanBy == "TimestampDescending" and EndTime - StartTime == timedelta(minutes=5)
        v = {"req": [120, 118, 130, 99, 101], "t5": [1, 0, 0, 0, 0], "e5": [self.e5, 0, 0], "p95": [self.p95, 0.1, 0.1], "unh": [self.unh, 0]}
        return {"MetricDataResults": [{"Id": q["Id"], "Values": v[q["Id"]]} for q in MetricDataQueries]}


class FakeSTS:
    def get_caller_identity(self):
        return {"Account": "336881700625"}


class RecordingELB(FakeELB):
    """Only answers describe_target_health; discovery calls must not happen when the env names the ALB."""

    def __init__(self):
        super().__init__()
        self.health_arns: list[str] = []

    def describe_target_groups(self):
        raise AssertionError("discovery must not run when TARGET_GROUP_SUFFIXES is set")

    def describe_load_balancers(self):
        raise AssertionError("discovery must not run when ALB_ARN_SUFFIX is set")

    def describe_target_health(self, TargetGroupArn):
        self.health_arns.append(TargetGroupArn)
        return super().describe_target_health(TargetGroupArn)


class RecordingCW(FakeCW):
    def __init__(self):
        super().__init__()
        self.queries: list[list[dict]] = []

    def get_metric_data(self, MetricDataQueries, StartTime, EndTime, ScanBy):
        self.queries.append(MetricDataQueries)
        return super().get_metric_data(MetricDataQueries, StartTime, EndTime, ScanBy)


def _fake(ecs=None, elb=None, cw=None, sts=None):
    return lambda: {"ecs": ecs or FakeECS(), "elbv2": elb or FakeELB(), "cloudwatch": cw or FakeCW(), "sts": sts or FakeSTS()}


def test_health_shaping_from_ecs_alb_cloudwatch(monkeypatch):
    monkeypatch.setattr(ops, "clients", _fake())
    d = ops.fetch(force=True, now=datetime(2026, 9, 17, 10, 0, tzinfo=UTC))
    assert d["source"] == "aws" and [s["name"] for s in d["services"]] == ops.SERVICES
    p = d["services"][0]
    assert p["desired"] == 1 and p["running"] == 1 and p["image_tag"] == "abc1234" and p["deployment"]["rollout_state"] == "COMPLETED"
    assert p["targets"] == {"healthy": 1, "unhealthy": 0, "total": 1, "states": ["healthy"]}
    assert p["metrics"]["request_count"] == 568 and p["metrics"]["target_5xx"] == 1 and p["metrics"]["p95_ms"] == 200
    assert p["metrics"]["elb_5xx_last_min"] == 0 and p["metrics"]["unhealthy_hosts"] == 0
    # the API is cached and served through the router
    from fastapi.testclient import TestClient

    from mission.main import app

    with TestClient(app) as c:
        assert c.get("/api/ops/health").json()["services"][0]["image_tag"] == "abc1234"


def test_health_degrades_without_aws(monkeypatch):
    def boom():
        raise RuntimeError("no credentials")

    monkeypatch.setattr(ops, "clients", boom)
    d = ops.fetch(force=True)
    assert d["source"] == "local" and "RuntimeError" in d["error"] and len(d["services"]) == 3 and d["services"][0]["metrics"] is None


def test_infra_alert_thresholds(monkeypatch):
    ops.reset_alert_state()
    monkeypatch.setattr(ops, "clients", _fake())
    quiet = ops.fetch(force=True)["services"]
    assert ops.conditions(quiet, now_s=1000) == []

    monkeypatch.setattr(ops, "clients", _fake(ecs=FakeECS(running=0, desired=2), elb=FakeELB(unhealthy=1), cw=FakeCW(e5=6, p95=2.5, unh=1)))
    bad = ops.fetch(force=True)["services"]
    rules = {(a["service"], a["rule"]) for a in ops.conditions(bad, now_s=1000)}
    assert ("atlas-platform", "unhealthy_hosts") in rules and ("atlas-platform", "latency_p95") in rules
    assert ("alb", "elb_5xx") in rules and not any(r == "elb_5xx" and s != "alb" for s, r in rules)  # ELB-wide: once
    assert ("atlas-platform", "under_capacity") not in rules  # must persist for 30 s first
    rules = {(a["service"], a["rule"]) for a in ops.conditions(bad, now_s=1031)}
    assert ("atlas-platform", "under_capacity") in rules
    # boundary: exactly 5 ELB 5xx and exactly 2 s p95 do not fire
    monkeypatch.setattr(ops, "clients", _fake(cw=FakeCW(e5=5, p95=2.0)))
    assert ops.conditions(ops.fetch(force=True)["services"], now_s=2000) == []


def test_alerts_need_two_consecutive_polls_and_dedupe_alb(monkeypatch):
    ops.reset_alert_state()
    monkeypatch.setattr(ops, "clients", _fake(cw=FakeCW(e5=74)))
    bad = ops.fetch(force=True)["services"]
    assert ops.evaluate_alerts(bad, now_s=100) == []  # first sighting: not yet
    fired = ops.evaluate_alerts(bad, now_s=115)
    assert [(a["service"], a["rule"], a["confirmed_polls"]) for a in fired] == [("alb", "elb_5xx", 2)]
    assert ops.alert_event(fired[0])["service_display"] == "Load balancer" and ops.alert_event(fired[0])["signature"] == "infra:alb:elb_5xx"
    # a blip that clears resets the streak
    monkeypatch.setattr(ops, "clients", _fake())
    assert ops.evaluate_alerts(ops.fetch(force=True)["services"], now_s=130) == []
    assert ops.evaluate_alerts(bad, now_s=145) == []


class DeployingECS(FakeECS):
    def __init__(self, rolling: bool, running=1, desired=1):
        super().__init__(running=running, desired=desired)
        self.rolling = rolling

    def describe_services(self, cluster, services):
        d = super().describe_services(cluster, services)
        for sv in d["services"]:
            if sv["serviceName"] == "atlas-platform":
                sv["deployments"] = ([{"status": "PRIMARY", "rolloutState": "IN_PROGRESS"}, {"status": "ACTIVE", "rolloutState": "COMPLETED"}]
                                     if self.rolling else [{"status": "PRIMARY", "rolloutState": "COMPLETED"}])
        return d


def test_our_own_deployments_do_not_alert(monkeypatch):
    ops.reset_alert_state()
    # rollout in progress on atlas-platform: its unhealthy target and the ALB-wide 5xx are ours
    monkeypatch.setattr(ops, "clients", _fake(ecs=DeployingECS(rolling=True), elb=FakeELB(unhealthy=1), cw=FakeCW(e5=74)))
    rolling = ops.fetch(force=True)["services"]
    for t in (0, 15, 30):
        assert ops.evaluate_alerts(rolling, now_s=t) == []
    # rollout finished: 120 s of quiet, still nothing at +60 s and +100 s
    monkeypatch.setattr(ops, "clients", _fake(ecs=DeployingECS(rolling=False), elb=FakeELB(unhealthy=1), cw=FakeCW(e5=74)))
    done = ops.fetch(force=True)["services"]
    assert ops.evaluate_alerts(done, now_s=45) == [] and ops.evaluate_alerts(done, now_s=105) == [] and ops.evaluate_alerts(done, now_s=145) == []
    # quiet window over (45 + 120 = 165): conditions start counting again and confirm on the second poll
    assert ops.evaluate_alerts(done, now_s=170) == []
    fired = {(a["service"], a["rule"]) for a in ops.evaluate_alerts(done, now_s=185)}
    assert fired == {("atlas-platform", "unhealthy_hosts"), ("alb", "elb_5xx")}


def test_chaos_kill_task_still_alerts(monkeypatch):
    """A task stopped outside a deployment: rollout COMPLETED, running < desired, one unhealthy target."""
    ops.reset_alert_state()
    monkeypatch.setattr(ops, "clients", _fake(ecs=DeployingECS(rolling=False, running=1, desired=2), elb=FakeELB(unhealthy=1)))
    sv = ops.fetch(force=True)["services"]
    assert ops.evaluate_alerts(sv, now_s=0) == []
    assert {(a["service"], a["rule"]) for a in ops.evaluate_alerts(sv, now_s=15)} == {("atlas-platform", "unhealthy_hosts")}
    ops.evaluate_alerts(sv, now_s=45)  # under_capacity first seen after 30 s
    fired = {(a["service"], a["rule"]) for a in ops.evaluate_alerts(sv, now_s=60)}
    assert ("atlas-platform", "under_capacity") in fired and ("atlas-platform", "unhealthy_hosts") in fired


def test_poll_emits_alert_once_per_cooldown(monkeypatch):
    ops.reset_alert_state()
    monkeypatch.setattr(ops, "clients", _fake(cw=FakeCW(e5=9)))
    emitted: list[tuple[str, dict]] = []
    assert ops.poll_once(lambda dt, d: emitted.append((dt, d)), now_s=4985) == []  # first sighting
    fired = ops.poll_once(lambda dt, d: emitted.append((dt, d)), now_s=5000)
    assert [(a["service"], a["rule"]) for a in fired] == [("alb", "elb_5xx")]  # once, not per service
    assert emitted[0][0] == "infra.alert" and emitted[0][1]["signature"] == "infra:alb:elb_5xx" and emitted[0][1]["kind"] == "infra"
    assert ops.poll_once(lambda dt, d: emitted.append((dt, d)), now_s=5100) == []  # cooldown
    assert len(ops.poll_once(lambda dt, d: emitted.append((dt, d)), now_s=5400)) == 1


def test_signal_by_kind_and_cluster_table():
    st = State()
    now = T0 + timedelta(minutes=2)
    st.apply(normalise(ev("atlas.platform", "error.raised", 0, None, None, "500", kind="crash", signature="/a:KeyError", endpoint="/a", error_type="KeyError",
                          message="k", customer_impact=3, stack='File "/app/atlas/x.py", line 1, in f', request_id="r1")))
    st.apply(normalise(ev("atlas.platform", "error.raised", 1, None, None, "422", kind="business_rule", signature="/b:BRV", endpoint="/b", error_type="BusinessRuleViolation", message="rule")))
    st.apply(normalise(ev("atlas.platform", "error.raised", 2, None, None, "slow", kind="performance", signature="/c:Slow", endpoint="/c", error_type="SlowRequest", message="p95 3.1s")))
    st.apply(normalise(ev("atlas.ops", "infra.alert", 3, {"handle": "ops", "kind": "system", "display_name": "Ops monitor", "mode": None}, None,
                          "atlas-platform: 9 ELB 5xx in the last minute", kind="infra", service="atlas-platform", rule="elb_5xx", value=9, threshold=5,
                          signature="infra:atlas-platform:elb_5xx", endpoint="atlas-platform", error_type="elb_5xx")))
    snap = st.snapshot(now=now)
    bk = snap["signal"]["by_kind"]
    assert {k: v["count"] for k, v in bk.items()} == {"crash": 1, "business_rule": 1, "performance": 1, "infra": 1}
    assert sum(bk["crash"]["rate"]) == 1 and bk["infra"]["last_ts"].startswith("2026-09-17T10:00:03")
    # infra alerts never become an OBSERVING pipeline row; the three real errors do (one row, dominant signature)
    assert snap["pipeline"] and snap["pipeline"][0]["observing"] and snap["pipeline"][0]["error"]["count"] == 3
    table = {c["signature"]: c for c in st.clusters(now)}
    assert table["/a:KeyError"]["status"] == "observing" and table["/a:KeyError"]["impact"] == 3 and table["/a:KeyError"]["samples"][0]["request_id"] == "r1"
    assert table["infra:atlas-platform:elb_5xx"]["status"] == "alerting" and table["infra:atlas-platform:elb_5xx"]["kind"] == "infra"
    # once a ticket owns a signature the row says so
    st.apply(normalise(ev("atlas.scout", "incident.opened", 10, {"handle": "scout", "kind": "agent", "display_name": "Scout", "mode": "autonomous"}, "ATLAS-50", "Opened",
                          incident={"signature": "/a:KeyError"}, issue={"key": "ATLAS-50", "title": "KeyError on /a"})))
    table = {c["signature"]: c for c in st.clusters(now)}
    assert table["/a:KeyError"]["status"] == "ticketed" and table["/a:KeyError"]["ticket"] == "ATLAS-50"
    assert [c["status"] for c in st.clusters(now)][:1] == ["alerting"]


def test_alb_identifiers_from_the_task_definition(monkeypatch):
    from mission.settings import settings

    monkeypatch.setattr(settings(), "alb_arn_suffix", "app/atlas-agentic-lab/956cc0833febdf0e")
    monkeypatch.setattr(
        settings(), "target_group_suffixes",
        "atlas-board=targetgroup/atlas-lab-atlas-board/623ce1f08c2f1d26,"
        "atlas-platform=targetgroup/atlas-lab-atlas-platform/aaa111,mission-control=targetgroup/atlas-lab-mission-control/bbb222",
    )
    elb, cw = RecordingELB(), RecordingCW()
    monkeypatch.setattr(ops, "clients", _fake(elb=elb, cw=cw))
    d = ops.fetch(force=True, now=datetime(2026, 9, 17, 10, 0, tzinfo=UTC))
    assert d["source"] == "aws"
    by = {s["name"]: s for s in d["services"]}
    # full ARNs built from STS account + suffix, one DescribeTargetHealth per service
    assert elb.health_arns == [
        "arn:aws:elasticloadbalancing:ap-southeast-2:336881700625:targetgroup/atlas-lab-atlas-platform/aaa111",
        "arn:aws:elasticloadbalancing:ap-southeast-2:336881700625:targetgroup/atlas-lab-atlas-board/623ce1f08c2f1d26",
        "arn:aws:elasticloadbalancing:ap-southeast-2:336881700625:targetgroup/atlas-lab-mission-control/bbb222",
    ]
    assert by["atlas-board"]["targets"]["healthy"] == 1 and by["atlas-board"]["metrics"]["request_count"] == 568
    # dimensions exactly as the env says: LoadBalancer + TargetGroup per service, LoadBalancer only for ELB 5xx
    q = {x["Id"]: x["MetricStat"] for x in cw.queries[1]}  # atlas-board
    assert q["req"]["Metric"]["Dimensions"] == [
        {"Name": "LoadBalancer", "Value": "app/atlas-agentic-lab/956cc0833febdf0e"},
        {"Name": "TargetGroup", "Value": "targetgroup/atlas-lab-atlas-board/623ce1f08c2f1d26"},
    ]
    assert q["e5"]["Metric"]["Dimensions"] == [{"Name": "LoadBalancer", "Value": "app/atlas-agentic-lab/956cc0833febdf0e"}]
    assert q["p95"]["Stat"] == "p95" and q["unh"]["Stat"] == "Maximum" and q["req"]["Period"] == 60
    assert by["mission-control"]["metrics"]["dimensions"]["TargetGroup"] == "targetgroup/atlas-lab-mission-control/bbb222"
