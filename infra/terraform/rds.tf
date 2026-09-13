resource "aws_db_subnet_group" "lab" {
  name       = local.name
  subnet_ids = aws_subnet.public[*].id
}

# Master password is generated and stored by RDS in Secrets Manager; it never enters state.
resource "aws_db_instance" "lab" {
  identifier                   = local.name
  engine                       = "postgres"
  engine_version               = "16"
  instance_class               = var.db_instance_class
  allocated_storage            = 20
  storage_type                 = "gp3"
  db_name                      = "atlas"
  username                     = "atlas_admin"
  manage_master_user_password  = true
  db_subnet_group_name         = aws_db_subnet_group.lab.name
  vpc_security_group_ids       = [aws_security_group.db.id]
  publicly_accessible          = true
  skip_final_snapshot          = true
  deletion_protection          = false
  backup_retention_period      = 0
  apply_immediately            = true
  auto_minor_version_upgrade   = false
  performance_insights_enabled = false
}
