# 既存のサービスアカウントを参照
data "google_service_account" "minecraft" {
  account_id = "minecraft-bot"
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

# ファイアウォールルール（minecraft-server SSH用）
resource "google_compute_firewall" "minecraft_server_ssh" {
  name    = "allow-ssh-minecraft-server"
  network = google_compute_network.minecraft.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["minecraft-server"]
}

# ファイアウォールルール（Discord Bot SSH用）
resource "google_compute_firewall" "discord_bot_ssh" {
  name    = "allow-ssh-discord-bot"
  network = google_compute_network.minecraft.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["discord-bot"]
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
  name         = var.instance_name
  machine_type = "e2-custom-2-4096"
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

  metadata = {
    startup-script = <<-EOF
      #!/bin/sh
      # エラー時に停止
      set -e

      # サーバーディレクトリの設定
      SERVER_DIR="/opt/minecraft_server"
      mkdir -p $SERVER_DIR
      cd $SERVER_DIR

      # 必要なパッケージのインストール
      yes | sudo apt update
      yes | sudo apt install -y openjdk-21-jdk screen wget unzip

      # Java 21をデフォルトに設定
      sudo update-alternatives --set java /usr/lib/jvm/java-21-openjdk-amd64/bin/java

      wget https://piston-data.mojang.com/v1/objects/4707d00eb834b446575d89a61a11b5d548d8c001/server.jar

      # EULAに同意
      echo "eula=true" > eula.txt

      # server.propertiesファイルの作成または修正
      if [ ! -f "server.properties" ]; then
          echo "online-mode=false" > server.properties
      else
          sed -i '/^online-mode=/c\online-mode=false' server.properties
      fi

      # Google Cloud SDKのインストール
      sudo snap remove google-cloud-cli
      sudo rm -f /usr/share/keyrings/cloud.google.gpg
      echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list
      curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
      sudo apt-get update
      sudo apt-get install google-cloud-cli -y

      # systemdサービスファイルの作成
      sudo sh -c "cat > /etc/systemd/system/minecraft.service <<EOL
      [Unit]
      Description=Minecraft Server
      After=network.target

      [Service]
      User=$USER
      Group=$USER
      WorkingDirectory=$SERVER_DIR
      ExecStart=/usr/lib/jvm/java-21-openjdk-amd64/bin/java -Xms1G -Xmx3G -jar server.jar nogui
      Restart=on-failure
      RestartSec=10s

      [Install]
      WantedBy=multi-user.target
      EOL"

      # backup.sh 作成
      sudo sh -c 'cat > $SERVER_DIR/backup.sh <<EOL
      #!/bin/sh
      BUCKET_NAME="${google_storage_bucket.minecraft_backups.name}"
      MINECRAFT_DIR="/opt/minecraft_server"
      BACKUP_NAME="world_backup.tar.gz"
      GCS_PATH="gs://$BUCKET_NAME/backups/$BACKUP_NAME"
      TEMP_DIR="$(mktemp -d)"

      echo "バックアップを作成します"
      sudo tar -czf "$TEMP_DIR/$BACKUP_NAME" -C "$MINECRAFT_DIR" world || {
          echo "バックアップの作成に失敗しました"
          exit 1
      }

      echo "GCSにアップロードします"
      gsutil -o GSUtil:parallel_composite_upload_threshold=150M cp "$TEMP_DIR/$BACKUP_NAME" "$GCS_PATH" || {
          echo "GCSへのアップロードに失敗しました"
          exit 1
      }

      echo "メタデータを設定します"
      gsutil setmeta -h "x-goog-meta-metadata:backup_file=$BACKUP_NAME" "$GCS_PATH" || echo "メタデータの設定に失敗しました"

      echo "クリーンアップを行います"
      rm -f "$TEMP_DIR/$BACKUP_NAME"
      rmdir "$TEMP_DIR"
      EOL'

      # ファイルのパーミッション設定
      chmod +x server.jar
      chmod +x backup.sh

      # サービスの有効化と起動
      sudo systemctl daemon-reload
      sudo systemctl enable minecraft.service
      sudo systemctl start minecraft.service

      echo "Minecraftサーバーがインストールされ、起動しました。"
      echo "サービスのステータスを確認するには: sudo systemctl status minecraft.service"
      echo "サーバーログを確認するには: sudo journalctl -u minecraft.service -f"
      echo "Complementary Unbound Shadersがshaderpacks/フォルダにインストールされました。"
      echo "注意: オフラインモードが有効になっています。セキュリティに注意してください。"

      # ファイルの権限を確認
      ls -l $SERVER_DIR
    EOF

    shutdown-script = <<-EOF
      #!/bin/bash
      nohup bash -c '
      set -e
      exec > >(tee /var/log/shutdown-script.log) 2>&1

      MINECRAFT_DIR="/opt/minecraft_server"

      echo "シャットダウンスクリプトを開始します"
      echo "Minecraftサーバーを停止します"
      sudo systemctl stop minecraft || echo "Minecraftサーバーの停止に失敗しました"

      sh $MINECRAFT_DIR/backup.sh

      echo "シャットダウンスクリプトが正常に完了しました"
      ' > /dev/null 2>&1 &
    EOF
    shutdown-script-timeout = "300" # 5分に延長
  }

  tags = ["minecraft-server"]

  service_account {
    email  = data.google_service_account.minecraft.email
    scopes = ["storage-rw", "compute-ro", "https://www.googleapis.com/auth/devstorage.full_control"]  # GCSアクセス用とインスタンス情報取得用のスコープ
  }
}

# Discord Bot用のインスタンス
resource "google_compute_instance" "discord_bot" {
  name         = "discord-bot"
  machine_type = "e2-micro"
  zone         = "us-west1-a" # Always Free対象リージョン
  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 10
    }
  }

  network_interface {
    subnetwork    = google_compute_subnetwork.discord_bot.self_link
    access_config {}
  }

  service_account {
    email  = data.google_service_account.minecraft.email
    scopes = ["storage-rw", "compute-rw"]
  }

  tags = ["discord-bot"]
}

# 新しいサブネット（Discord Bot用）
resource "google_compute_subnetwork" "discord_bot" {
  name          = "discord-bot-subnet"
  ip_cidr_range = "10.1.0.0/24"
  network       = google_compute_network.minecraft.self_link
  region        = "us-west1"
}