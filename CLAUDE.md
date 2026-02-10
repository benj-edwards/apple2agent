# Apple II Agent - THE MISSION

## Bobbin Emulator — Official Maintainer

**This agent is the official maintainer of Bobbin and the Apple II MCP server.**

- **Bobbin repo:** `bobbin-ai` on GitHub
- **MCP repo:** `apple2-mcp` on GitHub
- **Canonical source:** a checkout of `bobbin-ai`

The apple2agent project includes a copy of the Bobbin binary at `bobbin/src/bobbin`.
When making changes to Bobbin, edit the canonical source and rebuild, then copy to this project.

### Maintainer Responsibilities
- Fix bugs in Bobbin emulator and control socket
- Fix bugs in Apple II MCP server (`src/apple2_mcp/`)
- Keep GitHub repos in sync with local canonical source
- Support other agents/projects that depend on Bobbin or the MCP server
- Maintain the 6502/Apple II reference library (`library/`)

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
mcp__apple2-mcp__boot(machine="enhanced", uthernet2=true, disk="disks/agent_contiguous.dsk")
```

**Note:** Use `agent_contiguous.dsk` - it has proper boot blocks and contiguous file allocation for hardware disk emulators.

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

### Multi-Client Support

The control socket supports **up to 16 simultaneous clients**. This enables:
- Multiple AI agents working on the same emulator
- Parallel development of program variations
- MCP server + external scripts running together

```python
# Multiple agents can connect simultaneously
agent1 = BobbinControlSocket('/tmp/bobbin.sock')
agent2 = BobbinControlSocket('/tmp/bobbin.sock')
agent1.connect()
agent2.connect()

# Both can send commands - responses route to correct client
agent1.peek(0x400, 10)  # Agent 1 gets its response
agent2.peek(0x800, 10)  # Agent 2 gets its response
```

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

# State snapshots (saves 128KB: main + aux memory)
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
| **State** | `save_state`, `load_state` (128KB: main + aux memory) |
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
| `mcp__apple2-mcp__save_state` | Save emulator state to file |
| `mcp__apple2-mcp__load_state` | Load emulator state from file |
| `mcp__apple2-mcp__proxy_start` | Start the proxy server |
| `mcp__apple2-mcp__proxy_stop` | Stop the proxy server |
| `mcp__apple2-mcp__proxy_status` | Get proxy status (running, PID) |
| `mcp__apple2-mcp__proxy_log` | Get recent proxy log output |

## State Snapshots & Instant Environments

Save and restore complete emulator state (CPU, 128KB RAM, soft switches).

### MCP Tools

| Tool | Description |
|------|-------------|
| `save_state` | Save emulator state to a file |
| `load_state` | Load emulator state from a file |
| `load_basic_env` | Instantly load bare BASIC environment (no DOS) |
| `load_prodos_env` | Instantly load ProDOS BASIC environment |
| `load_dos33_env` | Instantly load DOS 3.3 BASIC environment |

All three `load_*_env` tools **auto-boot the emulator** if it's not already running. One call = instant ready.

### Pre-baked State Files

- `states/basic.state` - Apple //e at ] prompt (no disk, no DOS)
- `states/prodos.state` - ProDOS 2.4 with BASIC.SYSTEM at ] prompt
- `states/dos33.state` - DOS 3.3 at ] prompt (with CATALOG/SAVE/LOAD)

### Using Instant Environments

```python
# One call does everything - boots emulator if needed, loads state instantly
mcp__apple2-mcp__load_basic_env()    # Bare BASIC (no disk commands)
mcp__apple2-mcp__load_prodos_env()   # ProDOS BASIC (PREFIX, CAT, etc.)
mcp__apple2-mcp__load_dos33_env()    # DOS 3.3 BASIC (CATALOG, SAVE, LOAD, etc.)

