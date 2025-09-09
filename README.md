# LND Monitoring for Start9 Nodes

A modern Python-based monitoring solution that tracks the health of your Lightning Network Daemon (LND) node running on Start9 via .onion addresses and sends real-time notifications to Telegram. Built with async/await using the `python-telegram-bot` library for optimal performance and reliability.

## 🚀 Features

- **🔍 Real-time Monitoring**: Continuously monitors your Start9 LND node via Tor
- **📱 Modern Telegram Bot**: Built with `python-telegram-bot` v20+ for reliability
- **⚡ Async/Await Architecture**: High-performance async implementation
- **🧅 Tor Support**: Works seamlessly with .onion addresses via aiohttp
- **🐳 Docker Ready**: Easy deployment with Docker and Docker Compose
- **⚡ Smart Alerting**: Prevents false positives with intelligent state tracking
- **📊 Node Information**: Displays detailed node stats (alias, version, channels, sync status)
- **🔄 Auto-recovery Detection**: Notifies when node comes back online after outages
- **🤖 Interactive Bot Commands**: Rich command interface with authorization
- **⚡ Channel Management**: Monitor channel capacity, balances, and peer connections
- **💰 Balance Tracking**: View on-chain and Lightning balances in real-time
- **🌐 Peer Monitoring**: Track connected peers and sync status
- **💸 Fee Analytics**: Monitor routing performance and earnings
- **🔒 Security First**: Authorization middleware and readonly macaroon usage

## 📋 Prerequisites

- **Umbrel OS** or similar system with Docker support
- **Start9 LND Node** with .onion address
- **Telegram Bot** (created via @BotFather)
- **Tor** running on the monitoring system (port 9050)
- **Python 3.11+** (if running outside Docker)
- **Modern async libraries**: `python-telegram-bot` v20+, `aiohttp`, `aiohttp-socks`

## 🛠️ Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/lnd-monitoring.git
cd lnd-monitoring
```

### 2. Configure Environment Variables

Create a `.env` file with your configuration:

```bash
# Create .env file
touch .env
nano .env
```

Add the following variables:

```bash
# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# LND Node Configuration
LND_NODE_ONION_ADDRESS=your_node.onion
LND_MACAROON_RO=base64_encoded_readonly_macaroon
LND_NODE_PORT=8080

# Monitoring Configuration (optional)
CHECK_INTERVAL=120
TIMEOUT=30
MAX_RETRIES=3
```

### 3. Deploy with Docker Compose

```bash
docker-compose up -d
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from @BotFather | ✅ Yes | - |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID (get from @userinfobot) | ✅ Yes | - |
| `LND_NODE_ONION_ADDRESS` | Your Start9 LND node .onion address | ✅ Yes | - |
| `LND_MACAROON_RO` | Base64 encoded readonly macaroon | ✅ Yes | - |
| `LND_NODE_PORT` | LND REST API port | ❌ No | `8080` |
| `CHECK_INTERVAL` | Seconds between health checks | ❌ No | `120` |
| `TIMEOUT` | HTTP request timeout in seconds | ❌ No | `30` |
| `MAX_RETRIES` | Failed attempts before considering offline | ❌ No | `3` |
| `TOR_CHECK_URL` | URL to test Tor connectivity | ❌ No | `http://check.torproject.org/api/ip` |

### Getting Your Configuration Values

#### 1. Telegram Bot Setup

```bash
# 1. Message @BotFather on Telegram
# 2. Create new bot: /newbot
# 3. Get your bot token
# 4. Message @userinfobot to get your chat ID
```

#### 2. Start9 LND Configuration

```bash
# 1. Access your Start9 node dashboard
# 2. Go to LND service settings
# 3. Copy the .onion address
# 4. Export the readonly macaroon and convert to base64:
base64 -w 0 readonly.macaroon
```

#### 3. Python Dependencies (if running locally)

```bash
# Install required packages
pip install python-telegram-bot[all]>=20.7
pip install aiohttp>=3.9.0
pip install aiohttp-socks>=0.8.0

# Optional: For better async performance on Linux/macOS
pip install uvloop>=0.19.0
```

## 🐳 Docker Deployment

### Using Docker Compose (Recommended)

```yaml
services:
  lnd-monitor:
    build: .
    container_name: lnd-monitor
    restart: unless-stopped
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
      - LND_NODE_ONION_ADDRESS=${LND_NODE_ONION_ADDRESS}
      - LND_MACAROON_RO=${LND_MACAROON_RO}
      - LND_NODE_PORT=${LND_NODE_PORT:-8080}
      - CHECK_INTERVAL=${CHECK_INTERVAL:-120}
      - TIMEOUT=${TIMEOUT:-30}
      - MAX_RETRIES=${MAX_RETRIES:-3}
      - TOR_CHECK_URL=${TOR_CHECK_URL:-http://check.torproject.org/api/ip}
    volumes:
      - ./data:/data
```

