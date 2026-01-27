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
