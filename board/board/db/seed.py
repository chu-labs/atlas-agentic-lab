"""Deterministic demo data for the board.

Everything is invented: a fictional strata insurer ("ATLAS"), fictional people, a fictional GitHub
org `chu-labs`. Timestamps are fixed in Australian Eastern time across Sprint 14 (closed) and
Sprint 15 (active) so the board reads like a real team's fortnight, including a set of tickets
that the agents took from production error to verified deploy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from . import repo
from .pool import conn

AEST = timezone(timedelta(hours=10))
GITHUB = "https://github.com/chu-labs/atlas-platform"


def at(month: int, day: int, hh: int, mm: int = 0) -> datetime:
    return datetime(2026, month, day, hh, mm, tzinfo=AEST)


# ---------------------------------------------------------------- people

_ESCALATE = ["ambiguous_requirement", "security_impact", "data_migration", "cost_over_threshold"]


def _authority(**over) -> dict:
    base = {
        "can_read_production_telemetry": False,
        "can_write_code": False,
        "can_review": False,
        "can_merge": False,
        "can_deploy": False,
        "can_change_business_rules": False,
        "must_escalate_when": _ESCALATE,
    }
    base.update(over)
    return base


USERS = [
    dict(handle="maroun", display_name="Maroun", kind="human", avatar="🧭", color="#f5b942", remit="Product Owner", authority=None, mode=None),
    dict(handle="priya", display_name="Priya", kind="human", avatar="🌿", color="#ec4899", remit="Engineer", authority=None, mode=None),
    dict(handle="tom", display_name="Tom", kind="human", avatar="🎸", color="#22c55e", remit="Engineer", authority=None, mode=None),
    dict(handle="alex", display_name="Alex", kind="human", avatar="📐", color="#a78bfa", remit="Underwriting lead", authority=None, mode=None),
    dict(
        handle="scout", display_name="Scout", kind="agent", avatar="🔭", color="#f59e0b",
        remit="Triage: watches production errors, opens tickets",
        authority=_authority(can_read_production_telemetry=True), mode="autonomous",
    ),
    dict(
        handle="forge", display_name="Forge", kind="agent", avatar="⚒️", color="#3b82f6",
        remit="Engineering: reproduces, tests first, fixes, opens PRs",
        authority=_authority(can_read_production_telemetry=True, can_write_code=True), mode="autonomous",
    ),
    dict(
        handle="sentinel", display_name="Sentinel", kind="agent", avatar="🛡️", color="#a855f7",
        remit="Review: independent PR review",
        authority=_authority(can_review=True), mode="autonomous",
    ),
    dict(
        handle="conductor", display_name="Conductor", kind="agent", avatar="🎼", color="#10b981",
        remit="Release: verifies deploys, closes tickets",
        authority=_authority(can_read_production_telemetry=True, can_deploy=True), mode="autonomous",
    ),
    dict(
        handle="watchtower", display_name="Watchtower", kind="agent", avatar="🗼", color="#ef4444",
        remit="Incidents: timelines and postmortems",
        authority=_authority(can_read_production_telemetry=True), mode="autonomous",
    ),
]

SPRINTS = [
    dict(name="Sprint 14", goal="Renewal season hardening: no silent money errors, no 500s on the broker portal.", starts_on=date(2026, 8, 31), ends_on=date(2026, 9, 13), state="closed"),
    dict(name="Sprint 15", goal="Observability and quoting accuracy before the September renewal peak.", starts_on=date(2026, 9, 14), ends_on=date(2026, 9, 27), state="active"),
    dict(name="Sprint 16", goal="Broker self-service and rate table versioning.", starts_on=date(2026, 9, 28), ends_on=date(2026, 10, 11), state="future"),
]


# ---------------------------------------------------------------- issue specs


@dataclass
class Ev:
    at: datetime
    actor: str
    kind: str
    frm: str | None = None
    to: str | None = None
    body: str | None = None


@dataclass
class Spec:
    created_at: datetime
    type: str
    title: str
    status: str
    priority: str
    reporter: str
    sprint: str | None
    description: str = ""
    assignee: str | None = None
    labels: list[str] = field(default_factory=list)
    points: int | None = None
    pr_url: str | None = None
    branch: str | None = None
    source: dict | None = None
    events: list[Ev] = field(default_factory=list)


# Bugs that Scout opened from production errors and Forge fixed end to end.
AGENT_BUGS = [
    dict(
        t0=at(8, 18, 9, 12), slug="risk-zero-claims", pr=7, priority="High", points=2, pace=1.0,
        title="Risk score returns 500 for buildings with no claims history",
        endpoint="GET /api/buildings/{id}/risk", error="ZeroDivisionError", count=41, impact=12,
        module="atlas/domain/risk.py", func="claims_frequency", test="tests/test_risk.py::test_score_with_no_claims",
        message="division by zero",
        stack=[
            'File "/app/atlas/api/routes.py", line 88, in building_risk',
            "    r = risk.score(b, claims, today)",
            'File "/app/atlas/domain/risk.py", line 61, in score',
            "    freq = claims_frequency(claims, years=5)",
            'File "/app/atlas/domain/risk.py", line 34, in claims_frequency',
            "    return sum(c.incurred for c in claims) / len(claims) / years",
            "ZeroDivisionError: division by zero",
        ],
        repro="Curl `/api/buildings/2201/risk` (Coral Quays, insured since May, zero claims). 500 every time; any building with a non-empty claims list is fine.",
        fail_detail="`claims_frequency([], years=5)` raises instead of returning `Decimal(0)`.",
        root_cause="`claims_frequency` divides by `len(claims)` to get an average incurred, but a brand-new building legitimately has none.",
        fix="Guard the empty list: frequency is zero when there are no claims. Weights and bands untouched.",
        sentinel="One-line guard in the right place. I checked that the band table is unchanged and that a building with claims still scores identically (compared against a fixture from `main`).",
        maroun="Zero-claims buildings are exactly the ones brokers quote on first. Good catch.",
        smoke="GET /api/buildings/2201/risk → 200, band B; GET /api/buildings/1/risk unchanged at 63/C",
        not_changed="Risk weights, band thresholds, the 5-year window.",
    ),
    dict(
        t0=at(8, 19, 14, 3), slug="per-lot-split-odd", pr=9, priority="Highest", points=3, pace=1.3,
        title="Quote crashes when the per-lot premium split does not sum to the total (odd lot counts)",
        endpoint="POST /api/policies/{policy_number}/quote", error="AssertionError", count=118, impact=40,
        module="atlas/domain/rating.py", func="per_lot_split", test="tests/test_money.py::test_split_is_exact_for_odd_lot_counts",
        message="per-lot split 47000.01 != annual premium 47000.00",
        stack=[
            'File "/app/atlas/api/routes.py", line 121, in quote',
            "    q = rating.quote(policy, building, claims, today)",
            'File "/app/atlas/domain/rating.py", line 142, in quote',
            "    per_lot = per_lot_split(annual, building.lots)",
            'File "/app/atlas/domain/rating.py", line 97, in per_lot_split',
            '    assert sum(parts) == total, f"per-lot split {sum(parts)} != annual premium {total}"',
            "AssertionError: per-lot split 47000.01 != annual premium 47000.00",
        ],
        repro="`POST /api/policies/ATL-3312/quote` (Harbourview Towers, 37 lots). Total 47,000.00 split 37 ways rounds each share up; the sum is a cent over. Any lot count that does not divide the premium evenly fails.",
        fail_detail="37 lots × `quantize(ROUND_HALF_UP)` produces 47,000.01.",
        root_cause="Each share is rounded independently. The remainder cents are never redistributed, so the invariant the assertion protects is violated whenever `total % lots != 0`.",
        fix="Split with floor division and hand the leftover cents to the first `n` lots (largest-remainder). Assertion kept; it now holds.",
        sentinel="The assertion was doing its job and the fix keeps it. I ran the new test with 1..500 lots against random premiums; sum is always exact. No change to rates or loadings.",
        maroun="This is the one brokers screenshot. Ship it.",
        smoke="POST /api/policies/ATL-3312/quote → 200, 37 shares summing to 47000.00; error signature absent for 10 min",
        not_changed="Base rates, loadings, rounding mode for the annual premium itself.",
    ),
    dict(
        t0=at(8, 20, 10, 41), slug="commission-float", pr=11, priority="High", points=2, pace=0.9,
        title="Quote fails for brokers with a commission override (Decimal + float)",
        endpoint="POST /api/policies/{policy_number}/quote", error="TypeError", count=27, impact=9,
        module="atlas/domain/rating.py", func="apply_commission", test="tests/test_rating.py::test_commission_override_is_decimal",
        message="unsupported operand type(s) for *: 'decimal.Decimal' and 'float'",
        stack=[
            'File "/app/atlas/domain/rating.py", line 151, in quote',
            "    annual = apply_commission(annual, broker)",
            'File "/app/atlas/domain/rating.py", line 118, in apply_commission',
            "    return money.cents(net * (1 + broker.commission_override))",
            "TypeError: unsupported operand type(s) for *: 'decimal.Decimal' and 'float'",
        ],
        repro="Quote any policy under broker 17 (Bluegum Strata Brokers), who has `commission_override = 0.125` set. Brokers on the default rate quote fine.",
        fail_detail="The override arrives from the row as `float`; `Decimal * float` raises.",
        root_cause="`brokers.commission_override` is `double precision` in the schema and `repo._broker` copies it straight into the dataclass, so it is the only money-adjacent field that is a float.",
        fix="Coerce to `Decimal` at the repository boundary (`Decimal(str(x))`), where every other money field is already converted. No schema change.",
        sentinel="Correct layer for the fix (the boundary, not the domain). I looked for other float leaks in `repo.py` and found none. Would prefer a column type change later — noted as follow-up, not blocking.",
        maroun="Agree the column should change; that's a Sprint 16 item, not this PR.",
        smoke="POST /api/policies/ATL-2087/quote (broker 17) → 200, commission line 12.5%",
        not_changed="Commission rates, the brokers schema.",
    ),
    dict(
        t0=at(8, 21, 8, 27), slug="wa-timezone", pr=12, priority="High", points=1, pace=1.1,
        title="Renewal list crashes for WA policies: state timezone map lacks Australia/Perth",
        endpoint="GET /api/policies", error="KeyError", count=63, impact=31,
        module="atlas/domain/renewals.py", func="business_date_for_state", test="tests/test_renewals.py::test_every_state_has_a_timezone",
        message="'WA'",
        stack=[
            'File "/app/atlas/api/routes.py", line 44, in list_policies',
            "    days_until_expiry=renewals.days_until_expiry(p, today, state=b.state)",
            'File "/app/atlas/domain/renewals.py", line 52, in days_until_expiry',
            "    local = business_date_for_state(today, state)",
            'File "/app/atlas/domain/renewals.py", line 39, in business_date_for_state',
            "    return now.astimezone(ZoneInfo(STATE_TZ[state])).date()",
            "KeyError: 'WA'",
        ],
        repro="`GET /api/policies?due_within_days=30` with any WA building in the window. Every state east of the Nullarbor works; WA raises. Reproducible with building 3140 (Scarborough).",
        fail_detail="`STATE_TZ` has seven keys; `WA` is missing.",
        root_cause="`STATE_TZ` was copied from the state list at the time and WA was added to the book after. No test enumerated the states.",
        fix="Add `WA: Australia/Perth` and a test that asserts every state in `STATES` has a zone.",
        sentinel="Data fix plus the test that should have existed. Checked the zone name against `zoneinfo.available_timezones()`. Approve.",
        maroun="Approved.",
        smoke="GET /api/policies?due_within_days=30 → 200 with 4 WA rows; KeyError signature absent",
        not_changed="Business timezone default (Australia/Sydney), renewal window length.",
    ),
    dict(
        t0=at(8, 24, 11, 5), slug="policies-n-plus-one", pr=14, priority="Highest", points=3, pace=1.5,
        title="Policy list exhausts the connection pool under broker portal load (N+1 building lookups)",
        endpoint="GET /api/policies", error="PoolTimeout", count=212, impact=40,
        module="atlas/db/repo.py", func="buildings_by_ids", test="tests/test_api.py::test_policy_list_uses_one_building_query",
        message="couldn't get a connection after 30.00 sec",
        stack=[
            'File "/app/atlas/api/routes.py", line 38, in list_policies',
            "    buildings = {p.building_id: repo.get_building(p.building_id) for p in policies}",
            'File "/app/atlas/db/repo.py", line 26, in get_building',
            "    with conn() as c:",
            'File "/app/.venv/lib/python3.13/site-packages/psycopg_pool/pool.py", line 202, in getconn',
            "    raise PoolTimeout(f\"couldn't get a connection after {timeout:.2f} sec\")",
            "psycopg_pool.PoolTimeout: couldn't get a connection after 30.00 sec",
        ],
        repro="`GET /api/policies?limit=500` runs 501 queries (1 + one per building). Under the 09:00 broker portal burst the pool (max 8) is held for ~9 s per request and callers time out. Query count confirmed with `log_statement=all` locally.",
        fail_detail="The test counts statements via a psycopg hook and sees 501 for 500 policies.",
        root_cause="The route fetches each building individually inside the loop. `repo.buildings_by_ids` exists but is not used here.",
        fix="One `where id = any(%s)` lookup for the whole page; the route uses `buildings_by_ids`. Response shape identical.",
        sentinel="Response payload byte-identical to `main` on the seed portfolio (I diffed it). Query count 2. The test pins that, which stops this regressing. Approve.",
        maroun="This one was hurting brokers at 9am every day. Approved, thank you.",
        smoke="GET /api/policies?limit=500 p95 3.1 s → 140 ms; pool wait 0",
        not_changed="Pool size, page size limit, response schema.",
    ),
    dict(
        t0=at(8, 25, 15, 48), slug="claims-sort-str-date", pr=15, priority="Medium", points=2, pace=1.2,
        title="Claims history endpoint 500s when an imported claim carries a string loss_date",
        endpoint="GET /api/buildings/{id}/claims", error="TypeError", count=9, impact=3,
        module="atlas/db/repo.py", func="claims_for_building", test="tests/test_api.py::test_claims_sort_with_legacy_string_dates",
        message="'<' not supported between instances of 'str' and 'datetime.date'",
        stack=[
            'File "/app/atlas/api/routes.py", line 103, in building_claims',
            "    claims = repo.claims_for_building(building_id)",
            'File "/app/atlas/db/repo.py", line 88, in claims_for_building',
            "    return sorted((_claim(r) for r in rows), key=lambda c: c.loss_date, reverse=True)",
            "TypeError: '<' not supported between instances of 'str' and 'datetime.date'",
        ],
        repro="Building 1188 (Riverbend Court) has three claims migrated from the legacy system whose `loss_date` is stored in the `raw` jsonb as a string. `_claim` prefers `raw.loss_date` when present. `GET /api/buildings/1188/claims` → 500.",
        fail_detail="A fixture with one legacy row and one native row cannot be sorted.",
        root_cause="`_claim` falls back to the legacy `raw.loss_date` string without parsing it, so the dataclass can carry two types for one field.",
        fix="Parse the legacy string with `date.fromisoformat` in `_claim`; the sort key is then homogeneous. Also sort in SQL so Python never re-sorts.",
        sentinel="Fix is at the mapper, which is right. Parsing is strict ISO and the legacy data is ISO — I sampled 200 rows in the seed to confirm. Approve.",
        maroun="Approved.",
        smoke="GET /api/buildings/1188/claims → 200, 7 rows newest first",
        not_changed="Claims schema, the legacy `raw` column.",
    ),
    dict(
        t0=at(8, 26, 9, 33), slug="ai-report-prompt-length", pr=16, priority="Medium", points=3, pace=1.4,
        title="AI building report fails for buildings with more than ~200 claims (prompt too long)",
        endpoint="POST /api/ai/building-report/{id}", error="BadRequestError", count=6, impact=2,
        module="atlas/ai.py", func="building_report", test="tests/test_ai.py::test_report_prompt_is_bounded",
        message="prompt is too long: 214812 tokens > 200000 maximum",
        stack=[
            'File "/app/atlas/api/routes.py", line 140, in ai_building_report',
            "    report = ai.building_report(b, claims, risk)",
            'File "/app/atlas/ai.py", line 71, in building_report',
            "    resp = client.messages.create(model=model, max_tokens=1500, messages=[{'role': 'user', 'content': prompt}])",
            "anthropic.BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'prompt is too long: 214812 tokens > 200000 maximum'}}",
        ],
        repro="Building 402 (Marina Heights, 236 claims over 12 years). Every claim's full description is inlined into the prompt. Buildings under ~180 claims succeed.",
        fail_detail="The prompt for a 236-claim fixture is 214k tokens; the test asserts it stays under 60k.",
        root_cause="`building_report` concatenates every claim verbatim. Nothing bounds the input.",
        fix="Summarise claims into a per-peril table (count, total incurred, last loss) and include only the 25 most recent narratives. Prompt is now ~9k tokens for the worst building.",
        sentinel="Sensible bound and the report keeps what an underwriter reads first. I compared reports on two mid-size buildings before/after: same conclusions. No new dependency. Approve.",
        maroun="Report reads better, honestly. Approved.",
        smoke="POST /api/ai/building-report/402 → 200 in 11 s; report cached",
        not_changed="Model, max_tokens, report caching.",
    ),
    dict(
        t0=at(8, 27, 13, 19), slug="csv-blank-sum-insured", pr=18, priority="High", points=2, pace=1.0,
        title="Broker CSV import crashes on rows with an empty sum insured",
        endpoint="POST /api/brokers/{id}/import", error="InvalidOperation", count=14, impact=5,
        module="atlas/domain/money.py", func="cents", test="tests/test_money.py::test_cents_rejects_blank_with_a_clear_error",
        message="[<class 'decimal.ConversionSyntax'>]",
        stack=[
            'File "/app/atlas/api/routes.py", line 162, in broker_import',
            "    rows = [importer.parse_row(r) for r in reader]",
            'File "/app/atlas/domain/importer.py", line 40, in parse_row',
            "    sum_insured=cents(row['sum_insured']),",
            'File "/app/atlas/domain/money.py", line 12, in cents',
            "    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)",
            "decimal.InvalidOperation: [<class 'decimal.ConversionSyntax'>]",
        ],
        repro="Import the Coastline Risk Partners renewal spreadsheet (row 212 has a blank `sum_insured`). Whole file rejected with a 500 and no row number.",
        fail_detail="`cents('')` raises `InvalidOperation` with an unreadable message.",
        root_cause="`cents` assumes a well-formed string. The importer passes cell contents straight through. A blank cell is a data problem, not a crash.",
        fix="`parse_row` validates required money cells and raises a `BusinessRuleViolation('import.blank_sum_insured')` carrying the row number; the API returns 422 with that row. `cents` itself unchanged.",
        sentinel="Good: the domain rule is now explicit and the broker gets a row number. Checked that a valid file imports byte-for-byte the same. Approve.",
        maroun="Brokers will love the row number. Approved.",
        smoke="POST /api/brokers/9/import (bad file) → 422 row 212; (good file) → 201, 340 rows",
        not_changed="`money.cents`, import column mapping.",
    ),
    dict(
        t0=at(9, 1, 9, 2), slug="lapsed-null-expiry", pr=21, priority="High", points=1, pace=1.0,
        title="Renewal list 500s when a lapsed policy has no expiry date",
        endpoint="GET /api/policies", error="AttributeError", count=33, impact=18,
        module="atlas/domain/renewals.py", func="days_until_expiry", test="tests/test_renewals.py::test_days_until_expiry_ignores_lapsed_without_expiry",
        message="'NoneType' object has no attribute 'toordinal'",
        stack=[
            'File "/app/atlas/api/routes.py", line 44, in list_policies',
            "    days_until_expiry=renewals.days_until_expiry(p, today)",
            'File "/app/atlas/domain/renewals.py", line 58, in days_until_expiry',
            "    return (policy.expiry_date - today).days",
            "AttributeError: 'NoneType' object has no attribute 'toordinal'",
        ],
        repro="Policy ATL-0419 lapsed in July and its expiry was nulled by the cancellation job. `GET /api/policies` (no filter) includes it and dies. With `due_within_days` set the SQL excludes it, which is why the portal only broke on the unfiltered admin view.",
        fail_detail="`days_until_expiry` on a policy with `expiry_date=None`.",
        root_cause="The unfiltered branch of `list_policies` queries all active-or-lapsed policies, and lapsed policies may legitimately have no expiry.",
        fix="`days_until_expiry` returns `None` when there is no expiry; the schema already allows `days_until_expiry: int | None`.",
        sentinel="Minimal. Confirmed the response model already permits null. Approve.",
        maroun="Approved.",
        smoke="GET /api/policies → 200, 2500 rows, 4 with null days_until_expiry",
        not_changed="Cancellation job, renewal window.",
    ),
    dict(
        t0=at(9, 4, 10, 14), slug="legacy-cladding-flag", pr=22, priority="Medium", points=2, pace=1.1,
        title="Risk score crashes for legacy buildings missing the cladding flag",
        endpoint="GET /api/buildings/{id}/risk", error="KeyError", count=19, impact=7,
        module="atlas/domain/risk.py", func="score", test="tests/test_risk.py::test_score_treats_missing_cladding_as_unknown",
        message="'cladding_flag'",
        stack=[
            'File "/app/atlas/api/routes.py", line 88, in building_risk',
            "    r = risk.score(b, claims, today)",
            'File "/app/atlas/domain/risk.py", line 71, in score',
            "    if attrs['cladding_flag']:",
            "KeyError: 'cladding_flag'",
        ],
        repro="Buildings imported before 2019 (about 140) have no `cladding_flag` in their `attributes` jsonb. `GET /api/buildings/77/risk` → 500.",
        fail_detail="A building dict without the key raises inside `score`.",
        root_cause="`score` indexes the attributes jsonb directly. The column-backed `Building.cladding_flag` exists and defaults to `False`, but the risk code reads the raw jsonb instead.",
        fix="Read `building.cladding_flag` (the typed field) rather than the jsonb. Unknown stays `False`, which is the existing default; no loading change.",
        sentinel="Good catch that the typed field already exists. Ran the seed risk scores before/after: identical for all non-legacy buildings. Approve.",
        maroun="Approved.",
        smoke="GET /api/buildings/77/risk → 200, band C; 140 legacy buildings scored",
        not_changed="Cladding loading weight, band thresholds.",
    ),
]


def _scout_description(b: dict) -> str:
    stack = "\n".join(b["stack"])
    return f"""## What Scout saw

