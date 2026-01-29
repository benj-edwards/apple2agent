# Apple II Agent - THE MISSION

## PRIMARY DIRECTIVE

**AGENTIC SOFTWARE DEVELOPMENT FOR APPLE II**

This is NOT a chat system. This is an autonomous AI coding environment.

User speaks naturally → Claude writes code → **Streams progress to Apple II** → Tests in emulator → Deploys to Apple II

**NO SPECIAL COMMANDS NEEDED** - Claude understands natural language and knows how to do everything.

## Goal: Claude Code for Apple II

An **agentic AI development environment** where you talk in natural language and Claude makes Apple II software for you.

```
You: "Make a program that draws a circle"
Claude: [boots emulator, writes BASIC, injects, tests, fixes bugs, deploys to Apple II]
Apple II: [displays circle]
```

## THE AGENTIC LOOP (This is the core feature!)

**Agentic mode is ON by default.** Every message triggers the full development loop.

`/AGENT` command toggles it OFF if you just want simple chat (rare).

### What Happens When You Type Anything:
- Claude gets access to tools:
  - `emulator_boot` - Start Bobbin emulator
  - `emulator_inject_basic` - Load BASIC program
  - `emulator_run_basic` - Run commands
  - `emulator_read_screen` - See output
  - `emulator_assemble` - Assemble 6502 code
  - `apple2_send_code` - Deploy to real Apple II
- Claude runs up to 20 turns of tool use
- Tests in emulator, then deploys to real hardware

**Key file:** `proxy/agentic_claude.py` - The entire agentic loop

## Architecture

```
┌──────────────┐      TCP/IP      ┌──────────────┐      API      ┌──────────┐
│   Apple II   │◄────────────────►│    Proxy     │◄─────────────►│  Claude  │
│  (Uthernet)  │   A2P Protocol   │              │   + Tools     │   API    │
└──────────────┘                  │  agentic_    │               └──────────┘
       ▲                          │  claude.py   │
       │                          │      │       │
       │                          │      ▼       │
       │                          │  emulator_   │
       │                          │  bridge.py   │
       │                          │      │       │
       │                          └──────┼───────┘
       │                                 │ Unix Socket
       │                                 ▼
       │                          ┌──────────────┐
       └──────────────────────────│   Bobbin     │
              Deploy code         │  Emulator    │
                                  └──────────────┘
```

**Two ways to control emulator:**
1. **Proxy** uses `emulator_bridge.py` → control socket (for agentic loop)
2. **Claude Code** uses MCP server → control socket (for interactive testing)

## Quick Start

### 1. Start Proxy
```bash
cd proxy && python3 proxyctl.py start
```

API key in `proxy/.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Boot Emulator
```
mcp__apple2-mcp__boot(machine="enhanced", uthernet2=true, disk="disks/agent.dsk")
```

### 3. Run Agent
```
BRUN AGENT.BIN
```

### 4. Talk Naturally (Agentic mode is ON by default)
- "Make a program that prints the Fibonacci sequence"
- "Draw a house using HGR graphics"
- "Create a number guessing game"

Claude will:
1. **Stream status updates to Apple II** - you see everything happening in real-time
2. Boot the emulator
3. Write the code
4. Inject and test it
5. Fix any bugs (iterate until working)
6. Deploy to your Apple II
7. Tell you when it's ready

**Just like Claude Code** - you watch Claude work, step by step, on your Apple II screen.

## Bobbin Control Socket (USE THIS!)

**The control socket is the reliable way to control the emulator.** It bypasses all pexpect/PTY/signal issues.

### Python Client
```python
from apple2_mcp.control_socket import BobbinControlSocket

sock = BobbinControlSocket('/tmp/bobbin.sock')
sock.connect()

# Read screen
lines = sock.read_screen()  # 24 lines of 40 chars

# Memory access
data = sock.peek(0x400, 40)  # Read 40 bytes from $0400
sock.poke(0x6000, [0xA9, 0x00, 0x60])  # Write bytes

