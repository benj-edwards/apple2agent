#!/bin/bash
# Apple II Agent - Setup Script
# Sets up the proxy server for connecting to real Apple II hardware

set -e

echo "=== Apple II Agent Setup ==="
echo

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required but not installed."
    echo "Install it from https://python.org or via your package manager."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Found Python $PYTHON_VERSION"

# Check for pip
if ! python3 -m pip --version &> /dev/null; then
    echo "ERROR: pip is required but not installed."
    exit 1
fi

# Install anthropic package
echo
echo "Installing Python dependencies..."
python3 -m pip install --quiet anthropic
echo "Installed: anthropic"

# Check for API key
if [ ! -f proxy/.env ]; then
    echo
    echo "=== API Key Setup ==="
    echo "You need an Anthropic API key to use the proxy."
    echo "Get one at: https://console.anthropic.com/"
    echo
    read -p "Enter your Anthropic API key (or press Enter to skip): " API_KEY

    if [ -n "$API_KEY" ]; then
        echo "ANTHROPIC_API_KEY=$API_KEY" > proxy/.env
        echo "API key saved to proxy/.env"
    else
        cp proxy/.env.example proxy/.env
        echo "Created proxy/.env from template - edit it to add your API key"
    fi
else
    echo
    echo "Found existing proxy/.env"
fi

# Check for ca65 (optional, for building agent)
echo
if command -v ca65 &> /dev/null; then
    echo "Found ca65 (cc65 toolchain) - can build agent from source"
else
    echo "Note: ca65 not found - using pre-built AGENT.BIN"
    echo "Install cc65 if you want to modify the Apple II client"
fi

echo
echo "=== Setup Complete ==="
echo
echo "Quick Start:"
echo "  1. Start the proxy:    ./proxy.sh start"
echo "  2. Check status:       ./proxy.sh status"
echo "  3. View logs:          ./proxy.sh log"
echo "  4. Stop the proxy:     ./proxy.sh stop"
echo
echo "On your Apple II:"
echo "  1. Boot from disks/agent_contiguous.dsk"
echo "  2. Run: BRUN AGENT.BIN"
echo "  3. Use /SETIP to set your proxy's IP address"
echo "  4. Start chatting!"
echo
