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
ENV TOR_CHECK_URL="http://check.torproject.org/api/ip"

# Create Tor configuration for better circuit management
RUN echo "ControlPort 9051" >> /etc/tor/torrc && \
    echo "CookieAuthentication 1" >> /etc/tor/torrc && \
    echo "DataDirectory /var/lib/tor" >> /etc/tor/torrc

# Start Tor and the monitor script
CMD tor & sleep 10 && python /app/lnd_monitor.py