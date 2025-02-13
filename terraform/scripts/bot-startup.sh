#!/bin/bash

# 必要なパッケージのインストール
sudo apt-get update
sudo apt-get install -y python3-pip git

# アプリケーションディレクトリの作成
sudo mkdir -p /opt/discord-bot
sudo chown -R $USER:$USER /opt/discord-bot # アクセス権限を付与

cd /opt/discord-bot

# Gitリポジトリのクローン
sudo git clone https://github.com/FirstSS-Sub/minecraft-with-maru.git

# 依存関係のインストール
sudo pip3 install -r minecraft-with-maru/bot/requirements.txt

# 環境変数を .env から指定する必要が出てきてしまうが、gitからはignoreしているので手動で設定するしかない。そのためここから先はsshして手動で実行するようにする
# これらは確認コマンド
# gcloud compute ssh discord-bot
# systemctl status discord-bot
# journalctl -u discord-bot -f

# # 環境変数ファイルの作成
# sudo tee .env << 'EOL'
# DISCORD_TOKEN="your_token_here"
# DISCORD_CHANNEL_ID=1234567890
# # ... 他の環境変数 ...
# EOL

# # systemdサービスの設定
sudo tee /etc/systemd/system/discord-bot.service << 'EOL'
[Unit]
Description=Discord Bot for Minecraft Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/discord-bot/minecraft-with-maru/bot/bot.py
WorkingDirectory=/opt/discord-bot/minecraft-with-maru
User=root
Group=root
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# # サービスの有効化と起動
# sudo systemctl daemon-reload
# sudo systemctl enable discord-bot
# sudo systemctl start discord-bot