**{b['count']}** occurrences of `{b['error']}` on `{b['endpoint']}` in the last 6 hours, first seen {b['t0'].strftime('%d %b %H:%M')}. Estimated customer impact: **~{b['impact']} policyholders** per hour.

## Reproduction

{b['repro']}

## Stack trace (excerpt)

```
Traceback (most recent call last):
  {stack.replace(chr(10), chr(10) + '  ')}
```

## Signature

`{b['endpoint']}:{b['error']}` — grouped from `error.raised` events on the lab bus.

## Suggested owner

Forge. This is a crash, not a business-rule question; it does not need an underwriting decision.
"""


def _agent_bug(b: dict, sprint: str) -> Spec:
    t0: datetime = b["t0"]
    p = b["pace"]
    pr_url = f"{GITHUB}/pull/{b['pr']}"
    branch = f"forge/{b['slug']}"
    module, func, test = b["module"], b["func"], b["test"]

    def m(minutes: float) -> datetime:
        return t0 + timedelta(minutes=round(minutes * p))

    events = [
        Ev(m(0), "scout", "created", to="Triage"),
        Ev(m(0), "scout", "assigned", to="forge"),
        Ev(m(0.5), "scout", "commented", body=f"Grouped {b['count']} `error.raised` events into one signature. Threshold crossed at {b['count']//2}; opening rather than waiting. Assigning to Forge because the stack ends in application code, not infrastructure."),
        Ev(m(2), "forge", "reasoning", body=f"Reading CLAUDE.md and the ticket. The endpoint is `{b['endpoint']}`; following it from `atlas/api/routes.py` into `{module}`. The trace ends in `{func}`, so that is where I will look first — but I will reproduce before I touch anything."),
        Ev(m(3), "forge", "transitioned", frm="Triage", to="In Progress"),
        Ev(m(9), "forge", "reasoning", body=f"Reproduced with a failing test in `{test}`. It fails as the ticket describes: {b['fail_detail']} Running the rest of the suite to make sure it is otherwise green before I change anything — it is."),
        Ev(m(15), "forge", "reasoning", body=f"Root cause: {b['root_cause']} The smallest change is in `{func}`. I checked the CLAUDE.md rule about business constants: this fix does not touch rates, loadings, thresholds or the renewal window, so I can proceed without escalating."),
        Ev(m(21), "forge", "reasoning", body=f"{b['fix']} Full suite green, ruff clean. Opening the PR with the Root cause / Fix / Test / Not changed sections the repo asks for."),
        Ev(m(22), "forge", "field_changed", frm=None, to=branch, body="branch"),
        Ev(m(22), "forge", "field_changed", frm=None, to=pr_url, body="pr_url"),
        Ev(m(22.5), "forge", "commented", body=f"""Opened PR #{b['pr']}: {pr_url}

