# Apple II Agent

**Type a wish on your Apple II. Watch Claude build it. Press RETURN and play.**

You talk to your Apple II in plain English. Claude writes the program (Applesoft BASIC or 6502 assembly), tests it in an Apple //e emulator exactly the way your machine will run it, looks at the screen, fixes what's wrong, and sends it over Ethernet to your real Apple II, ready to run. When you're done, press ESC and you're back at the `AGENT>` prompt, ready to ask for changes.

```
AGENT> make a breakout game in hi-res with a score and sound

DRAWING THE PADDLE AND BRICKS FIRST.
* WRITING CODE
  JSR DRAWBRICKS
  LDA PADDLEX
  ...
  WROTE BREAKOUT.S (412 LINES)
* TESTING BREAKOUT.S IN EMULATOR
  (PREVIEW ON YOUR SCREEN - ANY KEY = LOG)
THE BALL PASSES THROUGH THE TOP ROW - FIXING THE COLLISION CHECK.
* EDITED BREAKOUT.S LINE 188
* TESTING BREAKOUT.S IN EMULATOR
* SENDING BREAKOUT TO YOUR APPLE II

BREAKOUT! ARROWS MOVE THE PADDLE, SPACE
LAUNCHES. ESC BRINGS YOU BACK HERE.

*** BREAKOUT IS READY! ***
RETURN = RUN IT   (OR TYPE TO CHAT)
```

## How It Works

