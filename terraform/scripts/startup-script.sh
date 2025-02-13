#!/bin/bash

# 必要なパッケージのインストール
apt-get update
apt-get install -y screen openjdk-17-jre-headless curl unzip

# Minecraftユーザーの作成（存在しない場合）
if ! id "minecraft" &>/dev/null; then
    useradd -r -m -U -d /minecraft minecraft
fi

# 必要なディレクトリの作成
mkdir -p /minecraft/server
mkdir -p /minecraft/server/mods
mkdir -p /minecraft/server/shaderpacks
chown -R minecraft:minecraft /minecraft

# Optifineのダウンロードとインストール（サーバー側でも必要）
curl -o /minecraft/server/mods/OptiFine.jar https://optifine.net/downloadx?f=OptiFine_1.20.1_HD_U_I7.jar

# Complementary Shadersのダウンロード
curl -L -o /minecraft/server/shaderpacks/complementary.zip https://www.complementary.dev/download/

# シェーダーパックの展開
cd /minecraft/server/shaderpacks
unzip complementary.zip
rm complementary.zip

# 権限の設定
chown -R minecraft:minecraft /minecraft/server/mods
chown -R minecraft:minecraft /minecraft/server/shaderpacks

# systemdサービスファイルを直接作成
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