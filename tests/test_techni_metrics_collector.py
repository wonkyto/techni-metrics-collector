import socket
import sys
import pytest
import paramiko
import yaml
from unittest.mock import MagicMock, patch

sys.path.insert(0, "app")
import techni_metrics_collector as tmc  # noqa: E402


# ---------------------------------------------------------------------------
# prepare_if_data
# ---------------------------------------------------------------------------

def test_prepare_if_data_interface_up():
    if_data = {
        "name": "lan",
        "status": 1,
        "ip": "192.168.0.1",
        "if_name": "br-lan",
        "rx_bytes": "1000",
        "rx_dropped": "2",
        "rx_errors": "3",
        "rx_packets": "100",
        "tx_bytes": "2000",
        "tx_dropped": "4",
        "tx_errors": "5",
        "tx_packets": "200",
    }
    result = tmc.prepare_if_data(if_data)
    assert result["measurement"] == "interface"
    assert result["tags"]["ifStatus"] == "up"
    assert result["tags"]["ip"] == "192.168.0.1"
    assert result["tags"]["ifName"] == "br-lan"
    assert result["fields"]["IfAdminStatus"] == 1
    assert result["fields"]["IfInOctets"] == 1000
    assert result["fields"]["IfInDiscards"] == 2
    assert result["fields"]["IfInErrors"] == 3
    assert result["fields"]["IfInPackets"] == 100
    assert result["fields"]["IfOutOctets"] == 2000
    assert result["fields"]["IfOutDiscards"] == 4
    assert result["fields"]["IfOutErrors"] == 5
    assert result["fields"]["IfOutPackets"] == 200


def test_prepare_if_data_interface_down_missing_fields():
    """Interface that is down may not have IP or counters parsed."""
    if_data = {"name": "wan", "status": 0}
    result = tmc.prepare_if_data(if_data)
    assert result["tags"]["ifStatus"] == "down"
    assert result["tags"]["ip"] == "unknown"
    assert result["tags"]["ifName"] == "unknown"
    assert result["fields"]["IfAdminStatus"] == 0
    assert result["fields"]["IfInOctets"] == 0
    assert result["fields"]["IfOutOctets"] == 0


# ---------------------------------------------------------------------------
# prepare_dsl_data
# ---------------------------------------------------------------------------

def test_prepare_dsl_data():
    dsl_data = {
        "max_up_rate": 29536,
        "max_down_rate": 56948,
        "snr_down": 5.9,
        "snr_up": 11.3,
        "attn_down": 20.0,
        "attn_up": 0.0,
        "link_uptime": 3600,
    }
    result = tmc.prepare_dsl_data(dsl_data)
    assert result["measurement"] == "dsl"
    assert result["fields"] is dsl_data


def test_prepare_dsl_data_empty():
    result = tmc.prepare_dsl_data({})
    assert result["measurement"] == "dsl"
    assert result["fields"] == {}


# ---------------------------------------------------------------------------
# load_yaml_file
# ---------------------------------------------------------------------------

def test_load_yaml_file_valid(tmp_path):
    config = {"InfluxDb": {"Host": "localhost", "Port": "8086", "Database": "mydb"}}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(config))
    result = tmc.load_yaml_file(str(config_file))
    assert result["InfluxDb"]["Host"] == "localhost"
    assert result["InfluxDb"]["Port"] == "8086"


def test_load_yaml_file_not_found():
    with pytest.raises(SystemExit):
        tmc.load_yaml_file("/nonexistent/path/config.yaml")


# ---------------------------------------------------------------------------
# connect_ssh
# ---------------------------------------------------------------------------

def test_connect_ssh_success():
    with patch("paramiko.SSHClient") as mock_ssh_class:
        mock_ssh = MagicMock()
        mock_ssh_class.return_value = mock_ssh
        result = tmc.connect_ssh("192.168.0.1", "root", "password")
        assert result is mock_ssh
        mock_ssh.connect.assert_called_once_with(
            "192.168.0.1", username="root", password="password", timeout=5
        )


def test_connect_ssh_auth_failure():
    with patch("paramiko.SSHClient") as mock_ssh_class:
        mock_ssh = MagicMock()
        mock_ssh_class.return_value = mock_ssh
        mock_ssh.connect.side_effect = paramiko.ssh_exception.AuthenticationException
        result = tmc.connect_ssh("192.168.0.1", "root", "wrongpassword")
        assert result is None


