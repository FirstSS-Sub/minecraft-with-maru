#!/bin/bash

# マウントポイントの作成
mkdir -p /minecraft
mount -o discard,defaults /dev/sdb /minecraft

# 必要なパッケージのインストール
apt-get update
apt-get install -y openjdk-17-jre-headless

# Minecraftディレクトリの作成
mkdir -p /minecraft/server
cd /minecraft/server

# サーバーJARが存在しない場合はダウンロード
if [ ! -f server.jar ]; then
    wget https://piston-data.mojang.com/v1/objects/c9df48efed58511cdd0213c56b9013a7b5c9ac1f/server.jar
fi

# EULAの同意
if [ ! -f eula.txt ]; then
    echo "eula=true" > eula.txt
fi

# server.propertiesの設定
if [ ! -f server.properties ]; then
    cat > server.properties << EOF
server-port=25565
max-players=2
view-distance=10
difficulty=normal
gamemode=survival
enable-command-block=true
max-world-size=5000
spawn-protection=16
EOF
fi

# Modを使用する場合はここでForgeやFabricをインストール
# 例：Forge installerのダウンロードと実行
# wget https://files.minecraftforge.net/maven/net/minecraftforge/forge/1.19.4-45.1.0/forge-1.19.4-45.1.0-installer.jar
# java -jar forge-1.19.4-45.1.0-installer.jar --installServer

# サーバー起動
java -Xmx2G -Xms2G -jar server.jar nogui