### Manual Docker Build

```bash
# Build the image
docker build -t lnd-monitor .

# Run the container
docker run -d \
  --name lnd-monitor \
  --restart unless-stopped \
  --env-file .env \
  -v ./data:/data \
  lnd-monitor
```

## 🤖 Interactive Bot Commands

The modern bot implementation provides a rich command interface with authorization middleware and automatic command registration. All commands are secured and only respond to the authorized chat ID.

### Available Commands

| Command | Description | Example Output |
|---------|-------------|----------------|
| `/help` | Show available commands and bot info | Command list and features |
| `/info` | Get current node information | Node alias, version, sync status, peers |
| `/balance` | Get total node balance | On-chain + Lightning balances |
| `/channels` | Get channel overview | Active channels, capacity, top peers |
| `/peers` | Get peer connections | Connected peers, sync status |
| `/fees` | Get routing performance | 30-day earnings, routing events |

### Security Features

- **Authorization Middleware**: All commands check user permissions
- **Command Registration**: Bot commands appear in Telegram UI automatically
- **Error Handling**: Graceful error handling with user-friendly messages
- **Async Performance**: Non-blocking command processing

### Command Examples

#### `/info` - Node Information

```text
📊 Node Information

🟢 LND Node Online
📛 Alias: MyLightningNode
🔧 Version: 0.17.4-beta
📊 Block: 825431
⚡ Active channels: 12
🔗 Synced: Yes

🔍 Additional Details:
🆔 Public Key: 03abc123def456...
🌐 Network: mainnet
🔗 Peers: 8
📡 Pending Channels: 0
```

#### `/balance` - Complete Balance Overview

```text
💰 Total Node Balance

🔗 On-Chain Wallet:
✅ Confirmed: 1.50000000 BTC (150,000,000 sats)
⏳ Unconfirmed: 0 sats

⚡ Lightning Channels:
💡 Available: 500k sats (500,000)

💎 Total Balance:
🎯 1.50500000 BTC (150,500,000 sats)
```

#### `/channels` - Channel Overview

```text
⚡ Channel Overview

📊 Summary:
• Active Channels: 12
• Total Capacity: 50M sats (50,000,000)
• Local Balance: 25M sats (25,000,000)
• Remote Balance: 25M sats (25,000,000)

🟢 Online: 11 | 🔴 Offline: 1
⏳ Pending: 0

🔝 Top Channels:
• ACINQ (5M sats) 🟢
• Bitrefill (3M sats) 🟢
• WalletOfSatoshi (2M sats) 🔴
```

#### `/peers` - Peer Connections

```text
🌐 Peer Connections

📡 Status:
• Connected Peers: 8
• Sync Status: ✅ Synced

🔗 Connected Peers:
• 03abc123def456...onion 📤
• 02def789ghi012...onion 📥
• 01ghi345jkl678...onion 📤
• lightning.bitrefill.com 📥
```

#### `/fees` - Routing Performance

```text
💸 Fee Summary (30 days)

📈 Routing Performance:
• Total Earned: 1,250 sats
• Routing Events: 45
• Average Fee: 27 sats
• Total Volume: 2.5M sats (2,500,000)

📊 Recent Activity:
• 100k sats → 25 sats fee
• 50k sats → 15 sats fee
• 200k sats → 45 sats fee
```

## 📱 Telegram Notifications

The modern implementation uses the `python-telegram-bot` library for reliable message delivery with built-in retry logic and error handling:

### 🚀 Startup Message

```text
🚀 Start9 LND Monitor Started
🎯 Node: abc123...xyz789.onion
⏱️ Interval: 120s
📍 From: UmbrelOS via Tor
🔧 Proxy: socks5://127.0.0.1:9050

🤖 Interactive Bot Active!
Send /help for available commands
```

### ✅ Node Back Online

```text
✅ Start9 Node BACK ONLINE!
⏰ 15/12/2024 14:30:25

🟢 LND Node Online
📛 Alias: MyLightningNode
🔧 Version: 0.17.4-beta
📊 Block: 825431
⚡ Active channels: 12
🔗 Synced: Yes
```

### 🚨 Node Offline Alert

```text
🚨 START9 NODE OFFLINE!
⏰ 15/12/2024 14:25:15
❌ Last successful check: 14:23:42
🔄 Failed attempts: 3
```

