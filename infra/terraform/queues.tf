resource "aws_sqs_queue" "dlq" {
  for_each                  = local.queues
  name                      = "${local.name}-${each.key}-dlq"
  message_retention_seconds = 86400 * 3
}

resource "aws_sqs_queue" "q" {
  for_each                   = local.queues
  name                       = "${local.name}-${each.key}"
  visibility_timeout_seconds = each.key == "forge" ? 1800 : 120
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = 3
  })
}

# EventBridge may deliver to every queue except prod-errors, which the platform writes to directly.
data "aws_iam_policy_document" "queue_from_events" {
  for_each = local.queues
  statement {
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.q[each.key].arn]
    # EventBridge presents the *rule* ARN as the source when delivering to a target.
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:events:${var.region}:${data.aws_caller_identity.me.account_id}:rule/${aws_cloudwatch_event_bus.lab.name}/*"]
    }
  }
}

resource "aws_sqs_queue_policy" "from_events" {
  for_each  = local.queues
  queue_url = aws_sqs_queue.q[each.key].id
  policy    = data.aws_iam_policy_document.queue_from_events[each.key].json
}
