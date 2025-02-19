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
    BUCKET_NAME,
    START_EMOJI_ID,
    STOP_EMOJI_ID,
    STATUS_EMOJI_ID,
    COSTS_EMOJI_ID
)
import datetime
from datetime import timezone
import aiohttp
import math

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

            # 起動後、IPアドレスが割り当てられるまで少し待つ
            await asyncio.sleep(1)  # (必要に応じて調整)

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
                    ip_address = getattr(config, 'nat_i_p', None) or getattr(config, 'external_ipv4', None)
                    if ip_address:
                        break

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
            logging.error(f"Error in start_server: {e}")
            await self.get_channel(CHANNEL_ID).send(f"サーバーの起動中にエラーが発生したよ...")

    async def stop_server(self):
        try:
            # コスト計算
            cost_info = await self.calculate_costs()

            request = compute_v1.StopInstanceRequest(
                project=self.project_id,
                zone=self.zone,
                instance=self.instance_name
            )
            operation = self.instance_client.stop(request=request)
            operation.result()

            # GCSからバックアップファイル名を取得
            backup_filename = await self.get_backup_filename()
            backup_message = f"バックアップファイル名は {backup_filename} だよ！" if backup_filename else "バックアップファイル名を取得できなかったよ..."

            await self.get_channel(CHANNEL_ID).send(
                f"サーバーを停止したよ！\n"
                f"{backup_message}\n"
                f"今回の稼働時間は {cost_info['runtime']} だったよ！\n"
                f"今回の費用は ¥{cost_info['session_cost']:.2f} になったよ！\n"
            )

        except Exception as e:
            await self.get_channel(CHANNEL_ID).send(f"エラーが発生しちゃった... : {str(e)}")

    async def get_backup_filename(self):
        try:
            bucket = self.storage_client.bucket(BUCKET_NAME)
            blobs = list(bucket.list_blobs(prefix="backups/"))
            if not blobs:
                return None

            # 最新のバックアップファイルを取得
            latest_blob = max(blobs, key=lambda blob: blob.time_created)

            # メタデータからファイル名を取得
            if 'backup_file' in latest_blob.metadata:
                return latest_blob.metadata['backup_file']
            else:
                return None
        except Exception as e:
            logging.exception(f"GCSからのファイル名取得中にエラーが発生しました: {str(e)}")
            return None

    async def check_server_status(self):
        try:
            instance = self.instance_client.get(
                project=self.project_id,
                zone=self.zone,
                instance=self.instance_name
            )

            logging.info(f"Instance status: {instance.status}")
            logging.info(f"Network interfaces: {instance.network_interfaces}")

            if instance.status == "RUNNING":
                ip_address = None
                for interface in instance.network_interfaces:
                    if hasattr(interface, 'access_configs') and interface.access_configs:
                        config = interface.access_configs[0]
                        ip_address = getattr(config, 'nat_i_p', None) or getattr(config, 'external_ipv4', None)
                        if ip_address:
                            break

                if ip_address:
                    try:
                        server = JavaServer(ip_address, 25565, timeout=5)
                        status_info = await server.async_status()
                        player_count = status_info.players.online
                        await self.get_channel(self.CHANNEL_ID).send(
                            f"サーバーは稼働中だよ！\n"
                            f"IPアドレスは {ip_address} だよ！\n"
                            f"今は {player_count}人が遊んでるよ！"
                        )

                        if status_info.players.online == 0:
                            if self.last_player_time is None:
                                self.last_player_time = datetime.datetime.now()
                            elif (datetime.datetime.now() - self.last_player_time).total_seconds() > 300:  # 5分
                                await self.stop_server()
                                self.last_player_time = None
                        else:
                            self.last_player_time = None

                    except Exception as e:
                        logging.error(f"Error connecting to Minecraft server: {e}")
                        await self.get_channel(self.CHANNEL_ID).send(
                            f"サーバーは稼働中だよ！\n"
                            f"IPアドレスは {ip_address} だよ！\n"
                            f"マイクラサーバーに接続できなかったみたい..."
                        )
                else:
                    logging.error("IP address not found in instance details")
                    await self.get_channel(self.CHANNEL_ID).send(f"サーバーは稼働中だけど、IPアドレスが見つからないよ...")
            else:
                await self.get_channel(self.CHANNEL_ID).send(f"サーバーは停止中だよ！")

        except Exception as e:
            logging.error(f"Error in check_server_status: {e}")
            await self.get_channel(self.CHANNEL_ID).send(f"サーバーの状態確認中にエラーが発生したよ...")

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

        start_time = datetime.datetime.fromisoformat(instance.last_start_timestamp.replace('Z', '+00:00'))
        current_time = datetime.datetime.now(timezone.utc)
        runtime = current_time - start_time

        # 分単位で切り上げ
        minutes = math.ceil(runtime.total_seconds() / 60)
        hours = minutes / 60

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
                            # 'nat_ip' の代わりに 'external_ipv4' を使用
                            ip_address = getattr(config, 'external_ipv4', None)
                            if ip_address:
                                break
                    if ip_address:
                        break

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
