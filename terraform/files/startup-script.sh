#!/bin/bash

# 必要なパッケージのインストール
apt-get update
apt-get install -y screen openjdk-17-jre-headless

# Minecraftユーザーの作成（存在しない場合）
if ! id "minecraft" &>/dev/null; then
    useradd -r -m -U -d /minecraft minecraft
fi

# 必要なディレクトリの作成
mkdir -p /minecraft/server
chown -R minecraft:minecraft /minecraft

# systemdサービスの設定
cat > /etc/systemd/system/minecraft.service << 'EOL'
[Unit]
Description=Minecraft Server
After=network.target

[Service]
WorkingDirectory=/minecraft/server
User=minecraft
Group=minecraft
Type=simple

ExecStart=/usr/bin/screen -DmS minecraft java -Xmx4G -Xms1G -jar server.jar nogui
ExecStop=/usr/bin/screen -p 0 -S minecraft -X eval 'stuff "say サーバーを停止します..."\015'
ExecStop=/usr/bin/screen -p 0 -S minecraft -X eval 'stuff "save-all"\015'
ExecStop=/usr/bin/screen -p 0 -S minecraft -X eval 'stuff "stop"\015'
ExecStop=/bin/sleep 10

Restart=on-failure
RestartSec=60s

[Install]
WantedBy=multi-user.target
EOL

# サービスの有効化と起動
systemctl daemon-reload
systemctl enable minecraft
systemctl start minecraft 