def test_connect_ssh_timeout():
    with patch("paramiko.SSHClient") as mock_ssh_class:
        mock_ssh = MagicMock()
        mock_ssh_class.return_value = mock_ssh
        mock_ssh.connect.side_effect = socket.timeout
        result = tmc.connect_ssh("192.168.0.1", "root", "password")
        assert result is None


def test_connect_ssh_refused():
    with patch("paramiko.SSHClient") as mock_ssh_class:
        mock_ssh = MagicMock()
        mock_ssh_class.return_value = mock_ssh
        mock_ssh.connect.side_effect = socket.error
        result = tmc.connect_ssh("192.168.0.1", "root", "password")
        assert result is None


# ---------------------------------------------------------------------------
# run_cmd
# ---------------------------------------------------------------------------

def _make_ssh_mock(stdout_lines, stderr_bytes=b""):
    mock_ssh = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()
    mock_stdout.readlines.return_value = stdout_lines
    mock_stderr.read.return_value = stderr_bytes
    mock_ssh.exec_command.return_value = (None, mock_stdout, mock_stderr)
    return mock_ssh


def test_run_cmd_success():
    mock_ssh = _make_ssh_mock(["line1\n", "line2\n"])
    result = tmc.run_cmd(mock_ssh, "ifconfig br-lan")
    assert result == ["line1\n", "line2\n"]


def test_run_cmd_empty_output():
    mock_ssh = _make_ssh_mock([])
    result = tmc.run_cmd(mock_ssh, "ifconfig ptm0")
    assert result == []


def test_run_cmd_with_stderr():
    mock_ssh = _make_ssh_mock([], stderr_bytes=b"command not found")
    result = tmc.run_cmd(mock_ssh, "badcommand")
    assert result == []


def test_run_cmd_ssh_exception():
    mock_ssh = MagicMock()
    mock_ssh.exec_command.side_effect = paramiko.ssh_exception.SSHException("error")
    result = tmc.run_cmd(mock_ssh, "ifconfig br-lan")
    assert result is None


# ---------------------------------------------------------------------------
# poll
# ---------------------------------------------------------------------------

GATEWAY = {"Host": "192.168.0.1", "User": "root", "Password": "password"}


def test_poll_ssh_failure():
    """When SSH connection fails, no metrics are written."""
    mock_influx = MagicMock()
    with patch.object(tmc, "connect_ssh", return_value=None):
        tmc.poll(mock_influx, GATEWAY)
    mock_influx.write_points.assert_not_called()


def test_poll_all_commands_fail():
    """When all SSH commands return None, write_points is not called."""
    mock_influx = MagicMock()
    mock_ssh = MagicMock()
    with patch.object(tmc, "connect_ssh", return_value=mock_ssh):
        with patch.object(tmc, "run_cmd", return_value=None):
            tmc.poll(mock_influx, GATEWAY)
    mock_influx.write_points.assert_not_called()
    mock_ssh.close.assert_called_once()


def test_poll_writes_metrics_on_success():
    """When commands succeed, write_points is called with collected metrics."""
    mock_influx = MagicMock()
    mock_influx.write_points.return_value = True
    mock_ssh = MagicMock()
    mock_if_data = {
        "name": "lan", "status": 1, "ip": "192.168.0.1", "if_name": "br-lan",
        "rx_bytes": "1000", "rx_dropped": "0", "rx_errors": "0", "rx_packets": "100",
        "tx_bytes": "2000", "tx_dropped": "0", "tx_errors": "0", "tx_packets": "200",
    }
    with patch.object(tmc, "connect_ssh", return_value=mock_ssh):
        with patch.object(tmc, "run_cmd", return_value=["output"]):
            with patch.object(tmc, "parse_if_data", return_value=mock_if_data):
                with patch.object(tmc, "parse_dsl_data", return_value={}):
                    tmc.poll(mock_influx, GATEWAY)
    mock_influx.write_points.assert_called_once()
    mock_ssh.close.assert_called_once()


def test_poll_ssh_closed_on_command_failure():
    """SSH connection is closed even if a command raises an exception."""
    mock_influx = MagicMock()
    mock_ssh = MagicMock()
    with patch.object(tmc, "connect_ssh", return_value=mock_ssh):
        with patch.object(tmc, "run_cmd", side_effect=Exception("unexpected")):
            with pytest.raises(Exception):
                tmc.poll(mock_influx, GATEWAY)
    mock_ssh.close.assert_called_once()
