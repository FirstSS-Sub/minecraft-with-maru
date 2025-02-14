#!/bin/bash

# 別ユーザからスクリプトを実行する際のsudoではなく、スクリプト自体をrootで実行。これによって root ユーザーとして最後にアプリを起動したときにモジュールが正常にインポートされた状態になる
if [ "$(id -u)" -ne 0 ]; then
  echo "スクリプトはrootユーザーとして実行してください"
  exit 1
fi

# 必要なパッケージのインストール
apt-get update
apt-get install -y software-properties-common python3-pip git

# Deadsnakes PPAの追加
add-apt-repository ppa:deadsnakes/ppa -y
apt-get update

# Python 3.11のインストール
apt-get install -y python3.11 python3.11-venv python3.11-dev

# Python 3.11用の pip インストール
curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11

# デフォルトの python3 を python3.11 に変更
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 2

# デフォルトの pip3 を pip3.11 に変更
update-alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3.10 1
update-alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3.11 2

# pycairoの依存関係をインストール
apt-get install -y libcairo2-dev pkg-config

# apt_pkgの依存関係をインストール
apt-get install -y python3-apt

# アプリケーションディレクトリの作成
mkdir -p /opt/discord-bot
chown -R root:root /opt/discord-bot # アクセス権限を付与

cd /opt/discord-bot

# Gitリポジトリのクローン
git clone https://github.com/FirstSS-Sub/minecraft-with-maru.git

cd minecraft-with-maru

# 依存関係のインストール
pip3 install -r bot/requirements.txt

# 環境変数ファイルの作成（必要に応じて手動で追加）
# tee .env << 'EOL'
# DISCORD_TOKEN="your_token_here"
# DISCORD_CHANNEL_ID=1234567890
# # ... 他の環境変数 ...
# EOL

# systemdサービスの設定
tee /etc/systemd/system/discord-bot.service << 'EOL'
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
# sudo systemctl daemon-reload
# sudo systemctl enable discord-bot
# sudo systemctl start discord-bot