terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 8.0"
    }
  }
  # Local state on purpose: the whole lab is throwaway. terraform.tfstate is gitignored.
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = local.tags
  }
}
