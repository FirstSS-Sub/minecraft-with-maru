from google.cloud import compute_v1, monitoring_v3, storage, billing
import datetime
from datetime import timezone
import logging
import aiohttp

logger = logging.getLogger('minecraft_bot')

class GCPInstance:
    def __init__(self, project_id, zone, instance_name):
        self.project_id = project_id
        self.zone = zone
        self.instance_name = instance_name
        self.client = compute_v1.InstancesClient()

    async def start(self):
        request = compute_v1.StartInstanceRequest(
            project=self.project_id,
            zone=self.zone,
            instance=self.instance_name
        )
        operation = self.client.start(request=request)
        return operation.result()

    async def stop(self):
        request = compute_v1.StopInstanceRequest(
            project=self.project_id,
            zone=self.zone,
            instance=self.instance_name
        )
        operation = self.client.stop(request=request)
        return operation.result()

    def get_ip(self):
        instance = self.client.get(
            project=self.project_id,
            zone=self.zone,
            instance=self.instance_name
        )
        return instance.network_interfaces[0].access_configs[0].nat_ip

    def get_uptime(self):
        instance = self.client.get(
            project=self.project_id,
            zone=self.zone,
            instance=self.instance_name
        )
        start_time = datetime.datetime.fromisoformat(
            instance.last_start_timestamp
        )
        return datetime.datetime.now() - start_time

class GCPManager:
    def __init__(self, project_id, zone, instance_name):
        self.project_id = project_id
        self.zone = zone
        self.instance_name = instance_name
        
        # クライアントの初期化
        self.instance_client = compute_v1.InstancesClient()
        self.monitoring_client = monitoring_v3.MetricServiceClient()
        self.storage_client = storage.Client()
        self.billing_client = billing.CloudBillingClient()
        
        # レート情報のキャッシュ
        self.last_rate_update = None
        self.current_rates = None

    async def start_instance(self):
        """インスタンスを起動"""
        try:
            request = compute_v1.StartInstanceRequest(
                project=self.project_id,
                zone=self.zone,
                instance=self.instance_name
            )
            operation = self.instance_client.start(request=request)
            operation.result()
            return self.get_instance_ip()
        except Exception as e:
            logger.error(f"インスタンス起動エラー: {str(e)}")
            raise

    async def stop_instance(self):
        """インスタンスを停止"""
        try:
            request = compute_v1.StopInstanceRequest(
                project=self.project_id,
                zone=self.zone,
                instance=self.instance_name
            )
            operation = self.instance_client.stop(request=request)
            return operation.result()
        except Exception as e:
            logger.error(f"インスタンス停止エラー: {str(e)}")
            raise

    def get_instance_status(self):
        """インスタンスの状態を取得"""
        instance = self.instance_client.get(
            project=self.project_id,
            zone=self.zone,
            instance=self.instance_name
        )
        return instance.status

    def get_instance_ip(self):
        """インスタンスのIPアドレスを取得"""
        instance = self.instance_client.get(
            project=self.project_id,
            zone=self.zone,
            instance=self.instance_name
        )
        return instance.network_interfaces[0].access_configs[0].nat_ip

    async def backup_to_gcs(self, local_path, timestamp):
        """GCSにバックアップを保存"""
        try:
            bucket = self.storage_client.bucket(f"{self.project_id}-minecraft-backups")
            blob = bucket.blob(f"world_backup_{timestamp}.tar.gz")
            blob.upload_from_filename(local_path)
            return True
        except Exception as e:
            logger.error(f"バックアップ保存エラー: {str(e)}")
            return False

    async def get_monthly_costs(self):
        """月間コストを取得"""
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
                amount = cost.cost * await self.get_exchange_rate()
                costs_by_service[service] = amount
                total_cost += amount
            
            return costs_by_service, total_cost
            
        except Exception as e:
            logger.error(f"コスト取得エラー: {str(e)}")
            raise

    async def get_exchange_rate(self):
        """為替レートを取得"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.exchangerate-api.com/v4/latest/USD') as response:
                    data = await response.json()
                    return data['rates']['JPY']
        except Exception:
            return 110  # フォールバック値
