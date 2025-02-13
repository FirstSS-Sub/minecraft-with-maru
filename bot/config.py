import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
INSTANCE_NAME = os.getenv('INSTANCE_NAME')
ZONE = os.getenv('ZONE')
BUCKET_NAME = os.getenv('BUCKET_NAME')
START_EMOJI_ID = os.getenv('START_EMOJI_ID')
STOP_EMOJI_ID = os.getenv('STOP_EMOJI_ID')
STATUS_EMOJI_ID = os.getenv('STATUS_EMOJI_ID')
COSTS_EMOJI_ID = os.getenv('COSTS_EMOJI_ID')

# 料金設定（円/時）
COSTS = {
    'instance': float(os.getenv('INSTANCE_COST', 0)),  # インスタンスの時間あたりのコスト
    'disk': float(os.getenv('DISK_COST', 0))          # ディスクの時間あたりのコスト
}
