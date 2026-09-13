resource "aws_lb" "lab" {
  name               = local.name
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
  idle_timeout       = 3600 # WebSocket for Mission Control
}

resource "aws_lb_target_group" "web" {
  for_each    = local.web_services
  name        = "atlas-lab-${each.key}"
  port        = each.value.container_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.lab.id

  deregistration_delay = 5

  health_check {
    path                = each.value.health
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

resource "aws_lb_listener" "web" {
  for_each          = local.web_services
  load_balancer_arn = aws_lb.lab.arn
  port              = each.value.port
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web[each.key].arn
  }
}
