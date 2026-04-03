variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "us-central1"
}

variable "db_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-custom-2-4096"
}

variable "db_password" {
  description = "Cloud SQL fraud_user password"
  type        = string
  sensitive   = true
}

variable "deletion_protection" {
  description = "Cloud SQL deletion protection (set false for teardown)"
  type        = bool
  default     = true
}
