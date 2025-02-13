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
FORGE_INSTALLER="forge-${FORGE_VERSION}-installer.jar"
FORGE_JAR="forge-${FORGE_VERSION}-server.jar"

wget -O $FORGE_INSTALLER "https://maven.minecraftforge.net/net/minecraftforge/forge/${FORGE_VERSION}/forge-${FORGE_VERSION}-installer.jar"
yes | java -jar $FORGE_INSTALLER --installServer

# シムJARファイルを正しい名前にリネーム
if [ -f "forge-${FORGE_VERSION}-shim.jar" ]; then
    mv "forge-${FORGE_VERSION}-shim.jar" "$FORGE_JAR"
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
