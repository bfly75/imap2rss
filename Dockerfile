FROM debian:unstable-slim

MAINTAINER Bodo Fly <docker-hub@b-fly.nl>

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -q -y --no-install-recommends python3-minimal procps less nano && \
    apt-get install -q -y --no-install-recommends build-essential python3-pip python3-setuptools \
      python3-wheel python3-dev && \
    python3 -m pip install beautifulsoup4 python-dateutil lxml feedgen Flask toml && \
    apt-get purge -q -y build-essential python3-pip python3-setuptools \
      python3-wheel python3-dev && \
    apt-get autoremove -q -y && \
    rm /etc/localtime && \
    if [ -z ${TIMEZONE} ]; then TIMEZONE="Etc/UTC"; fi && \
    ln -s /usr/share/zoneinfo/$TIMEZONE /etc/localtime

COPY config.toml main.py entrypoint.sh LICENSE /app/

ENTRYPOINT ["/app/entrypoint.sh"]