# CPU control
cpu = sock.get_cpu_state()  # {pc, a, x, y, sp, p, cycles, frames}
sock.step(100)  # Single-step 100 instructions
sock.pause()    # Pause emulation
sock.resume()   # Resume

# Breakpoints
sock.break_set(0x6000)   # Break at address
sock.watch_set(0x400)    # Break when memory changes
bps = sock.break_list()  # List all breakpoints

# Disks
sock.disk_insert('/path/to/disk.dsk', drive=1)
sock.disk_eject(drive=1)
status = sock.disk_status()  # {active, spinning}

# Graphics capture
sock.capture_hgr('/tmp/screen.ppm', page=1, color=True)
sock.capture_gr('/tmp/lores.ppm')

# State snapshots
sock.save_state('/tmp/state.bin')
sock.load_state('/tmp/state.bin')

# System info
switches = sock.get_softswitches()  # {text, hires, page2, ...}
slots = sock.get_slots()  # {3: 'uthernet2', 6: 'disk2', ...}

# Mouse control
sock.mouse(x=140, y=96, button=True)

sock.disconnect()
```

### Available Commands (Protocol v2.0)

| Category | Commands |
|----------|----------|
| **Basic** | `ping`, `quit` |
| **Memory** | `peek`, `poke`, `load`, `screen`, `screen_raw` |
| **CPU** | `cpu`, `step`, `reset`, `pause`, `resume`, `call`, `disasm` |
| **Breakpoints** | `break_set`, `break_clear`, `break_list`, `break_enable`, `break_disable`, `watch_set` |
| **Disks** | `disk_status`, `disk_insert`, `disk_eject` |
| **Graphics** | `hgr`, `gr`, `dhgr`, `dgr` (export to PPM) |
| **State** | `save_state`, `load_state` |
| **System** | `keys`, `mouse`, `slots`, `softswitches`, `speed`, `cycles`, `trace` |

### Starting Bobbin with Socket
```bash
bobbin --simple --control-socket /tmp/bobbin.sock -m enhanced --disk disks/agent.dsk
```

The MCP server (`emulator.py`) automatically uses the socket when available and falls back to pexpect if not.

## Emulator Bridge (FOR THE PROXY)

**`proxy/emulator_bridge.py`** provides the connection between the agentic loop and Bobbin.

### Why It Exists

The proxy needs to control the emulator for testing code before deploying to real hardware.
The MCP server is for Claude Code's interactive use - the proxy needs its own interface.

**DO NOT** try to call MCP tools from the proxy. Use the emulator bridge instead.

### How It Works

```python
# In unified_proxy.py:
from emulator_bridge import mcp_call as emulator_mcp_call

proxy = UnifiedProxy(mcp_call=emulator_mcp_call)
```

The bridge:
1. Starts Bobbin with `--control-socket /tmp/bobbin.sock`
2. Connects via `BobbinControlSocket`
3. Translates MCP-style tool calls to control socket commands

### Using the Bridge Directly

```python
from emulator_bridge import mcp_call, get_bridge

# Boot emulator
mcp_call('mcp__apple2-mcp__boot', {'machine': 'enhanced'})

# Read screen
screen = mcp_call('mcp__apple2-mcp__read_screen', {})

# Tokenize and inject BASIC
result = mcp_call('mcp__apple2-mcp__tokenize', {'source': '10 PRINT "HI"'})
mcp_call('mcp__apple2-mcp__inject_tokenized_basic', {
    'hex_data': result['hex'],
    'auto_run': True
})

