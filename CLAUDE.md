# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
make build    # Build the Docker image (required after Dockerfile or requirements.txt changes)
make lint     # Run ruff linter via Docker
make format   # Run ruff formatter via Docker
make pytest   # Run unit tests via Docker
make test     # Run the script in Docker with local ./app and ./config mounted (fast iteration)
make run      # Run the collector using the built image with ./config mounted
```

During development, use `make test` to avoid rebuilding the image — it mounts `./app` into the container so changes to the Python script are picked up immediately.

## Architecture

This is a single-file Python application (`app/techni_metrics_collector.py`) that:

1. **SSHes into a Telstra Technicolor DJA0231 gateway** every 5 minutes using `paramiko`, running `ifconfig` (for LAN `br-lan` and WAN `ptm0` interfaces) and `xdslctl info --stats` (for DSL line stats).
2. **Parses the CLI output** via regex in `parse_if_data()` and `parse_dsl_data()`.
3. **Writes metrics to InfluxDB** via `influxdb` client, using two measurements: `interface` (with tags for name/IP/status) and `dsl`.
4. **Schedules polling** with `APScheduler` (`BackgroundScheduler`) on a cron trigger every 5 minutes, with an immediate poll on startup.

On startup the app retries the InfluxDB connection (with backoff up to 60 s) to allow InfluxDB to be ready before proceeding (intended for docker-compose deployment alongside InfluxDB).

## Configuration

`config/config.yaml` requires:

- `InfluxDb.Host`, `InfluxDb.Port`, `InfluxDb.Database` — InfluxDB connection details
- `Gateway.Host`, `Gateway.User`, `Gateway.Password` — SSH credentials for the gateway

The config is mounted at `/config/config.yaml` inside the container.
