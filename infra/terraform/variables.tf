variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "Primary AWS deployment region"
}

variable "environment" {
  type        = string
  default     = "production"
  description = "Deployment environment (production/staging)"
}

variable "db_password" {
  type        = string
  sensitive   = true
  description = "RDS PostgreSQL master database password"
}
