resource "aws_ecr_repository" "img" {
  for_each             = local.images
  name                 = "${local.name}/${each.key}"
  force_delete         = true
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = false
  }
}

resource "aws_ecr_lifecycle_policy" "img" {
  for_each   = local.images
  repository = aws_ecr_repository.img[each.key].name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep last 10"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}