# Or use control socket directly (emulator must be running)
sock.load_state('states/basic.state')
```

### Recreating Snapshots

The bare BASIC state can be auto-generated:
```bash
python3 tools/create_snapshots.py
```

ProDOS and DOS 3.3 states require interactive boot (menu navigation). Create manually:
1. Boot with the appropriate disk via MCP
2. Navigate to BASIC prompt
3. `save_state` to `states/prodos.state` or `states/dos33.state`

### State File Format

- Header: `BOBBIN_STATE_V2\n` (16 bytes)
- CPU registers (Registers struct)
- Memory (128KB: main 64KB + aux 64KB)
- Soft switches (SoftSwitches struct)

V1 files (64KB only) are still supported for loading.

## Disk Toolchain

Tools for creating and managing ProDOS disk images. **All tools are working and tested.**

### Quick Reference

```bash
# List files on a disk
python3 tools/prodos.py list disks/agent_contiguous.dsk

# Add a file to disk
python3 tools/prodos.py add <disk> <local_file> <prodos_name> [type] [aux_addr]
# Example: python3 tools/prodos.py add disks/agent.dsk build/AGENT.BIN AGENT.BIN BIN 6000

# Delete a file from disk
python3 tools/prodos.py del <disk> <prodos_name>

# Create fresh bootable agent disk (contiguous allocation)
python3 tools/make_agent_disk.py [output.dsk] [--test]
```

### File Types

| Type | Code | Description |
|------|------|-------------|
| BIN | 06 | Binary file (requires aux=load address) |
| SYS | FF | System file (ProDOS executable) |
| BAS | FC | Applesoft BASIC (aux=$0801) |
| TXT | 04 | Text file |

### Disk Formats

| Extension | Format | Notes |
|-----------|--------|-------|
| `.dsk` | DOS-order | Uses sector interleaving, most common |
| `.do` | DOS-order | Same as .dsk |
| `.po` | ProDOS-order | Sequential blocks, less common |

**Use `.dsk` files** - they work with hardware disk emulators and are the default.

### Rebuilding Agent Disk

```bash
# Full rebuild workflow
make agent                              # Build AGENT.BIN
python3 tools/make_agent_disk.py        # Create disks/agent_contiguous.dsk
python3 tools/prodos.py list disks/agent_contiguous.dsk  # Verify
```

### Tool Architecture

```
tools/prodos.py          # Unified CLI (delegates to below)
  ├── tools/prodos_add.py    # Add files (handles .dsk/.po format)
  └── tools/prodos_delete.py # Delete files, list catalog

