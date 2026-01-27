# Apple II Agent - Claude Code Instructions

Interactive AI chat client for Apple IIe over TCP/IP using Uthernet II.

## Quick Start

### 1. Start the Unified Proxy
```bash
cd proxy && python3 unified_proxy.py
```

Set your API key first:
```bash
export ANTHROPIC_API_KEY="your-key-here"
```

### 2. Boot the Apple IIe
- Insert `disks/agent_test.dsk`
- Run: `BRUN AGENT.BIN`
- Configure IP with `/SETIP` and `/PORT` commands

### 3. Chat with Claude
Type messages at the `CLAUDE>` prompt. The agent sends to the proxy, which forwards to Claude API.

---

## Agent Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/HELP` | Show commands | `/HELP` |
| `/IP` | Show current proxy IP | `/IP` |
| `/SETIP` | Set proxy IP address | `/SETIP 192.168.1.100` |
| `/PORT` | Set proxy port | `/PORT 8080` |
| `/MODEL` | Set AI model | `/MODEL S`, `/MODEL O`, `/MODEL H` |
| `/SAVE` | Save config to disk | `/SAVE` |
| `/CODE` | Generate BASIC program | `/CODE DRAW A CIRCLE` |
| `/CLEAR` | Clear screen | `/CLEAR` |
| `ESC` | Show menu | Press ESC key |

### AI Models

| Command | Model | Description |
|---------|-------|-------------|
| `/MODEL S` | Sonnet | Default - balanced speed/quality |
| `/MODEL O` | Opus | Most capable - best for complex tasks |
| `/MODEL H` | Haiku | Fastest - best for simple queries |

All config changes (IP, port, model) are auto-saved to disk.

### Example Session
```
CLAUDE> HELLO
HELLO! I'M CLAUDE, AN AI ASSISTANT.
HOW CAN I HELP YOU TODAY?

CLAUDE> /CODE PRINT HELLO WORLD
Generating...
...
PROGRAM LOADED - TYPE RUN
```

---

## A2P Protocol

The agent uses A2P (Apple II Protocol) for reliable communication:

**Packet format:** `[A2][Type][Len:2][Seq][Data...][Checksum]`

| Type | Name | Description |
|------|------|-------------|
| 0x00 | INIT | Initialize connection |
| 0x01 | CHAT | User message |
| 0x02 | RESP | AI response (streaming) |
| 0x03 | CODE | BASIC code chunk |
| 0x04 | STATUS | Status message |
| 0x05 | ACK | Acknowledgment |
| 0x06 | NACK | Request retransmit |
| 0x0F | ERR | Error message |

---

## Build Process

```bash
# Build the unified agent
make agent

# Install to test disk
make install-agent-test

# Install to production disk
make install-agent

# Start unified proxy
make unified-proxy

# Run protocol tests
make test
```

---

## IP Configuration

The agent stores IP configuration at memory $0300-$0307:
- `$0300-$0303` - Proxy IP (4 bytes)
- `$0304-$0305` - Port (2 bytes, little-endian)
- `$0307` - Magic byte ($A2 = valid config)

**Default:** 192.168.64.1:8080 (Bobbin/MAME vmnet gateway)

**Commands:**
- `/SETIP 192.168.1.100` - Set proxy IP address
- `/PORT 8080` - Set proxy port
- `/SAVE` - Save config to disk as `CLAUDE.CONF`

Config is automatically loaded from `CLAUDE.CONF` on startup if it exists.

---

## Project Structure

```
apple2agent/
├── CLAUDE.md              # This file
├── Makefile               # Build automation
│
├── proxy/                 # Python proxy servers
│   ├── unified_proxy.py   # Main proxy (A2P protocol)
│   ├── a2p_protocol.py    # Protocol encoder/decoder
│   └── basic_tokenizer_streaming.py
│
├── asm/                   # Assembly sources
│   ├── agent.s            # Unified agent binary
│   └── agent.cfg          # Linker config
│
├── tests/                 # Test suite
│   ├── test_protocol.py   # Protocol unit tests
│   └── test_e2e.py        # End-to-end test
│
├── disks/                 # Disk images
│   ├── agent_test.dsk     # Testing disk
│   └── agent.dsk          # Production disk
│
└── build/                 # Build output
    └── AGENT.BIN          # Compiled agent (~9.5KB)
```

---

## Memory Map

```
$0300-$030F   Configuration (IP, port, flags)
$03F5-$03F7   Ampersand hook vector
$0400-$07FF   Text screen
$0801-$5FFF   BASIC program area (~22KB)
$6000-$7FFF   AGENT.BIN code (~9.5KB)
$8000-$8FFF   Receive buffer (4KB circular)
$9000-$93FF   Screen save buffer
```

---

## Testing

### Protocol Test (no hardware needed)
```bash
# Terminal 1: Start proxy
python3 proxy/unified_proxy.py

# Terminal 2: Run E2E test
python3 tests/test_e2e.py
```

### Emulator Test (Bobbin)
```bash
# Start proxy
python3 proxy/unified_proxy.py

# Run Bobbin with Uthernet II
./bobbin --simple -m enhanced --uthernet2 --disk disks/agent_test.dsk
```

### Real Hardware
1. Start proxy on your computer
2. Boot Apple IIe with Uthernet II
3. Run: `BRUN AGENT.BIN`
4. Configure IP: `/SETIP <your-computer-ip>`
5. Chat away!

---

## Common Issues

| Problem | Solution |
|---------|----------|
| "CONNECTION FAILED" | Check `/IP`, use `/SETIP` to fix |
| "API KEY NOT SET" | Export `ANTHROPIC_API_KEY` |
| Network init fails | Ensure Uthernet II in slot 3 |
| Garbled display | Use `/CLEAR` to redraw |

---

## MCP Tools

For Claude Code integration, MCP tools are available:
- `boot` - Start Bobbin emulator
- `read_screen` - Capture text display
- `type_text` - Send keyboard input
- `peek/poke` - Memory access
- `prodos_list/add/del` - Disk operations
