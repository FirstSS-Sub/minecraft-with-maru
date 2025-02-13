import os
import discord
from discord.ext import commands
import asyncio
from google.cloud import compute_v1
from google.cloud import monitoring_v3
from google.cloud import storage
from google.cloud import billing
import datetime
from mcstatus import JavaServer
import json
from config import (
    DISCORD_TOKEN, 
    DISCORD_CHANNEL_ID as CHANNEL_ID,
    GCP_PROJECT_ID,
    INSTANCE_NAME,
    ZONE,
    COSTS,
    START_EMOJI_ID,
    STOP_EMOJI_ID,
    STATUS_EMOJI_ID,
    COSTS_EMOJI_ID
)
from datetime import timezone
import aiohttp
import logging

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
        super().__init__(command_prefix='!', intents=intents)
        
        self.project_id = GCP_PROJECT_ID
        self.zone = ZONE
        self.instance_name = INSTANCE_NAME
        
        self.instance_client = compute_v1.InstancesClient()
        self.monitoring_client = monitoring_v3.MetricServiceClient()
        self.storage_client = storage.Client()
        self.billing_client = billing.CloudBillingClient()
        self.compute_client = compute_v1.ComputeClient()
        self.last_player_time = None
        self.shutdown_task = None
        self.last_rate_update = None
        self.current_rates = None

    async def setup_hook(self):
        self.bg_task = self.loop.create_task(self.check_server_status())

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.user} has connected to Discord!')
        
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return
            
        if str(reaction.emoji.id) == START_EMOJI_ID:  # サーバー起動
            await reaction.message.channel.send("サーバーを起動します...")
            await self.start_server()
            
        elif str(reaction.emoji.id) == STOP_EMOJI_ID:  # サーバー停止
            await reaction.message.channel.send("サーバーを停止します...")
            await self.stop_server()
            
        elif str(reaction.emoji.id) == STATUS_EMOJI_ID:  # サーバー状態確認
            await self.check_status(reaction.message.channel)
            
        elif str(reaction.emoji.id) == COSTS_EMOJI_ID:  # コスト確認
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
            ip_address = instance.network_interfaces[0].access_configs[0].nat_ip
            
            await self.get_channel(CHANNEL_ID).send(
                f"サーバーを起動したよ！\n"
                f"IPアドレスは {ip_address} だよ！"
            )
            
        except Exception as e:
            await self.get_channel(CHANNEL_ID).send(f"エラーが発生しちゃった... : {str(e)}")

    async def backup_world(self):
        try:
            instance = self.instance_client.get(
                project=self.project_id,
                zone=self.zone,
                instance=self.instance_name
            )
            
            # SSHでワールドデータを圧縮
            ip_address = instance.network_interfaces[0].access_configs[0].nat_ip
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            remote_commands = [
                'cd /minecraft/server',
                'tar -czf /tmp/world_backup.tar.gz world',
            ]
            
            # GCSにアップロード
            bucket = self.storage_client.bucket(f"{self.project_id}-minecraft-backups")
            blob = bucket.blob(f"world_backup_{timestamp}.tar.gz")
            
            # SCPでローカルに一時ダウンロード
            local_path = '/tmp/world_backup.tar.gz'
            # Note: ここではssh-keyの設定が必要です
            os.system(f'scp minecraft@{ip_address}:/tmp/world_backup.tar.gz {local_path}')
            
            # GCSにアップロード
            blob.upload_from_filename(local_path)
            
            # 一時ファイルの削除
            os.remove(local_path)
            
            return True
            
        except Exception as e:
            print(f"バックアップ中にエラーが発生しました: {str(e)}")
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
                f"今月の合計は ¥{cost_info['monthly_cost']:.2f} だよ！"
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
        # 1時間ごとにレート更新
        now = datetime.datetime.now(timezone.utc)
        if (self.last_rate_update is None or 
            (now - self.last_rate_update).total_seconds() > 3600):
            
            try:
                # SKUの情報を取得
                skus_request = {
                    "parent": f"services/6F81-5844-456A",  # Compute Engine service ID
                    "filter": f"displayName:('Compute Instance Core' OR 'Storage PD Capacity')"
                }
                
                rates = {
                    'instance': 0,
                    'disk': 0
                }
                
                # インスタンスタイプとリージョンに基づいて料金を取得
                instance_request = compute_v1.GetMachineTypeRequest(
                    project=self.project_id,
                    zone=self.zone,
                    machine_type="e2-standard-2"
                )
                machine_type = self.instance_client.get(request=instance_request)
                
                for sku in self.billing_client.list_skus(request=skus_request):
                    if "asia-northeast1" in sku.service_regions:
                        if "Compute Instance Core" in sku.description:
                            if "Preemptible" in sku.description:
                                # vCPUあたりの料金 × vCPU数
                                rates['instance'] = (
                                    float(sku.pricing_info[0].pricing_expression.tiered_rates[0].unit_price.nanos) 
                                    * 1e-9 
                                    * machine_type.guest_cpus
                                )
                        elif "Storage PD Capacity" in sku.description:
                            # GBあたりの料金 × ディスクサイズ
                            rates['disk'] = (
                                float(sku.pricing_info[0].pricing_expression.tiered_rates[0].unit_price.nanos) 
                                * 1e-9 
                                * 20  # 20GB
                            )
                
                # USDからJPYへの換算
                # 為替レートAPIを使用してより正確なレートを取得
                exchange_rate = await self.get_exchange_rate()
                rates = {k: v * exchange_rate for k, v in rates.items()}
                
                self.current_rates = rates
                self.last_rate_update = now
                
            except Exception as e:
                print(f"料金レート取得エラー: {str(e)}")
                # エラー時は.envの値を使用
                self.current_rates = COSTS
                
        return self.current_rates

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
        
        # 今月の初日を取得
        now = datetime.datetime.now(timezone.utc)
        first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # 今月の総コストを取得
        request = {
            "name": f"projects/{self.project_id}",
            "interval": {
                "start_time": first_day.isoformat(),
                "end_time": now.isoformat()
            }
        }
        
        try:
            monthly_cost = 0
            for cost in self.billing_client.get_project_costs(request):
                monthly_cost += cost.cost

            monthly_cost = monthly_cost * 110  # USDからJPYへの概算換算
        except Exception as e:
            print(f"月間コスト取得エラー: {str(e)}")
            monthly_cost = session_cost  # エラー時は簡易計算
        
        return {
            "runtime": str(runtime).split('.')[0],
            "session_cost": session_cost,
            "monthly_cost": monthly_cost
        }

    async def get_monthly_costs(self, channel):
        """月間コストを取得して表示する関数"""
        try:
            now = datetime.datetime.now(timezone.utc)
            first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            request = {
                "name": f"projects/{self.project_id}",
                "interval": {
                    "start_time": first_day.isoformat(),
                    "end_time": now.isoformat()
                }
            }
            
            costs_by_service = {}
            total_cost = 0
            
            for cost in self.billing_client.get_project_costs(request):
                service = cost.service.name
                amount = cost.cost * 110  # USDからJPYへの概算換算
                costs_by_service[service] = amount
                total_cost += amount
            
            # コスト情報を整形して送信
            message = "今月の費用を報告するね！\n"
            for service, cost in costs_by_service.items():
                message += f"{service}: ¥{cost:.2f}\n"
            message += f"\n合計で ¥{total_cost:.2f} になったよ！"
            
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
            
            if instance.status == "RUNNING":
                ip_address = instance.network_interfaces[0].access_configs[0].nat_ip
                try:
                    server = JavaServer(ip_address, 25565)
                    status_info = server.status()
                    player_count = status_info.players.online
                    await channel.send(
                        f"サーバーは{status}だよ！\n"
                        f"IPアドレスは {ip_address} だよ！\n"
                        f"今は {player_count}人が遊んでるよ！"
                    )
                except:
                    await channel.send(
                        f"サーバーは{status}だよ！\n"
                        f"IPアドレスは {ip_address} だよ！\n"
                        f"でも、Minecraftサーバーが応答してくれないよ..."
                    )
            else:
                await channel.send(f"サーバーは{status}だよ！")
                
        except Exception as e:
            await channel.send(f"エラーが発生しちゃった... : {str(e)}")

    @commands.command()
    async def start(self, ctx):
        """サーバーを起動するコマンド"""
        await ctx.send("サーバーを起動するね...")
        await self.start_server()

    @commands.command()
    async def stop(self, ctx):
        """サーバーを停止するコマンド"""
        await ctx.send("サーバーを停止するね...")
        await self.stop_server()

    @commands.command()
    async def status(self, ctx):
        """サーバーの状態を確認するコマンド"""
        await self.check_status(ctx.channel)

    @commands.command()
    async def costs(self, ctx):
        """月間コストを確認するコマンド"""
        await self.get_monthly_costs(ctx.channel)

bot = MinecraftBot()
bot.run(DISCORD_TOKEN)