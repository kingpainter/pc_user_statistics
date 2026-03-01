"""Integration tests for coordinator module."""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import time

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = Mock(spec=HomeAssistant)
    hass.states = Mock()
    hass.bus = Mock()
    hass.async_create_task = Mock(side_effect=lambda coro: None)
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = Mock(spec=ConfigEntry)
    entry.entry_id = "test_entry_123"
    entry.data = {
        "host": "localhost",
        "port": 8086,
        "database": "homeassistant",
        "username": "test_user",
        "password": "test_pass",
        "user_mappings": {"konge": "flemming", "lukas": "lukas", "sebas": "sebastian"},
        "tracked_users": ["flemming", "lukas", "sebastian"]
    }
    return entry


class TestPCStatisticsCoordinator:
    """Tests for PCStatisticsCoordinator."""
    
    @patch('custom_components.pc_user_statistics.PCStatisticsCoordinator._async_load_monthly_data')
    def test_initialization(self, mock_load, mock_hass, mock_config_entry):
        """Test coordinator initialization."""
        from custom_components.pc_user_statistics import PCStatisticsCoordinator
        
        coordinator = PCStatisticsCoordinator(mock_hass, mock_config_entry)
        
        assert coordinator.current_user is None
        assert coordinator.acc_time == 0.0
        assert coordinator.acc_energy == 0.0
        assert coordinator.acc_cost == 0.0
        assert "flemming" in coordinator.monthly
        assert "lukas" in coordinator.monthly
        assert "sebastian" in coordinator.monthly
        assert len(coordinator.failed_writes) == 0
    
    @patch('custom_components.pc_user_statistics.PCStatisticsCoordinator._async_load_monthly_data')
    def test_get_power_valid_states(self, mock_load, mock_hass, mock_config_entry):
        """Test _get_power with valid sensor states."""
        from custom_components.pc_user_statistics import PCStatisticsCoordinator
        
        # Mock sensor states
        watt_state = Mock()
        watt_state.state = "500.0"
        device_power_state = Mock()
        device_power_state.state = "50.0"
        
        mock_hass.states.get = Mock(side_effect=lambda x: {
            "sensor.gamer_pc_power_monitor_current_consumption": watt_state,
            "sensor.gamer_pc_power_monitor_device_power": device_power_state
        }.get(x))
        
        coordinator = PCStatisticsCoordinator(mock_hass, mock_config_entry)
        power = coordinator._get_power()
        
        assert power == 450.0  # 500 - 50
    
    @patch('custom_components.pc_user_statistics.PCStatisticsCoordinator._async_load_monthly_data')
    def test_get_power_unavailable_states(self, mock_load, mock_hass, mock_config_entry):
        """Test _get_power with unavailable sensor states."""
        from custom_components.pc_user_statistics import PCStatisticsCoordinator
        
        # Mock unavailable sensor states
        watt_state = Mock()
        watt_state.state = STATE_UNAVAILABLE
        device_power_state = Mock()
        device_power_state.state = STATE_UNAVAILABLE
        
        mock_hass.states.get = Mock(side_effect=lambda x: {
            "sensor.gamer_pc_power_monitor_current_consumption": watt_state,
            "sensor.gamer_pc_power_monitor_device_power": device_power_state
        }.get(x))
        
        coordinator = PCStatisticsCoordinator(mock_hass, mock_config_entry)
        power = coordinator._get_power()
        
        assert power == 0.0
    
    @patch('custom_components.pc_user_statistics.PCStatisticsCoordinator._async_load_monthly_data')
    def test_get_power_negative_result(self, mock_load, mock_hass, mock_config_entry):
        """Test _get_power with negative result (should clamp to 0)."""
        from custom_components.pc_user_statistics import PCStatisticsCoordinator
        
        # Mock states where device power > watt
        watt_state = Mock()
        watt_state.state = "30.0"
        device_power_state = Mock()
        device_power_state.state = "50.0"
        
        mock_hass.states.get = Mock(side_effect=lambda x: {
            "sensor.gamer_pc_power_monitor_current_consumption": watt_state,
            "sensor.gamer_pc_power_monitor_device_power": device_power_state
        }.get(x))
        
        coordinator = PCStatisticsCoordinator(mock_hass, mock_config_entry)
        power = coordinator._get_power()
        
        assert power == 0.0
    
    @patch('custom_components.pc_user_statistics.PCStatisticsCoordinator._async_load_monthly_data')
    def test_get_price(self, mock_load, mock_hass, mock_config_entry):
        """Test _get_price."""
        from custom_components.pc_user_statistics import PCStatisticsCoordinator
        
        price_state = Mock()
        price_state.state = "2.5"
        
        mock_hass.states.get = Mock(return_value=price_state)
        
        coordinator = PCStatisticsCoordinator(mock_hass, mock_config_entry)
        price = coordinator._get_price()
        
        assert price == 2.5
    
    @patch('custom_components.pc_user_statistics.PCStatisticsCoordinator._async_load_monthly_data')
    def test_get_data(self, mock_load, mock_hass, mock_config_entry):
        """Test _get_data returns correct structure."""
        from custom_components.pc_user_statistics import PCStatisticsCoordinator
        
        coordinator = PCStatisticsCoordinator(mock_hass, mock_config_entry)
        coordinator.current_user = "flemming"
        coordinator.acc_time = 3600.0
        coordinator.acc_energy = 1.5
        coordinator.acc_cost = 2.5
        
        data = coordinator._get_data()
        
        assert data["current_user"] == "flemming"
        assert data["acc_time"] == 3600.0
        assert data["acc_energy"] == 1.5
        assert data["acc_cost"] == 2.5
        assert "monthly" in data
        assert "flemming" in data["monthly"]
    
    @patch('custom_components.pc_user_statistics.PCStatisticsCoordinator._async_load_monthly_data')
    def test_buffer_failed_write(self, mock_load, mock_hass, mock_config_entry):
        """Test buffering failed writes."""
        from custom_components.pc_user_statistics import PCStatisticsCoordinator
        
        coordinator = PCStatisticsCoordinator(mock_hass, mock_config_entry)
        
        write_data = {
            "point": "test_point",
            "timestamp": 123456789,
            "attempts": 0
        }
        
        coordinator._buffer_failed_write(write_data)
        
        assert len(coordinator.failed_writes) == 1
        assert coordinator.failed_writes[0]["point"] == "test_point"
    
    @patch('custom_components.pc_user_statistics.PCStatisticsCoordinator._async_load_monthly_data')
    def test_buffer_overflow(self, mock_load, mock_hass, mock_config_entry):
        """Test buffer overflow handling."""
        from custom_components.pc_user_statistics import PCStatisticsCoordinator
        from custom_components.pc_user_statistics.const import MAX_BUFFERED_WRITES
        
        coordinator = PCStatisticsCoordinator(mock_hass, mock_config_entry)
        
        # Fill buffer to max
        for i in range(MAX_BUFFERED_WRITES):
            coordinator._buffer_failed_write({
                "point": f"point_{i}",
                "timestamp": 123456789 + i,
                "attempts": 0
            })
        
        assert len(coordinator.failed_writes) == MAX_BUFFERED_WRITES
        
        # Add one more - should drop oldest
        coordinator._buffer_failed_write({
            "point": "point_new",
            "timestamp": 999999999,
            "attempts": 0
        })
        
        assert len(coordinator.failed_writes) == MAX_BUFFERED_WRITES
        assert coordinator.failed_writes[0]["point"] == "point_1"  # point_0 was dropped
        assert coordinator.failed_writes[-1]["point"] == "point_new"


