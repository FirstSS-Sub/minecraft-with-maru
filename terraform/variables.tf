variable "region" {
  description = "Region for GCP resources"
  default     = "asia-northeast1"
}

variable "project_id" {
  description = "GCP project ID"
  default     = "minecraft-with-maru"
}

variable "zone" {
  description = "Zone for GCP resources"
  default     = "asia-northeast1-a"
}

variable "discord_token" {
  description = "Discord Bot Token"
  type        = string
  sensitive   = true
}

variable "discord_channel_id" {
  description = "Discord Channel ID"
  type        = string
}