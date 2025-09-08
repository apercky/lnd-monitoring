#!/usr/bin/env python3
"""
Lightning Node Monitor for Start9
Monitors an LND node on Start9 (via .onion) from Umbrel and sends Telegram notifications
"""

import requests
import time
from datetime import datetime
import logging
import sys
import os
import base64
import binascii
import threading
import json

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
TIMEOUT = int(os.getenv('TIMEOUT', '30'))                 # Timeout for HTTP requests
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))          # Attempts before considering offline

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
TOR_PROXY = {
    'http': 'socks5h://127.0.0.1:9050',
    'https': 'socks5h://127.0.0.1:9050'
}

# ============= FUNCTIONS =============

def test_tor_connection():
    """Test that Tor works for .onion domains"""
    try:
        logger.info("Testing Tor connection with .onion...")
        # Test with a known .onion site
        response = requests.get(
            TOR_CHECK_URL,
            proxies=TOR_PROXY,
            timeout=15
        )
        if response.status_code == 200:
            logger.info("✅ Tor works correctly for .onion domains")
            return True
        else:
            logger.warning(f"Tor responds but with status code: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Tor test error: {e}")
        return False

def send_telegram_message(message, chat_id=None):
    """Send Telegram message"""
    try:
        target_chat_id = chat_id or TELEGRAM_CHAT_ID
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": target_chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=data, timeout=10)
        if response.status_code == 200:
            logger.info("Telegram message sent successfully")
            return True
        else:
            logger.error(f"Telegram sending error: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Telegram sending error: {e}")
        return False

