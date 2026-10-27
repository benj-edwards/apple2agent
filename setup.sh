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

# Python packages go in a project virtualenv (.venv); the proxy switches
# into it automatically, however it's started
echo
echo "Creating .venv and installing Python dependencies..."
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo "Installed: $(.venv/bin/pip list 2>/dev/null | grep -iE '^(anthropic|pillow) ' | tr -s ' ' | paste -sd ',' -)"

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
    echo "Note: ca65 not found - using the pre-built agent disk"
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
echo "On your Apple II (128K //e recommended, Uthernet II in slot 3):"
echo "  1. Boot disks/agent_contiguous.dsk - it starts the agent by itself"
echo "  2. /SETIP <this computer's IP>   (the proxy listens on port 6502)"
echo "  3. Ask for anything: MAKE A BREAKOUT GAME IN HI-RES"
echo
