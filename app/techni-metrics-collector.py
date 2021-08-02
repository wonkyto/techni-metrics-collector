#!/usr/bin/env python3

import argparse
import asyncio
import logging
import paramiko
import re
import socket
import sys
import time
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from influxdb import InfluxDBClient

default_config_file = "/config/config.yaml"

# Set up logger
logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
fmt = logging.Formatter(fmt='%(asctime)s.%(msecs)03d - '
                        + '%(levelname)s - %(message)s',
                        datefmt="%Y/%m/%d %H:%M:%S")
ch.setFormatter(fmt)
logger.addHandler(ch)


def get_args():
    """Parse the command line options

    Returns argparse object
    """

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=False, help='Config File '
                        + 'Default: (' + default_config_file + ')',
                        default=default_config_file)
    args = parser.parse_args()
    return args


def run_cmd(host, user, password, command):
    """Run a remote command on remote host

    Returns stdout of command as a string array
    """
    result = None

    # Make an ssh connection
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(host, username=user, password=password, timeout=5)
        stdin, stdout, stderr = ssh.exec_command(command)
        result = stdout.readlines()
        ssh.close()
    except (paramiko.ssh_exception.BadHostKeyException,
            paramiko.ssh_exception.AuthenticationException,
            paramiko.ssh_exception.SSHException) as e:
        logger.error("Login Failure: {}".format(str(e)))
    except socket.timeout:
        logger.error('timeout')
    except socket.error:
        logger.error('Connection Refused')
    return result


def load_yaml_file(yaml_file):
    """Load the config file info from the yaml

    Returns dict
    """
    result = None

    # Open the yaml file
    try:
        with open(yaml_file) as data_file:
            data = yaml.load(data_file, Loader=yaml.FullLoader)
        result = data
    except (FileNotFoundError) as e:
        logger.error("Could not open file: {} - {}".format(yaml_file, str(e)))
        sys.exit(1)
    return result


def parse_if_data(data, name):
    """Parse the output of ifconfig to get the interface counters

    Returns dict of data
    """
    interface = {}
    interface['name'] = name
    for line in data:
        # Get if_name, MAC
        # br-lan    Link encap:Ethernet  HWaddr A4:91:B1:64:21:72
        m = re.search(r"^([\w\-]+).*HWaddr ([a-fA-F0-9:]+)", line)
        if m:
            interface['if_name'] = m.group(1)
            interface['mac'] = m.group(2)

        # Get IP
        m = re.search(r"inet addr:([\d\.]+)", line)
        if m:
            interface['ip'] = m.group(1)

        # Get up/down status
        m = re.search(r"UP BROADCAST RUNNING", line)
        if m:
            interface['status'] = 1

        # Get RX packets, errors, drops
        # RX packets:54280044 errors:0 dropped:14834 overruns:0 frame:0
        m = re.search(r"RX packets:([\d]+) errors:([\d]+) dropped:([\d]+)",
                      line)
        if m:
            interface['rx_packets'] = m.group(1)
            interface['rx_errors'] = m.group(2)
            interface['rx_dropped'] = m.group(3)

        # Get TX packets, errors, drops
        # TX packets:54280044 errors:0 dropped:14834 overruns:0 frame:0
        m = re.search(r"TX packets:([\d]+) errors:([\d]+) dropped:([\d]+)",
                      line)
        if m:
            interface['tx_packets'] = m.group(1)
            interface['tx_errors'] = m.group(2)
            interface['tx_dropped'] = m.group(3)

        # Get bytes
        # RX bytes:16060081777 (14.9 GiB)  TX bytes:114602693632 (106.7 GiB)
        m = re.search(r"RX bytes:([\d]+).*TX bytes:([\d]+)", line)
        if m:
            interface['rx_bytes'] = m.group(1)
            interface['tx_bytes'] = m.group(2)

    if 'status' not in interface:
        interface['status'] = 0

    return interface


