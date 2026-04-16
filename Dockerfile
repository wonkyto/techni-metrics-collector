FROM python:3.13-slim-bookworm AS base

RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y bash build-essential gcc libssl-dev libffi-dev python3-dev tzdata && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN cp /usr/share/zoneinfo/Australia/NSW /etc/localtime && \
    echo "Australia/NSW" > /etc/timezone

FROM base AS production
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && rm requirements.txt
COPY app /app
CMD [ "python", "./techni_metrics_collector.py" ]

FROM base AS dev
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt && rm requirements.txt requirements-dev.txt
