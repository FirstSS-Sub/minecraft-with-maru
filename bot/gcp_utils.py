from google.cloud import compute_v1
import datetime

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
