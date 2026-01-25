# Apple II Agent

Control a real Apple IIe over TCP/IP using AI. This project enables autonomous AI interaction with vintage Apple II hardware via Uthernet II network card.

## Hardware Requirements

- Apple IIe (Enhanced recommended)
- Uthernet II network card (slot 3)
- ProDOS-bootable disk drive
- Network connection

## Software Requirements

- Python 3.11+
- cc65 toolchain (ca65, ld65)
- Claude Code with MCP support

## Quick Start

### 1. Install Dependencies

```bash
# macOS
brew install cc65

# Verify installation
ca65 --version
ld65 --version
```

### 2. Configure IP Address

Edit `asm/remote_shell.s` lines 37-40 to set your Mac's IP address:

```assembly
SERVER_IP_1 = 192      ; Your Mac's IP
SERVER_IP_2 = 168
SERVER_IP_3 = 1
SERVER_IP_4 = 43
```

### 3. Build and Install

```bash
make              # Build REMOTE.BIN
make install      # Add to agent.dsk
```

### 4. Boot the Apple II

1. Copy `disks/agent.dsk` to physical media (FloppyEmu, CFFA, etc.)
2. Boot from the disk
3. The remote shell starts automatically and connects to your Mac

### 5. Start the Proxy

```bash
cd proxy
python3 remote_proxy.py
```

You should see `[READY]` when the Apple II connects.

## Using with Claude Code

1. Open Claude Code in this directory
2. The MCP server provides Apple II control tools
3. Claude can peek/poke memory, run BASIC programs, and more

### Example Session

```
You: Read the character at screen position 0,0
Claude: [Uses peek tool to read $0400]
        The character code is $C1 (letter 'A')

You: Write "HELLO" to the screen
Claude: [Uses poke tool to write to $0400-$0404]
        Done. "HELLO" is now displayed at the top-left.
```

## Project Structure

```
proxy/           - Python proxy servers
asm/             - 6502 assembly source
libs/ip65/       - TCP/IP stack library
tools/           - Disk utilities
disks/           - Bootable disk images
build/           - Compiled binaries
src/apple2_mcp/  - MCP server for Claude Code
```

## Proxy Commands

| Command | Description |
|---------|-------------|
| `P addr` | Peek memory |
| `O addr val` | Poke memory |
| `D addr len` | Dump memory region |
| `L addr hex` | Load bytes to memory |
| `C addr` | Call subroutine |
| `QS text` | Print text |
| `X` | Exit remote shell |

## Testing with Emulator

For development without hardware, use Bobbin emulator with Uthernet II support.

### Get Bobbin

```bash
# Clone the AI-enabled fork
git clone -b bobbin-ai https://github.com/benj-edwards/bobbin.git
cd bobbin

# Build
./configure
make

# Get Apple II ROMs (required - not included due to copyright)
# Place in bobbin/src/roms/:
#   apple2e_enh.rom (16KB) - Enhanced Apple IIe ROM
# ROMs can be dumped from real hardware or found online
```

### Run with Emulator

```bash
# Terminal 1: Start proxy
cd proxy && python3 remote_proxy.py

# Terminal 2: Run emulator
cd /path/to/bobbin/src
./bobbin --simple -m enhanced --uthernet2 --disk /path/to/disks/agent_test.dsk
```

## License

See individual components for licensing.
- IP65 library: BSD license
- Assembly code: MIT license
