# 既存のサービスアカウントを参照
data "google_service_account" "minecraft" {
  account_id = "minecraft-bot"
}

# GCSバケット（バックアップ用）
resource "google_storage_bucket" "minecraft" {
  name     = "minecraft-with-maru-backup"
  location = var.region
  
  versioning {
    enabled = true
  }
  
  lifecycle_rule {
    condition {
      num_newer_versions = 5 # 最大5つの最新バージョンを保存
    }
    action {
      type = "Delete"
    }
  }
}

# GCSバケット（バックアップ用）
resource "google_storage_bucket" "minecraft_backups" {
  name     = "${var.project_id}-minecraft-backups"
  location = "ASIA-NORTHEAST1"
  
  lifecycle_rule {
    condition {
      num_newer_versions = 5
    }
    action {
      type = "Delete"
    }
  }
  
  versioning {
    enabled = true
  }
}

# VPCネットワーク
resource "google_compute_network" "minecraft" {
  name                    = "minecraft-network"
  auto_create_subnetworks = false
}

# サブネット
resource "google_compute_subnetwork" "minecraft" {
  name          = "minecraft-subnet"
  ip_cidr_range = "10.0.0.0/24"
  network       = google_compute_network.minecraft.self_link
  region        = var.region
}

# ファイアウォールルール（Minecraft用）
resource "google_compute_firewall" "minecraft" {
  name    = "minecraft-server"
  network = google_compute_network.minecraft.name

  allow {
    protocol = "tcp"
    ports    = ["25565"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["minecraft-server"]
}

# ファイアウォールルール（SSH用）
resource "google_compute_firewall" "ssh" {
  name    = "allow-ssh"
  network = google_compute_network.minecraft.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["minecraft-server"]
}

# 永続ディスク
resource "google_compute_disk" "minecraft" {
  name = "minecraft-disk"
  type = "pd-standard"
  zone = var.zone
  size = 20
}

# Compute Engineインスタンス
resource "google_compute_instance" "minecraft" {
  name         = "minecraft-server"
  machine_type = "e2-standard-2"
  zone         = var.zone

  scheduling {
    preemptible       = true
    automatic_restart = false
  }

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
    }
  }

  attached_disk {
    source = google_compute_disk.minecraft.self_link
  }

  network_interface {
    subnetwork = google_compute_subnetwork.minecraft.self_link
    access_config {
      // 一時的な外部IPを割り当て
    }
  }

  metadata_startup_script = file("${path.module}/startup-script.sh")

  tags = ["minecraft-server"]

  service_account {
    email  = data.google_service_account.minecraft.email
    scopes = ["storage-rw", "compute-ro"]  # GCSアクセス用とインスタンス情報取得用のスコープ
  }
}
