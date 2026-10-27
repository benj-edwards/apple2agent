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

## Git Identity

For all commits, use this identity:

```
git config user.name "<your name>"
git config user.email "<your email>"
```

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

**Agentic mode is ON by default.** Every message runs the full loop in `proxy/agentic_claude.py`:

1. Claude (Opus 5.5 by default, streaming, adaptive thinking, `display: "updates"`) writes the program into `programs/` with `write_file`/`edit_file`.
2. `run_in_emulator` builds it (`proxy/deploy.py`: Applesoft tokenizer or ca65/ld65) and launches it in a fresh Bobbin **exactly the way the real Apple II will** (same memory layout, same page-3 return hooks), types keys, waits, and reports: running / ended at ] / BASIC error / crashed into BRK / exited to agent, the text screen, a **color PNG screenshot** (Claude sees it), and memory-safety problems (writes into agent memory, page-3 hooks, $BF00).
3. Claude fixes and retests, then `deploy_to_apple` streams it to the Apple II, which shows **READY - RETURN TO RUN**.
4. ESC (program-implemented), ESC at ] or at an INPUT prompt, &, Ctrl-Y, Ctrl-Reset or BRK all return to `AGENT>`. Crashes and BASIC errors come back pre-filled as `FIX: ...`.

Everything streams to the Apple II while it happens: progress notes, tool steps, code lines as they're written, emulator text output, and **HGR screenshots as live previews** (SHOW packet; any key flips back to the log).

## Architecture

```
┌──────────────┐      TCP/IP      ┌──────────────┐      API      ┌──────────┐
│   Apple II   │◄────────────────►│    Proxy     │◄─────────────►│  Claude  │
│  (Uthernet)  │   A2P (port 6502)│  agentic_    │   + Tools     │ Opus 5.5 │
└──────────────┘                  │  claude.py   │               └──────────┘
 AGENT.SYSTEM                     │  deploy.py   │
                                  │  emulator_   │──► test Bobbin (bridge socket)
                                  │  bridge.py   │
                                  └──────────────┘
```

**Two ways to control an emulator:**
1. **Proxy** uses `emulator_bridge.py` → its own test Bobbin (`/tmp/bobbin_bridge.sock`)
2. **Claude Code** uses the MCP server → `/tmp/bobbin.sock` (e.g. the emulated "real" Apple II)

### Launch modes (asm/agent_deploy.s + proxy/deploy.py must agree)

