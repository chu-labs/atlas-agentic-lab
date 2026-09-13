data "aws_caller_identity" "me" {}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role: pull images, write logs, read secrets at container start.
resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = concat(
      [for s in aws_secretsmanager_secret.s : s.arn],
      [aws_db_instance.lab.master_user_secret[0].secret_arn],
    )
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# One task role for everything in the lab. Authority between agents is enforced in code
# (agent.yaml) and shown on the dashboard; IAM is not the demo's policy layer.
resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "task" {
  statement {
    sid       = "Queues"
    actions   = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes", "sqs:GetQueueUrl", "sqs:PurgeQueue"]
    resources = [for q in aws_sqs_queue.q : q.arn]
  }
  statement {
    sid       = "Events"
    actions   = ["events:PutEvents"]
    resources = [aws_cloudwatch_event_bus.lab.arn]
  }
  statement {
    sid     = "Secrets"
    actions = ["secretsmanager:GetSecretValue"]
    resources = concat(
      [for s in aws_secretsmanager_secret.s : s.arn],
      [aws_db_instance.lab.master_user_secret[0].secret_arn],
    )
  }
  statement {
    sid       = "ReadLab"
    actions   = ["ecs:DescribeServices", "ecs:DescribeTasks", "ecs:ListTasks", "ecs:DescribeTaskDefinition", "elasticloadbalancing:DescribeTargetHealth", "logs:GetLogEvents", "logs:FilterLogEvents"]
    resources = ["*"]
  }
  statement {
    sid       = "Metrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = [local.name]
    }
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "lab"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

# GitHub Actions deploys via OIDC. Scoped to the two repos in the org.
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "gha_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      # GitHub's sub claim may carry numeric ids: repo:<org>@<id>/<repo>@<id>:ref:... Accept both forms.
      values = [
        "repo:${var.github_org}/atlas-platform:*", "repo:${var.github_org}/atlas-agentic-lab:*",
        "repo:${var.github_org}@*/atlas-platform@*:*", "repo:${var.github_org}@*/atlas-agentic-lab@*:*",
      ]
    }
  }
}

resource "aws_iam_role" "gha_deploy" {
  name               = "${local.name}-gha-deploy"
  assume_role_policy = data.aws_iam_policy_document.gha_assume.json
}

data "aws_iam_policy_document" "gha_deploy" {
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    actions   = ["ecr:BatchCheckLayerAvailability", "ecr:CompleteLayerUpload", "ecr:InitiateLayerUpload", "ecr:PutImage", "ecr:UploadLayerPart", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:DescribeImages"]
    resources = [for r in aws_ecr_repository.img : r.arn]
  }
  statement {
    actions   = ["ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition", "ecs:DescribeServices", "ecs:UpdateService", "ecs:RunTask", "ecs:DescribeTasks", "ecs:ListTasks"]
    resources = ["*"]
  }
  statement {
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.execution.arn, aws_iam_role.task.arn]
  }
  statement {
    actions   = ["events:PutEvents"]
    resources = [aws_cloudwatch_event_bus.lab.arn]
  }
}

resource "aws_iam_role_policy" "gha_deploy" {
  name   = "deploy"
  role   = aws_iam_role.gha_deploy.id
  policy = data.aws_iam_policy_document.gha_deploy.json
}
