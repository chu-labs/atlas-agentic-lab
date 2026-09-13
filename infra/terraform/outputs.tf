output "alb_dns" {
  value = aws_lb.lab.dns_name
}

output "urls" {
  value = { for k, v in local.web_services : k => "http://${aws_lb.lab.dns_name}:${v.port}" }
}

output "db_host" {
  value = aws_db_instance.lab.address
}

output "db_master_secret_arn" {
  value = aws_db_instance.lab.master_user_secret[0].secret_arn
}

output "ecr" {
  value = { for k, r in aws_ecr_repository.img : k => r.repository_url }
}

output "queues" {
  value = { for k, q in aws_sqs_queue.q : k => q.id }
}

output "event_bus" {
  value = aws_cloudwatch_event_bus.lab.name
}

output "secrets" {
  value = { for k, s in aws_secretsmanager_secret.s : k => s.arn }
}

output "cluster" {
  value = aws_ecs_cluster.lab.name
}

output "gha_deploy_role_arn" {
  value = aws_iam_role.gha_deploy.arn
}

output "services" {
  value = keys(local.all_services)
}