- **EXCHANGE** (128K //e, the normal case): program may use `$0800-$BEFF`. LOAD bytes are staged in **aux** memory. At launch a blob in the stack page copies the program's pages below `$6000` aux→main and swaps `$6000-$BEFF` main↔aux. Return swaps back. `/RUN` replays from the pristine aux copy.
- **RESIDENT** (64K): program in `$0800-$5FFF`, agent stays at `$6000+`.

Page 3 contract: `$03C7` crash mark, `$03C8` BRK stub, `$03D0` return entry (resident `JMP agent_reentry`; exchange `STA $C003` → aux `$03D3` `JMP agent_xreturn`), `$03D3` KSW hook (ESC typed into GETLN, i.e. RDKEY called from `$FDxx`: the `]` prompt or an INPUT line; GET still gets ESC), `$03F0-$03FA` vectors. Programs own `$0300-$03C6`.

## Quick Start

### 1. Start Proxy
```bash
./proxy.sh start            # or MCP proxy_start(port=6502)
```
API key in `proxy/.env`. Python deps live in `.venv` (`./setup.sh`); `unified_proxy.py` re-execs itself into `.venv` when started with the system python3.

### 2. Boot the Apple II (emulated)
```
mcp__apple2-mcp__boot(machine="enhanced", uthernet2=true, disk="disks/agent_contiguous.dsk", wait_for_prompt=false)
```
The disk boots **PRODOS → AGENT.SYSTEM** directly (no BASIC.SYSTEM, no BRUN). The agent finds the proxy by broadcast (`A2AGENT?` to UDP 6502; the proxy answers with its port) and goes straight to `AGENT>`. Bobbin passes the broadcast to localhost and routes 192.168.64.x/65.x to localhost. A found address is saved to `CLAUDECONF` on the boot disk.

### 3. Talk Naturally
- "Make a program that prints the Fibonacci sequence"
- "Make a breakout game in hi-res"
- `/SEND TESTHGR.BAS` sends a workspace file without Claude (good for testing deploys)

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

# Breakpoints (stop *before* the instruction; poll cpu() for paused/break_hit)
sock.break_set(0x6000)   # Break at address
sock.watch_set(0x400)    # Break when memory changes
bps = sock.break_list()  # List all breakpoints
cpu = sock.get_cpu_state()  # ... 'paused': True, 'break_hit': <id>
sock.resume()            # runs the instruction it stopped on, then can stop there again
# (The first visit to $2000 is the PRODOS kernel's loader, the second is AGENT.SYSTEM.)

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

**`proxy/emulator_bridge.py`** runs the proxy's own test Bobbin (socket `$APPLE2_BRIDGE_DIR/bobbin_bridge.sock`, default `/tmp`). The MCP server is for Claude Code; **the proxy never calls MCP tools.**

The agent loop uses the **test harness**:

```python
from emulator_bridge import get_bridge
import deploy
b = get_bridge()
prog = deploy.build_basic(open('programs/TESTHGR.BAS').read(), 'TEST', has_aux=True)
b.run_program(prog)      # builds a launch state file (program bytes, page-3 hooks,
                         # BASIC pointers, guard patterns) and load_states it
b.send_input("{RIGHT}{SPACE}")
obs = b.observe()        # status, screen, mode, PNG image, hgr_page, problems
b.shutdown()
```

Gotchas learned the hard way:
- Bobbin `--simple` sets **stdin O_NONBLOCK**. Never let it inherit someone else's stdin (it killed the MCP server once). The bridge gives it `stdin=PIPE`; `proxy_control` starts the proxy with `stdin=DEVNULL`.
- Unix socket paths max out at 104 chars on macOS: keep `APPLE2_BRIDGE_DIR` short.
- Never `cp` over a running/signed `bobbin` binary: macOS SIGKILLs it (exit 137). `rm` then `cp`.
- `get_softswitches()` returns the inner dict already.
- The harness runs Bobbin with **`--no-turbo`** (real 1 MHz): `--simple` is otherwise unthrottled (~40x), and Claude judges game speed from these runs.
- `run_program` fills main and aux `$0800-$BEFF` with junk first: a real Apple II's memory is never clean, and programs that assume zeros must fail here.

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
# Example: python3 tools/prodos.py add disks/mydisk.dsk build/GAME.BIN GAME BIN 0800

# Delete a file from disk
python3 tools/prodos.py del <disk> <prodos_name>

# Build the agent boot disk (what `make disk` runs)
python3 tools/build_agent_disk.py [output.dsk] [--test]
```

### The boot disk: copy a disk the real machine boots, never build from scratch

**A real //e (enhanced, Floppy Emu) crashed at `2002-` on disks with the ProDOS 2.4 kernel** (`disks/ProDOS_2_4.dsk`, the first 2.4 release), even the stock 2.4 disk, and on disks built from scratch by `tools/make_agent_disk.py`. Bobbin boots all of them. The disk that boots it is the January one (ProDOS 1.9 + BASIC.SYSTEM, made with AppleCommander), so:

- `disks/base_jan19.dsk` = that January disk with the old agent files deleted.
- `tools/build_agent_disk.py` copies it and adds `AGENT.SYSTEM` with **AppleCommander** (`tools/ac.jar` or `$AC_JAR`), checks that AGENT.SYSTEM is the first `.SYSTEM` entry and reads back exactly, and boot-tests it.
- `src/apple2_mcp/README.md` ("Disk Images - The Big Gotchas") says the same: never write ProDOS structures by hand. `make_agent_disk.py` / `make_diag_disk.py` still do (diag disk only).

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

### Copying a disk to an SD card (Floppy Emu-style adapter)

The adapter needs each image to be **one contiguous run of clusters** on the FAT card. A plain `cp` (or `rm` + `cp`) on macOS can fragment it; the adapter then says "file not contiguous", or may silently read the wrong clusters (the first real-hardware boot most likely got zeros for AGENT.SYSTEM that way). Always use:

```bash
python3 tools/copy_to_card.py disks/agent_contiguous.dsk "/Volumes/<card>/<folder>/Apple II Agent.dsk"
sudo python3 tools/fat_check.py "/Volumes/<card>" "<folder>/Apple II Agent.dsk"   # sudo: the user runs this one
```

(`disks/agent_diag.dsk` is built from scratch with ProDOS 2.4 and crashes on the real machine.)

### Rebuilding Agent Disk

```bash
make disk                               # AGENT.SYSTEM + disks/agent_contiguous.dsk
python3 tools/prodos.py list disks/agent_contiguous.dsk  # PRODOS, AGENT.SYSTEM, BASIC.SYSTEM
```

### Tool Architecture

```
tools/prodos.py          # Unified CLI (delegates to below)
  ├── tools/prodos_add.py    # Add files (handles .dsk/.po format)
  └── tools/prodos_delete.py # Delete files, list catalog

tools/build_agent_disk.py # The agent boot disk: base_jan19.dsk + AppleCommander (make disk)
tools/make_agent_disk.py # From scratch, ProDOS 2.4: crashes the real //e (diag disk only)
tools/prodos_disk.py     # Reference library (not used by CLI)
```

## Key Files

| File | Purpose |
|------|---------|
| `proxy/agentic_claude.py` | **THE AGENT LOOP** - system prompt, tools, streaming display, previews |
| `proxy/deploy.py` | **Program building + memory layout** (BASIC around HGR pages, ca65 binaries, RUN descriptor) - shared by test harness and real deploys |
| `proxy/emulator_bridge.py` | **Test harness** - launches programs like the real Apple II, observes, screenshots |
| `proxy/unified_proxy.py` | Proxy: sessions, commands, DEPLOY/LOAD/RUN/SHOW senders |
| `proxy/a2p_protocol.py` | Wire protocol |
| `asm/agent.s` | Apple II client: UI, TCP, packets |
| `asm/agent_deploy.s` | **Deploy/launch/return**: LOAD staging, READY prompt, EXCHANGE blob, page-3 hooks, reentry |
| `asm/agent_screen.s` | The agent's screen routines (`vid80_out`, `clear_eol`, `clear_screen`, `read_key`, `text40`): 80 columns without the firmware. Agent UI code calls these, never `CLREOL`/`HOME`/`RDKEY` directly. NB `VTAB` in agent.s is the ROM's TABV: it sets CV from A |
| `asm/agent_sysload.s`, `asm/agent_sys.cfg` | AGENT.SYSTEM loader ($2000 -> $6000) |
| `programs/` | Claude's workspace; `programs/history/` = every deployed version |
| `src/apple2_mcp/` | MCP server for emulator control (used by Claude Code) |
| `tools/build_agent_disk.py` | The boot disk: `disks/base_jan19.dsk` (ProDOS 1.9) + AGENT.SYSTEM via AppleCommander |
| `library/` | 6502/Apple II reference library |

## Commands

Handled on the Apple II: `/RUN`, `/EXIT` (`/SUSPEND`, `/QUIT`), `/SETIP`, `/PORT`, `/IP`, `/SAVE`, `/LIST`, `/CODE`, `/CLEAR` (screen), `/MORE`, `/DISPLAY` and `/MODEL` (also forwarded), `/RESET` (forwarded). Matching is whole-word; **anything else goes to the proxy**: `/HELP`, `/UNDO`, `/VERSIONS`, `/SEND <FILE>`, `/EFFORT`, `/LIMIT`, `/PROMPT`, `/AGENT`, `/CHAT`.

Sent by the Apple II itself: `/STOP` (ESC while waiting; a second ESC stops waiting) and `/RERUN` (`/RUN` of machine code that reaches `$6000`+, or any RESIDENT machine code: a fresh copy, run on arrival). ESC at `AGENT>` clears the line. `/EXIT` leaves a plain `]` prompt; ESC there, `&` and Ctrl-Y all land on RETURN_ENTRY.

### Workflow

```
AGENT> make a hello world      -> Claude writes, tests, deploys
*** HELLO IS READY! ***         -> RETURN runs it (typing anything else = keep chatting)
(program runs; ESC / Ctrl-Reset)
WELCOME BACK!                   -> /RUN plays again, or ask for changes
```

## A2P Protocol

| Type | Name | Description |
|------|------|-------------|
| 0x00 | INIT | caps (CAP_80_COL 1, CAP_AUX_RAM 8, CAP_DEPLOY $10), model, display, version (2) |
| 0x01 | CHAT | User message |
| 0x02 | RESP | Text for the log (flag 1 = final) |
| 0x03 | CODE | BASIC at $0801 (legacy clients only) |
| 0x04 | STATUS | Status line; `DONE` ends a response |
| 0x05 | ACK | Acknowledgment |
| 0x07 | LOAD | addr(2) + up to 126 bytes |
| 0x08 | DEPLOY | mode (0 main, 1 aux) + purpose (0 program, 1 preview) |
| 0x09 | RUN | descriptor: kind, start, prgend, lomem, himem, mode, lo/hi page, name |
| 0x0A | SHOW | 0 text, 1 HGR preview |

## Build

```bash
make agent              # build/AGENT.SYSTEM (and AGENT.BIN, which is now too big to BRUN)
make disk               # ...and a fresh disks/agent_contiguous.dsk
```

## Testing

```bash
tests/run_all.sh                 # all no-API tests, one after another (~15 min)
tests/run_all.sh --real-speed    # + e2e at a real 1 MHz
.venv/bin/python tests/live_agent.py "<request>" --start-proxy --out <dir>   # one real Claude request
BOBBIN_U2_RESET_ON_RESET=1 .venv/bin/python tests/e2e_agent.py           # Uthernet resets with Ctrl-Reset
```

- **Each test has its own discovery channel**: its Bobbin gets `BOBBIN_U2_UDP_PORT=<port+10000>` (Bobbin sends the virtual network's UDP there instead of 6502) and its proxy `APPLE2_DISCOVERY_PORT=<port+10000>`. Without that, a test's Apple II found the everyday proxy on 6502 (it happened). Ports: e2e/soak 6599, setup 6598, display 6597, live 6596; the everyday proxy is 6502. Still run them one at a time (they share `/tmp` work dirs).
- Test proxies use `APPLE2_PROXY_CONTROL_DIR` so they never touch `/tmp/claude/proxy.pid` (the everyday proxy's).
- Bobbin's virtual network behaves like a real host (536-byte segments, the Apple's window, resends, duplicate drops) - it caught an ACK bug the old one hid. If something passes only with small segments, it's broken.
- `BOBBIN_U2_CORRUPT_LEN_EVERY=n` misreports every nth frame's length in the W5100 RX ring (a misread header): the stock IP65 driver then misreads every frame after; ours skips to the next frame (`libs/ip65/drivers/w5100.s`).
- Stall reports from the real Apple II (watchdog `/RESYNC`) land in `logs/stall_reports.log`, decoded.
- `BOBBIN_U2_CORRUPT_EVERY=n` garbles one byte of every nth virtual TCP segment, as a flaky bus on the real //e did (IP65 didn't check TCP checksums: the first real deploy stalled and lost a packet). `run_all.sh` runs e2e with n=5.
- Test disks write a 10-byte `CLAUDECONF` with the stall watchdog **off** (byte 10 = 0): Bobbin runs unthrottled, so 20 emulated seconds pass in half a real one. `e2e_display.py` tests the watchdog on its own (2 s).

## Current Status (2026-10-23)

All automated tests pass (display, first-run setup, e2e at turbo and real speed, with and without a Uthernet reset on Ctrl-Reset, 25-cycle soak). Live Claude runs: times table, hi-res breakout (machine code), lo-res snake (machine code), Applesoft hi-res sketch, ESC-to-stop + follow-up request. 80 columns works (the agent draws it itself, `asm/agent_screen.s`; programs start in 40 and the agent comes back in 80).

Real hardware (2026-10-23): **the agent boots on a real enhanced //e (Floppy Emu, Uthernet II), finds the proxy and chats with Claude.** Every earlier disk crashed at `2002-`: they all had the ProDOS 2.4 kernel (the stock 2.4 disk crashes too). The disk is now built from a January ProDOS 1.9 disk (see "The boot disk" above). Not yet tried on the real machine: a deploy and a program run, 80 columns.

Port: **6502** everywhere (8080 is often taken).

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

1. **USE THE CONTROL SOCKET** - `BobbinControlSocket` is the reliable way to control an emulator
2. **THE PROXY USES ITS OWN TEST BOBBIN** via `emulator_bridge.py`, never MCP tools
3. **deploy.py IS THE SINGLE SOURCE OF TRUTH** for memory layout; the test harness and real deploys must launch identically
4. **agent_deploy.s and deploy.py must agree** on the RUN descriptor, page-3 addresses and modes
5. **Progress streams to the Apple II** - the user watches Claude work, so keep the loop chatty
6. **Every program must exit with ESC** (BASIC `TEXT : HOME : &`, machine code RTS / `JMP $03D0`)
7. **Page 3 $03C7-$03FF belongs to the agent**; programs get $0300-$03C6
8. **Agentic mode is ON by default** - `/AGENT` toggles it off
9. **PROXY VIA MCP** - `proxy_start(port=6502)` etc.; the proxy hops into `.venv` by itself
10. **Bobbin fixes go to the canonical Bobbin source**, then rebuild and `rm` + `cp` the binary into `bobbin/src/bobbin`
11. **DON'T WASTE TOKENS** - MCP: use `source=` not `hex_data=`, `load_file` not `load_binary`
12. **TESTS RUN ONE AT A TIME** - `tests/run_all.sh`; each has its own discovery port (`BOBBIN_U2_UDP_PORT`/`APPLE2_DISCOVERY_PORT`), never the everyday 6502
13. **SD CARD: `tools/copy_to_card.py`**, never plain `cp` - the adapter needs contiguous files
14. **BOOT DISK = `make disk`** (`base_jan19.dsk` + AppleCommander). Never build ProDOS disks from scratch; ProDOS 2.4 crashed a real //e
