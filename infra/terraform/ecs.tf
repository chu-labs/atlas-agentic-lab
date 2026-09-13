resource "aws_ecs_cluster" "lab" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "lab" {
  cluster_name       = aws_ecs_cluster.lab.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
}

locals {
  common_env = {
    AWS_REGION            = var.region
    LAB_NAME              = local.name
    EVENT_BUS             = aws_cloudwatch_event_bus.lab.name
    DB_HOST               = aws_db_instance.lab.address
    DB_PORT               = "5432"
    DB_USER               = aws_db_instance.lab.username
    ALB_DNS               = aws_lb.lab.dns_name
    GITHUB_ORG            = var.github_org
    QUEUE_URL_PROD_ERRORS = aws_sqs_queue.q["prod-errors"].id
    QUEUE_URL_FORGE       = aws_sqs_queue.q["forge"].id
    QUEUE_URL_SENTINEL    = aws_sqs_queue.q["sentinel"].id
    QUEUE_URL_CONDUCTOR   = aws_sqs_queue.q["conductor"].id
    BOARD_URL             = "http://${aws_lb.lab.dns_name}:8081"
    ALB_ARN_SUFFIX        = aws_lb.lab.arn_suffix
    TARGET_GROUP_SUFFIXES = join(",", [for k, tg in aws_lb_target_group.web : "${k}=${tg.arn_suffix}"])
    PLATFORM_URL          = "http://${aws_lb.lab.dns_name}:8082"
    SECRET_ANTHROPIC      = aws_secretsmanager_secret.s["anthropic-api-key"].arn
    SECRET_GITHUB_APP     = aws_secretsmanager_secret.s["github-app"].arn
    SECRET_BASIC_AUTH     = aws_secretsmanager_secret.s["basic-auth"].arn
  }

  common_secrets = [
    { name = "DB_PASSWORD", valueFrom = "${aws_db_instance.lab.master_user_secret[0].secret_arn}:password::" },
    { name = "BASIC_AUTH_USER", valueFrom = "${aws_secretsmanager_secret.s["basic-auth"].arn}:username::" },
    { name = "BASIC_AUTH_PASS", valueFrom = "${aws_secretsmanager_secret.s["basic-auth"].arn}:password::" },
    { name = "ANTHROPIC_API_KEY", valueFrom = "${aws_secretsmanager_secret.s["anthropic-api-key"].arn}:api_key::" },
    { name = "GITHUB_HUMAN_TOKEN", valueFrom = "${aws_secretsmanager_secret.s["github-human"].arn}:token::" },
    { name = "GITHUB_HUMAN_LOGIN", valueFrom = "${aws_secretsmanager_secret.s["github-human"].arn}:login::" },
  ]
}

resource "aws_ecs_task_definition" "svc" {
  for_each                 = local.all_services
  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([{
    name         = each.key
    image        = "${aws_ecr_repository.img[each.value.image].repository_url}:${var.image_tag}"
    essential    = true
    portMappings = contains(keys(local.web_services), each.key) ? [{ containerPort = 8000, protocol = "tcp" }] : []
    environment = [for k, v in merge(local.common_env, {
      SERVICE_NAME             = each.key
      AGENT_NAME               = each.key
      QUEUE_URL                = try(aws_sqs_queue.q[each.value.queue].id, "")
      QUEUE_URL_MISSION_EVENTS = aws_sqs_queue.q["mission-events"].id
    }) : { name = k, value = v }]
    secrets = local.common_secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.svc[each.key].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "task"
      }
    }
  }])
}

resource "aws_ecs_service" "web" {
  for_each        = local.web_services
  name            = each.key
  cluster         = aws_ecs_cluster.lab.id
  task_definition = aws_ecs_task_definition.svc[each.key].arn
  desired_count   = lookup(var.desired_counts, each.key, 0)

  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web[each.key].arn
    container_name   = each.key
    container_port   = 8000
  }

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 30

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_lb_listener.web]
}

resource "aws_ecs_service" "agent" {
  for_each        = local.agent_services
  name            = each.key
  cluster         = aws_ecs_cluster.lab.id
  task_definition = aws_ecs_task_definition.svc[each.key].arn
  desired_count   = lookup(var.desired_counts, each.key, 0)

  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 1
  }

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}
