FROM python:3.9-buster

RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y bash build-essential gcc git libssl-dev libffi-dev python-dev tzdata

WORKDIR /app

# Change the timezone (required for localtime when logging)
RUN cp /usr/share/zoneinfo/Australia/NSW /etc/localtime
RUN echo "Australia/NSW" > /etc/timezone

ENV CRYPTOGRAPHY_DONT_BUILD_RUST=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN rm requirements.txt

COPY app /app

CMD [ "python", "./techni-metrics-collector.py" ]
