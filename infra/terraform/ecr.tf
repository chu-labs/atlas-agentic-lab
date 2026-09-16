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
  # Only defect builds and untagged layers expire; baseline and release images are never evicted,
  # so `labctl reset` can always roll back.
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "keep the last 8 defect builds"
        selection    = { tagStatus = "tagged", tagPrefixList = ["defect-"], countType = "imageCountMoreThan", countNumber = 8 }
        action       = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "untagged layers expire after a day"
        selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 1 }
        action       = { type = "expire" }
      },
    ]
  })
}
