import os
from dotenv import load_dotenv

load_dotenv()

def get_env_or_raise(key: str) -> str:
    """環境変数を取得し、存在しない場合は例外を発生させる"""
    value = os.getenv(key)
    if value is None:
        raise ValueError(f"Environment variable {key} is not set")
    return value

# 文字列として読み込むもの
DISCORD_TOKEN = get_env_or_raise('DISCORD_TOKEN')
GCP_PROJECT_ID = get_env_or_raise('GCP_PROJECT_ID')
INSTANCE_NAME = get_env_or_raise('INSTANCE_NAME')
ZONE = get_env_or_raise('ZONE')
BUCKET_NAME = get_env_or_raise('BUCKET_NAME')

# Snowflake ID
DISCORD_CHANNEL_ID = int(get_env_or_raise('DISCORD_CHANNEL_ID'))
START_EMOJI_ID = int(get_env_or_raise('START_EMOJI_ID'))
STOP_EMOJI_ID = int(get_env_or_raise('STOP_EMOJI_ID'))
STATUS_EMOJI_ID = int(get_env_or_raise('STATUS_EMOJI_ID'))
COSTS_EMOJI_ID = int(get_env_or_raise('COSTS_EMOJI_ID'))

# 数値（浮動小数点）
COSTS = {
    'instance': float(get_env_or_raise('INSTANCE_COST')),
    'disk': float(get_env_or_raise('DISK_COST'))
}
