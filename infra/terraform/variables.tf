variable "region" {
  type    = string
  default = "ap-southeast-2"
}

variable "aws_profile" {
  type    = string
  default = "chu-ai"
}

variable "project" {
  type    = string
  default = "atlas-agentic-lab"
}

variable "owner" {
  type    = string
  default = "maroun"
}

variable "destroy_after" {
  type    = string
  default = "2026-09-30"
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "admin_cidr" {
  description = "CIDR allowed to reach Postgres directly (your laptop). Set in terraform.tfvars."
  type        = string
  default     = "127.0.0.1/32"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "log_retention_days" {
  type    = number
  default = 3
}

variable "image_tag" {
  description = "Initial image tag for task definitions. CI registers later revisions; Terraform ignores them."
  type        = string
  default     = "bootstrap"
}

variable "desired_counts" {
  description = "Desired count per service. Default 0 so apply succeeds before images exist. labctl scales services."
  type        = map(number)
  default     = {}
}

variable "github_org" {
  type    = string
  default = "chu-labs"
}
