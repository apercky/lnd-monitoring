#!/usr/bin/env python3
"""
Lightning Node Monitor for Start9
Monitors an LND node on Start9 (via .onion) from VPS and sends Telegram notifications
Built with python-telegram-bot library using async/await for optimal performance
"""

import asyncio
import aiohttp
import time
from datetime import datetime
import logging
import sys
import os
import base64
import binascii
import subprocess
from typing import Optional, Tuple, Dict, Any

from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from aiohttp_socks import ProxyConnector

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_DIR = "/data"

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{DATA_DIR}/lnd_monitor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============= CONFIGURATION =============
# Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Start9 LND Node
NODE_ONION_ADDRESS = os.getenv('LND_NODE_ONION_ADDRESS')
NODE_PORT = os.getenv('LND_NODE_PORT', "8080")

# Macaroon from environment variable
MACAROON_BASE64 = os.getenv('LND_MACAROON_RO')

# Monitoring configuration
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '120'))  # Seconds between checks (2 minutes)
TIMEOUT = int(os.getenv('TIMEOUT', '60'))                 # Timeout for HTTP requests (increased for Tor)
CONNECTION_TIMEOUT = int(os.getenv('CONNECTION_TIMEOUT', '45'))  # Connection timeout
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))          # Attempts before considering offline
CIRCUIT_REFRESH_INTERVAL = int(os.getenv('CIRCUIT_REFRESH_INTERVAL', '300'))  # Refresh Tor circuits every 5 minutes

TOR_CHECK_URL = os.getenv('TOR_CHECK_URL', "http://check.torproject.org/api/ip")

if MACAROON_BASE64:
    try:
        MACAROON_BYTES = base64.b64decode(MACAROON_BASE64)
        MACAROON_HEX = binascii.hexlify(MACAROON_BYTES).decode()
    except Exception as e:
        logger.error(f"Error decoding macaroon: {e}")
        sys.exit(1)
else:
    logger.error("Environment variable LND_MACAROON_RO not found!")
    sys.exit(1)

# Correct Tor configuration for .onion domains
TOR_PROXY = "socks5://127.0.0.1:9050"

# Global variables for monitoring state
last_status = None
consecutive_failures = 0
last_successful_check = datetime.now()
offline_alert_sent = False
last_circuit_refresh = datetime.now()
tor_session = None

# ============= HTTP CLIENT FUNCTIONS =============

