# Apple II Agent: Development Report

## An AI That Programs a 1977 Computer

**Apple II Agent** is an autonomous AI coding environment that lets you talk in plain English to an Apple II, and Claude — Anthropic's AI — writes, tests, debugs, and deploys software for you. It works on real Apple II hardware connected to Ethernet, and in an emulator for development. The entire project was built by Claude Code (Anthropic's agentic coding tool) in collaboration with a human developer, mostly over a 17-day stretch in late January and early February 2026.

**Repository:** https://github.com/benj-edwards/apple2agent
**License:** MIT

---

## What It Does

You sit at an Apple II. You type:

```
AGENT> make a number guessing game
```

The Apple II sends your message over Ethernet to a proxy server on your local network. The proxy calls Claude, which has access to a full development toolkit: an Apple II emulator, BASIC tokenizer, 6502 assembler, memory inspector, graphics capture, and disk tools. Claude writes the code, boots the emulator, injects the program, runs it, reads the screen to check the output, fixes any bugs, retests, and when it's satisfied, deploys the working program to your real Apple II. The whole process streams status updates to your 40-column screen in real-time — you watch Claude work.

It handles Applesoft BASIC and 6502 assembly language. It can generate lo-res graphics, hi-res graphics, double hi-res, text programs, games, utilities — anything that runs on an Apple II.

### The Agentic Loop

This is the core innovation. Claude doesn't just generate code and hope for the best. It runs an **agentic loop** — up to 20 rounds of tool use per request — where it:

1. Writes code (BASIC or 6502 assembly)
2. Boots an Apple II emulator (Bobbin)
3. Injects the code into emulator memory
4. Runs the program
5. Reads the screen output
6. If there's a bug, analyzes the error, fixes the code, and goes back to step 3
7. Captures graphics output if it's a visual program
8. Deploys the working code to the real Apple II
9. Tells the user it's ready

This is the same develop-test-iterate loop a human programmer uses, running autonomously on a machine from 1977.

---

## How It Works (Technical Architecture)

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

### The Apple II Client

A 6502 assembly program (`AGENT.BIN`, ~8KB) that runs on the Apple II. It handles:

- **Uthernet II networking** via the IP65 TCP/IP stack — a complete TCP implementation for 6502
- **A2P protocol** — a custom binary protocol for reliable communication with the proxy
- **Full-screen UI** — output area (rows 1-20), status line (row 22), input line (row 23)
- **Text display** — word wrapping, scrolling, pagination with `[MORE]`
- **Code injection** — receives tokenized BASIC from the proxy and writes it directly to Apple II memory at $0801
- **Command system** — 16 slash commands for controlling the agent
- **ROM patching** — patches Applesoft BASIC's error handler in Language Card RAM to intercept natural language input at the `]` prompt
- **Session persistence** — reconnects to existing proxy sessions after network interruptions

Built with the cc65 toolchain (ca65 assembler, ld65 linker) and the IP65 TCP/IP library.

### The Proxy Server

A Python server (`unified_proxy.py`) that bridges the Apple II to Claude. It handles:

- **TCP server** on port 8080, accepts connections from the Apple II
- **A2P protocol** parsing and response assembly
- **Claude API integration** (`agentic_claude.py`) — sends messages with tool definitions, processes tool calls, streams responses
- **Emulator bridge** (`emulator_bridge.py`) — starts and controls Bobbin via Unix socket for testing code
- **BASIC tokenizer** (`basic_tokenizer_streaming.py`) — converts BASIC source to the tokenized format the Apple II stores in memory
- **Real-time status streaming** — sends status updates to the Apple II as Claude works ("BOOTING EMULATOR...", "INJECTING BASIC...", "READING SCREEN...", "DEPLOYING TO APPLE II...")
- **Code versioning** — saves every generated program to a git-tracked `programs/` directory for undo/redo
- **Prompt caching** — uses Anthropic's prompt caching to reduce API latency
- **Rate limit retry** — automatically backs off and retries on API rate limits

### The Emulator (Bobbin)

