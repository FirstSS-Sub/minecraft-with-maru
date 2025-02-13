from mcstatus import JavaServer
import asyncio

class MinecraftServerStatus:
    def __init__(self, ip, port=25565):
        self.ip = ip
        self.port = port

    async def get_status(self):
        try:
            server = JavaServer(self.ip, self.port)
            status = await server.async_status()
            return {
                'online': True,
                'players': status.players.online,
                'max_players': status.players.max,
                'latency': status.latency
            }
        except:
            return {
                'online': False,
                'players': 0,
                'max_players': 0,
                'latency': 0
            }