**Root cause** — {b['root_cause']}

**Fix** — {b['fix']}

**Test** — `{test}` (fails on `main`, passes on `{branch}`).

**Not changed** — {b['not_changed']}

Waiting for Sentinel's review and a human approval before merge; I cannot merge."""),
        Ev(m(23), "forge", "transitioned", frm="In Progress", to="In Review"),
        Ev(m(31), "sentinel", "commented", body=f"""Reviewed PR #{b['pr']} independently (fresh checkout, did not read Forge's reasoning first).

{b['sentinel']}

- Test fails on `main`, passes on the branch ✔
- Diff confined to the ticket ✔
- No business constants changed ✔
- No new dependencies ✔

**Approve.** Merge still needs a human — that is not mine to do."""),
        Ev(m(52), "maroun", "commented", body=f"{b['maroun']} Approving the merge from Mission Control."),
        Ev(m(59), "conductor", "commented", body=f"""Deploy `{b['slug'][:4]}{b['pr']:02d}a3` (PR #{b['pr']}) rolled out via the ECS service; health green after 40 s.

Smoke: {b['smoke']}.

Watched the error bus for 10 minutes after deploy: signature `{b['endpoint']}:{b['error']}` **not seen**. Closing."""),
        Ev(m(60), "conductor", "transitioned", frm="In Review", to="Done"),
    ]
    return Spec(
        created_at=t0, type="Bug", title=b["title"], status="Done", priority=b["priority"], reporter="scout",
        assignee="forge", sprint=sprint, description=_scout_description(b), labels=["production", "agent-fixed", module.split("/")[-1].replace(".py", "")],
        points=b["points"], pr_url=pr_url, branch=branch,
        source={"kind": "error.raised", "signature": f"{b['endpoint']}:{b['error']}", "count": b["count"], "customer_impact": b["impact"], "first_seen": t0.isoformat()},
        events=events,
    )


