# Changelog

All notable changes to the LND Monitoring project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-01-08

### 🚀 Major Release - Modern Async Implementation

This is a major rewrite of the LND monitoring system, migrating from the legacy `requests`-based implementation to a modern async architecture using `python-telegram-bot` v20+.

### ✨ Added

- **Modern Async Architecture**: Complete rewrite using `asyncio` and `async/await` patterns
- **python-telegram-bot Integration**: Upgraded to `python-telegram-bot` v20+ for reliable Telegram bot functionality
- **Enhanced Command System**: Rich interactive commands with automatic registration in Telegram UI
- **Authorization Middleware**: Decorator-based security system for command authorization
- **Concurrent Operations**: Non-blocking monitoring that doesn't interfere with command processing
- **Improved Error Handling**: Graceful error recovery with detailed logging
- **Command Registration**: Bot commands automatically appear in Telegram interface
- **Enhanced Security**: Input validation and authorization checks for all commands

### 🔄 Changed

- **HTTP Client**: Migrated from `requests` to `aiohttp` for better async performance
- **Tor Proxy Support**: Updated to use `aiohttp-socks` for .onion connections
- **Monitoring Logic**: Improved offline/online detection with better state management
- **Message Formatting**: Enhanced Telegram message formatting with HTML support
- **Dependencies**: Updated to modern async libraries with performance optimizations

### 🛠️ Technical Improvements

- **Performance**: Significantly improved response times with async operations
- **Reliability**: Better connection handling and retry logic
- **Maintainability**: Cleaner code structure with proper type hints
- **Security**: Enhanced authorization and input validation
- **Documentation**: Comprehensive README with architecture details

### 📦 Dependencies

- `python-telegram-bot>=20.7` - Modern Telegram bot framework
- `aiohttp>=3.9.0` - High-performance async HTTP client
- `aiohttp-socks>=0.8.0` - Tor proxy support
- `uvloop>=0.19.0` - High-performance event loop (Linux/macOS)

### 🗑️ Removed

- **Legacy Implementation**: Removed old `requests`-based monitoring system
- **Deprecated Dependencies**: Removed `requests`, `requests[socks]` dependencies
- **Version Selection**: Simplified Docker configuration (no more version switching)

### 🔧 Fixed

- **Offline Notifications**: Fixed bug where offline alerts weren't sent properly
- **Recovery Messages**: Fixed "back online" notifications after outages
- **State Management**: Improved monitoring state tracking
- **Connection Handling**: Better error handling for network issues

### 💔 Breaking Changes

- **Python Version**: Now requires Python 3.11+ for optimal async performance
- **Configuration**: Environment variables remain the same (backward compatible)
- **Docker**: Simplified Dockerfile (no breaking changes for users)
- **Commands**: All existing commands work the same but with better performance

### 📋 Migration Guide

If upgrading from v1.x:

1. **No Configuration Changes Required**: All environment variables remain the same
2. **Docker Users**: Simply rebuild the container - no changes needed
3. **Local Installation**: Update dependencies with `pip install -r requirements.txt`
4. **Python Version**: Ensure Python 3.11+ is installed for best performance

### 🔍 What's Next

- Enhanced analytics and reporting features
- Additional monitoring metrics
- Web dashboard (planned for v2.1.0)
- Multi-node support (planned for v2.2.0)

---

## [1.0.0] - Previous Releases

### Legacy Implementation

- Basic LND node monitoring via Tor
- Telegram notifications for offline/online status
- Interactive commands for node information
- Docker containerization
- Start9 .onion address support

---

**Full Changelog**: [View on GitHub](https://github.com/yourusername/lnd-monitoring/compare/v1.0.0...v2.0.0)