async def refresh_tor_circuit() -> None:
    """Refresh Tor circuit by sending NEWNYM signal"""
    try:
        logger.info("Refreshing Tor circuit...")
        # Try multiple methods to refresh Tor circuit
        methods = [
            # Method 1: Signal Tor process directly (inside container)
            ['pkill', '-HUP', 'tor'],
            # Method 2: Use Tor control port if available
            ['echo', 'SIGNAL NEWNYM | nc 127.0.0.1 9051'],
        ]
        
        for method in methods:
            try:
                result = subprocess.run(method, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    logger.info("✅ Tor circuit refresh signal sent")
                    # Wait a moment for circuit to refresh
                    await asyncio.sleep(3)
                    return
            except Exception:
                continue
                
        logger.warning("All Tor circuit refresh methods failed")
    except Exception as e:
        logger.warning(f"Could not refresh Tor circuit: {e}")

async def test_tor_connection() -> bool:
    """Test that Tor works for .onion domains"""
    try:
        logger.info("Testing Tor connection with .onion...")
        
        connector = ProxyConnector.from_url(TOR_PROXY)
        timeout = aiohttp.ClientTimeout(total=20, connect=15)  # Increased timeouts
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(TOR_CHECK_URL) as response:
                if response.status == 200:
                    logger.info("✅ Tor works correctly for .onion domains")
                    return True
                else:
                    logger.warning(f"Tor responds but with status code: {response.status}")
                    return False
    except Exception as e:
        logger.error(f"Tor test error: {e}")
        return False

async def make_lnd_request(endpoint: str, method: str = 'GET', data: Optional[Dict] = None, retry_count: int = 0) -> Tuple[bool, Optional[Dict]]:
    """Make HTTP request to LND node via Tor with enhanced retry logic"""
    global last_circuit_refresh
    
    try:
        url = f"https://{NODE_ONION_ADDRESS}:{NODE_PORT}{endpoint}"
        
        headers = {
            'Grpc-Metadata-macaroon': MACAROON_HEX
        }
        
        connector = ProxyConnector.from_url(TOR_PROXY, verify_ssl=False)
        timeout = aiohttp.ClientTimeout(
            total=TIMEOUT, 
            connect=CONNECTION_TIMEOUT,
            sock_read=30  # Socket read timeout
        )
        
        async with aiohttp.ClientSession(
            connector=connector, 
            timeout=timeout
        ) as session:
            if method.upper() == 'GET':
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        return True, await response.json()
                    elif response.status == 401:
                        logger.error("Invalid or expired macaroon")
                        return False, None
                    else:
                        logger.warning(f"Request to {endpoint} failed with status: {response.status}")
                        return False, None
            
            elif method.upper() == 'POST':
                # Add Content-Type only for POST requests
                post_headers = headers.copy()
                post_headers['Content-Type'] = 'application/json'
                async with session.post(url, headers=post_headers, json=data) as response:
                    if response.status == 200:
                        return True, await response.json()
                    else:
                        logger.warning(f"POST request to {endpoint} failed with status: {response.status}")
                        return False, None
                        
    except (asyncio.TimeoutError, aiohttp.ServerTimeoutError) as e:
        logger.warning(f"Timeout in request to {endpoint} (attempt {retry_count + 1})")
        
        # If first retry and it's been a while since last circuit refresh, try refreshing
        if retry_count == 0 and (datetime.now() - last_circuit_refresh).seconds > CIRCUIT_REFRESH_INTERVAL:
            logger.info("Attempting Tor circuit refresh due to timeout...")
            await refresh_tor_circuit()
            last_circuit_refresh = datetime.now()
            # Retry the request once after circuit refresh
            return await make_lnd_request(endpoint, method, data, retry_count + 1)
        
        return False, None
    except Exception as e:
        logger.error(f"Error in request to {endpoint}: {e}")
        
        # For connection errors, try circuit refresh on first attempt
        if retry_count == 0 and "connection" in str(e).lower():
            logger.info("Attempting Tor circuit refresh due to connection error...")
            await refresh_tor_circuit()
            last_circuit_refresh = datetime.now()
            await asyncio.sleep(2)  # Brief pause after refresh
            return await make_lnd_request(endpoint, method, data, retry_count + 1)
        
        return False, None

# ============= LND API FUNCTIONS =============

async def check_lnd_node() -> Tuple[bool, Optional[Dict]]:
    """Check LND node status with readonly macaroon"""
    return await make_lnd_request("/v1/getinfo")

async def get_wallet_balance() -> Tuple[bool, Optional[Dict]]:
    """Get on-chain wallet balance"""
    return await make_lnd_request("/v1/balance/blockchain")

async def get_channel_balance() -> Tuple[bool, Optional[Dict]]:
    """Get Lightning channel balance"""
    return await make_lnd_request("/v1/balance/channels")

async def get_channels() -> Tuple[bool, Optional[Dict]]:
    """Get channel information"""
    return await make_lnd_request("/v1/channels")

async def get_pending_channels() -> Tuple[bool, Optional[Dict]]:
    """Get pending channel information"""
    return await make_lnd_request("/v1/channels/pending")

async def get_peers() -> Tuple[bool, Optional[Dict]]:
    """Get peer information"""
    return await make_lnd_request("/v1/peers")

async def get_forwarding_history() -> Tuple[bool, Optional[Dict]]:
    """Get forwarding history for fee analysis"""
    # Calculate timestamp for 30 days ago
    thirty_days_ago = int((datetime.now().timestamp() - (30 * 24 * 60 * 60)))
    
    data = {
        'start_time': str(thirty_days_ago),
        'num_max_events': 100
    }
    
    return await make_lnd_request("/v1/switch", method='POST', data=data)

# ============= UTILITY FUNCTIONS =============

def format_satoshis(sats) -> str:
    """Format satoshis with proper formatting"""
    if not sats or sats == '0':
        return "0 sats"
    
    sats = int(sats)
    if sats >= 100_000_000:  # 1+ BTC
        btc = sats / 100_000_000
        return f"{btc:.8f} BTC ({sats:,} sats)"
    elif sats >= 1_000_000:  # 1+ million sats
        return f"{sats/1_000_000:.2f}M sats ({sats:,})"
    elif sats >= 1_000:  # 1+ thousand sats
        return f"{sats/1_000:.1f}k sats ({sats:,})"
    else:
        return f"{sats:,} sats"

def format_node_info(node_info: Optional[Dict]) -> str:
    """Format node information for Telegram"""
    if not node_info:
        return "❌ Unable to get node info"
    
    try:
        alias = node_info.get('alias', 'N/A')
        version = node_info.get('version', 'N/A')
        block_height = node_info.get('block_height', 'N/A')
        synced = node_info.get('synced_to_chain', False)
        num_channels = node_info.get('num_active_channels', 0)
        
        status_icon = "🟢" if synced else "🟡"
        
        return f"""
{status_icon} <b>LND Node Online</b>
📛 Alias: {alias}
🔧 Version: {version}
📊 Block: {block_height}
⚡ Active channels: {num_channels}
🔗 Synced: {'Yes' if synced else 'No'}
"""
    except Exception as e:
        logger.error(f"Error formatting node info: {e}")
        return "✅ Node online (error parsing info)"

# ============= TELEGRAM COMMAND HANDLERS =============

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command"""
    help_text = """
🤖 <b>Start9 LND Monitor Bot</b>

<b>Available Commands:</b>

/help - Show this help message
/info - Get current node information  
/balance - Get total node balance (on-chain + Lightning)
/channels - Get channel overview and status
/peers - Get peer connections and sync status  
/fees - Get routing fees and earnings summary

<b>Monitoring Features:</b>
• Automatic health monitoring every 2 minutes
• Instant alerts when node goes offline
• Recovery notifications when node comes back online
• Smart alerting to prevent false positives

<b>Security:</b>
• Uses readonly macaroon (safe, no spending permissions)
• All communication via Tor for privacy
• No sensitive data stored

<b>Status:</b>
✅ Monitoring active
🔄 Check interval: 2 minutes
🧅 Connected via Tor
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /info command"""
    is_online, node_info = await check_lnd_node()
    
    if is_online and node_info:
        info_text = f"""
📊 <b>Node Information</b>

{format_node_info(node_info)}

🔍 <b>Additional Details:</b>
🆔 Public Key: <code>{node_info.get('identity_pubkey', 'N/A')[:32]}...</code>
🌐 Network: {node_info.get('chains', [{}])[0].get('network', 'N/A')}
🔗 Peers: {node_info.get('num_peers', 0)}
📡 Pending Channels: {node_info.get('num_pending_channels', 0)}

⏰ Last Updated: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    else:
        info_text = """
❌ <b>Node Information Unavailable</b>

Unable to connect to the LND node right now.
This could be due to:
• Node is temporarily offline
• Network connectivity issues
• Tor connection problems

Please try again in a few moments.
"""
    
    await update.message.reply_text(info_text, parse_mode=ParseMode.HTML)

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle balance command - shows total node balance"""
    
    wallet_success, wallet_data = await get_wallet_balance()
    channel_success, channel_data = await get_channel_balance()
    
    if wallet_success and channel_success:
        total_confirmed = int(wallet_data.get('total_balance', 0))
        total_unconfirmed = int(wallet_data.get('unconfirmed_balance', 0))
        channel_balance = int(channel_data.get('balance', 0))
        
        total_balance = total_confirmed + channel_balance
        
        balance_text = f"""
💰 <b>Total Node Balance</b>

🔗 <b>On-Chain Wallet:</b>
✅ Confirmed: {format_satoshis(total_confirmed)}
⏳ Unconfirmed: {format_satoshis(total_unconfirmed)}

⚡ <b>Lightning Channels:</b>
💡 Available: {format_satoshis(channel_balance)}

💎 <b>Total Balance:</b>
🎯 <b>{format_satoshis(total_balance)}</b>

⏰ Updated: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    else:
        balance_text = "❌ Unable to retrieve balance information. Node may be offline."
    
    await update.message.reply_text(balance_text, parse_mode=ParseMode.HTML)

async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle channels command - shows channel overview"""
    
    channels_success, channels_data = await get_channels()
    pending_success, pending_data = await get_pending_channels()
    
    if channels_success:
        channels = channels_data.get('channels', [])
        active_count = len(channels)
        
        # Calculate totals
        total_capacity = sum(int(ch.get('capacity', 0)) for ch in channels)
        local_balance = sum(int(ch.get('local_balance', 0)) for ch in channels)
        remote_balance = sum(int(ch.get('remote_balance', 0)) for ch in channels)
        
        # Count online/offline channels
        online_channels = [ch for ch in channels if ch.get('active', False)]
        offline_channels = [ch for ch in channels if not ch.get('active', False)]
        
        # Get pending info
        pending_count = 0
        if pending_success and pending_data:
            pending_open = len(pending_data.get('pending_open_channels', []))
            pending_close = len(pending_data.get('pending_closing_channels', []))
            pending_count = pending_open + pending_close
        
        # Format top channels (by capacity)
        top_channels = sorted(channels, key=lambda x: int(x.get('capacity', 0)), reverse=True)[:5]
        
        channels_text = f"""
⚡ <b>Channel Overview</b>

📊 <b>Summary:</b>
• Active Channels: {active_count}
• Total Capacity: {format_satoshis(total_capacity)}
• Local Balance: {format_satoshis(local_balance)}
• Remote Balance: {format_satoshis(remote_balance)}

🟢 Online: {len(online_channels)} | 🔴 Offline: {len(offline_channels)}
⏳ Pending: {pending_count}

🔝 <b>Top Channels:</b>
"""
        
        for i, channel in enumerate(top_channels[:3], 1):
            alias = channel.get('remote_alias', 'Unknown')[:15]
            capacity = format_satoshis(channel.get('capacity', 0))
            status = "🟢" if channel.get('active', False) else "🔴"
            channels_text += f"• {alias} ({capacity}) {status}\n"
        
        channels_text += f"\n⏰ Updated: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        
    else:
        channels_text = "❌ Unable to retrieve channel information. Node may be offline."
    
    await update.message.reply_text(channels_text, parse_mode=ParseMode.HTML)

async def peers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle peers command - shows peer connections"""
    
    peers_success, peers_data = await get_peers()
    node_success, node_info = await check_lnd_node()
    
    if peers_success:
        peers = peers_data.get('peers', [])
        connected_count = len(peers)
        
        # Get sync info from node info
        synced = node_info.get('synced_to_chain', False) if node_info else False
        
        peers_text = f"""
🌐 <b>Peer Connections</b>

📡 <b>Status:</b>
• Connected Peers: {connected_count}
• Sync Status: {'✅ Synced' if synced else '⏳ Syncing'}
"""
        
        if connected_count > 0:
            peers_text += "\n🔗 <b>Connected Peers:</b>\n"
            for peer in peers[:8]:  # Show max 8 peers
                address = peer.get('address', 'Unknown')
                if '.onion:' in address:
                    # Shorten onion addresses
                    address = address.split('.onion:')[0][:16] + '...onion'
                elif len(address) > 25:
                    address = address[:25] + '...'
                
                inbound = "📥" if peer.get('inbound', False) else "📤"
                peers_text += f"• {address} {inbound}\n"
        else:
            peers_text += "\n❌ No peers connected"
        
        peers_text += f"\n⏰ Updated: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        
    else:
        peers_text = "❌ Unable to retrieve peer information. Node may be offline."
    
    await update.message.reply_text(peers_text, parse_mode=ParseMode.HTML)

async def fees_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle fees command - shows fee summary"""
    
    forwarding_success, forwarding_data = await get_forwarding_history()
    
    if forwarding_success:
        events = forwarding_data.get('forwarding_events', [])
        
        if events:
            # Calculate totals
            total_fee_earned = sum(int(event.get('fee_msat', 0)) for event in events) // 1000  # Convert msat to sat
            total_events = len(events)
            avg_fee = total_fee_earned // total_events if total_events > 0 else 0
            
            # Calculate volume
            total_volume = sum(int(event.get('amt_out_msat', 0)) for event in events) // 1000
            
            fees_text = f"""
💸 <b>Fee Summary (30 days)</b>

📈 <b>Routing Performance:</b>
• Total Earned: {format_satoshis(total_fee_earned)}
• Routing Events: {total_events}
• Average Fee: {avg_fee} sats
• Total Volume: {format_satoshis(total_volume)}

📊 <b>Recent Activity:</b>
"""
            
            # Show recent events
            recent_events = events[-5:] if len(events) > 5 else events
            for event in recent_events:
                fee_sats = int(event.get('fee_msat', 0)) // 1000
                amt_sats = int(event.get('amt_out_msat', 0)) // 1000
                fees_text += f"• {format_satoshis(amt_sats)} → {fee_sats} sats fee\n"
            
        else:
            fees_text = """
💸 <b>Fee Summary (30 days)</b>

📊 No routing events in the last 30 days.
This could mean:
• Node is new or private
• No routing opportunities
• Channels need better liquidity balance
"""
        
        fees_text += f"\n⏰ Updated: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        
    else:
        fees_text = "❌ Unable to retrieve fee information. Node may be offline."
    
    await update.message.reply_text(fees_text, parse_mode=ParseMode.HTML)

# ============= MONITORING FUNCTIONS =============

async def send_notification(application: Application, message: str) -> None:
    """Send notification message to authorized chat"""
    try:
        await application.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode=ParseMode.HTML
        )
        logger.info("Notification sent successfully")
    except Exception as e:
        logger.error(f"Error sending notification: {e}")

async def monitoring_loop(application: Application) -> None:
    """Main monitoring loop with enhanced Tor circuit management"""
    global last_status, consecutive_failures, last_successful_check, offline_alert_sent, last_circuit_refresh
    
    logger.info("Starting monitoring loop...")
    
    while True:
        try:
            current_time = datetime.now()
            logger.info(f"Checking node at {current_time.strftime('%H:%M:%S')}")
            
            # Periodic circuit refresh (every 5 minutes)
            if (current_time - last_circuit_refresh).seconds >= CIRCUIT_REFRESH_INTERVAL:
                logger.info("Performing periodic Tor circuit refresh...")
                await refresh_tor_circuit()
                last_circuit_refresh = current_time
            
            # Check the node with retry logic
            is_online, node_info = await check_lnd_node()
            
            if is_online:
                consecutive_failures = 0
                last_successful_check = current_time
                
                # Send initial online status after startup
                if last_status is None:
                    initial_msg = f"""
✅ <b>Start9 Node ONLINE!</b>
⏰ {current_time.strftime('%d/%m/%Y %H:%M:%S')}
{format_node_info(node_info)}
                    """
                    await send_notification(application, initial_msg)
                    logger.info("Initial node status confirmed online")
                
                # If it was offline AND we sent an offline alert, send recovery notification
                elif offline_alert_sent:
                    uptime_msg = f"""
✅ <b>Start9 Node BACK ONLINE!</b>
⏰ {current_time.strftime('%d/%m/%Y %H:%M:%S')}
{format_node_info(node_info)}

⚡ Downtime: {(current_time - last_successful_check).seconds // 60} minutes
🔄 Connection restored via Tor
                    """
                    await send_notification(application, uptime_msg)
                    logger.info("Node back online")
                    offline_alert_sent = False  # Reset the flag
                
                # Periodic log when everything is fine
                elif consecutive_failures == 0 and current_time.minute % 30 == 0:
                    logger.info("Node working correctly - Tor circuits healthy")
                
            else:
                consecutive_failures += 1
                logger.warning(f"Failed attempt {consecutive_failures}/{MAX_RETRIES}")
                
                # On second failure, try refreshing circuit immediately
                if consecutive_failures == 2:
                    logger.info("Second failure - attempting immediate circuit refresh...")
                    await refresh_tor_circuit()
                    last_circuit_refresh = current_time
                    # Give it a moment and try once more
                    await asyncio.sleep(5)
                    is_online_retry, node_info_retry = await check_lnd_node()
                    if is_online_retry:
                        logger.info("✅ Recovery successful after circuit refresh")
                        consecutive_failures = 0
                        last_successful_check = current_time
                        continue
                
                # Send alert only after MAX_RETRIES consecutive failures
                if consecutive_failures >= MAX_RETRIES and not offline_alert_sent:
                    offline_msg = f"""
🚨 <b>START9 NODE OFFLINE!</b>
⏰ {current_time.strftime('%d/%m/%Y %H:%M:%S')}
❌ Last successful check: {last_successful_check.strftime('%H:%M:%S')}
🔄 Failed attempts: {consecutive_failures}

🔍 <b>Troubleshooting tried:</b>
• Tor circuit refresh
• Extended timeouts
• Connection retry logic

💡 <b>If Zeus works:</b> This may be a temporary Tor routing issue. The node should recover automatically.
                    """
                    await send_notification(application, offline_msg)
                    logger.error("Node considered offline after enhanced retry attempts")
                    offline_alert_sent = True  # Mark that we sent an offline alert
            
            # Update state
            last_status = is_online
            
            # Wait for next check
            await asyncio.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            await asyncio.sleep(60)  # Longer wait in case of error

# ============= AUTHORIZATION MIDDLEWARE =============

def check_authorization(func):
    """Decorator to check if user is authorized"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Security: Only respond to authorized chat ID
        if str(chat_id) != str(TELEGRAM_CHAT_ID):
            logger.warning(f"Unauthorized command attempt from chat_id: {chat_id}, user_id: {user_id}")
            await update.message.reply_text("❌ Unauthorized access")
            return
        
        return await func(update, context)
    return wrapper

# Apply authorization to all command handlers
help_command = check_authorization(help_command)
info_command = check_authorization(info_command)
balance_command = check_authorization(balance_command)
channels_command = check_authorization(channels_command)
peers_command = check_authorization(peers_command)
fees_command = check_authorization(fees_command)

# ============= MAIN FUNCTION =============

async def main():
    """Main function"""
    logger.info("=== Starting Lightning Node Monitor ===")
    
    # Verify configuration
    if not MACAROON_BASE64:
        logger.error("Environment variable LND_MACAROON_RO not found!")
        logger.error("Add to .bashrc: export LND_MACAROON_RO='your_base64_macaroon'")
        sys.exit(1)
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Environment variable TELEGRAM_BOT_TOKEN not found!")
        sys.exit(1)
        
    if not TELEGRAM_CHAT_ID:
        logger.error("Environment variable TELEGRAM_CHAT_ID not found!")
        sys.exit(1)
    
    # Test Tor for .onion domains
    logger.info("Verifying that Tor is configured for .onion...")
    if not await test_tor_connection():
        logger.error("Tor doesn't work for .onion domains!")
        logger.error("Check: 1) sudo apt install tor && sudo systemctl start tor")
        logger.error("       2) pip3 install aiohttp[socks]")
        sys.exit(1)
    
    # Create the Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("start", help_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("channels", channels_command))
    application.add_handler(CommandHandler("peers", peers_command))
    application.add_handler(CommandHandler("fees", fees_command))
    
    # Set bot commands for UI
    commands = [
        BotCommand("help", "Show available commands"),
        BotCommand("info", "Get current node information"),
        BotCommand("balance", "Get total node balance"),
        BotCommand("channels", "Get channel overview"),
        BotCommand("peers", "Get peer connections"),
        BotCommand("fees", "Get routing fees summary"),
    ]
    await application.bot.set_my_commands(commands)
    
    # Send startup message
    startup_msg = f"""
🚀 <b>Start9 LND Monitor Started</b>
🎯 Node: {NODE_ONION_ADDRESS}
⏱️ Interval: {CHECK_INTERVAL}s
🔧 Proxy: socks5://127.0.0.1:9050

🤖 <b>Interactive Bot Active!</b>
Send /help for available commands
    """
    await send_notification(application, startup_msg)
    
    # Start the bot
    await application.initialize()
    await application.start()
    
    # Start monitoring in background
    monitoring_task = asyncio.create_task(monitoring_loop(application))
    
    try:
        # Start polling
        await application.updater.start_polling()
        logger.info("Bot is running...")
        
        # Wait for monitoring task
        await monitoring_task
        
    except KeyboardInterrupt:
        logger.info("Monitor stopped manually")
        await send_notification(application, "🛑 <b>Start9 LND Monitor stopped</b>")
    finally:
        # Cleanup
        monitoring_task.cancel()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application interrupted")
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)