def _incident() -> Spec:
    t0 = at(9, 3, 9, 41)

    def m(minutes: int) -> datetime:
        return t0 + timedelta(minutes=minutes)

    description = """## Incident: quote error rate 14% after deploy of rating v0.4.2

**Detected** 03 Sep 09:41 AEST by Scout (threshold crossed on `POST /api/policies/{policy_number}/quote:InvalidOperation`).
**Impact** ~1 in 7 quotes failed for 26 minutes during the morning broker peak. No incorrect premiums were issued; failures were hard errors.
**Severity** SEV-2.

## Timeline (AEST)

| Time | What |
|---|---|
| 09:14 | Conductor deploys `a91f2c` (PR #19, rating: regional loading table refresh). Smoke passes. |
| 09:38 | First `InvalidOperation` on quote for a QLD policy. |
| 09:41 | Scout crosses threshold (30 in 3 min), opens this incident and pages Watchtower. |
| 09:44 | Watchtower correlates: 100% of failures are QLD postcodes 4800–4899. |
| 09:47 | Conductor rolls back to `7c02e1`. Error rate returns to 0 by 09:50. |
| 10:05 | Root cause identified: the refreshed loading table has `"1.15 "` (trailing space) for the 48xx band; `Decimal("1.15 ")` raises. |
| 10:40 | Fix PR #20 (strip and validate loading table cells on load, with a test) reviewed and merged. |
| 11:10 | Redeployed. Verified. |

## Root cause

A data file change shipped in a code deploy with no validation of the values it contained.

## Actions

- [x] Validate every loading table cell at import (PR #20)
- [x] Add a `loading_table_valid` startup check that fails the health endpoint
- [ ] Separate rate-table changes from code deploys (ATLAS Sprint 16: rate table versioning)
"""
    events = [
        Ev(m(0), "scout", "created", to="Triage"),
        Ev(m(0), "scout", "assigned", to="watchtower"),
        Ev(m(1), "watchtower", "transitioned", frm="Triage", to="In Progress"),
        Ev(m(2), "watchtower", "reasoning", body="Incident opened. First job is the timeline, not the fix. Pulling the last hour of `error.raised` events and the deploy log from the bus."),
        Ev(m(3), "watchtower", "commented", body="**09:44** — Correlation: all 41 failures so far are quotes for QLD postcodes 4800–4899. Nothing else has changed since the 09:14 deploy of `a91f2c` (PR #19, loading table refresh). Recommending rollback to Conductor."),
        Ev(m(6), "conductor", "commented", body="**09:47** — Rolled back to `7c02e1`. Health green. Watching the quote error rate."),
        Ev(m(9), "watchtower", "commented", body="**09:50** — Quote error rate back to 0. Impact window 09:38–09:50, ~26 minutes including the tail. Now looking at *why* the 48xx band failed."),
        Ev(m(24), "watchtower", "reasoning", body="Diffed the loading table between the two deploys. The 4800–4899 row reads `\"1.15 \"` — a trailing space in the CSV. `Decimal(\"1.15 \")` raises `InvalidOperation`. This is a data-validation gap, not a rating logic problem, so Forge can fix it without an underwriting decision."),
        Ev(m(25), "watchtower", "commented", body="**10:05** — Root cause: trailing whitespace in one cell of the refreshed loading table; `Decimal()` refuses it. Handing the fix to Forge (ATLAS ticket via Scout); keeping this incident open for the postmortem."),
        Ev(m(89), "conductor", "commented", body="**11:10** — PR #20 (validate loading table cells on load, plus a test) merged after Sentinel review and Maroun's approval; redeployed. Quote smoke on 12 QLD policies green."),
        Ev(m(95), "watchtower", "transitioned", frm="In Progress", to="In Review"),
        Ev(m(96), "watchtower", "commented", body="Postmortem draft is in the description. One open action needs a product decision: separating rate-table changes from code deploys. Proposing it for Sprint 16."),
        Ev(at(9, 4, 16, 30), "maroun", "commented", body="Reviewed the postmortem. Blameless and accurate. Rate table versioning is now ATLAS Sprint 16 work. Closing."),
        Ev(at(9, 4, 16, 31), "maroun", "transitioned", frm="In Review", to="Done"),
    ]
    return Spec(
        created_at=t0, type="Incident", title="INC 2026-09-03: quote error rate 14% after rating v0.4.2 deploy",
        status="Done", priority="Highest", reporter="scout", assignee="watchtower", sprint="Sprint 15",
        description=description, labels=["incident", "sev2", "rating"], points=None,
        source={"kind": "incident.opened", "signature": "POST /api/policies/{policy_number}/quote:InvalidOperation", "count": 41, "customer_impact": 120},
        events=events,
    )