An Apple II with a [Uthernet II](http://a2retrosystems.com/products.htm) Ethernet card connects to a Python proxy on your network. The proxy runs the agent loop with Claude, which has its own Apple //e emulator to test in.

```
┌──────────────┐     TCP/IP      ┌──────────────┐      API       ┌──────────┐
│   Apple II   │◄───────────────►│    Proxy     │◄──────────────►│  Claude  │
│  Uthernet II │  A2P Protocol   │  port 6502   │                │ Opus 5.5 │
└──────────────┘                 │              │                └──────────┘
                                 │  Test     ───┼──► Bobbin (Apple //e emulator)
                                 │  harness     │
                                 │  Tokenizer   │
                                 │  ca65/ld65   │
                                 └──────────────┘
```

1. You type a request at `AGENT>`.
2. Claude plans, then writes the program. You see its progress notes, and the code scrolls by as it's written.
3. Claude runs it in the emulator, launched exactly the way your Apple II will launch it (same memory layout, same return hooks), presses keys, and **looks at the screen**. Hi-res screenshots come back to Claude as real color images, and they show up on your Apple II as live previews.
4. Claude fixes problems and retests until it works.
5. The program streams to your Apple II, which shows **READY**. Press RETURN to run it.
6. **ESC** (or Ctrl-Reset) brings you back to the agent. If the program crashed or hit an error, the agent says so and pre-fills `FIX: ...`, so one RETURN gets Claude working on it.

## What It Can Do

- **Games and demos in hi-res**: Claude sees the screenshots, so it can judge and fix graphics, not just code.
- **Big programs**: on a 128K //e the agent moves itself into auxiliary memory while your program runs, so the program gets nearly all of main memory (`$0800-$BEFF`, about 46K). On 64K machines programs get `$0800-$5FFF`.
- **Applesoft BASIC**: tokenized on the proxy and placed around the hi-res pages automatically (variables go above HGR, so drawing never corrupts them).
- **6502 assembly**: ca65 syntax, any load address from `$0800`, 65C02 opcodes allowed on an enhanced //e.
- **Always a way back**: ESC in the program, ESC at the `]` prompt, `&`, Ctrl-Y, Ctrl-Reset, or a crash into BRK all return to `AGENT>` with your conversation intact.
- **Iterate**: "make the aliens faster", "add a high score". Claude remembers the program. `/RUN` plays it again and `/UNDO` brings back the previous version.

## Requirements

- **Apple IIe** (enhanced, 128K recommended) with a **Uthernet II** card in slot 3. An emulator works too.
- **Python 3.10+** on the computer running the proxy
- **Anthropic API key** ([get one here](https://console.anthropic.com/))
- **cc65** (`ca65`/`ld65`): Claude assembles machine-code programs with it, and it builds the Apple II client
- **Bobbin** emulator (included, or [build from source](https://github.com/benj-edwards/bobbin-ai))

## Quick Start

### 1. Setup

```bash
./setup.sh
```

Creates `.venv` with the Python dependencies and asks for your Anthropic API key (stored in `proxy/.env`).

### 2. Start the Proxy

```bash
./proxy.sh start
```

The proxy listens on **port 6502**.

### 3. Boot the Apple II

Boot `disks/agent_contiguous.dsk` (a 5.25" image). ProDOS starts the agent, which finds the proxy on your network by itself and remembers it. If the proxy is on another network (so the agent's broadcast can't reach it), tell it where:

```
/SETIP 192.168.1.100
```

On a Floppy Emu or similar SD card adapter, the image must sit in one unbroken piece on the card. Copy it with `python3 tools/copy_to_card.py disks/agent_contiguous.dsk "/Volumes/<card>/<folder>/Apple II Agent.dsk"`.

The disk uses ProDOS 1.9. Disks with the first ProDOS 2.4 release crashed a real //e at boot (`2002-`) while emulators booted them fine, so `make disk` (`tools/build_agent_disk.py`) starts from a ProDOS 1.9 disk that has booted on real hardware and adds the agent with [AppleCommander](https://applecommander.github.io/) rather than writing disk structures itself.

### 4. Ask for Anything

```
AGENT> make a number guessing game
AGENT> draw a mandelbrot set in hi-res
AGENT> make a space invaders game in 6502 assembly
AGENT> make the invaders speed up as you clear them
```

When the program is ready, press **RETURN** to run it. Press **ESC** to come back.

While Claude works, **ESC** asks it to stop; ESC again stops waiting.

## Commands

| Command | Description |
|---------|-------------|
| `/RUN` | Run your program again (from a fresh copy if it changed itself) |
| `/UNDO` | Bring back the previous program |
| `/VERSIONS` | Programs sent this session |
| `/SEND <FILE>` | Send a program from the proxy's `programs/` folder as is |
| `/RESET` | Forget the conversation, start fresh |
| `/MODEL O\|S\|H` | Opus 5.5 (default), Sonnet 5.5, Haiku 5.5 |
| `/EFFORT LOW\|MEDIUM\|HIGH\|XHIGH\|MAX` | How hard Claude thinks (default medium) |
| `/LIMIT <n>` | Max agent steps per request (default 60) |
| `/PROMPT <text>` | Standing instructions (e.g. `/PROMPT always use sound`) |
| `/DISPLAY 40\|40L\|80` | 40-column uppercase, 40 mixed case, or 80 columns (programs always start in 40) |
| `/EXIT` | Drop to the `]` prompt (come back with ESC, `&` or Ctrl-Y) |
| `/CLEAR` | Clear the screen |
| `/SETIP x.x.x.x` | Set the proxy's IP address (only needed if it isn't found automatically) |
| `/PORT n` | Set the proxy's port |
| ESC | Clear the line you're typing; while Claude works, stop it |
| `/IP` | Show the proxy address |
| `/HELP` | Show commands |

## Proxy Server

```bash
./proxy.sh start      # Start proxy (port 6502)
./proxy.sh stop       # Stop proxy
./proxy.sh status     # Check if running
./proxy.sh log        # Tail log output
./proxy.sh restart    # Restart
```

Or use the MCP tools from Claude Code: `proxy_start`, `proxy_stop`, `proxy_status`, `proxy_log`.

### Claude's Tools

| Tool | What it does |
|------|--------------|
| `write_file` / `edit_file` / `read_file` | Source files in `programs/` (`.BAS` or `.S`) |
| `run_in_emulator` | Build, launch in a fresh //e exactly like the real launch, type keys, wait, look. Reports running / ended / error / crashed / exited, the text screen, color screenshots, and memory-safety problems |
| `emulator_input` | Keep playing the running program |
| `emulator_memory` | Hex dump, registers and assembler labels, for debugging machine code |
| `deploy_to_apple` | Send the program to the Apple II's READY screen |
| `web_search` | Look things up |

The API key lives in `proxy/.env`:

```
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

## Testing with the Emulator Only

No hardware needed. With Claude Code and the apple2-mcp server (copy `.mcp.json.example` to `.mcp.json` and fill in where this repo is):

```
boot(machine="enhanced", uthernet2=true, disk="disks/agent_contiguous.dsk", wait_for_prompt=false)
proxy_start()
```

The emulated Apple II finds the proxy the same way a real one does (Bobbin passes its broadcast to this machine and forwards 192.168.64.x/65.x to localhost).

### Automated tests

```bash
tests/run_all.sh              # everything that needs no API calls (~15 minutes)
tests/run_all.sh --real-speed # ...plus the end-to-end run at a real 1 MHz
.venv/bin/python tests/live_agent.py "make a breakout game" --start-proxy   # one real request
```

The emulated Uthernet II behaves like a real network peer (full-size TCP segments, resends, the Apple's window), and Claude's own test emulator runs at real speed with uninitialized memory, so what passes here is what a real Apple II will see. Tests run one at a time: their proxies all answer discovery on UDP 6502.

## How Programs Get Back to the Agent

The agent reserves `$03C7-$03FF` in page 3 (the rest of page 3 is free for programs):

| Address | Purpose |
|---------|---------|
| `$03C7` | Crash marker |
| `$03C8` | BRK vector target: marks a crash, goes to `$03D0` |
| `$03D0` | The way home. Resident: `JMP` into the agent. Exchange: `STA $C003`, so the next instruction comes from aux memory, where the agent is waiting |
| `$03D3` | Keyboard hook: ESC at the `]` prompt goes home |
| `$03F0-$03FA` | BRK, reset, `&` and Ctrl-Y vectors, all pointed home |

In EXCHANGE mode (128K) the program bytes are staged in aux memory while they download. At launch the program's low pages are copied into main memory and `$6000-$BEFF` (where the agent lives) is swapped with aux by a small routine in the stack page. The return trip swaps it back. The staged copy stays in aux, so `/RUN` starts the program fresh.

## Project Structure

```
proxy/                    # Proxy server (Python)
  unified_proxy.py        # TCP server, sessions, commands, deploy packets
  agentic_claude.py       # Claude agent loop: tools, streaming, previews
  deploy.py               # Program building and memory layout (BASIC + ca65)
  emulator_bridge.py      # Test harness on Bobbin's control socket
  basic_tokenizer_streaming.py  # Applesoft tokenizer
  a2p_protocol.py         # Wire protocol

asm/                      # Apple II client (6502, ca65)
  agent.s                 # UI, TCP, A2P protocol, display
  agent_deploy.s          # Deploy, launch, return-to-agent
  agent_sysload.s         # AGENT.SYSTEM loader ($2000 -> $6000)

programs/                 # Claude's workspace (program sources, history/)
src/apple2_mcp/           # MCP server for Claude Code
disks/agent_contiguous.dsk  # Boot disk: PRODOS, AGENT.SYSTEM, BASIC.SYSTEM
states/                   # Emulator snapshots used by the test harness
library/                  # 6502/Apple II reference library
tools/                    # Disk tools
```

## The A2P Protocol

Packets are `'A2' type len(2) seq data... checksum` over TCP.

| Type | Name | Direction | Description |
|------|------|-----------|-------------|
| 0x00 | INIT | Apple → proxy | Capabilities (80-col, 128K, deploy support), model, display, version |
| 0x01 | CHAT | Apple → proxy | What you typed |
| 0x02 | RESP | proxy → Apple | Text for the scrolling log |
| 0x03 | CODE | proxy → Apple | BASIC at `$0801` (old clients) |
| 0x04 | STATUS | proxy → Apple | Status line; `DONE` ends a response |
| 0x05 | ACK | both | Acknowledgment |
| 0x07 | LOAD | proxy → Apple | Program bytes: address + data |
| 0x08 | DEPLOY | proxy → Apple | Start a transfer: main or aux, program or preview |
| 0x09 | RUN | proxy → Apple | Launch descriptor; the Apple shows READY |
| 0x0A | SHOW | proxy → Apple | Text or HGR preview |

## Building from Source

```bash
make disk               # Build AGENT.SYSTEM and a fresh boot disk
```

Requires [cc65](https://cc65.github.io/).

## Bobbin Emulator

The proxy uses [Bobbin](https://github.com/benj-edwards/bobbin-ai), an Apple II emulator with a JSON control socket designed for AI integration: Apple II+ and enhanced //e, Uthernet II with a virtual bridge to the host, 128KB state snapshots, GR/HGR/DHGR/DGR export, stepping, breakpoints and tracing.

## License

MIT