tools/make_agent_disk.py # Standalone: creates bootable disk with contiguous allocation
tools/prodos_disk.py     # Reference library (not used by CLI)
```

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
| `tools/make_agent_disk.py` | **Creates contiguous disk images** - uses ProDOS 2.4 boot blocks |
| `tools/prodos_disk.py` | ProDOS disk manipulation (catalog, add, extract) |
| `tools/create_snapshots.py` | **Creates environment snapshots** - BASIC and ProDOS states |
| `states/` | Pre-baked environment snapshots for instant loading |
| `bobbin_socket.md` | Control socket design document |
| `library/` | **6502/Apple II reference library** - instruction set, ca65, ld65, ProDOS MLI, soft switches, memory map, ROM routines |

## Commands

| Command | Description |
|---------|-------------|
| `/EXIT` | **Drop to BASIC to run your program** (or `/SUSPEND`) |
| `/AGENT` | Toggle agentic mode OFF (it's ON by default) |
| `/CLEAR` | Clear conversation history |
| `/MODEL S/O/H` | Set model (Sonnet/Opus/Haiku) |
| `/IP` | Show proxy IP |
| `/SETIP x.x.x.x` | Set proxy IP address |
| `/PORT xxxx` | Set proxy port (default: 8080) |
| `/HELP` | Show commands |

### Workflow: Running Generated Code

```
1. AGENT> make a hello world     → Code generated and injected
2. AGENT> /EXIT                  → Drops to BASIC ]
3. ] RUN                         → Program runs!
4. ] &                           → Returns to AGENT> (or Ctrl-Y)
5. AGENT>                        → Ready for next request
```

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
- **State save/load** - 128KB (main + aux) snapshots ✅
- **Instant environments** - load_basic_env, load_prodos_env, load_dos33_env all working (auto-boot) ✅
- **Multi-client socket** - up to 16 simultaneous connections ✅
- **Disk tools** - `prodos.py` list/add/del and `make_agent_disk.py` work correctly ✅
- **Proxy control via MCP** - `proxy_start`, `proxy_stop`, `proxy_status`, `proxy_log` tools ✅

Needs testing:
- End-to-end with real Apple II hardware
- Full agentic workflow (user request → emulator test → deploy)
- **Proxy MCP tools** - restart MCP server to load new tools, then test `proxy_start`/`proxy_stop`
- **Agent network connection** - agent connects to proxy at configured IP, test with `/SETIP`

Known issues:
- **Agent default IP** - defaults to 192.168.64.1, use `/SETIP 192.168.65.1` for Bobbin emulator

## Working Features (Jan 31, 2026)

- **Code injection works!** - ask for any program, code is tokenized and injected
- **`/EXIT` command** - drops to BASIC so you can `RUN` your program (also `/SUSPEND`)
- **Return hooks** - type `&` or press Ctrl-Y at BASIC prompt to return to agent
- **Double-response bug fixed** - no more connection resets after code injection
- **TCP connection reuse fixed** - multiple requests now work (Bobbin virtual bridge fix)
- **Disk format auto-detection** - `save_basic_to_disk` works with both ProDOS and DOS 3.3
- **Web search** - Anthropic native web search tool for looking up Apple II info
- **Disk save tools** - `disk_save_basic`, `disk_save_binary`, `disk_save_text` in agentic mode

## Avoiding Token Waste

Every token through the API costs money and latency. These patterns avoid passing large data through the conversation:

| Bad (wastes tokens) | Good (efficient) |
|---------------------|-----------------|
| `tokenize()` then `inject_tokenized_basic(hex_data=...)` | `inject_tokenized_basic(source="10 ...")` |
| `assemble()` then `load_binary(hex_data=...)` | `assemble(source="...")` — auto-loads |
| `load_binary(hex_data="A9 00 8D...")` for data files | `load_file(path="/path/to/file.bin", address=0x6000)` |

- **`inject_tokenized_basic`**: Always use `source=` parameter. It tokenizes server-side. Never pass `hex_data`.
- **`assemble`**: Auto-loads binary into emulator memory. Never call `load_binary` after.
- **`load_file`**: Loads a local file directly into emulator memory. Use for sprites, fonts, lookup tables, pre-built binaries — anything larger than a few bytes. Never stream hex through `load_binary` for data files.
- **Write data to files first**: If you generate binary data (sprite tables, character sets, level maps), write it to a file with the Write tool, then `load_file` it. The file contents never touch the API.

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
10. **MULTI-CLIENT SOCKET** - up to 16 agents can connect simultaneously for parallel work
11. **INSTANT ENVIRONMENTS** - `load_basic_env`, `load_prodos_env`, `load_dos33_env` auto-boot + load state in one call
12. **DISK TOOLS WORK** - `python3 tools/prodos.py list/add/del` and `make_agent_disk.py` are fully functional
13. **PROXY VIA MCP** - use `proxy_start`/`proxy_stop`/`proxy_status`/`proxy_log` MCP tools instead of shell commands
14. **SET AGENT IP** - use `/SETIP x.x.x.x` on Apple II to configure proxy IP (default 192.168.64.1 rarely works)
15. **DON'T WASTE TOKENS** - use `source=` not `hex_data=`, use `load_file` not `load_binary` for data files, never stream hex through the API