def get_telegram_updates(offset=0):
    """Get updates from Telegram bot"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        params = {
            "offset": offset,
            "timeout": 10
        }
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Error getting Telegram updates: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error getting Telegram updates: {e}")
        return None

def handle_help_command(chat_id):
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
    send_telegram_message(help_text, chat_id)

def handle_info_command(chat_id):
    """Handle /info command"""
    is_online, node_info = check_lnd_node()
    
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
    
    send_telegram_message(info_text, chat_id)

def handle_balance_command(chat_id):
    """Handle balance command - shows total node balance"""
    
    wallet_success, wallet_data = get_wallet_balance()
    channel_success, channel_data = get_channel_balance()
    
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
    
    send_telegram_message(balance_text, chat_id)

def handle_channels_command(chat_id):
    """Handle channels command - shows channel overview"""
    
    channels_success, channels_data = get_channels()
    pending_success, pending_data = get_pending_channels()
    
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
    
    send_telegram_message(channels_text, chat_id)

def handle_peers_command(chat_id):
    """Handle peers command - shows peer connections"""
    
    peers_success, peers_data = get_peers()
    node_success, node_info = check_lnd_node()
    
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
    
    send_telegram_message(peers_text, chat_id)

def handle_fees_command(chat_id):
    """Handle fees command - shows fee summary"""
    
    forwarding_success, forwarding_data = get_forwarding_history()
    
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
    
    send_telegram_message(fees_text, chat_id)

def clear_old_telegram_messages():
    """Clear old Telegram messages to prevent spam on startup"""
    try:
        logger.info("Clearing old Telegram messages...")
        updates = get_telegram_updates(0)
        
        if updates and updates.get('ok') and updates.get('result'):
            if updates['result']:
                # Get the highest update_id to skip all old messages
                highest_id = max(update['update_id'] for update in updates['result'])
                # Mark all as read by calling getUpdates with offset = highest_id + 1
                get_telegram_updates(highest_id + 1)
                logger.info(f"Cleared {len(updates['result'])} old messages")
            else:
                logger.info("No old messages to clear")
        
    except Exception as e:
        logger.error(f"Error clearing old messages: {e}")

def process_telegram_commands():
    """Process incoming Telegram commands"""
    # Clear old messages first to prevent spam
    clear_old_telegram_messages()
    
    last_update_id = 0
    logger.info("Telegram command processor ready")
    
    while True:
        try:
            updates = get_telegram_updates(last_update_id + 1)
            
            if updates and updates.get('ok') and updates.get('result'):
                for update in updates['result']:
                    last_update_id = update['update_id']
                    
                    if 'message' in update:
                        message = update['message']
                        chat_id = message['chat']['id']
                        
                        # Security: Only respond to authorized chat ID
                        if str(chat_id) != str(TELEGRAM_CHAT_ID):
                            logger.warning(f"Unauthorized command attempt from chat_id: {chat_id}")
                            continue
                        
                        if 'text' in message:
                            text = message['text'].lower().strip()
                            logger.info(f"Received command: {text}")
                            
                            if text == '/help' or text == '/start':
                                handle_help_command(chat_id)
                            elif text == '/info':
                                handle_info_command(chat_id)
                            elif text == '/balance':
                                handle_balance_command(chat_id)
                            elif text == '/channels':
                                handle_channels_command(chat_id)
                            elif text == '/peers':
                                handle_peers_command(chat_id)
                            elif text == '/fees':
                                handle_fees_command(chat_id)
                            elif text.startswith('/'):
                                # Only respond to unknown commands that start with /
                                send_telegram_message("❓ Unknown command. Send /help for available commands.", chat_id)
                            # Ignore non-command messages
            
            time.sleep(2)  # Poll every 2 seconds
            
        except Exception as e:
            logger.error(f"Error processing Telegram commands: {e}")
            time.sleep(10)  # Wait longer on error

def check_lnd_node():
    """Check LND node status with readonly macaroon"""
    try:
        url = f"https://{NODE_ONION_ADDRESS}:{NODE_PORT}/v1/getinfo"
        
        headers = {
            'Grpc-Metadata-macaroon': MACAROON_HEX,
        }
        
        response = requests.get(
            url, 
            headers=headers,
            proxies=TOR_PROXY,
            timeout=TIMEOUT,
            verify=False  
        )
        
        if response.status_code == 200:
            node_info = response.json()
            return True, node_info
        elif response.status_code == 401:
            logger.error("Invalid or expired macaroon")
            return False, None
        else:
            logger.warning(f"Node responds with status code: {response.status_code}")
            return False, None
            
    except requests.exceptions.Timeout:
        logger.warning("Timeout in node connection")
        return False, None
    except requests.exceptions.ConnectionError:
        logger.warning("Node connection error")
        return False, None
    except Exception as e:
        logger.error(f"Error in node check: {e}")
        return False, None

def get_wallet_balance():
    """Get on-chain wallet balance"""
    try:
        url = f"https://{NODE_ONION_ADDRESS}:{NODE_PORT}/v1/balance/blockchain"
        headers = {'Grpc-Metadata-macaroon': MACAROON_HEX}
        
        response = requests.get(
            url, 
            headers=headers,
            proxies=TOR_PROXY,
            timeout=TIMEOUT,
            verify=False
        )
        
        if response.status_code == 200:
            return True, response.json()
        else:
            logger.warning(f"Wallet balance request failed: {response.status_code}")
            return False, None
            
    except Exception as e:
        logger.error(f"Error getting wallet balance: {e}")
        return False, None

def get_channel_balance():
    """Get Lightning channel balance"""
    try:
        url = f"https://{NODE_ONION_ADDRESS}:{NODE_PORT}/v1/balance/channels"
        headers = {'Grpc-Metadata-macaroon': MACAROON_HEX}
        
        response = requests.get(
            url, 
            headers=headers,
            proxies=TOR_PROXY,
            timeout=TIMEOUT,
            verify=False
        )
        
        if response.status_code == 200:
            return True, response.json()
        else:
            logger.warning(f"Channel balance request failed: {response.status_code}")
            return False, None
            
    except Exception as e:
        logger.error(f"Error getting channel balance: {e}")
        return False, None

def get_channels():
    """Get channel information"""
    try:
        url = f"https://{NODE_ONION_ADDRESS}:{NODE_PORT}/v1/channels"
        headers = {'Grpc-Metadata-macaroon': MACAROON_HEX}
        
        response = requests.get(
            url, 
            headers=headers,
            proxies=TOR_PROXY,
            timeout=TIMEOUT,
            verify=False
        )
        
        if response.status_code == 200:
            return True, response.json()
        else:
            logger.warning(f"Channels request failed: {response.status_code}")
            return False, None
            
    except Exception as e:
        logger.error(f"Error getting channels: {e}")
        return False, None

def get_pending_channels():
    """Get pending channel information"""
    try:
        url = f"https://{NODE_ONION_ADDRESS}:{NODE_PORT}/v1/channels/pending"
        headers = {'Grpc-Metadata-macaroon': MACAROON_HEX}
        
        response = requests.get(
            url, 
            headers=headers,
            proxies=TOR_PROXY,
            timeout=TIMEOUT,
            verify=False
        )
        
        if response.status_code == 200:
            return True, response.json()
        else:
            logger.warning(f"Pending channels request failed: {response.status_code}")
            return False, None
            
    except Exception as e:
        logger.error(f"Error getting pending channels: {e}")
        return False, None

def get_peers():
    """Get peer information"""
    try:
        url = f"https://{NODE_ONION_ADDRESS}:{NODE_PORT}/v1/peers"
        headers = {'Grpc-Metadata-macaroon': MACAROON_HEX}
        
        response = requests.get(
            url, 
            headers=headers,
            proxies=TOR_PROXY,
            timeout=TIMEOUT,
            verify=False
        )
        
        if response.status_code == 200:
            return True, response.json()
        else:
            logger.warning(f"Peers request failed: {response.status_code}")
            return False, None
            
    except Exception as e:
        logger.error(f"Error getting peers: {e}")
        return False, None

def get_forwarding_history():
    """Get forwarding history for fee analysis"""
    try:
        url = f"https://{NODE_ONION_ADDRESS}:{NODE_PORT}/v1/switch"
        headers = {'Grpc-Metadata-macaroon': MACAROON_HEX}
        
        # Calculate timestamp for 30 days ago
        thirty_days_ago = int((datetime.now().timestamp() - (30 * 24 * 60 * 60)))
        
        data = {
            'start_time': str(thirty_days_ago),
            'num_max_events': 100
        }
        
        response = requests.post(
            url, 
            headers=headers,
            json=data,
            proxies=TOR_PROXY,
            timeout=TIMEOUT,
            verify=False
        )
        
        if response.status_code == 200:
            return True, response.json()
        else:
            logger.warning(f"Forwarding history request failed: {response.status_code}")
            return False, None
            
    except Exception as e:
        logger.error(f"Error getting forwarding history: {e}")
        return False, None

def format_satoshis(sats):
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

def format_node_info(node_info):
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

def main():
    """Main monitor function"""
    logger.info("=== Starting Lightning Node Monitor ===")
    
    # Verify configuration
    if not MACAROON_BASE64:
        logger.error("Environment variable LND_MACAROON_RO not found!")
        logger.error("Add to .bashrc: export LND_MACAROON_RO='your_base64_macaroon'")
        sys.exit(1)
    
    # Test Tor for .onion domains
    logger.info("Verifying that Tor is configured for .onion...")
    if not test_tor_connection():
        logger.error("Tor doesn't work for .onion domains!")
        logger.error("Check: 1) sudo apt install tor && sudo systemctl start tor")
        logger.error("       2) pip3 install requests[socks]")
        sys.exit(1)
    
    # Send startup message
    startup_msg = f"""
