import os
import discord
from discord.ext import commands
import logging
import requests
from discord import app_commands
import asyncio
from google.cloud import compute_v1
from google.cloud import monitoring_v3
from google.cloud import storage
from mcstatus import JavaServer
import json
from config import (
    DISCORD_TOKEN,
    DISCORD_CHANNEL_ID as CHANNEL_ID,
    GCP_PROJECT_ID,
    INSTANCE_NAME,
    ZONE,
    START_EMOJI_ID,
    STOP_EMOJI_ID,
    STATUS_EMOJI_ID,
    COSTS_EMOJI_ID
)
import datetime
from datetime import timezone
import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('minecraft_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('minecraft_bot')

class MinecraftBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        super().__init__(command_prefix=None, intents=intents)

        self.project_id = GCP_PROJECT_ID
        self.zone = ZONE
        self.instance_name = INSTANCE_NAME

        self.instance_client = compute_v1.InstancesClient()
        self.monitoring_client = monitoring_v3.MetricServiceClient()
        self.storage_client = storage.Client()
        self.last_player_time = None
        self.shutdown_task = None
        self.last_rate_update = None
        self.current_rates = None

    async def setup_hook(self):
        self.bg_task = self.loop.create_task(self.check_server_status())

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.user} has connected to Discord!')
        await self.tree.sync()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return

        # カスタム絵文字でない場合はスキップ
        if reaction.emoji.id is None:
            return

        if reaction.emoji.id == START_EMOJI_ID:  # サーバー起動
            await reaction.message.channel.send("サーバーを起動するね...")
            await self.start_server()

        elif reaction.emoji.id == STOP_EMOJI_ID:  # サーバー停止
            await reaction.message.channel.send("サーバーを停止するね...")
            await self.stop_server()

        elif reaction.emoji.id == STATUS_EMOJI_ID:  # サーバー状態確認
            await self.check_status(reaction.message.channel)

        elif reaction.emoji.id == COSTS_EMOJI_ID:  # コスト確認
            await self.get_monthly_costs(reaction.message.channel)

    async def start_server(self):
        try:
            request = compute_v1.StartInstanceRequest(
                project=self.project_id,
                zone=self.zone,
                instance=self.instance_name
            )
            operation = self.instance_client.start(request=request)
            operation.result()  # 完了を待つ

            # IPアドレスの取得
            instance = self.instance_client.get(
                project=self.project_id,
                zone=self.zone,
                instance=self.instance_name
            )

            ip_address = None
            for interface in instance.network_interfaces:
                if hasattr(interface, 'access_configs') and interface.access_configs:
                    config = interface.access_configs[0]
                    # 'nat_ip'の代わりに'external_ipv4'を使用
                    ip_address = getattr(config, 'external_ipv4', None)
                    if ip_address:
                        break

            # メタデータサーバーからIPアドレスを取得
            if not ip_address:
                try:
                    metadata_url = "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip"
                    headers = {"Metadata-Flavor": "Google"}
                    response = requests.get(metadata_url, headers=headers, timeout=5)
                    if response.status_code == 200:
                        ip_address = response.text.strip()
                        logging.info(f"IP address from metadata: {ip_address}")
                except Exception as e:
                    logging.error(f"Error fetching IP from metadata: {str(e)}")

            if ip_address:
                await self.get_channel(CHANNEL_ID).send(
                    f"サーバーを起動したよ！\n"
                    f"IPアドレスは {ip_address} だよ！"
                )
            else:
                await self.get_channel(CHANNEL_ID).send(
                    "サーバーを起動したけど、IPアドレスが見つからなかったよ..."
                )
                logging.error("IP address not found")

        except Exception as e:
            logging.exception("Error in start_server")
            await self.get_channel(CHANNEL_ID).send(f"エラーが発生しちゃった... : {str(e)}")

    async def backup_world(self):
        try:
            # GCSクライアントの初期化
            storage_client = storage.Client()
            bucket = storage_client.bucket('your-bucket-name')

            # バックアップファイルの作成
            backup_filename = f"world_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"
            minecraft_dir = "/path/to/minecraft/server"  # Minecraftサーバーのディレクトリを指定してね
            os.system(f"tar -czf /tmp/{backup_filename} -C {minecraft_dir} world")

            # GCSへのアップロード
            blob = bucket.blob(f"backups/{backup_filename}")
            blob.upload_from_filename(f"/tmp/{backup_filename}")

            # 一時ファイルの削除
            os.remove(f"/tmp/{backup_filename}")

            await self.get_channel(CHANNEL_ID).send(f"ワールドのバックアップが完了したよ！ファイル名は {backup_filename} だよ！")
            return True
        except Exception as e:
            logging.exception(f"バックアップ中にエラーが発生しました: {str(e)}")
            await self.get_channel(CHANNEL_ID).send(f"バックアップ中にエラーが起きちゃったみたい...\n{str(e)}")
            return False

    async def stop_server(self):
        try:
            # バックアップを実行
            backup_success = await self.backup_world()
            backup_message = "バックアップ成功だよ！" if backup_success else "バックアップ失敗しちゃった..."

            # コスト計算
            cost_info = await self.calculate_costs()

            request = compute_v1.StopInstanceRequest(
                project=self.project_id,
                zone=self.zone,
                instance=self.instance_name
            )
            operation = self.instance_client.stop(request=request)
            operation.result()

            await self.get_channel(CHANNEL_ID).send(
                f"サーバーを停止したよ！\n"
                f"バックアップ: {backup_message}\n"
                f"今回の稼働時間は {cost_info['runtime']} だったよ！\n"
                f"今回の費用は ¥{cost_info['session_cost']:.2f} になったよ！\n"
            )

        except Exception as e:
            await self.get_channel(CHANNEL_ID).send(f"エラーが発生しちゃった... : {str(e)}")

    async def check_server_status(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                instance = self.instance_client.get(
                    project=self.project_id,
                    zone=self.zone,
                    instance=self.instance_name
                )

                if instance.status == "RUNNING":
                    # サーバーが稼働中の場合、プレイヤー数をチェック
                    ip_address = instance.network_interfaces[0].access_configs[0].nat_ip
                    server = JavaServer(ip_address, 25565)
                    status = server.status()

                    if status.players.online == 0:
                        if self.last_player_time is None:
                            self.last_player_time = datetime.datetime.now()
                        elif (datetime.datetime.now() - self.last_player_time).total_seconds() > 300:  # 5分
                            await self.stop_server()
                            self.last_player_time = None
                    else:
                        self.last_player_time = None

            except Exception as e:
                print(f"Error checking server status: {str(e)}")

            await asyncio.sleep(60)  # 1分ごとにチェック

    async def get_current_rates(self):
        """現在の料金レートを取得する"""
        try:
            # gcloud コマンドを使用して料金を取得
            cpu_cost, ram_cost = os.popen('gcloud compute machine-types describe e2-standard-2 --zone asia-northeast1 --format="value(hourlyCpuCost),value(hourlyRamCost)"').read().split(',')
            disk_size, disk_cost = os.popen('gcloud compute disk-types describe pd-standard --zone asia-northeast1 --format="value(defaultDiskSizeGb),value(validDiskSizeGb)"').read().split(',')

            # 料金を float に変換
            cpu_cost = float(cpu_cost)
            ram_cost = float(ram_cost)
            disk_cost = float(disk_cost)

            # インスタンス料金を計算
            instance_cost = cpu_cost + ram_cost  # 1時間あたりのインスタンス料金

            # ディスク料金を計算
            disk_size = float(disk_size)  # ディスクのサイズ
            monthly_disk_cost = disk_size * disk_cost  # 1ヶ月あたりのディスク料金

            # 料金を格納
            rates = {
                'instance': instance_cost,  # 1時間あたりのインスタンス料金
                'disk': monthly_disk_cost / (24 * 30),  # 1時間あたりのディスク料金（月額を時間換算）
            }

            # USDからJPYへの換算
            exchange_rate = await self.get_exchange_rate()
            rates = {k: v * exchange_rate for k, v in rates.items()}

            return rates

        except Exception as e:
            print(f"料金レート取得エラー: {str(e)}")
            # エラー時のデフォルト値を設定
            rates = {
                'instance': 0.0836,  # e2-standard-2 in asia-northeast1 (概算)
                'disk': 0.000068  # pd-standard 20GB in asia-northeast1 (概算)
            }
            # USDからJPYへの換算
            exchange_rate = await self.get_exchange_rate()
            rates = {k: v * exchange_rate for k, v in rates.items()}
            return rates

    async def get_exchange_rate(self):
        """現在のUSD/JPYレートを取得"""
        try:
            # 外部為替レートAPIを使用
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.exchangerate-api.com/v4/latest/USD') as response:
                    data = await response.json()
                    return data['rates']['JPY']
        except Exception as e:
            print(f"為替レート取得エラー: {str(e)}")
            return 110  # エラー時のフォールバック値

    async def calculate_costs(self):
        instance = self.instance_client.get(
            project=self.project_id,
            zone=self.zone,
            instance=self.instance_name
        )

        start_time = datetime.datetime.fromisoformat(instance.last_start_timestamp)
        runtime = datetime.datetime.now(timezone.utc) - start_time.replace(tzinfo=timezone.utc)
        hours = runtime.total_seconds() / 3600

        # 現在のレートを取得
        rates = await self.get_current_rates()
        session_cost = hours * (rates['instance'] + rates['disk'])

        return {
            "runtime": str(runtime).split('.')[0],
            "session_cost": session_cost,
        }

    async def get_monthly_costs(self, channel):
        """月間コストを取得して表示する関数"""
        try:
            cost_info = await self.calculate_costs()
            message = f"現在の稼働時間は {cost_info['runtime']} で、\n"
            message += f"現在のセッションの費用は ¥{cost_info['session_cost']:.2f} だよ！\n"
            message += "月額の正確な合計は取得できないんだ。ごめんね。。"
            await channel.send(message)
        except Exception as e:
            await channel.send(f"費用情報の取得中にエラーが発生しちゃった... : {str(e)}")

    async def check_status(self, channel):
        """サーバーの状態を確認する共通関数"""
        try:
            instance = self.instance_client.get(
                project=self.project_id,
                zone=self.zone,
                instance=self.instance_name
            )
            status = "稼働中" if instance.status == "RUNNING" else "停止中"

            # インスタンス情報のデバッグ出力
            logging.info(f"Instance status: {instance.status}")
            logging.info(f"Network interfaces: {instance.network_interfaces}")

            if instance.status == "RUNNING":
                # IPアドレスの取得方法を修正
                ip_address = None
                for interface in instance.network_interfaces:
                    logging.info(f"Interface: {interface}")
                    if interface.access_configs:
                        for config in interface.access_configs:
                            logging.info(f"Access config: {config}")
                            if config.type == 'ONE_TO_ONE_NAT':
                                ip_address = config.nat_ip
                                break
                    if ip_address:
                        break

                # メタデータサーバーからIPアドレスを取得する試み
                if not ip_address:
                    try:
                        metadata_url = "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip"
                        headers = {"Metadata-Flavor": "Google"}
                        response = requests.get(metadata_url, headers=headers, timeout=5)
                        if response.status_code == 200:
                            ip_address = response.text.strip()
                            logging.info(f"IP address from metadata: {ip_address}")
                    except Exception as e:
                        logging.error(f"Error fetching IP from metadata: {str(e)}")

                if ip_address:
                    try:
                        server = JavaServer(ip_address, 25565, timeout=5)  # タイムアウトを5秒に設定
                        status_info = await server.async_status() # async対応
                        player_count = status_info.players.online
                        await channel.send(
                            f"サーバーは{status}だよ！\n"
                            f"IPアドレスは {ip_address} だよ！\n"
                            f"今は {player_count}人が遊んでるよ！"
                        )
                    except Exception as e:
                        await channel.send(
                            f"サーバーは{status}だよ！\n"
                            f"IPアドレスは {ip_address} だよ！\n"
                            f"マイクラサーバーに接続できなかったみたい..."
                        )
                else:
                    await channel.send(f"サーバーは{status}だけど、IPアドレスが見つからないよ...")
            else:
                await channel.send(f"サーバーは{status}だよ！")

        except Exception as e:
            await channel.send(f"サーバーの状態確認中にエラーが発生しちゃった... : {str(e)}")
            logging.exception(f"Error in check_status: {str(e)}")

bot = MinecraftBot()

from discord import app_commands

@bot.tree.command(name="start", description="サーバーを起動する")
async def start_command(interaction: discord.Interaction):
    await interaction.response.send_message("サーバーを起動するね...")
    await bot.start_server()

@bot.tree.command(name="stop", description="サーバーを停止する")
async def stop_command(interaction: discord.Interaction):
    await interaction.response.send_message("サーバーを停止するね...")
    await bot.stop_server()

@bot.tree.command(name="status", description="サーバーの状態を確認する")
async def status_command(interaction: discord.Interaction):
    await bot.check_status(interaction.channel)

@bot.tree.command(name="costs", description="月間コストを確認する")
async def costs_command(interaction: discord.Interaction):
    await bot.get_monthly_costs(interaction.channel)

bot.run(DISCORD_TOKEN)