def _human(
    t0: datetime, type_: str, title: str, status: str, priority: str, reporter: str, sprint: str | None,
    *, assignee: str | None = None, labels: list[str] | None = None, points: int | None = None, description: str = "",
    steps: list[tuple[int, str, str, str]] | None = None, comments: list[tuple[int, str, str]] | None = None,
    pr_url: str | None = None, branch: str | None = None,
) -> Spec:
    """A ticket with an ordinary human history: created, maybe assigned, moved through some statuses."""
    events = [Ev(t0, reporter, "created", to="Backlog")]
    if assignee:
        events.append(Ev(t0, reporter, "assigned", to=assignee))
    for minutes, actor, frm, to in steps or []:
        events.append(Ev(t0 + timedelta(minutes=minutes), actor, "transitioned", frm=frm, to=to))
    for minutes, actor, body in comments or []:
        events.append(Ev(t0 + timedelta(minutes=minutes), actor, "commented", body=body))
    events.sort(key=lambda e: e.at)
    return Spec(
        created_at=t0, type=type_, title=title, status=status, priority=priority, reporter=reporter, sprint=sprint,
        assignee=assignee, labels=labels or [], points=points, description=description, pr_url=pr_url, branch=branch, events=events,
    )


DAY = 24 * 60
DONE_14 = [(30, "maroun", "Backlog", "Triage")]  # the rest is filled per ticket