[Bobbin](https://github.com/benj-edwards/bobbin-ai) is an Apple II emulator written in C, modified specifically for AI integration. Key features:

- **Unix socket control interface** — JSON protocol over `/tmp/bobbin.sock`, supports up to 16 simultaneous clients. This is how the proxy and MCP server control the emulator without PTY/signal issues.
- **Uthernet II emulation** — virtual Ethernet bridge so the Apple II agent can connect to the proxy running on the same machine
- **State save/load** — saves complete emulator state (CPU registers, 128KB RAM, soft switches) for instant environment restoration
- **Graphics export** — captures GR, HGR, DHGR, DGR screens as PPM/PNG images in both monochrome and 16-color modes
- **CPU debugging** — single-step, breakpoints, watchpoints, instruction tracing, disassembly

### The MCP Server

An MCP (Model Context Protocol) server that gives Claude Code direct access to the emulator. 50+ tools covering machine control, BASIC injection, 6502 assembly, memory access, disk management, graphics capture, and state snapshots. This is used for interactive development from the terminal — separate from the proxy's agentic loop.

---

## Timeline: How It Was Built

### Day 0: Project Extraction (January 22, 2026)

The project began by extracting working code from a larger umbrella project. Claude Code created the `apple2agent` directory structure and copied the relevant files: proxy server, MCP server, assembly source, IP65 TCP/IP library, ProDOS disk tools, and disk images. The initial setup included `.mcp.json` for Claude Code integration, a Makefile, and documentation.

At this point the system was a basic remote shell — the Apple II could connect to the proxy and send/receive text, but there was no code generation or agentic loop.

### Days 1-2: Foundation (January 25-26)

**January 25** — Initial commit. The Apple II agent client existed as `remote_shell.s`, a 6502 assembly program that connected via Uthernet II and exchanged text with the proxy.

An alternative "ampersand hook" version (`claude_agent_ampersand.s`) was added that installed itself as BASIC's `&` handler, allowing the user to type `&` at the BASIC prompt to invoke the agent.

**January 26** — The big day. Six commits in rapid succession transformed the project from a text chat into an agentic coding environment:

- **Unified agent** with A2P protocol and model selection (Sonnet/Opus/Haiku)
- **`/PROMPT` command** for custom system prompts
- **Agentic mode with tool use** — Claude gets access to emulator tools and iterates
- **`/TURNS`, `/HISTORY`, `/CLEAR` commands** for controlling the agentic loop
- **Automatic conversation compaction** (like Claude Code does when context gets long)
- **Bobbin debugger reliability improvements** with retry logic

The first "Claude Code experience" was added — BASIC and assembly support through the proxy. A web interface was also created (later superseded by the Apple II native client).

Bug fixes piled up fast: UTF-8 encoding errors in the tokenizer, keyboard buffer corruption in the emulator's key injection, debugger entry crashing when using SIGINT (fixed by switching to SIGQUIT).

### Day 3: Bug Crushing (January 27)

Major display and stability fixes:

- **Blank screen bug** — `print_multiline` was destroying the Y register via `CLREOL` during scrolling, causing the screen to go blank on `/HELP` and `/MODEL` commands
- **Wrong output position** — `output_row` was uninitialized in BSS, text appeared on row 0 instead of the output area
- **Wrong column** — `CH` (horizontal cursor) wasn't being reset after `VTAB`, text started mid-line
- **ESC menu broken** — key input used `AND #$DF` which doesn't clear RDKEY's high bit; switched to `AND #$7F`
- **Memory collision with IP65** — the agent's buffers at $8000-$9000 overlapped IP65's Ethernet buffers (which extend to $9D40). Sending packets corrupted the screen save and receive buffers. Relocated to $A000+.

Non-blocking screen capture was added using SIGUSR1 — the emulator writes the screen to a file without entering the debugger, preserving active TCP connections.

### Day 4: The Control Socket Revolution (January 28)

This was the pivotal technical breakthrough. The pexpect/PTY interface to Bobbin was fundamentally unreliable — sending signals to enter the debugger caused race conditions, EOF errors, and state corruption. Every MCP tool that needed to read memory or peek at the screen was fragile.

**The fix: a Unix domain socket control interface added directly to Bobbin.** JSON commands over `/tmp/bobbin.sock`, with clean request-response semantics. No signals, no PTY, no pexpect. Every operation — peek, poke, screen read, key injection, CPU state, breakpoints, graphics capture — went through the socket.

This was a modification to the Bobbin emulator itself (`control_socket.c`, ~800 lines of C). The Python client (`control_socket.py`) and MCP server were updated to use the socket when available, falling back to pexpect if not.

The control socket protocol launched with ~25 commands covering memory, CPU, display, input, breakpoints, disks, graphics, and state management.

The tokenizer also got a fix for a word boundary bug where BASIC keywords inside variable names were being incorrectly tokenized (e.g., `FORMULA` being tokenized as `FOR` + `MULA`).

### Day 5: The Emulator Bridge (January 29)

With the control socket working, the proxy needed its own way to drive the emulator. The **emulator bridge** (`emulator_bridge.py`) was created — it starts a Bobbin instance with the control socket, connects to it, and translates the proxy's MCP-style tool calls into socket commands.

This completed the agentic loop: user types request → proxy sends to Claude → Claude calls emulator tools through the bridge → tests code → deploys to Apple II.

Other additions this day:
- **Contiguous disk creation tool** — `make_agent_disk.py` creates ProDOS disks with contiguous file allocation (required for hardware disk emulators like the Floppy Emu)
- **State save/restore** — complete 128KB emulator snapshots (CPU, main RAM, aux RAM, soft switches)
- **Instant environments** — pre-baked states for bare BASIC, ProDOS, and DOS 3.3. One MCP call = instant ready, no boot sequence.
- **Multi-client socket** — up to 16 simultaneous connections to the control socket, enabling parallel AI agents
- **Proxy control via MCP** — `proxy_start`, `proxy_stop`, `proxy_status`, `proxy_log` tools

### Day 6: Polish and UX (January 31)

A marathon session focused on the user experience on the Apple II itself:

- **Screen corruption fixes** — the agent's output was getting garbled due to state machine bugs
- **Double-response bug** — the agentic loop was sending two responses per request
- **`/EXIT` and `/SUSPEND` commands** — drop to BASIC prompt to run generated code, return with `&` or Ctrl-Y
- **Web search tool** — Claude can search the web for Apple II documentation during the agentic loop
- **Disk save tools** — save programs to ProDOS disks from within the agentic loop
- **Fixed command area** — status line (row 22), input line (row 23), output area (rows 1-20), command separator
- **Persistent TCP connection** — the Apple II maintains the connection across multiple requests
- **`[MORE]` pagination** — output pauses when the screen fills, press any key to continue
- **Real-time status streaming** — shows what Claude is doing as it works ("BOOTING EMULATOR...", "INJECTING CODE...", "READING SCREEN...")
- **Agentic optimization** — skip the emulator for simple programs that are unlikely to have bugs

### Day 7: Continued Polish (February 1)

- **`/LIST` command** — display the generated BASIC code
- **Auto-boot STARTUP file** — the agent disk boots directly into the agent
- **BASIC editing crash fix** — programs injected by the agent crashed when the user tried to edit them (missing end-of-program markers)
- **Stale process cleanup** — PID file tracking to prevent zombie Bobbin processes
- **Pause/resume** — the emulator can be paused to save CPU (drops to 0% when idle)
- **Easy setup** — `setup.sh` installer script and `proxy.sh` control script
- **Status line improvements** — all status messages use direct screen memory writes to avoid scrolling the output area

### Days 8-9: Session Persistence and Error Detection (February 3-5)

- **Session persistence** — the agent reconnects to existing proxy sessions after network interruptions. No conversation loss.
- **`/RESET` command** — full session reset
- **`/PROMPT` command working** — set custom system prompts ("talk like a pirate", "respond in haiku")

### Day 10: Natural Language at the BASIC Prompt (February 6)

The most technically ambitious feature. The user can now type **anything** at the BASIC `]` prompt — if Applesoft can't parse it, instead of showing `?SYNTAX ERROR`, the agent intercepts the error and sends the original text to Claude.

```
] MAKE A PROGRAM THAT COUNTS TO 10
  → Intercepted SYNTAX ERROR
  → "MAKE A PROGRAM THAT COUNTS TO 10" sent to Claude
  → Claude generates and injects code
] RUN
  → Program runs!
```

**How it works:** The Applesoft ROM ($D000-$FFFF) is copied to Language Card bank 2 RAM. Then the error handler at $D412 is patched with a `JMP error_intercept`. When BASIC hits a SYNTAX ERROR in immediate mode (detected by checking CURLIN_H at $76 for $FF), the code saves the user's original input from the $200 keyboard buffer, sets a flag, and restarts BASIC via `JMP $E003`. A KSWL keyboard hook auto-stuffs `&` + CR at the warm start prompt, which triggers the ampersand handler, which detects the flag and sends the saved text to Claude.

This required discovering several Apple II ROM internals:
- ONERR GOTO doesn't work for immediate-mode errors (only traps during program execution)
- The Language Card bank 2 must have valid ROM content before patching (copied from ROM first)
- Applesoft only sets CURLIN_H ($76) to $FF for immediate mode, not CURLIN_L ($75)

A long-standing bug was also found and fixed: the screen save buffer at $A000 overlapped with BSS data extending to $A19E and IP65's IOBUF to $A5FF. Every call to `save_screen` was corrupting TCP connection state, which is why the `&` return from BASIC had been failing intermittently.

**TCP keepalive** was also added to prevent connection timeouts during extended BASIC sessions.

### Day 11: Network Hardening (February 7)

- **TCP connection death fix** — the Wiznet W5100 chip (Uthernet II) was sending more data than its internal buffer could hold. A mismatch between the W5100's TX buffer size register and the amount of data being written caused packet corruption. Fixed by respecting the chip's actual free buffer space.
- **Proxy hardening** — better error handling for malformed packets, connection resets, and partial reads
- **Checkpoint system** — every generated program is saved to a git-tracked `programs/` directory
- **`/UNDO` and `/VERSIONS` commands** — restore previous program versions, show version history
- **Chunked code injection** — large programs are sent in chunks to avoid TCP buffer overflows
- **DUNGEON OF DOOM** — a complete text RPG generated by the agentic loop as a test case
- **Instant environment switching in proxy** — the agentic loop can switch between BASIC, ProDOS, and DOS 3.3 environments mid-session

### Day 12: Display Modes and Performance (February 8)

- **Multi-display mode** — 40-column uppercase, 40-column with lowercase, 80-column (requires enhanced //e)
- **Prompt caching** — Anthropic's prompt caching reduces API latency for repeated conversations
- **Rate limit retry** — automatic exponential backoff on API rate limits
- **Emulator screen streaming** — when the agent reads the emulator screen, the contents are streamed to the Apple II so the user can see what Claude sees
- **Clear-on-wrap** — when the 20-line output area fills and wraps, it clears all 20 lines for a clean "page break" instead of overwriting stale text one line at a time
- **Graphics capture streaming** — captures are shown in the output area

### Day 13: Token Efficiency (February 8-9)

Every token through the Claude API costs money and adds latency. Several changes reduced token waste:

- **`inject_tokenized_basic(source=...)`** — tokenizes server-side. Previously required two calls: tokenize → inject hex data
- **`assemble(source_file=...)`** — reads assembly from a file on disk instead of sending it through the API
- **`load_file`** — loads binary data directly from the local filesystem into emulator memory
- **Help tool** — a built-in `help()` MCP tool with the full Apple II development guide, so agents don't need to search documentation
- **Hex dump suppression** — the tokenize tool no longer returns hex in its output

### Days 14-16: Ecosystem (February 9-10)

- **DHGR 16-color capture** — Bobbin's DHGR (double hi-res) export was monochrome only. Added full 16-color support: extract 4-bit color pixels from interleaved aux/main memory, render at 140x192 scaled to 560x192. Changes spanned Bobbin C code, the control socket protocol, the Python client, and the MCP server.
- **6502/Apple II reference library** — seven comprehensive reference files (3,006 lines total): 6502 instruction set, ca65 assembler, ld65 linker, ProDOS MLI, soft switches, memory map, ROM routines
- **Auto-scaled PNG screenshots** — all PNG captures are scaled 3x with nearest-neighbor interpolation. Apple II native resolutions (280x192 for HGR) are too small for AI vision models to parse details. 3x makes them 840x576, much more readable.
- **Public release preparation** — rewrote the README and pushed to GitHub

---

## Features Summary

### Apple II Client Commands

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
| `/PROMPT <text>` | Set custom system prompt |
| `/DISPLAY 40\|40L\|80` | Set display mode |
| `/CLEAR` | Clear conversation history |
| `/RESET` | Full session reset |
| `/SETIP x.x.x.x` | Set proxy IP address |
| `/PORT xxxx` | Set proxy port |
| `/IP` | Show connection info |
| `/HELP` | Show command list |

### Agentic Tools (Available to Claude During the Loop)

**Emulator:** boot, load environment, inject BASIC, run commands, read screen, read program from memory, capture graphics, type keystrokes, peek/poke memory, assemble 6502, call machine code

**Deployment:** send BASIC to Apple II, send binary to Apple II, display message, update status line

**Disk:** save BASIC program, save binary, save text, list catalog

**Other:** web search for Apple II documentation

### Natural Language Integration

Three ways to talk to Claude from the Apple II:

1. **Agent prompt** — type at `AGENT>` when in agent mode
2. **BASIC prompt** — type anything at `]` that isn't valid BASIC, it gets sent to Claude automatically
3. **Error assistance** — type `&` after a BASIC error, the agent detects the error and asks Claude for help

---

## Technical Challenges and Solutions

### The PTY Problem → Control Socket

The original MCP server controlled Bobbin through pexpect (Python's expect library), which uses pseudo-terminals. This worked for simple operations but was fundamentally unreliable for the agentic loop. Entering the debugger required sending Unix signals, which caused race conditions, EOF errors, and state corruption — especially during network operations.

**Solution:** A Unix domain socket added directly to Bobbin's main loop. JSON commands, clean request-response, no signals. This one change made everything reliable. The socket supports 16 simultaneous clients, enabling parallel AI agents.

### Memory Layout Wars

The Apple II has 48KB of usable RAM (64KB minus I/O and ROM space). The agent client, IP65 TCP stack, Applesoft BASIC, program storage, screen memory, and various buffers all compete for space. Multiple crashes traced to overlapping buffers:

- IP65's Ethernet buffers at $8ED7-$9D40 overlapped the agent's receive buffer at $8000
- The screen save buffer at $A000 overlapped BSS data extending to $A19E
- IOBUF extended to $A5FF

Each fix required relocating buffers and updating all references. The final memory map puts the agent code at $6000, IP65 BSS below $9E00, screen save at $A600, and the receive buffer at $AA00.

### TCP Buffer Overflow on Uthernet II

The Wiznet W5100 chip has internal TX/RX buffers. When the proxy sent long responses, the agent code was writing more data to the W5100 than its buffer could hold, causing packet corruption and connection death. Fixed by checking the chip's free buffer space register before each write.

### ROM Patching for Natural Language Input

Intercepting BASIC errors required patching the Applesoft ROM in Language Card RAM. The error handler at $D412 is in ROM, but the Apple //e's Language Card allows writing to the $D000-$FFFF address space. The solution: copy ROM to Language Card bank 2, patch the error handler, then switch the memory bank. This runs the patched code while preserving the rest of the ROM.

### Token Efficiency

Every byte through the Claude API costs tokens. Assembly source, hex data, BASIC programs — all add up. Several design decisions minimize token waste:

- Server-side tokenization (BASIC source → tokens happens on the server, not in the API conversation)
- File-based assembly (source read from disk, never sent through the API)
- Direct file loading (binary data loaded from filesystem into emulator memory)
- Hex dump suppression (tools return byte counts, not hex strings)

---

## How to Use It

### With Real Hardware

Requirements:
- Apple II, IIe, or IIgs with a Uthernet II Ethernet card
- A computer on the same network running the proxy

Setup:
1. `./setup.sh` — installs Python dependencies, prompts for Anthropic API key
2. `./proxy.sh start` — starts the proxy on port 8080
3. Boot the Apple II from `disks/agent_contiguous.dsk`
4. The agent connects automatically. If your proxy is at a different IP: `/SETIP x.x.x.x`
5. Type naturally at the `AGENT>` prompt

### With Emulator Only

You don't need real hardware. With Claude Code and the apple2-mcp server:

1. `boot(machine="enhanced", uthernet2=true, disk="disks/agent_contiguous.dsk")`
2. `proxy_start()`
3. The agent connects and you can interact via `read_screen()` and `type_text()`

Or skip the agent entirely and use the MCP tools directly for BASIC/assembly development.

### Where It's Available

- **Source code:** https://github.com/benj-edwards/apple2agent (MIT license)
- **Bobbin emulator:** https://github.com/benj-edwards/bobbin-ai
- **MCP server:** Included in the apple2agent repo, also at https://github.com/benj-edwards/apple2-mcp
- **Requires:** Python 3.8+, Anthropic API key, Apple II with Uthernet II (or Bobbin emulator)

---

## Statistics

- **Development period:** January 22 - February 10, 2026 (17 active days, not all consecutive)
- **Total commits:** 88
- **Languages:** Python (proxy, MCP server, tools), 6502 assembly (Apple II client), C (Bobbin emulator modifications)
- **Key files:** `asm/agent.s` (Apple II client, ~3500 lines of 6502 assembly), `proxy/agentic_claude.py` (agentic loop, ~1500 lines), `proxy/unified_proxy.py` (proxy server, ~800 lines)
- **Emulator modifications:** Control socket (~800 lines C), DHGR color export, state save/load, pause/resume, multi-client support
- **Tools available to Claude:** 16 emulator tools, 4 deployment tools, 4 disk tools, 1 web search tool
- **Apple II client commands:** 16 slash commands
- **Reference library:** 7 files, 3,006 lines covering the complete 6502/Apple II development ecosystem

## The Humans and AIs Involved

The project was developed by **BX Foundry** using **Claude Code** (Anthropic's agentic coding CLI tool, powered by Claude). Most of the code — Python, 6502 assembly, C modifications to Bobbin, documentation — was written by Claude under human direction. The human provided the vision ("Claude Code for Apple II"), made architectural decisions, tested on real hardware, and directed the development priorities. Claude handled the implementation, debugging, and documentation.

The Bobbin emulator was originally written by Micah Cowan. The control socket interface and AI-integration features were added during this project.

The IP65 TCP/IP stack is an open-source library that provides TCP/IP networking for 6502 systems.