### 🛑 Monitor Stopped

```text
🛑 Start9 LND Monitor stopped
```

## 🏗️ Architecture

### Modern Async Implementation

The monitor is built using modern Python async/await patterns for optimal performance:

- **`python-telegram-bot` v20+**: Latest async Telegram bot framework
- **`aiohttp`**: High-performance async HTTP client for LND API calls
- **`aiohttp-socks`**: Tor proxy support for .onion connections
- **Concurrent Operations**: Non-blocking monitoring and command handling
- **Graceful Error Handling**: Robust error recovery and logging

### Key Components

```python
# Main components of the async architecture
async def main():
    # Initialize bot application
    application = Application.builder().token(TOKEN).build()
    
    # Start monitoring loop in background
    monitoring_task = asyncio.create_task(monitoring_loop(application))
    
    # Start telegram bot polling
    await application.updater.start_polling()
```

### Dependencies

| Library | Purpose | Version |
|---------|---------|---------|
| `python-telegram-bot` | Modern Telegram bot framework | ≥20.7 |
| `aiohttp` | Async HTTP client for LND API | ≥3.9.0 |
| `aiohttp-socks` | Tor proxy support | ≥0.8.0 |
| `uvloop` | High-performance event loop (Linux/macOS) | ≥0.19.0 |

## 📊 Monitoring Logic

### Smart State Tracking

- **No False Positives**: Only sends "BACK ONLINE" after actual offline alerts
- **Configurable Retries**: Requires multiple consecutive failures before alerting
- **Intelligent Recovery**: Tracks actual outage vs temporary network issues
- **Async Monitoring**: Non-blocking health checks don't interfere with bot commands

### Check Sequence

1. **Health Check**: Calls LND's `/v1/getinfo` endpoint via Tor (async)
2. **Failure Tracking**: Counts consecutive failed attempts
3. **Offline Alert**: Sends alert after `MAX_RETRIES` failures
4. **Recovery Detection**: Notifies when node comes back online
5. **Periodic Logging**: Logs status every 30 minutes when healthy
6. **Command Processing**: Handles Telegram commands concurrently

## 🔧 Troubleshooting

### Common Issues

#### Tor Connection Failed

```bash
# Check if Tor is running
sudo systemctl status tor

# Start Tor if not running
sudo systemctl start tor

# Install Tor if missing
sudo apt update && sudo apt install tor
```

#### Invalid Macaroon Error

```bash
# Verify macaroon is base64 encoded
echo "your_macaroon_here" | base64 -d | hexdump -C

# Re-export from Start9 dashboard
# Make sure to use readonly macaroon
```

#### Bot Authorization Issues

```bash
# Check if bot token is valid
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe"

# Verify chat ID is correct
# Message @userinfobot on Telegram to get your chat ID

# Check bot logs for authorization errors
docker logs lnd-monitor | grep -i "unauthorized"
```

#### Async/Await Issues

```bash
# If running locally, ensure Python 3.11+
python3 --version

# Install all async dependencies
pip install python-telegram-bot[all]>=20.7
pip install aiohttp>=3.9.0 aiohttp-socks>=0.8.0

# For better performance on Linux/macOS
pip install uvloop>=0.19.0
```

### Logs and Debugging

```bash
# View container logs
docker logs lnd-monitor

# Follow logs in real-time
docker logs -f lnd-monitor

# Check log files
tail -f data/lnd_monitor.log
```

## 🔒 Security Considerations

- **Readonly Macaroon**: Uses only readonly permissions for LND access
- **Environment Variables**: Sensitive data stored in `.env` file (not committed)
- **Tor Proxy**: All LND communication goes through Tor for privacy
- **No Data Storage**: Only logs operational status, no sensitive node data
- **Authorization Middleware**: Decorator-based command authorization
- **Chat ID Verification**: Bot only responds to authorized Telegram chat ID
- **SSL Verification**: Disabled only for .onion connections (required for Tor)
- **Input Validation**: All user inputs are validated and sanitized
- **Error Handling**: Sensitive information is never leaked in error messages

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚡ Support

If you find this project helpful, consider:

- ⭐ Starring the repository
- 🐛 Reporting issues
- 💡 Suggesting improvements
- ☕ [Buying me a coffee](https://lightning.network)

## 🙏 Acknowledgments

- **Start9** for making self-sovereign Bitcoin infrastructure accessible
- **Lightning Network** community for the amazing technology
- **Umbrel** for the excellent node management platform
- **python-telegram-bot** team for the excellent async Telegram bot framework
- **aiohttp** developers for the high-performance async HTTP library

---

**⚡ Keep your Lightning Node healthy! ⚡**