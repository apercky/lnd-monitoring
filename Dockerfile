FROM python:3.11-slim

# installo Tor + requests con socks
RUN apt-get update && apt-get install -y tor && rm -rf /var/lib/apt/lists/*
RUN pip install requests[socks]

WORKDIR /app
COPY lnd_monitor.py .

# volume per i log
VOLUME /data

# Environment variables
ENV LND_NODE_ONION_ADDRESS=""
ENV LND_MACAROON_RO=""
ENV LND_NODE_PORT="8080"
ENV TELEGRAM_BOT_TOKEN=""
ENV TELEGRAM_CHAT_ID=""
ENV CHECK_INTERVAL="120"
ENV TIMEOUT="30"
ENV MAX_RETRIES="3"
ENV TOR_CHECK_URL="http://check.torproject.org/api/ip"

# avvio tor + lo script
CMD tor & sleep 5 && python /app/lnd_monitor.py