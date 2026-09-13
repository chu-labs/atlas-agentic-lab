resource "aws_cloudwatch_event_bus" "lab" {
  name = local.name
}

# Event contract: source = "atlas.<component>", detail-type = "<domain>.<verb>".
# Mission Control sees everything. Agents see what they own.
locals {
  rules = {
    mission-events = { pattern = { source = [{ prefix = "atlas." }] } }
    forge          = { pattern = { source = ["atlas.board", "atlas.sentinel", "atlas.workbench"], detail-type = ["issue.assigned", "review.changes_requested", "workbench.dispatch"] } }
    sentinel       = { pattern = { source = ["atlas.forge", "atlas.workbench"], detail-type = ["pr.opened", "pr.updated"] } }
    conductor      = { pattern = { source = ["atlas.mission-control", "atlas.github"], detail-type = ["human.approved", "pr.merged", "deploy.completed"] } }
    watchtower     = { pattern = { source = ["atlas.scout"], detail-type = ["incident.threshold_crossed", "incident.resolved"] } }
  }
}

resource "aws_cloudwatch_event_rule" "route" {
  for_each       = local.rules
  name           = "${local.name}-${each.key}"
  event_bus_name = aws_cloudwatch_event_bus.lab.name
  event_pattern  = jsonencode(each.value.pattern)
}

resource "aws_cloudwatch_event_target" "route" {
  for_each       = local.rules
  rule           = aws_cloudwatch_event_rule.route[each.key].name
  event_bus_name = aws_cloudwatch_event_bus.lab.name
  arn            = aws_sqs_queue.q[each.key].arn
  target_id      = each.key
}
