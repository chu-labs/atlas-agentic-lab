resource "aws_cloudwatch_log_group" "svc" {
  for_each          = local.all_services
  name              = "/${local.name}/${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "oneoff" {
  for_each          = toset(["seeder", "traffic", "migrate"])
  name              = "/${local.name}/${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_resourcegroups_group" "lab" {
  name = local.name
  resource_query {
    query = jsonencode({
      ResourceTypeFilters = ["AWS::AllSupported"]
      TagFilters          = [{ Key = "Project", Values = [var.project] }]
    })
  }
}
