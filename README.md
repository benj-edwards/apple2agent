# Apple II Agent

**AI-powered development environment for Apple II** - talk naturally and Claude writes Apple II software for you.

```
You: "Make a program that draws a circle"
Claude: [writes BASIC, injects into Apple II memory]
Apple II: [displays circle]
```

## Quick Start

### 1. Setup

```bash
./setup.sh
```

This installs dependencies and prompts for your Anthropic API key.

### 2. Start the Proxy

```bash
./proxy.sh start
```

The proxy listens on port 8080 and bridges your Apple II to Claude.

### 3. Connect from Apple II

Boot from `disks/agent_contiguous.dsk` and run:

```
BRUN AGENT.BIN
```

The agent will connect via Uthernet II. If your proxy is on a different IP:

```
/SETIP 192.168.1.100
```

### 4. Start Coding!

Just type naturally:

```
AGENT> make a number guessing game
AGENT> draw a house in hi-res graphics
AGENT> write a program to calculate fibonacci numbers
```

Claude generates the code, injects it into your Apple II's memory, and you can run it immediately.

## Commands

| Command | Description |
|---------|-------------|
| `/EXIT` | Drop to BASIC to run your program |
| `/LIST` | Show the generated code |
| `/CLEAR` | Clear conversation history |
| `/MODEL S/O/H` | Switch model (Sonnet/Opus/Haiku) |
| `/SETIP x.x.x.x` | Set proxy IP address |
| `/HELP` | Show all commands |

After `/EXIT`, type `RUN` at the BASIC prompt. Return to agent with `&` or Ctrl-Y.

## Proxy Control

```bash
./proxy.sh start    # Start proxy
./proxy.sh stop     # Stop proxy
./proxy.sh status   # Check if running
./proxy.sh log      # Follow log output
./proxy.sh restart  # Restart proxy
```

## Requirements

- **Python 3.8+** with pip
- **Anthropic API key** ([get one here](https://console.anthropic.com/))
- **Apple II** with Uthernet II card (or emulator)

### Optional (for development)

- **cc65** - to rebuild the Apple II agent from source
- **Bobbin** - Apple II emulator with network support

## Testing with Emulator

If you have Claude Code with the apple2-mcp server configured:

```bash
# Boot emulator with agent disk
mcp__apple2-mcp__boot(machine="enhanced", uthernet2=true, disk="disks/agent_contiguous.dsk")

# The agent auto-connects to proxy at 192.168.65.1:8080
```

## Project Structure

```
proxy/           # Proxy server (Python)
  unified_proxy.py    # Main proxy
  agentic_claude.py   # Claude API integration
  proxyctl.py         # Control script

asm/             # Apple II client (6502 assembly)
  agent.s             # Main agent source

disks/           # Disk images
  agent_contiguous.dsk  # Ready-to-boot disk

build/           # Compiled binaries
  AGENT.BIN           # Compiled agent
```

## How It Works

```
┌──────────────┐      TCP/IP      ┌──────────────┐      API      ┌──────────┐
│   Apple II   │◄────────────────►│    Proxy     │◄─────────────►│  Claude  │
│  (Uthernet)  │   A2P Protocol   │  (Python)    │               │   API    │
└──────────────┘                  └──────────────┘               └──────────┘
```

1. You type a request on the Apple II
2. Agent sends it to the proxy via TCP
3. Proxy calls Claude API with coding tools
4. Claude generates BASIC code
5. Proxy tokenizes and sends code back
6. Agent injects code into Apple II memory
7. You run the program!

## License

MIT