# Shutdown when done
get_bridge().shutdown()
```

### Supported Tools

| Tool | Description |
|------|-------------|
| `mcp__apple2-mcp__boot` | Start emulator |
| `mcp__apple2-mcp__read_screen` | Get 40x24 text screen |
| `mcp__apple2-mcp__type_text` | Type into emulator |
| `mcp__apple2-mcp__run_basic` | Run BASIC command |
| `mcp__apple2-mcp__tokenize` | Tokenize BASIC source |
| `mcp__apple2-mcp__inject_tokenized_basic` | Inject program into memory |
| `mcp__apple2-mcp__peek` | Read memory |
| `mcp__apple2-mcp__poke` | Write memory |
| `mcp__apple2-mcp__load_binary` | Load hex data |
| `mcp__apple2-mcp__assemble` | Assemble 6502 code (requires ca65) |
| `mcp__apple2-mcp__call` | Call machine code routine |
| `mcp__apple2-mcp__get_registers` | Get CPU state |
| `mcp__apple2-mcp__reset` | Reset emulator |

## Key Files

| File | Purpose |
|------|---------|
| `proxy/agentic_claude.py` | **THE AGENTIC LOOP** - tools and 20-turn iteration |
| `proxy/emulator_bridge.py` | **EMULATOR BRIDGE** - connects agentic loop to Bobbin via control socket |
| `proxy/unified_proxy.py` | Main proxy, calls agentic_claude when `/AGENT` enabled |
| `proxy/basic_tokenizer_streaming.py` | Tokenizes BASIC for injection |
| `asm/agent.s` | Apple II client (6502 assembly) |
| `src/apple2_mcp/` | MCP server for emulator control (used by Claude Code) |
| `src/apple2_mcp/control_socket.py` | **Control socket client** - USE THIS for emulator control |
| `bobbin_socket.md` | Control socket design document |

## Commands

| Command | Description |
|---------|-------------|
| `/AGENT` | Toggle agentic mode OFF (it's ON by default) |
| `/CLEAR` | Clear conversation history |
| `/MODEL S/O/H` | Set model (Sonnet/Opus/Haiku) |
| `/IP` | Show proxy IP |
| `/HELP` | Show commands |

## A2P Protocol

| Type | Name | Description |
|------|------|-------------|
| 0x00 | INIT | Initialize connection |
| 0x01 | CHAT | User message |
| 0x02 | RESP | AI response (streaming) |
| 0x03 | CODE | BASIC code chunk (tokenized) |
| 0x04 | STATUS | Status message |
| 0x05 | ACK | Acknowledgment |

## Build

```bash
make agent              # Build AGENT.BIN
make install-agent      # Install to agent.dsk
```

## Current Status

Working:
- TCP connection via Uthernet II
- A2P protocol with reliable packet delivery
- Claude API integration with streaming
- Text display on Apple II (40-column)
- Agentic mode with tools (proxy-side) ✅
- **Emulator bridge** - proxy can boot, inject, run, test code ✅
- `/CODE` command - generates and injects BASIC code ✅
- Code tokenization and memory injection ✅
- Control socket integration ✅

Needs testing:
- End-to-end with real Apple II hardware
- Full agentic workflow (user request → emulator test → deploy)

Known issues:
- **Agentic mode code injection** - fix ready in `asm/agent.s` (dst_ptr init at offset=0)
- `tools/prodos.py` corrupts disk images - can't deploy new agent
- Connection drops after first response (timeout handling)

## Ready to Deploy (blocked by disk tool)

The fix for agentic mode code injection is in `asm/agent.s`:
- `handle_code_chunk` now initializes `dst_ptr` to `BASIC_START` when offset=0
- `inject_program` is called when end marker received to update BASIC pointers
- Build with `make agent` - file is at `build/AGENT.BIN`

## NEVER FORGET

1. **USE THE CONTROL SOCKET** - `BobbinControlSocket` is the reliable way to control the emulator
2. **PROXY USES EMULATOR BRIDGE** - `proxy/emulator_bridge.py` connects agentic loop to Bobbin (DO NOT reinvent this!)
3. **Agentic mode is ON by default** - `/AGENT` toggles it OFF for simple chat
4. **Progress streams to Apple II** - user watches Claude work in real-time
5. **agentic_claude.py has the loop** - 20 turns of tool use
6. **Test in emulator first** - then deploy to real hardware
7. **The mission is autonomous coding** - not just chat
8. **/CODE command WORKS** - use it while agentic mode injection is broken
9. **Control socket has EVERYTHING** - peek, poke, step, breakpoints, graphics capture, state save/load