def parse_dsl_data(data):
    """Parse the output of xdslctl to get the dsl stats

    Returns dict of data
    """
    dsl = {}

    for line in data:
        # Get Max Rates
        # Max:	Upstream rate = 29536 Kbps, Downstream rate = 56948 Kbps
        m = re.search(r"^Max:	Upstream rate = (\d+) Kbps, Downstream rate = (\d+) Kbps",
                      line)
        if m:
            dsl['max_up_rate'] = int(m.group(1))
            dsl['max_down_rate'] = int(m.group(2))

        # Get Max Bearer Rate 0
        # Bearer:	0, Upstream rate = 22600 Kbps, Downstream rate = 56009 Kbps
        m = re.search(r"^Bearer:	0, Upstream rate = (\d+) Kbps, Downstream rate = (\d+) Kbps",
                      line)
        if m:
            dsl['bearer0_up_rate'] = int(m.group(1))
            dsl['bearer0_down_rate'] = int(m.group(2))

        # Get SNR
        # SNR (dB):	 5.9		 11.3
        # SNR (dB):\t 5.9\t\t 11.3\n
        m = re.search(r"SNR \(dB\):\t ([0-9\.]+)\t\t ([0-9\.]+)", line)
        if m:
            dsl['snr_down'] = float(m.group(1))
            dsl['snr_up'] = float(m.group(2))

        # Get Attn
        # Attn(dB):\t 20.0\t\t 0.0\n
        m = re.search(r"Attn\(dB\):\t ([0-9\.]+)\t\t ([0-9\.]+)", line)
        if m:
            dsl['attn_down'] = float(m.group(1))
            dsl['attn_up'] = float(m.group(2))

        # Get Power
        # Pwr(dBm):\t 14.3\t\t 7.6\n
        m = re.search(r"Pwr\(dBm\):\t ([0-9\.]+)\t\t ([0-9\.]+)", line)
        if m:
            dsl['pwr_down'] = float(m.group(1))
            dsl['pwr_up'] = float(m.group(2))

        # Get Link Uptime in seconds
        m = re.search(r"^AS:\s+([\d\.]+)", line)
        if m:
            dsl['link_uptime'] = int(m.group(1))

    return dsl


def prepare_if_data(if_data):
    """Prepare the parsed data into a data object that's ready to send to InfluxDB

    Returns dict of interface metrics to send to influxDB
    """

    status = 'down'
    if if_data['status']:
        status = 'up'

    interface = {
        'measurement': 'interface',
        'tags': {
            'name': if_data['name'],
            'ip': if_data['ip'],
            'ifName': if_data['if_name'],
            'ifStatus': status
        },
        'fields': {
            'IfAdminStatus': int(if_data['status']),
            'IfInOctets': int(if_data['rx_bytes']),
            'IfInDiscards': int(if_data['rx_dropped']),
            'IfInErrors': int(if_data['rx_errors']),
            'IfInPackets': int(if_data['rx_packets']),
            'IfOutOctets': int(if_data['tx_bytes']),
            'IfOutDiscards': int(if_data['tx_dropped']),
            'IfOutErrors': int(if_data['tx_errors']),
            'IfOutPackets': int(if_data['tx_packets']),
        }
    }
    return interface


def prepare_dsl_data(dsl_data):
    """Prepare the parsed data into a data object that's ready to send to InfluxDB

    Returns dict of interface metrics to send to influxDB
    """

    dsl = {
        'measurement': 'dsl',
        'fields': dsl_data
    }
    return dsl


def poll(influx_client, gateway):
    """Poll the network device, send collecte data to influxDB"""
    logger.info("Polling {}@{}".format(gateway['User'], gateway['Host']))

    # Get LAN and WAN interface counter data
    lan_result = run_cmd(gateway['Host'], gateway['User'],
                         gateway['Password'], "ifconfig br-lan")
    wan_result = run_cmd(gateway['Host'], gateway['User'],
                         gateway['Password'], "ifconfig ptm0")

    # Get DSL Stats
    dsl_result = run_cmd(gateway['Host'], gateway['User'],
                         gateway['Password'], "xdslctl info --stats")

    metrics = []
    if lan_result is not None:
        if_data = parse_if_data(lan_result, 'lan')
        if_metrics = prepare_if_data(if_data)
        metrics.append(if_metrics)

    if wan_result is not None:
        if_data = parse_if_data(wan_result, 'wan')
        if_metrics = prepare_if_data(if_data)
        metrics.append(if_metrics)

    if dsl_result is not None:
        dsl_data = parse_dsl_data(dsl_result)
        dsl_metrics = prepare_dsl_data(dsl_data)
        metrics.append(dsl_metrics)

    if influx_client.write_points(metrics):
        logger.debug("Sending metrics to influxdb: successful")
    else:
        logger.debug("Sending metrics to influxdb: failed")


def main():
    # Get arguements
    args = get_args()
    # Load configure file
    config = load_yaml_file(args.config)

    # We will be running this container in the same docker-compose
    # configuration as influxdb. To ensure we provide enough time
    # for influxdb to start, we wait 60 seconds
    time.sleep(60)

    # Make a connection to the InfluxDB Database
    # Create a new database if it doesn't exist
    influx_client = InfluxDBClient(host=config['InfluxDb']['Host'],
                                   port=config['InfluxDb']['Port'])
    influx_client.create_database(config['InfluxDb']['Database'])
    influx_client.switch_database(config['InfluxDb']['Database'])

    # Create a scheduler, and run the poller every 5 minutes
    scheduler = AsyncIOScheduler()
    scheduler.add_job(poll, 'cron',
                      minute='00,5,10,15,20,25,30,35,40,45,50,55',
                      args=(influx_client, config['Gateway']))
    scheduler.start()

    # Execution will block here until Ctrl+C is pressed.
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass

    influx_client.close()


if __name__ == '__main__':
    main()
