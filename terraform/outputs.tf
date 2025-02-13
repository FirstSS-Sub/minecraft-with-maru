output "instance_ip" {
  description = "The external IP of the Minecraft server"
  value       = google_compute_instance.minecraft.network_interface[0].access_config[0].nat_ip
}

output "backup_bucket" {
  description = "The name of the backup bucket"
  value       = google_storage_bucket.minecraft.name
}