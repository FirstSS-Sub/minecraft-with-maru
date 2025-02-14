#!/bin/bash

# 必要なパッケージのインストール
sudo apt-get update
sudo apt-get install -y software-properties-common python3-pip git

# Deadsnakes PPAの追加
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt-get update

# Python 3.11のインストール
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev

# Python 3.11用の pip インストール
curl -sS https://bootstrap.pypa.io/get-pip.py | sudo python3.11

# デフォルトの python3 を python3.11 に変更
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 2

# デフォルトの pip3 を pip3.11 に変更
sudo update-alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3.10 1
sudo update-alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3.11 2

# アプリケーションディレクトリの作成
sudo mkdir -p /opt/discord-bot
sudo chown -R $USER:$USER /opt/discord-bot # アクセス権限を付与

cd /opt/discord-bot

# Gitリポジトリのクローン
git clone https://github.com/FirstSS-Sub/minecraft-with-maru.git

cd minecraft-with-maru

# 依存関係のインストール
pip3 install -r bot/requirements.txt

# 環境変数を .env から指定する必要が出てきてしまうが、gitからはignoreしているので手動で設定するしかない。そのためここから先はsshして手動で実行するようにする
# これらは確認コマンド
# gcloud compute ssh discord-bot
# systemctl status discord-bot
# journalctl -u discord-bot -f

# 環境変数ファイルの作成
# sudo tee .env << 'EOL'
# DISCORD_TOKEN="your_token_here"
# DISCORD_CHANNEL_ID=1234567890
# # ... 他の環境変数 ...
# EOL

# systemdサービスの設定
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

# サービスの有効化と起動
sudo systemctl daemon-reload
sudo systemctl enable discord-bot
sudo systemctl start discord-bot