def _sprint14_human() -> list[Spec]:
    return [
        _human(
            at(8, 17, 9, 5), "Story", "Add Prometheus /metrics endpoint with request and error counters", "Done", "High", "maroun", "Sprint 14",
            assignee="priya", labels=["observability"], points=3,
            description="As the on-call engineer I want `/metrics` in Prometheus text format so the lab dashboard can show request rates and error counts without scraping logs.\n\n**Acceptance**\n- `atlas_http_requests_total{path,status}`\n- `atlas_errors_total{kind}`\n- `/metrics` is open (no basic auth) like `/health`",
            steps=[(40, "maroun", "Backlog", "Triage"), (DAY + 15, "priya", "Triage", "In Progress"), (3 * DAY, "priya", "In Progress", "In Review"), (3 * DAY + 400, "tom", "In Review", "Done")],
            comments=[(3 * DAY, "priya", f"PR: {GITHUB}/pull/3 — counters are process-local, which is fine for two workers behind the ALB."), (3 * DAY + 390, "tom", "Reviewed and merged. Nice and small.")],
            pr_url=f"{GITHUB}/pull/3", branch="priya/metrics",
        ),
        _human(
            at(8, 17, 9, 20), "Task", "Structured JSON logging with request id on every line", "Done", "Medium", "maroun", "Sprint 14",
            assignee="tom", labels=["observability"], points=2,
            description="Switch the root logger to `python-json-logger`. Every line carries `ts`, `level`, `logger`, `service`, `env`, and `request_id` when inside a request.",
            steps=[(45, "maroun", "Backlog", "Triage"), (DAY + 60, "tom", "Triage", "In Progress"), (2 * DAY + 30, "tom", "In Progress", "In Review"), (2 * DAY + 300, "priya", "In Review", "Done")],
            comments=[(2 * DAY + 30, "tom", f"{GITHUB}/pull/4")],
            pr_url=f"{GITHUB}/pull/4", branch="tom/json-logs",
        ),
        _human(
            at(8, 17, 10, 2), "Story", "Business-date helper: renewals computed in Australia/Sydney, not UTC", "Done", "High", "alex", "Sprint 14",
            assignee="priya", labels=["renewals", "timezone"], points=3,
            description="Renewals at 00:10 AEST were being treated as the previous day because the server clock is UTC. Introduce `renewals.business_today(now, tz)` and use it everywhere a renewal date is compared.",
            steps=[(20, "maroun", "Backlog", "Triage"), (4 * DAY, "priya", "Triage", "In Progress"), (6 * DAY, "priya", "In Progress", "In Review"), (6 * DAY + 200, "tom", "In Review", "Done")],
            comments=[(6 * DAY, "priya", f"{GITHUB}/pull/6 — one helper, every call site updated, tests cover the midnight boundary.")],
            pr_url=f"{GITHUB}/pull/6", branch="priya/business-today",
        ),
        _human(
            at(8, 17, 10, 30), "Task", "Make the seed deterministic (fixed RNG seed, fictional 9xxxxx plan numbers)", "Done", "Low", "tom", "Sprint 14",
            assignee="tom", labels=["dev-experience"], points=1,
            description="Tests and the demo both need the same portfolio every time. Seed the RNG, and keep plan numbers in the obviously fictional 9xxxxx range.",
            steps=[(10, "tom", "Backlog", "Triage"), (DAY, "tom", "Triage", "In Progress"), (DAY + 120, "tom", "In Progress", "In Review"), (DAY + 400, "priya", "In Review", "Done")],
            pr_url=f"{GITHUB}/pull/5", branch="tom/seed-determinism",
        ),
    ]


