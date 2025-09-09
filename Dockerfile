FROM python:3.11-slim

# Install Tor and system dependencies
RUN apt-get update && apt-get install -y tor && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY lnd_monitor.py .
COPY lnd_monitor_ptb.py .

# Volume for logs
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

# Environment variable to choose which version to run
# Set to "ptb" for python-telegram-bot version, "original" for requests version
ENV MONITOR_VERSION="ptb"

# Start Tor and the appropriate monitor script
CMD tor & sleep 5 && \
    if [ "$MONITOR_VERSION" = "ptb" ]; then \
        python /app/lnd_monitor_ptb.py; \
    else \
        python /app/lnd_monitor.py; \
    fi