class TestCoordinatorCalculations:
    """Tests for delta calculations."""
    
    @patch('custom_components.pc_user_statistics.PCStatisticsCoordinator._async_load_monthly_data')
    @patch('custom_components.pc_user_statistics.PCStatisticsCoordinator._async_write_to_influx')
    def test_calculate_deltas_no_user(self, mock_write, mock_load, mock_hass, mock_config_entry):
        """Test that deltas are not calculated when no user is active."""
        from custom_components.pc_user_statistics import PCStatisticsCoordinator
        
        coordinator = PCStatisticsCoordinator(mock_hass, mock_config_entry)
        coordinator.current_user = None
        
        # Should return early without calculations
        import asyncio
        asyncio.run(coordinator._calculate_deltas(time.time()))
        
        mock_write.assert_not_called()
    
    @patch('custom_components.pc_user_statistics.PCStatisticsCoordinator._async_load_monthly_data')
    @patch('custom_components.pc_user_statistics.PCStatisticsCoordinator._async_write_to_influx')
    def test_calculate_deltas_negative_time(self, mock_write, mock_load, mock_hass, mock_config_entry):
        """Test that deltas are not calculated for negative time."""
        from custom_components.pc_user_statistics import PCStatisticsCoordinator
        
        coordinator = PCStatisticsCoordinator(mock_hass, mock_config_entry)
        coordinator.current_user = "flemming"
        coordinator.last_time = time.time() + 100  # Future time
        
        # Should return early
        import asyncio
        asyncio.run(coordinator._calculate_deltas(time.time()))
        
        mock_write.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])