def _sprint15_human() -> list[Spec]:
    s = "Sprint 15"
    return [
        # Done by humans
        _human(
            at(8, 31, 9, 10), "Task", "Upgrade psycopg to 3.2 and pin the pool size per worker", "Done", "Medium", "tom", s,
            assignee="tom", labels=["dependencies"], points=1,
            description="3.2 fixes the pool timeout accounting we hit in Sprint 14. Set `max_size=8` per worker explicitly.",
            steps=[(15, "tom", "Backlog", "Triage"), (60, "tom", "Triage", "In Progress"), (300, "tom", "In Progress", "In Review"), (DAY, "priya", "In Review", "Done")],
            pr_url=f"{GITHUB}/pull/17", branch="tom/psycopg-3-2",
        ),
        _human(
            at(8, 31, 9, 30), "Story", "Claims severity uses incurred, not paid, in the risk score", "Done", "High", "alex", s,
            assignee="priya", labels=["risk"], points=3,
            description="Underwriting decision (Alex, 28 Aug): severity should reflect *incurred* (paid + reserves), because open large claims are exactly the signal we need at renewal. Paid-only understates buildings with a live large loss.\n\nThis is a business-rule change and is approved by the underwriting lead in this ticket.",
            steps=[(20, "maroun", "Backlog", "Triage"), (DAY, "priya", "Triage", "In Progress"), (3 * DAY, "priya", "In Progress", "In Review"), (4 * DAY, "alex", "In Review", "Done")],
            comments=[(3 * DAY, "priya", f"{GITHUB}/pull/23 — weight unchanged, input changed to `incurred`. 14 buildings move band; list attached in the PR."), (4 * DAY - 10, "alex", "Checked the 14. All defensible. Approved.")],
            pr_url=f"{GITHUB}/pull/23", branch="priya/severity-incurred",
        ),
        _human(
            at(8, 31, 10, 0), "Story", "Broker list endpoint: paginate and add a state filter", "Done", "Medium", "maroun", s,
            assignee="tom", labels=["brokers"], points=2,
            description="`GET /api/brokers` returns all 40 brokers unpaged. Add `limit`/`offset` and `state=` so the portal can filter by licence state.",
            steps=[(20, "maroun", "Backlog", "Triage"), (2 * DAY, "tom", "Triage", "In Progress"), (3 * DAY, "tom", "In Progress", "In Review"), (3 * DAY + 240, "priya", "In Review", "Done")],
            comments=[(3 * DAY, "tom", f"{GITHUB}/pull/19 — same shape as the policies list.")],
            pr_url=f"{GITHUB}/pull/19", branch="tom/brokers-paging",
        ),
        _human(
            at(9, 8, 14, 30), "Task", "Renewal reminder email: underwriting review of the wording", "In Progress", "Low", "maroun", s,
            assignee="alex", labels=["renewals", "brokers"], points=1,
            description="The 30-day reminder still says 'your premium may change' with no reason. Alex to review the wording against the product disclosure statement before Tom wires it into the batch job.",
            steps=[(10, "maroun", "Backlog", "Triage"), (DAY, "alex", "Triage", "In Progress")],
        ),
        # In Review
        _human(
            at(9, 7, 9, 45), "Task", "Add request id to every log line and to error events", "In Review", "Medium", "maroun", s,
            assignee="forge", labels=["observability", "agent-fixed"], points=2,
            description="Error events on the bus carry `request_id`; the JSON logs do not. Correlating a Scout ticket to the log lines is manual today.",
            steps=[(10, "maroun", "Backlog", "Triage"), (DAY + 20, "forge", "Triage", "In Progress"), (DAY + 75, "forge", "In Progress", "In Review")],
            comments=[
                (DAY + 74, "forge", f"Opened PR #24: {GITHUB}/pull/24\n\n**Root cause** — the JSON formatter has no access to request scope.\n**Fix** — a `contextvar` set by the request-id middleware and read by a logging filter.\n**Test** — `tests/test_logging.py::test_request_id_on_every_line`.\n**Not changed** — log format field names."),
                (DAY + 130, "sentinel", "Reviewing. One question: the contextvar is reset in `finally`, but the exception handler logs *after* the reset in one path. Requesting a change."),
                (DAY + 150, "forge", "Good catch — moved the reset after the handler runs. Pushed."),
            ],
            pr_url=f"{GITHUB}/pull/24", branch="forge/request-id-logs",
        ),
        _human(
            at(9, 8, 11, 0), "Bug", "Broker portfolio total drifts by cents (float sum in the export)", "In Review", "High", "alex", s,
            assignee="priya", labels=["money", "brokers"], points=2,
            description="The broker CSV export sums `sum_insured` with `sum()` over floats coming from the DictWriter path. A 340-row portfolio is off by $0.03.",
            steps=[(30, "maroun", "Backlog", "Triage"), (DAY, "priya", "Triage", "In Progress"), (2 * DAY, "priya", "In Progress", "In Review")],
            comments=[(2 * DAY, "priya", f"{GITHUB}/pull/25 — Decimal all the way to the CSV writer.")],
            pr_url=f"{GITHUB}/pull/25", branch="priya/export-decimal",
        ),
        # In Progress
        _human(
            at(9, 2, 14, 0), "Story", "Batch renewal quote job for month-end broker statements", "In Progress", "High", "maroun", s,
            assignee="tom", labels=["renewals", "brokers"], points=5,
            description="Brokers want every policy renewing next month quoted in one run on the 25th, with a CSV per broker. Reuse `rating.quote`; no new rating logic.",
            steps=[(60, "maroun", "Backlog", "Triage"), (2 * DAY, "tom", "Triage", "In Progress")],
            comments=[(5 * DAY, "tom", "Job runs in 40 s for the whole book locally. Working on the per-broker CSV split and the idempotency key.")],
        ),
        _human(
            at(9, 5, 10, 15), "Task", "Document the risk band thresholds and loadings in the API docs", "In Progress", "Low", "alex", s,
            assignee="priya", labels=["docs", "risk"], points=1,
            description="Brokers keep asking what moves a building from B to C. Publish the thresholds table from `risk.py` in the OpenAPI description, generated from the constants so it cannot drift.",
            steps=[(30, "maroun", "Backlog", "Triage"), (3 * DAY, "priya", "Triage", "In Progress")],
        ),
        _human(
            at(9, 4, 17, 0), "Task", "Postmortem actions from INC 2026-09-03: startup validation of loading tables", "In Progress", "High", "watchtower", s,
            assignee="tom", labels=["incident", "rating"], points=2,
            description="From the incident postmortem: the service must refuse to start (fail `/health`) if any loading table cell does not parse as a Decimal in range.",
            steps=[(10, "maroun", "Backlog", "Triage"), (DAY + 60, "tom", "Triage", "In Progress")],
        ),
        # Triage
        _human(
            at(9, 10, 8, 50), "Bug", "Quote endpoint returns 500 for lapsed policies instead of a 422 business-rule error", "Triage", "Medium", "scout", s,
            assignee=None, labels=["production", "rating"], points=None,
            description="## What Scout saw\n\n**7** occurrences of `BusinessRuleViolation` escaping as 500 on `POST /api/policies/{policy_number}/quote` since 08:20.\n\n## Reproduction\n\n`POST /api/policies/ATL-0419/quote` (lapsed). Expected 422 `quote.inactive_policy`; got 500 `internal_error`.\n\n## Stack trace (excerpt)\n\n```\n  File \"/app/atlas/api/routes.py\", line 121, in quote\n    q = rating.quote(policy, building, claims, today)\n  File \"/app/atlas/domain/rating.py\", line 131, in quote\n    raise BusinessRuleViolation(\"quote.inactive_policy\", ...)\natlas.domain.errors.BusinessRuleViolation: quote.inactive_policy\n```\n\nThe exception handler is registered but the route wraps the call in a bare `except Exception` that re-raises as `RuntimeError`.\n\nLeaving unassigned: low volume, and Forge is on ATLAS request-id work.",
            steps=[(1, "scout", "Backlog", "Triage")],
        ),
        _human(
            at(9, 9, 9, 30), "Story", "Sum insured indexation: apply the 6% cap before or after the CPI uplift?", "Triage", "High", "alex", s,
            assignee="alex", labels=["rating", "needs-decision"], points=3,
            description="Brokers report renewals where the indexed sum insured exceeds the 6% cap. `rating.index_sum_insured` applies CPI then the cap; the product sheet reads as cap-then-CPI.\n\nThis needs an underwriting decision before any code changes.",
            steps=[(15, "maroun", "Backlog", "Triage"), (DAY, "forge", "Triage", "In Progress"), (DAY + 18, "forge", "In Progress", "Triage")],
            comments=[
                (DAY + 5, "forge", "Read the ticket and `rating.py`. Reproduced the reported number. Both orderings are internally consistent; the code matches the docstring, the product sheet says otherwise."),
            ],
        ),
        # Backlog (in sprint)
        _human(
            at(9, 11, 15, 20), "Story", "Claims photo upload for assessors (spike)", "Backlog", "Low", "maroun", s,
            labels=["claims", "spike"], points=2,
            description="Time-boxed spike: can assessors attach photos to a claim from the portal? Storage, size limits, virus scanning. Output is a one-page recommendation, not code.",
        ),
        _human(
            at(9, 12, 10, 5), "Task", "Investigate slow GET /api/buildings?state=QLD (p95 1.8 s)", "Backlog", "Medium", "scout", s,
            labels=["performance", "production"],
            description="No errors, but p95 for the QLD listing is 1.8 s against 220 ms for NSW. QLD has fewer buildings. Suspect a missing index on `buildings(state, postcode)` or the coastal-distance subquery.",
        ),
    ]


