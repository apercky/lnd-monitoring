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

def send_telegram_message(message):
    """Send Telegram message"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
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
    """
    send_telegram_message(startup_msg)
    
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
                
                # If it was offline AND we sent an offline alert, send recovery notification
                if last_status is False and offline_alert_sent:
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
