import pytest
from unittest.mock import Mock, patch, AsyncMock
from bot.bot import MinecraftBot
from bot.gcp_utils import GCPManager
import discord

@pytest.fixture
async def bot():
    """テスト用のボットインスタンスを作成"""
    bot = MinecraftBot()
    return bot

@pytest.fixture
def gcp_manager():
    """テスト用のGCPManagerインスタンスを作成"""
    return GCPManager("test-project", "test-zone", "test-instance")

@pytest.mark.asyncio
async def test_start_server(bot):
    """サーバー起動テスト"""
    with patch('bot.gcp_utils.GCPManager.start_instance') as mock_start:
        mock_start.return_value = "192.168.1.1"
        channel = Mock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        
        await bot.start_server()
        
        mock_start.assert_called_once()
        channel.send.assert_called_with("サーバーが起動しました！\nIP: 192.168.1.1")

@pytest.mark.asyncio
async def test_backup_world(bot):
    """バックアップ機能テスト"""
    with patch('bot.gcp_utils.GCPManager.backup_to_gcs') as mock_backup:
        mock_backup.return_value = True
        
        result = await bot.backup_world()
        
        assert result == True
        mock_backup.assert_called_once()

@pytest.mark.asyncio
async def test_get_monthly_costs(gcp_manager):
    """月間コスト取得テスト"""
    with patch('bot.gcp_utils.GCPManager.get_monthly_costs') as mock_costs:
        mock_costs.return_value = ({"Compute Engine": 1000}, 1000)
        
        costs, total = await gcp_manager.get_monthly_costs()
        
        assert costs["Compute Engine"] == 1000
        assert total == 1000 