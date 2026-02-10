# Apple II Agent

**An autonomous AI coding environment for Apple II.** You talk naturally, Claude writes Applesoft BASIC or 6502 assembly, tests it in an emulator, and deploys the working code to your real Apple II over Ethernet.

```
AGENT> make a starfield animation in hi-res
  [Claude writes HGR code, injects into emulator, tests it, fixes a bug,
   re-tests, deploys to Apple II]
Apple II: [displays starfield]
```

This is **Claude Code for Apple II** — an agentic loop where you watch Claude work, step by step, on your 40-column screen.

## How It Works

An Apple II with a [Uthernet II](http://a2retrosystems.com/products.htm) Ethernet card connects to a Python proxy over TCP. The proxy talks to the Claude API, which has access to a full suite of development tools — an emulator, assembler, BASIC tokenizer, disk tools, and a deployment channel back to the real hardware.

```
┌──────────────┐     TCP/IP      ┌──────────────┐      API       ┌──────────┐
│   Apple II   │◄───────────────►│    Proxy     │◄──────────────►│  Claude  │
│  Uthernet II │  A2P Protocol   │   Server     │   Anthropic    │   API    │
└──────────────┘                 │              │                └──────────┘
                                 │  Emulator    │
                                 │  Bridge  ────┼──► Bobbin (Apple //e emulator)
                                 │              │
                                 │  Assembler   │
                                 │  Tokenizer   │
                                 │  Disk Tools  │
                                 └──────────────┘
```

1. You type a request on the Apple II
2. The agent sends it to the proxy via TCP (A2P protocol)
3. The proxy calls Claude with development tools
4. Claude writes code (BASIC or 6502 assembly)
5. Claude boots the emulator, injects the code, and tests it
6. If something's wrong, Claude reads the screen, fixes the bug, and retests
7. Once working, Claude deploys the code to your Apple II
8. You run the program

The agentic loop runs up to 20 tool-use turns per request. Claude streams status updates to the Apple II in real-time so you can watch it work.

## What It Can Do

- **Applesoft BASIC** — generates, tokenizes, and injects programs directly into memory
- **6502 Assembly** — assembles ca65 source, loads into emulator, calls routines
- **All graphics modes** — lo-res (GR), hi-res (HGR), double hi-res (DHGR), double lo-res (DGR)
- **Emulator testing** — boots Bobbin, runs code, reads screen output, captures graphics, iterates until working
- **Memory access** — peek, poke, load binaries, inspect and modify machine state
- **Disk management** — save programs to ProDOS disks, list catalogs, manage files
- **Code versioning** — undo/redo with `/UNDO` and `/VERSIONS`
- **Web search** — Claude can look up Apple II documentation and programming references
- **Natural language at BASIC prompt** — type anything at `]` and if BASIC can't parse it, it goes to Claude automatically

## Requirements

- **Apple II** (or IIe/IIgs) with a **Uthernet II** Ethernet card
- **Python 3.8+**
- **Anthropic API key** ([get one here](https://console.anthropic.com/))
- **Bobbin** emulator (included as binary, or [build from source](https://github.com/benj-edwards/bobbin-ai))

### Optional

- **cc65** — to rebuild the Apple II agent client from 6502 assembly source
- **Claude Code** with **apple2-mcp** — for interactive emulator access from your terminal

## Quick Start

### 1. Setup

```bash
./setup.sh
```

Installs Python dependencies and prompts for your Anthropic API key (stored in `proxy/.env`).

### 2. Start the Proxy

```bash
./proxy.sh start
```

The proxy listens on port 8080 and bridges your Apple II to Claude.

### 3. Boot the Apple II

Boot from `disks/agent_contiguous.dsk`. The agent binary loads automatically. If your proxy is on a different IP:

```
/SETIP 192.168.1.100
```

### 4. Talk Naturally

```
AGENT> make a number guessing game
AGENT> draw a mandelbrot set in hi-res
AGENT> write a sort routine in assembly at $6000
AGENT> create a lo-res animation with all 16 colors
```

Claude handles everything — writing, testing, debugging, deploying.

### 5. Run Your Program

```
AGENT> /EXIT              ← drop to BASIC
] RUN                     ← run the program
] &                       ← return to agent (or Ctrl-Y)
```

## Commands

| Command | Description |
|---------|-------------|
| `/EXIT` or `/SUSPEND` | Drop to BASIC prompt to run your program |
| `/AGENT` | Toggle agentic mode on/off (on by default) |
| `/CODE <desc>` | Generate BASIC code directly (bypasses agentic loop) |
| `/CHAT <msg>` | Chat without code generation |
| `/MODEL S\|O\|H` | Switch Claude model (Sonnet / Opus / Haiku) |
| `/LIMIT <n>` | Set max agentic turns (1-100, default 20) |
| `/UNDO` | Restore previous program version |
| `/VERSIONS` | Show program version history |
| `/PROMPT <text>` | Set custom system prompt (e.g. `/PROMPT talk like a pirate`) |
| `/DISPLAY 40\|40L\|80` | Set display mode (40-col, 40-col lowercase, 80-col) |
| `/CLEAR` | Clear conversation history |
| `/RESET` | Full session reset |
| `/SETIP x.x.x.x` | Set proxy IP address |
| `/PORT xxxx` | Set proxy port |
| `/IP` | Show connection info |
| `/HELP` | Show command list |

After `/EXIT`, type `RUN` at the `]` prompt. Return to the agent with `&` or Ctrl-Y.

## Proxy Server

The proxy is the bridge between the Apple II and Claude. It manages the TCP connection, the Claude API session, the emulator, and code deployment.

### Control

```bash
./proxy.sh start      # Start proxy (port 8080)
./proxy.sh stop       # Stop proxy
./proxy.sh status     # Check if running
./proxy.sh log        # Tail log output
./proxy.sh restart    # Restart
```

Or use MCP tools from Claude Code: `proxy_start`, `proxy_stop`, `proxy_status`, `proxy_log`.

### Agentic Tools

When agentic mode is on (the default), Claude has access to these tools during each request:

**Emulator:**

| Tool | Description |
|------|-------------|
| `emulator_load_env` | Instant start — load BASIC, ProDOS, or DOS 3.3 environment |
| `emulator_boot` | Cold boot the emulator (slower, use `load_env` instead) |
| `emulator_inject_basic` | Tokenize and inject BASIC program into memory |
| `emulator_run_basic` | Execute a BASIC command and wait for prompt |
| `emulator_read_screen` | Read the 40x24 text screen |
| `emulator_read_basic_program` | Detokenize the program currently in memory |
| `emulator_capture_graphics` | Capture lo-res or hi-res screen as ASCII art |
| `emulator_type` | Type keystrokes into the emulator |
| `emulator_peek` | Read bytes from memory |
| `emulator_poke` | Write bytes to memory |
| `emulator_assemble` | Assemble 6502 code (ca65) and load into memory |
| `emulator_call` | JSR to a machine language routine |

**Deployment (to real Apple II):**

| Tool | Description |
|------|-------------|
| `apple2_send_code` | Deploy BASIC program to Apple II |
| `apple2_send_binary` | Deploy assembled machine code to Apple II |
| `apple2_send_message` | Display a message on the Apple II |
| `apple2_send_status` | Update the Apple II status line |

**Disk:**

| Tool | Description |
|------|-------------|
| `disk_save_basic` | Save BASIC program to ProDOS disk |
| `disk_save_binary` | Save binary file to disk |
| `disk_save_text` | Save text file to disk |
| `disk_list` | List files on current disk |

**Other:**

| Tool | Description |
|------|-------------|
| `web_search` | Search the web for Apple II documentation |

### Configuration

API key is stored in `proxy/.env`:

```
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

Copy `proxy/.env.example` and fill in your key.

## Testing with Emulator Only

You don't need real hardware to develop. If you have Claude Code with the [apple2-mcp](https://github.com/benj-edwards/apple2-mcp) server:

```bash
# Boot emulator with agent disk and Uthernet II
boot(machine="enhanced", uthernet2=true, disk="disks/agent_contiguous.dsk")

# Start the proxy
proxy_start()

# The agent connects automatically — use it from read_screen()
```

Or use the emulator standalone for BASIC/assembly development without the proxy.

## Project Structure

```
proxy/                    # Proxy server (Python)
  unified_proxy.py        # Main proxy — TCP server, session management
  agentic_claude.py       # Claude API integration, tool loop, streaming
  emulator_bridge.py      # Connects proxy to Bobbin via control socket
  basic_tokenizer_streaming.py  # Applesoft BASIC tokenizer
  proxyctl.py             # Proxy control script (start/stop/status)

asm/                      # Apple II client (6502 assembly, ca65)
  agent.s                 # Main agent — UI, TCP, A2P protocol, display

src/apple2_mcp/           # MCP server for Claude Code integration
  server.py               # Tool definitions and handlers
  emulator.py             # Bobbin emulator wrapper
  control_socket.py       # Unix socket client for Bobbin

disks/                    # Disk images
  agent_contiguous.dsk    # Ready-to-boot ProDOS disk with agent
  ProDOS_2_4.dsk          # Clean ProDOS 2.4 master disk

states/                   # Pre-baked emulator snapshots
  basic.state             # Bare BASIC (instant boot)
  prodos.state            # ProDOS BASIC (instant boot)
  dos33.state             # DOS 3.3 BASIC (instant boot)

library/                  # 6502/Apple II reference library
tools/                    # Disk management utilities
```

## The A2P Protocol

The Apple II agent and proxy communicate over TCP using the A2P (Apple II Protocol) binary format:

| Type | Name | Description |
|------|------|-------------|
| 0x00 | INIT | Initialize connection |
| 0x01 | CHAT | User message (Apple II → proxy) |
| 0x02 | RESP | AI response, streamed (proxy → Apple II) |
| 0x03 | CODE | Tokenized BASIC code chunk (proxy → Apple II) |
| 0x04 | STATUS | Status update (proxy → Apple II) |
| 0x05 | ACK | Acknowledgment |

## Building from Source

The Apple II agent client is written in 6502 assembly (ca65/ld65):

```bash
make agent              # Build AGENT.BIN
make install-agent      # Build and install to agent disk
```

Requires the [cc65](https://cc65.github.io/) toolchain.

## Bobbin Emulator

The proxy uses [Bobbin](https://github.com/benj-edwards/bobbin-ai), an Apple II emulator with a Unix socket control interface designed for AI integration. Bobbin supports:

- Apple II+ and enhanced //e emulation
- Uthernet II network card (virtual bridge to host)
- JSON control protocol over Unix socket (multi-client, up to 16 simultaneous connections)
- State save/load (128KB snapshots)
- Graphics export (GR, HGR, DHGR, DGR — mono and 16-color)
- CPU stepping, breakpoints, watchpoints, instruction tracing

## License

MIT