🚀 <b>Start9 LND Monitor Started</b>
🎯 Node: {NODE_ONION_ADDRESS}
⏱️ Interval: {CHECK_INTERVAL}s
📍 From: UmbrelOS via Tor
🔧 Proxy: socks5h://127.0.0.1:9050

🤖 <b>Interactive Bot Active!</b>
Send /help for available commands
    """
    send_telegram_message(startup_msg)
    
    # Start command processing in a separate thread
    logger.info("Starting Telegram command processor...")
    command_thread = threading.Thread(target=process_telegram_commands, daemon=True)
    command_thread.start()
    
    # Wait a moment for command processor to clear old messages
    time.sleep(3)
    
    # Previous state to avoid spam
    last_status = None
    consecutive_failures = 0
    last_successful_check = datetime.now()
    offline_alert_sent = False  # Track if we actually sent an offline alert
    
    logger.info("Starting monitoring...")
    
    while True:
        try:
            current_time = datetime.now()
            logger.info(f"Checking node at {current_time.strftime('%H:%M:%S')}")
            
            # Check the node
            is_online, node_info = check_lnd_node()
            
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
                    send_telegram_message(initial_msg)
                    logger.info("Initial node status confirmed online")
                
                # If it was offline AND we sent an offline alert, send recovery notification
                elif last_status is False and offline_alert_sent:
                    uptime_msg = f"""
✅ <b>Start9 Node BACK ONLINE!</b>
⏰ {current_time.strftime('%d/%m/%Y %H:%M:%S')}
{format_node_info(node_info)}
                    """
                    send_telegram_message(uptime_msg)
                    logger.info("Node back online")
                    offline_alert_sent = False  # Reset the flag
                
                # Periodic log when everything is fine
                elif consecutive_failures == 0 and current_time.minute % 30 == 0:
                    logger.info("Node working correctly")
                
            else:
                consecutive_failures += 1
                logger.warning(f"Failed attempt {consecutive_failures}/{MAX_RETRIES}")
                
                # Send alert only after MAX_RETRIES consecutive failures
                if consecutive_failures >= MAX_RETRIES and last_status is not False:
                    offline_msg = f"""
🚨 <b>START9 NODE OFFLINE!</b>
⏰ {current_time.strftime('%d/%m/%Y %H:%M:%S')}
❌ Last successful check: {last_successful_check.strftime('%H:%M:%S')}
🔄 Failed attempts: {consecutive_failures}
                    """
                    send_telegram_message(offline_msg)
                    logger.error("Node considered offline")
                    offline_alert_sent = True  # Mark that we sent an offline alert
            
            # Update state
            last_status = is_online
            
            # Wait for next check
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("Monitor stopped manually")
            send_telegram_message("🛑 <b>Start9 LND Monitor stopped</b>")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(60)  # Longer wait in case of error

if __name__ == "__main__":
    main()
