#!/bin/bash

# 必要なパッケージのインストール
apt-get update
apt-get install -y python3-pip git

# アプリケーションディレクトリの作成
mkdir -p /opt/discord-bot
cd /opt/discord-bot

# Gitリポジトリのクローン
git clone https://github.com/your-repo/minecraft-server-bot.git .

# 依存関係のインストール
pip3 install -r requirements.txt

# 環境変数ファイルの作成
cat > .env << 'EOL'
DISCORD_TOKEN="your_token_here"
DISCORD_CHANNEL_ID=1234567890
# ... 他の環境変数 ...
EOL

# systemdサービスの設定
cat > /etc/systemd/system/discord-bot.service << 'EOL'
[Unit]
Description=Discord Bot for Minecraft Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/discord-bot/bot/bot.py
WorkingDirectory=/opt/discord-bot
User=root
Group=root
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# サービスの有効化と起動
systemctl daemon-reload
systemctl enable discord-bot
systemctl start discord-bot 