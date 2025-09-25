FROM python:3.11-slim

# Install Tor and system dependencies
RUN apt-get update && apt-get install -y tor && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application file
COPY lnd_monitor.py .

# Volume for logs
VOLUME /data

# Environment variables
ENV LND_NODE_ONION_ADDRESS=""
ENV LND_MACAROON_RO=""
ENV LND_NODE_PORT="8080"
ENV TELEGRAM_BOT_TOKEN=""
ENV TELEGRAM_CHAT_ID=""
ENV CHECK_INTERVAL="120"
ENV TIMEOUT="60"
ENV CONNECTION_TIMEOUT="45"
ENV MAX_RETRIES="3"
ENV CIRCUIT_REFRESH_INTERVAL="300"
ENV LOG_RETENTION_DAYS="7"
ENV LOG_MAX_SIZE_MB="10"
ENV TOR_CHECK_URL="http://check.torproject.org/api/ip"

# Fix Tor permissions - simple solution
RUN chown -R root:root /var/lib/tor

# Start Tor and the monitor script
CMD tor & sleep 10 && python /app/lnd_monitor.py