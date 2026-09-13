locals {
  name = var.project

  tags = {
    Project      = var.project
    Owner        = var.owner
    Lifecycle    = "ephemeral"
    DestroyAfter = var.destroy_after
  }

  azs = ["${var.region}a", "${var.region}b"]

  # Public listener port -> service. No domain, so ports are the routing.
  web_services = {
    mission-control = { port = 80, container_port = 8000, cpu = 256, memory = 512, image = "mission-control", health = "/health" }
    atlas-board     = { port = 8081, container_port = 8000, cpu = 256, memory = 512, image = "atlas-board", health = "/health" }
    atlas-platform  = { port = 8082, container_port = 8000, cpu = 256, memory = 512, image = "atlas-platform", health = "/health" }
  }

  # Queue-polling agents. All share one image except Forge, which carries Claude Code.
  agent_services = {
    scout      = { cpu = 256, memory = 512, image = "agent", queue = "prod-errors" }
    sentinel   = { cpu = 256, memory = 512, image = "agent", queue = "sentinel" }
    conductor  = { cpu = 256, memory = 512, image = "agent", queue = "conductor" }
    watchtower = { cpu = 256, memory = 512, image = "agent", queue = "watchtower" }
    forge      = { cpu = 1024, memory = 2048, image = "forge", queue = "forge" }
  }

  all_services = merge(local.web_services, local.agent_services)

  images = toset(["atlas-platform", "atlas-board", "mission-control", "agent", "forge"])

  # Work queues. prod-errors is fed by atlas-platform directly; the rest by EventBridge rules.
  queues = toset(["prod-errors", "forge", "sentinel", "conductor", "watchtower", "mission-events"])
}
