#!/bin/bash
# Apple II Agent - Proxy Control Script
# Simple wrapper for proxy management

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROXY_DIR="$SCRIPT_DIR/proxy"

case "$1" in
    start)
        cd "$PROXY_DIR" && python3 proxyctl.py start
        ;;
    stop)
        cd "$PROXY_DIR" && python3 proxyctl.py stop
        ;;
    restart)
        cd "$PROXY_DIR" && python3 proxyctl.py stop
        sleep 1
        cd "$PROXY_DIR" && python3 proxyctl.py start
        ;;
    status)
        cd "$PROXY_DIR" && python3 proxyctl.py status
        ;;
    log|logs)
        if [ -f /tmp/claude/proxy.log ]; then
            tail -f /tmp/claude/proxy.log
        else
            echo "No log file found. Is the proxy running?"
        fi
        ;;
    *)
        echo "Apple II Agent - Proxy Control"
        echo
        echo "Usage: $0 {start|stop|restart|status|log}"
        echo
        echo "Commands:"
        echo "  start   - Start the proxy server"
        echo "  stop    - Stop the proxy server"
        echo "  restart - Restart the proxy server"
        echo "  status  - Show proxy status"
        echo "  log     - Follow the proxy log (Ctrl-C to exit)"
        echo
        exit 1
        ;;
esac
