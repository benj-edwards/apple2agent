# Apple II Agent - Testing Guide

## What's Built

### 1. Claude Streaming Proxy (`proxy/claude_streaming_proxy.py`)
- HTTP server on port 8080
- Accepts natural language requests
- Calls Claude API to generate BASIC code
- Returns tokenized BASIC in BAS2 format
- Validates syntax before sending

### 2. Claude Code UI (`build/CLAUDE.CODE`)
- 8094 bytes, loads at $6000
- Full-screen terminal interface
- Input line at bottom
- Streams progress from proxy
- Installs `&` hook for quick return
- Requires Uthernet II

### 3. IP Setup Program (`build/IP.SETUP`)
- BASIC program for configuring proxy IP
- Stores IP at $0300-$0303
- Sets flag at $0304 ($A2)
- Default: 192.168.64.1

### 4. Disk Image (`disks/claude_code.dsk`)
Contains:
- PRODOS
- BASIC.SYSTEM
- CLAUDE.CODE (BIN)
- IP.SETUP (BAS)

## Testing on Real Hardware

### Prerequisites
1. Apple IIe with 128KB
2. Uthernet II in slot 3
3. Network connection to proxy server

### Setup
1. Start the proxy on your Mac/PC:
   ```bash
   cd proxy
   export ANTHROPIC_API_KEY='your-key'
   python3 claude_streaming_proxy.py --port 8080
   ```

2. Boot Apple IIe with `claude_code.dsk`

3. Run IP setup:
   ```
   -IP.SETUP
   ```
   Enter your proxy server's IP address

4. Run Claude Code:
   ```
   -CLAUDE.CODE
   ```

5. At the `CLAUDE>` prompt, type your request

### Testing with Bobbin Emulator

The emulator has some quirks:
- Boot without disk works best
- Some direct-mode commands fail (use programmed mode)
- `load_binary` and `poke` work when debugger cooperates

```bash
# Start emulator with Uthernet
# Boot without disk, then load manually
```

## Proxy Endpoints

- `POST /claude/binary` - Generate BAS2 program
- `POST /claude/stream` - Stream progress + BAS2
- `GET /status` - Health check

## BAS2 Protocol

```
"BAS2"              (4 bytes magic)
total_length        (2 bytes, little-endian)
start_address       (2 bytes, little-endian)
[chunk_size + data] (repeated)
0x0000              (end marker)
```

## Known Issues

1. **Emulator Disk Boot**: ProDOS disk sometimes hangs at "System OK" with Uthernet enabled
2. **Debugger Mode**: MCP tools intermittently fail to enter debugger
3. **Direct Commands**: Immediate-mode BASIC commands sometimes give SYNTAX ERROR in emulator

## Critical Bug Fix: Debugger Single-Step Mode (2025-01-26)

### Problem Identified
We were sending **empty lines** to verify we're at the Bobbin debugger prompt. However, in Bobbin's debug.c (line 310-313):
```c
if (HAVE("") || HAVE(" ") || HAVE("s")) {
    loop = false;  // but debugging_flag stays TRUE!
}
```
An empty line triggers **single-step mode** - the debugger executes one instruction and re-enters, causing:
- Debugger output (`3735- A=17 X=00...`) after every instruction
- Asterisk (`*`) step prompt instead of BASIC prompt (`]`)
- All commands interpreted as debugger commands
- SYNTAX ERROR on any BASIC command

### Fix Applied (emulator.py)
1. **enter_debugger()**: Changed prompt verification from empty line to `help` command
2. **exit_debugger()**: Simplified to just send `c` (continue) without any verification

```python
# In enter_debugger - use 'help' to verify, NOT empty line:
self.process.sendline("help")  # NOT sendline("")

# In exit_debugger - just continue:
self.process.sendline("c")
```

### Testing Required After Fix
1. **Basic Commands After Peek**: `boot -> PRINT 1 -> peek -> PRINT 2` should work
2. **Program Injection**: `boot -> inject_tokenized_basic -> LIST -> RUN` should work
3. **Graphics Capture**: `boot -> GR program -> capture_gr -> TEXT` should work
4. **Multiple Debugger Ops**: `boot -> peek -> poke -> peek -> PRINT` should work

### Current Workaround (If Fix Not Active)
1. Use `type_text` to enter BASIC programs (stdin-based, no debugger)
2. Use `capture_gr`/`capture_hgr` for graphics (uses debugger, corrupts state)
3. Shutdown and reboot emulator after each capture

## Files

```
proxy/
  claude_streaming_proxy.py  - Main proxy server
  basic_tokenizer_streaming.py - BASIC tokenizer

asm/
  claude_code_ui.s           - Apple II Claude Code source

build/
  CLAUDE.CODE                - Compiled binary (8094 bytes)
  IP.SETUP                   - Tokenized BASIC (483 bytes)

disks/
  claude_code.dsk            - Ready-to-use ProDOS disk
```
