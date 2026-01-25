# Apple II Agent - Claude Code Instructions

This project enables AI-controlled Apple IIe over TCP/IP using Uthernet II.

## Quick Start

### 1. Start the Proxy Server
```bash
cd proxy && python3 remote_proxy.py
```

### 2. Boot the Apple IIe
- Insert `disks/agent.dsk` (or boot via network)
- The remote shell auto-runs and connects to the proxy
- Proxy shows `[READY]` when connected

### 3. Send Commands
The proxy provides an interactive shell. Commands:

| Command | Description | Example |
|---------|-------------|---------|
| `P addr` | Peek (read byte) | `P C000` |
| `O addr val` | Poke (write byte) | `O 0400 C1` |
| `D addr len` | Dump memory | `D 0400 40` |
| `L addr hex...` | Load bytes | `L 6000 A9 00 8D...` |
| `C addr` | Call subroutine | `C 6000` |
| `QS text` | Quick string (print) | `QS HELLO` |
| `SCAN` | Memory scan | `SCAN` |
| `X` | Exit shell | `X` |

---

## Agentic Mode

For autonomous operation, use the agentic proxy:
```bash
cd proxy && python3 agentic_proxy.py
```

This provides:
- BASIC program injection via tokenizer
- Screen capture and parsing
- Error detection and recovery
- Full autonomous loop

---

## IP Addresses

| Target | IP Address | Port | Disk |
|--------|------------|------|------|
| Real Apple IIe | 192.168.1.50 | 8080 | `agent.dsk` |
| Bobbin emulator | 192.168.64.1 | 8080 | `agent_test.dsk` |

To change IP, edit `asm/remote_shell.s` lines 37-40 and rebuild.

---

## Build Process

```bash
# Build the remote shell
make

# Install to production disk (real hardware)
make install

# Install to test disk (emulator)
make install-test

# View disk contents
make catalog
```

### Manual Build

```bash
# Assemble
ca65 --cpu 6502 -I libs/ip65/inc -o build/remote_shell.o asm/remote_shell.s

# Link
ld65 -C asm/agent.cfg -o build/REMOTE.BIN build/remote_shell.o \
    libs/ip65/ip65_tcp.lib \
    libs/ip65/drivers/a2uther2.lib \
    apple2.lib

# Add to disk
python3 tools/prodos.py add disks/agent.dsk build/REMOTE.BIN REMOTE.BIN BIN 6000
```

---

## MCP Tools

The MCP server provides Apple II control tools:

### ProDOS Disk Tools
- `prodos_list` - List files on disk
- `prodos_add` - Add binary file to disk
- `prodos_del` - Delete file from disk

### Emulator Tools (Bobbin)
- `boot` - Start emulator
- `type_text` - Type on keyboard
- `read_screen` - Capture text screen
- `capture_gr/hgr` - Capture graphics
- `peek/poke` - Memory access
- `run_basic` - Execute BASIC command
- `inject_tokenized_basic` - Load BASIC program

---

## Project Structure

```
apple2agent/
├── CLAUDE.md           # This file
├── README.md           # Human setup guide
├── Makefile            # Build automation
├── .mcp.json           # MCP server config
│
├── proxy/              # Python proxy servers
│   ├── remote_proxy.py       # Main interactive proxy
│   ├── agentic_proxy.py      # Autonomous agent loop
│   ├── basic_tokenizer.py    # BASIC tokenizer
│   ├── program_injector.py   # Program injection
│   ├── screen_reader.py      # Screen capture
│   └── error_parser.py       # Error detection
│
├── src/apple2_mcp/     # MCP server
│   ├── server.py
│   └── emulator.py
│
├── asm/                # Assembly sources
│   ├── remote_shell.s  # Remote shell (main)
│   └── agent.cfg       # Linker config
│
├── libs/ip65/          # TCP/IP stack
│
├── tools/              # Disk utilities
│   └── prodos.py       # ProDOS disk tool
│
├── disks/              # Disk images
│   ├── agent.dsk       # Production (192.168.1.50)
│   └── agent_test.dsk  # Testing (192.168.64.1)
│
└── build/              # Build output
    └── REMOTE.BIN      # Compiled binary
```

---

## Memory Map

```
$0000-$00FF   Zero page (IP65 uses $06-$07)
$0100-$01FF   Stack
$0200-$02FF   Input buffer
$0400-$07FF   Text screen
$0800-$5FFF   BASIC / free RAM
$6000-$7A72   REMOTE SHELL (~7KB)
$7A73-$95FF   Free RAM
$9600-$BFFF   ProDOS
$C000-$C0FF   Soft switches (DANGEROUS)
$D000-$FFFF   ROM
```

### Safe PEEK Regions
- `$0000-$BFFF` - Main RAM
- `$D000-$FFFF` - ROM

### AVOID
- `$C000-$C0FF` - Soft switches have side effects!

---

## Remote Shell Protocol

```
Apple II -> Proxy:  READY\r\n
Proxy -> Apple II:  P C000\r\n     (command)
Apple II -> Proxy:  OK 8D\r\n      (response)
```

### Response Codes
- `OK value` - Success with hex value
- `OK` - Success (no value)
- `ERR msg` - Error with message

---

## Testing with Emulator

### Bobbin (Recommended)
```bash
# Terminal 1: Start proxy
cd proxy && python3 remote_proxy.py

# Terminal 2: Run Bobbin
cd /path/to/bobbin/src
./bobbin --simple -m enhanced --uthernet2 --disk /path/to/disks/agent_test.dsk
```

### MAME (via Ample)
```bash
/Applications/Ample.app/Contents/MacOS/mame64 apple2e \
  -flop1 disks/agent.dsk \
  -window \
  -sl3 uthernet2
```

Note: Homebrew MAME does NOT have Uthernet II.

---

## Common Issues

| Problem | Cause | Solution |
|---------|-------|----------|
| "Connection refused" | Wrong IP in binary | Rebuild with correct IP |
| Network timeout | Wrong emulator | Use Ample MAME or Bobbin |
| PEEK crashes | Zero page conflict | IP65 uses $06-$07 |
| Binary crashes | Wrong load address | Use agent.cfg ($6000) |
