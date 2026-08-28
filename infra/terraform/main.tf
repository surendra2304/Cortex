terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ── 1. VPC & NETWORKING ──────────────────────────────────────────────────────
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "nexus-vpc-${var.environment}"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway   = true
  single_nat_gateway   = var.environment != "production"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Environment = var.environment
    Project     = "Nexus"
  }
}

# ── 2. DATABASE: RDS POSTGRESQL MULTI-AZ ────────────────────────────────────
resource "aws_db_subnet_group" "nexus" {
  name       = "nexus-db-subnet-group-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name        = "nexus-rds-sg-${var.environment}"
  description = "Allow inbound traffic from ECS tasks"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "postgres" {
  identifier           = "nexus-db-${var.environment}"
  engine               = "postgres"
  engine_version       = "15.4"
  instance_class       = var.environment == "production" ? "db.m6g.large" : "db.t4g.medium"
  allocated_storage    = 100
  max_allocated_storage = 1000
  storage_type         = "gp3"
  multi_az             = var.environment == "production"
  db_name              = "nexus"
  username             = "nexus_admin"
  password             = var.db_password
  db_subnet_group_name = aws_db_subnet_group.nexus.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  skip_final_snapshot  = var.environment != "production"
  backup_retention_period = 7
  deletion_protection  = var.environment == "production"
}

# ── 3. CACHE: ELASTICACHE REDIS CLUSTER ──────────────────────────────────────
resource "aws_elasticache_subnet_group" "redis" {
  name       = "nexus-redis-subnet-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "redis" {
  name        = "nexus-redis-sg-${var.environment}"
  description = "Allow inbound Redis traffic from ECS"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "nexus-redis-${var.environment}"
  engine               = "redis"
  node_type            = "cache.t4g.medium"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  engine_version       = "7.0"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.redis.name
  security_group_ids   = [aws_security_group.redis.id]
}

# ── 4. ECS FARGATE CLUSTER & SERVICES ───────────────────────────────────────
resource "aws_ecs_cluster" "main" {
  name = "nexus-cluster-${var.environment}"
}

resource "aws_security_group" "ecs" {
  name        = "nexus-ecs-sg-${var.environment}"
  description = "ECS Task security group"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── 5. APPLICATION LOAD BALANCER ────────────────────────────────────────────
resource "aws_security_group" "alb" {
  name        = "nexus-alb-sg-${var.environment}"
  description = "ALB public ingress"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── 6. S3 ARTIFACT & BACKUP STORAGE ─────────────────────────────────────────
resource "aws_s3_bucket" "artifacts" {
  bucket = "nexus-artifacts-${var.environment}-${var.aws_region}"
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}