def _sprint16_and_backlog() -> list[Spec]:
    s16 = "Sprint 16"
    return [
        _human(at(9, 10, 16, 0), "Story", "Rate table versioning: rate changes ship separately from code", "Backlog", "Highest", "maroun", s16, labels=["rating", "incident-followup"], points=8,
               description="From INC 2026-09-03. Loading and base-rate tables get a version, an effective date, and a validation step, and are loaded at runtime rather than baked into the image."),
        _human(at(9, 10, 16, 10), "Story", "Broker self-service renewal portal (MVP)", "Backlog", "High", "maroun", s16, labels=["brokers"], points=8,
               description="Brokers see their renewing policies, request a quote, and download the schedule without emailing underwriting."),
        _human(at(9, 10, 16, 20), "Task", "Change brokers.commission_override from double precision to numeric(5,4)", "Backlog", "Medium", "tom", s16, labels=["money", "migration"], points=2,
               description="Follow-up from ATLAS Sentinel review of PR #11. Schema change, human-approved."),
        _human(at(9, 11, 9, 0), "Story", "Flood zone data refresh from the 2026 state datasets", "Backlog", "Medium", "alex", s16, labels=["risk", "data"], points=5,
               description="Load the new flood overlays for NSW and QLD and re-score affected buildings. Report the band movements to underwriting before they take effect."),
        _human(at(9, 11, 9, 15), "Task", "Trace ids across the SQS error queue and EventBridge", "Backlog", "Low", "tom", s16, labels=["observability"], points=3,
               description="Carry `request_id` through `error.raised` → Scout → board ticket so Mission Control can link a ticket back to the exact request."),
        _human(at(9, 12, 11, 30), "Task", "Remove the deprecated v0 quote endpoint", "Backlog", "Lowest", "priya", None, labels=["cleanup"], points=1,
               description="`POST /api/v0/quote` has had zero traffic for 60 days. Remove it and its tests."),
        _human(at(9, 12, 11, 45), "Story", "Broker commission statements (monthly PDF)", "Backlog", "Low", "alex", None, labels=["brokers", "money"], points=5,
               description="Monthly statement per broker: policies bound, premium, commission. Decimal throughout."),
        _human(at(9, 12, 12, 0), "Bug", "Timezone: renewal reminder emails go out at 10:00 UTC, not 10:00 AEST", "Backlog", "Medium", "priya", None, labels=["timezone", "renewals"], points=1,
               description="The reminder cron is expressed in UTC in the task definition. Brokers get reminders at 20:00 local."),
    ]


def build_specs() -> list[Spec]:
    specs: list[Spec] = []
    for b in AGENT_BUGS:
        specs.append(_agent_bug(b, "Sprint 14" if b["t0"].month == 8 else "Sprint 15"))
    specs.append(_incident())
    specs += _sprint14_human() + _sprint15_human() + _sprint16_and_backlog()
    specs.sort(key=lambda s: s.created_at)
    return specs


# ---------------------------------------------------------------- loading


def reset() -> None:
    with conn() as c:
        c.execute("truncate activity, comments, issues, sprints, projects, users restart identity cascade")


def seed() -> dict:
    with conn() as c:
        if c.execute("select count(*) as n from users").fetchone()["n"]:
            return {"skipped": "already seeded"}
        users = {u["handle"]: repo.upsert_user(c, u)["id"] for u in USERS}
        c.execute("insert into projects (key, name, issue_counter) values ('ATLAS', 'ATLAS', 0)")
        sprints = {}
        for s in SPRINTS:
            r = c.execute(
                "insert into sprints (name, goal, starts_on, ends_on, state) values (%(name)s, %(goal)s, %(starts_on)s, %(ends_on)s, %(state)s) returning id",
                s,
            ).fetchone()
            sprints[s["name"]] = r["id"]

        n_issues = n_activity = n_comments = 0
        for spec in build_specs():
            last = max((e.at for e in spec.events), default=spec.created_at)
            issue = repo.insert_issue(
                c,
                {
                    "type": spec.type, "title": spec.title, "description": spec.description, "status": spec.status,
                    "priority": spec.priority, "assignee_id": users[spec.assignee] if spec.assignee else None,
                    "reporter_id": users[spec.reporter], "labels": spec.labels, "story_points": spec.points,
                    "sprint_id": sprints[spec.sprint] if spec.sprint else None, "pr_url": spec.pr_url, "branch": spec.branch,
                    "source": spec.source, "resolved_at": last if spec.status == "Done" else None,
                },
                created_at=spec.created_at,
            )
            for e in spec.events:
                if e.kind == "commented":
                    repo.add_comment(c, issue["id"], users[e.actor], e.body or "", at=e.at)
                    n_comments += 1
                else:
                    repo.add_activity(c, issue["id"], users[e.actor], e.kind, from_value=e.frm, to_value=e.to, body=e.body, at=e.at)
                n_activity += 1
            c.execute("update issues set updated_at = %s where id = %s", (last, issue["id"]))
            n_issues += 1
        return {"users": len(users), "sprints": len(sprints), "issues": n_issues, "activity": n_activity, "comments": n_comments}
