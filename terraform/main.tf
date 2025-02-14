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

      # Forgeのダウンロードとインストール
      FORGE_VERSION="1.21.4-54.1.0"
      FORGE_INSTALLER="forge-$FORGE_VERSION-installer.jar"
      FORGE_JAR="forge-$FORGE_VERSION-server.jar"

      wget -O $FORGE_INSTALLER "https://maven.minecraftforge.net/net/minecraftforge/forge/$FORGE_VERSION/forge-$FORGE_VERSION-installer.jar"
      yes | java -jar $FORGE_INSTALLER --installServer

      # シムJARファイルを正しい名前にリネーム
      if [ -f "forge-$FORGE_VERSION-shim.jar" ]; then
          mv "forge-$FORGE_VERSION-shim.jar" "$FORGE_JAR"
      fi

      # Complementary Unbound Shadersのダウンロードと配置
      SHADER_URL="https://cdn.modrinth.com/data/R6NEzAwj/versions/Z1zqMzjh/ComplementaryUnbound_r5.4.zip"
      wget -O ComplementaryUnbound.zip "$SHADER_URL"
      mkdir -p $SERVER_DIR/shaderpacks
      yes | unzip -o ComplementaryUnbound.zip -d $SERVER_DIR/shaderpacks/

      # EULAに同意
      echo "eula=true" > eula.txt

      # server.propertiesファイルの作成または修正
      if [ ! -f "server.properties" ]; then
          echo "online-mode=false" > server.properties
      else
          sed -i '/^online-mode=/c\online-mode=false' server.properties
      fi

      # systemdサービスファイルの作成
      sudo sh -c "cat > /etc/systemd/system/minecraft.service <<EOL
      [Unit]
      Description=Minecraft Server
      After=network.target

      [Service]
      User=$USER
      Group=$USER
      WorkingDirectory=$SERVER_DIR
      ExecStart=/usr/lib/jvm/java-21-openjdk-amd64/bin/java -Xms2G -Xmx4G -jar $FORGE_JAR nogui
      Restart=on-failure
      RestartSec=10s

      [Install]
      WantedBy=multi-user.target
      EOL"

      # ファイルのパーミッション設定
      chmod +x $FORGE_JAR

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
      BUCKET_NAME="${google_storage_bucket.minecraft_backups.name}"
      MINECRAFT_DIR="/path/to/minecraft/server"
      BACKUP_NAME="world_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
      GCS_PATH="gs://$BUCKET_NAME/backups/$BACKUP_NAME"

      # ワールドデータをバックアップ
      tar -czf /tmp/$BACKUP_NAME -C $MINECRAFT_DIR world

      # GCSにアップロード
      gsutil cp /tmp/$BACKUP_NAME $GCS_PATH

      # メタデータにファイル名を保存
      gsutil setmeta -h "metadata:backup_file=$BACKUP_NAME" $GCS_PATH

      # 一時ファイルを削除
      rm /tmp/$BACKUP_NAME

      # Minecraftサーバーを停止
      systemctl stop minecraft
    EOF
  }

  tags = ["minecraft-server"]

  service_account {
    email  = data.google_service_account.minecraft.email
    scopes = ["storage-rw", "compute-ro"]  # GCSアクセス用とインスタンス情報取得用のスコープ
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