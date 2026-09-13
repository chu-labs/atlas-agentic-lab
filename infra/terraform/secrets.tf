# Terraform creates the secrets with placeholders. Real values are written by `labctl secrets`
# and Terraform ignores the value thereafter, so nothing sensitive is in state or the repo.
locals {
  secrets = {
    anthropic-api-key = jsonencode({ api_key = "REPLACE_ME" })
    github-app        = jsonencode({ id = "0", slug = "chu-atlas-agents", installation_id = "0", pem = "REPLACE_ME" })
    basic-auth        = jsonencode({ username = "REPLACE_ME", password = "REPLACE_ME" })
  }
}

resource "aws_secretsmanager_secret" "s" {
  for_each                = local.secrets
  name                    = "${local.name}/${each.key}"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "s" {
  for_each      = local.secrets
  secret_id     = aws_secretsmanager_secret.s[each.key].id
  secret_string = each.value
  lifecycle {
    ignore_changes = [secret_string]
  }
}
