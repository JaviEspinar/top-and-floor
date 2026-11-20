"""Indicator dashboard for stocks, ETFs and crypto."""
import os

import certifi

# The uv-managed Python does not read the macOS keychain, so the TradingView
# websocket fails certificate checks unless we point it at a CA bundle.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
