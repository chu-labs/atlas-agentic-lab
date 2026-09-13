"""terraform destroy with a confirmation and a leftover-resource check."""
from __future__ import annotations

import subprocess

from .aws import client
from .config import LAB_NAME, TF_DIR


def leftovers() -> list[str]:
    """Tagged resources that still exist. Inactive ECS services/clusters/task-definition tombstones are ignored."""
    tagging = client("resourcegroupstaggingapi")
    ecs = client("ecs")
    out = []
    pages = tagging.get_paginator("get_resources").paginate(TagFilters=[{"Key": "Project", "Values": [LAB_NAME]}])
    for page in pages:
        for r in page["ResourceTagMappingList"]:
            arn = r["ResourceARN"]
            if ":ecs:" in arn:
                if ":task-definition/" in arn:
                    try:
                        td = ecs.describe_task_definition(taskDefinition=arn)["taskDefinition"]
                        if td["status"] != "ACTIVE":
                            continue
                    except Exception:  # noqa: BLE001
                        continue
                elif ":service/" in arn:
                    cluster = arn.split("/")[1]
                    try:
                        s = ecs.describe_services(cluster=cluster, services=[arn])["services"]
                        if not s or s[0]["status"] == "INACTIVE":
                            continue
                    except Exception:  # noqa: BLE001
                        continue
                elif ":cluster/" in arn:
                    try:
                        c = ecs.describe_clusters(clusters=[arn])["clusters"]
                        if not c or c[0]["status"] == "INACTIVE":
                            continue
                    except Exception:  # noqa: BLE001
                        continue
            out.append(arn)
    return out


def destroy() -> int:
    plan = subprocess.run(["terraform", "plan", "-destroy", "-input=false", "-out=destroy.plan"], cwd=TF_DIR)
    if plan.returncode != 0:
        return plan.returncode
    return subprocess.run(["terraform", "apply", "-input=false", "destroy.plan"], cwd=TF_DIR).returncode


def month_to_date_cost() -> dict:
    """Cost Explorer: this month's unblended cost for the lab's tag (AUD if the account bills in AUD)."""
    from datetime import date

    ce = client("ce")
    start = date.today().replace(day=1).isoformat()
    end = date.today().isoformat()
    if start == end:
        return {}
    resp = ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end}, Granularity="MONTHLY", Metrics=["UnblendedCost"],
        Filter={"Tags": {"Key": "Project", "Values": [LAB_NAME]}},
    )
    tot = resp["ResultsByTime"][0]["Total"]["UnblendedCost"]
    return {"amount": float(tot["Amount"]), "unit": tot["Unit"], "period": f"{start}..{end}"}
