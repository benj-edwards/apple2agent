# Changelog

All notable changes to the Apple II Agent project.

## [2.1] - 2026-10-22 - Getting ready for real hardware

The first boots on a real //e (Floppy Emu) crashed into the monitor at `2002-`: ProDOS started, then jumped into an empty AGENT.SYSTEM. The cause was the ProDOS 2.4 kernel (the first 2.4 release): the stock 2.4 disk crashes that machine too, while ProDOS 1.9 and 2.0.3 disks boot. The agent disk is now built from the ProDOS 1.9 disk that booted there in January, and **the agent boots on the real //e, finds the proxy and talks to Claude**. Along the way a reviewer and a much more realistic emulator turned up a list of real-hardware bugs.

### Added

- **Finds the proxy by itself.** At boot the agent broadcasts `A2AGENT?` to UDP 6502 and the proxy answers with its port; the answer's source address is the proxy. No `/SETIP` on a home network. Found addresses are saved (only when they change). If the saved address stops answering - the Mac got a new address, or the proxy started late - the agent asks again before restarting the network.
- **Settings are saved to disk** (`CLAUDECONF`): `/SETIP`, `/PORT`, found addresses. A write-protected disk says so on the status line.
- **ESC while waiting**: the first asks Claude to stop (`/STOP`; the proxy stops at the next safe point and the conversation stays valid), the second stops waiting (for a network that has quietly gone away).
- **Boot goes straight to `AGENT>`** when the proxy answers; when it doesn't, the screen says how to start it, and the next thing typed finds it.
- **Diagnostic disk** (`tools/make_diag_disk.py`, `asm/diag.s`): machine/ROM/ProDOS/slot info, every block checked against build-time checksums, AGENT.SYSTEM loaded the way ProDOS does and verified, RETURN starts the agent.
- **SD card tools**: `tools/copy_to_card.py` (contiguous copy, verified) and `tools/fat_check.py` (walks the FAT chain; needs `sudo` on a real card).
- **Tests**: `tests/run_all.sh` runs everything that needs no API: `e2e_display.py` (screen contents via a fake proxy), `e2e_setup.py` (first run, discovery, saved settings, late proxy), `e2e_agent.py` (now also fresh-copy `/RUN`; `E2E_REAL_SPEED=1` for real 1 MHz timings; `BOBBIN_U2_RESET_ON_RESET=1` for a Uthernet that resets with Ctrl-Reset), `soak_agent.py` (25+ deploy/run/return cycles), `test_stream_display.py`, `test_build_contract.py` (the harness's page-3 hooks are the agent's). `e2e_display.py` and `e2e_agent.py` also run in 80 columns. `tests/live_agent.py` runs a real request end to end (`--start-proxy` for this checkout's proxy).

### Fixed - Apple II agent

- **The first real deploy stalled, then ran with "?SYNTAX ERROR IN 100"** (TriPeaks, 2026-10-26). IP65 checked only the IP header of incoming packets, never the TCP checksum. A byte garbled between the Uthernet and the CPU reached the agent: in the data it broke an A2P packet (dropped, so part of the program never arrived); in the TCP header length it moved the ACK point past what the Mac had sent, a stall neither side recovers from (12K sat in the Mac's send queue). IP65 now verifies TCP checksums and drops bad segments, which the Mac resends. Bobbin can now garble segments the same way (`BOBBIN_U2_CORRUPT_EVERY`): the old agent froze on its first deploy, the new one passes all 30 e2e checks with every 5th segment garbled.
- **The connection still stalled twice while TriPeaks was built** (the watchdog rescued it both times). Each frame in the W5100's receive ring starts with a 2-byte length, and the driver moves its read pointer by it: one misread length and every frame after is read from the wrong place, until the chip is reset. The driver now rejects a length no frame can have (shorter than an Ethernet header, longer than 1520, or more than has arrived), skips what's in the ring and picks up at the next frame (`w5100_rx_resyncs` counts it). With Bobbin misreporting every 7th frame's length (`BOBBIN_U2_CORRUPT_LEN_EVERY`), the old driver froze on the first deploy; the new one passes the e2e, with garbled segments on top.
- **The watchdog's `/RESYNC` carries a stall report**: segments since the last good packet, all segments and bad checksums, ring skips, bad A2P packets, the W5100's socket status and waiting bytes, and the expected and last sequence numbers. The proxy decodes it into `logs/stall_reports.log`, so a stall on the real machine explains itself.
- A deploy with a packet that failed its checksum is no longer run: the agent fetches a fresh copy (`/RERUN`, at most twice) and offers that one.
- **Stall watchdog**: 20 s of silence while waiting (the proxy says something every 2 s while it works) restarts the network, reconnects and sends `/RESYNC`; the proxy re-sends the reply's end and the program. Seconds are the 10th byte of `CLAUDECONF` (0 = off; older 9-byte files get 20).
- AGENT.SYSTEM may now be bigger than 16K (the loader copies top-down; the linker limit was the old 16K image area).

- **TCP acknowledged only the low byte of segments of 256+ bytes** (the receive loop counted down IP65's own length). Bobbin never sent segments that big; real hosts send 512-536, and every deploy batch is 540. With a realistic emulated host a 28K deploy took 48 s instead of 1 s.
- Bytes after a `DONE` in the same TCP segment were dropped (and acknowledged).
- **The log left old text on screen** after it filled up (`CLREOL` cleared from a stale column; row 20 was never cleared) - the merged lines seen in the first live run.
- **`/EXIT` wiped ProDOS**: it copied the ROM over the language card to patch Applesoft's error handler, and polled the network from a keyboard hook in the middle of Applesoft input (IP65 shares Applesoft's zero page). `/EXIT` is now a plain `]` prompt; ESC there, `&` and Ctrl-Y come back.
- **`/PORT` always set port 0** (`temp1+1` is `temp2`, the digit). Bare commands read the end of an earlier, longer line; `/SETIP` accepted octets over 255 and partial addresses (and changed the address before checking).
- **`/RUN` replayed modified memory** for machine code above `$6000` (EXCHANGE swaps that part out as the run left it) and for any 64K (RESIDENT) machine code: it now fetches a fresh copy (`/RERUN`) and runs it on arrival.
- **A Uthernet reset by Ctrl-Reset** would hang the next send: the agent notices the W5100 lost its bus mode and restarts the network first.
- ESC at `AGENT>` opened a menu that swallowed typing - which is where a held ESC from a game lands. ESC now clears the line.
- The READY banner could be split by a page turn of the log, leaving "RETURN = RUN IT" with no name; it now always starts where all four lines fit. The request is echoed (word-wrapped, by the proxy) at the top of the log and the input line clears while Claude works. The boot screen shows one line for the network ("THIS APPLE II IS ...") instead of IP65's full report.
- **80 columns never worked** (text went through the 40-column ROM routine: every other column showed leftover aux memory). The agent now draws 80 columns itself (`asm/agent_screen.s`: output, clearing, scrolling and a blinking cursor across aux and main), without the 80-column firmware. Programs still start in plain 40-column text and the agent comes back in 80. Needs an 80-column card (ProDOS MACHID); without one it's 40 mixed case.
- **The `]` prompt after `/EXIT` rejected everything** with `?SYNTAX ERROR`, `&` included: the keyboard hook ran `TSX` to see who was asking, which wiped out X, GETLN's place in the line. It also overwrote A, the character KEYIN puts back under the cursor, so programs' `INPUT` and `GET` left a stray character behind (the `}` after a `]` line). The hook now calls KEYIN first and looks only when the key is ESC.
- Applesoft's warm-start and string-print vectors (`$00`, `$03`) were left pointing at its cold start (the placeholder a cold start overwrites at the end).
- After `/CLEAR` or `/DISPLAY` a row of dashes sat in the log (the divider was drawn at the wrong row, a leftover of a dropped design).
- Debug counters were written into page 3 (program-owned) on every packet.
- Before sending, up to 24 queued frames are handled (not 3): on a real LAN a FIN can sit behind broadcasts.
- IP65 `tcp_send`: its resend counter was reset only in unreachable code, so resends piled up over a connection's life; its ACK wait ignored a closed connection.

- **ESC at a program's INPUT prompt comes back to the agent** (GETLN swallows ESC, so a program built on INPUT had no way out). GET still hands ESC to the program.
- **The final message lost its first lines** (what the program is, its controls) when Claude's last notes filled the log page: once a program is deployed, the message is shown again on a fresh page (form feed, which older clients ignore) right above the READY banner.
- Requests go as typed on a mixed-case screen (40L, 80); only 40U (and /commands) are sent in uppercase. The log no longer shouts your own words back.
- **Requests were cut off at 120 characters**, silently (the live test's long game request lost its second half). The input line now holds 239 (a `]` line's worth) and beeps when it's full.

### Fixed - proxy

- `/RESYNC` (the watchdog): re-sends the last request's final message and program; while Claude still works the new connection takes over and gets the program again at the end. The end of a request (DONE) now goes to the agent's current connection, not the one it started on.
- Importing `unified_proxy` no longer swaps out stdout/stderr (it closed a test runner's capture file).

- **A big game request produced nothing**: Claude's first turn planned the whole game and ran out of output (64K tokens) before writing a line, and the loop gave up ("MY REPLY GOT CUT OFF") after 12 minutes. Output is now 128K (Opus 5.5's cap); a turn cut off before any tool call is dropped and retried with a note to plan briefly and build in pieces (twice at most); the prompt says to write a first playable version, test it, then grow it.
- **A big request showed only "THINKING 7M" for minutes**: under thinking display `updates` the up-front reasoning comes back empty (only short notes between tool calls have text). The display is now `summarized`, each paragraph cut to three lines.
- Machine code that turns on hi-res and has code or data inside a page it draws on gets a WARNING in the build summary (it would wipe itself out); the prompt says where big hi-res programs fit.
- **Tests could reach the user's real proxy**: once it answered discovery on UDP 6502, a test's emulated Apple II connected to it instead of the test's own. Each test now has its own discovery channel (Bobbin `BOBBIN_U2_UDP_PORT`, proxy `APPLE2_DISCOVERY_PORT`).

- **The live code view showed one line of a 724-line program** (the SDK's tool-input snapshot leaves a string out until it's complete); it now parses the raw JSON with trailing strings. Thinking notes stream line by line instead of arriving at the end of a 2-minute think.
- **Claude's test emulator ran about 40x too fast** (Bobbin `--simple` is unthrottled unless `--no-turbo`), so Claude tuned game speed against a fast-forward. It runs at a real 1 MHz now.
- Claude's test runs started from zeroed memory; they now start from leftovers, like the real machine (and the prompt says so).
- Two requests could run on one agent at once after a reconnect; busy is now tracked on the agent.
- **Claude's test emulator sent RETURN for the down arrow** (Bobbin turns LF into RETURN) - Claude had started making programs accept both. Keys now arrive as the //e's own codes, at a typist's pace (all at once, programs that flush the keyboard "dropped" them).
- A stop during a long silent think waited for the next stream event (minutes); `stream.close()` from another thread blocked on the reader's connection. The stop now shuts the stream's socket down, which ends the read at once.
- Test proxies shared the real proxy's PID and shutdown files (`APPLE2_PROXY_CONTROL_DIR`).

### Fixed - disk images

- **The boot disk crashed the real //e** (`2002-`): every image had the ProDOS 2.4 kernel, and was built from scratch. `make disk` (`tools/build_agent_disk.py`) now copies `disks/base_jan19.dsk` - the January agent disk (ProDOS 1.9 + BASIC.SYSTEM) that booted the real machine, old files removed - and adds AGENT.SYSTEM with AppleCommander, as the MCP README's disk guide says to. It checks that AGENT.SYSTEM is the first `.SYSTEM` entry and reads back byte for byte, then boot-tests it. Bobbin booted the bad disks fine, which is why it took a real machine to find.

- **`make_agent_disk.py` corrupted the ProDOS kernel**: it read a sparse index entry (pointer 0) as block 0, so the last 232 bytes of PRODOS were boot-block code instead of zeros. It also marked nonexistent blocks 280-287 free. It now reads the finished image back and compares every file byte, the boot blocks and the bitmap before saving.


### Bobbin

- Control-socket breakpoints work; `$C019` vertical blank; virtual UDP (service discovery); the virtual TCP behaves like a real host (536-byte segments, honors the Apple's window, resends from its ACK, drops duplicates); `BOBBIN_U2_RESET_ON_RESET=1`; `BOBBIN_U2_UDP_PORT=n` (the virtual network's UDP goes to localhost:n). See Bobbin's changelog.

## [2.0] - 2026-10-20 - "Make it magical"

Type a wish, watch Claude build it, press RETURN and play; ESC comes back.

### Added

- **READY-to-run deploys**: the proxy streams any program (Applesoft BASIC or 6502 machine code) with new DEPLOY/LOAD/RUN packets; the Apple II shows `*** NAME IS READY! ***` and RETURN runs it. `/RUN` plays it again, `/UNDO` brings back the previous version, `/SEND <FILE>` sends a workspace program without Claude.
- **EXCHANGE launch mode (128K //e)**: programs get `$0800-$BEFF`. Bytes are staged in aux memory during the download; at launch the program's low pages are copied in and `$6000-$BEFF` is swapped with aux by a stack-page routine, so the agent waits in aux. RESIDENT mode remains for 64K machines (`$0800-$5FFF`).
- **Ways back to the agent**: ESC (program convention: `TEXT : HOME : &` or RTS), ESC at the `]` prompt (KSW hook), `&`, Ctrl-Y, Ctrl-Reset (reset vector) and BRK crashes all return to `AGENT>` with the session intact. Crashes and Applesoft errors come back pre-filled as `FIX: ...`.
- **New agent loop** (`proxy/agentic_claude.py`): Claude Opus 5.5 by default (`/MODEL O|S|H` = Opus/Sonnet/Haiku 5.5), streaming with adaptive thinking and progress updates, `/EFFORT`, server-side refusal fallback, server-side compaction, prompt caching. Tools: `write_file`, `edit_file`, `read_file`, `run_in_emulator`, `emulator_input`, `emulator_memory`, `deploy_to_apple`, web search.
- **Test harness** (`emulator_bridge.run_program`/`observe`): launches programs in a fresh Bobbin exactly as the real Apple II will (same layout, same page-3 hooks), types keys, and reports running/ended/error/crashed/exited, the text screen, color PNG screenshots that Claude looks at, and memory-safety violations.
- **Live previews**: Claude's hi-res test screenshots appear on the Apple II (HGR mixed mode with the status line still live; any key flips back to the log).
- **Live log**: progress notes, tool steps and the code itself scroll by while Claude writes it.
- **`proxy/deploy.py`**: one place for memory layout; Applesoft programs are placed around the HGR page(s) they use, with variables above the graphics.
- **AGENT.SYSTEM**: the boot disk starts the agent directly from ProDOS (loader at `$2000` copies it to `$6000`); no BASIC.SYSTEM in memory, no BRUN size limit.

### Changed

- Default port is now **6502** (agent and proxy).
- Commands are matched by whole word on the Apple II; unknown commands go to the proxy (fixes `/SEND` running `/SETIP`, `/EFFORT` running `/EXIT`).
- Long input scrolls sideways instead of wrapping the bottom line (which scrolled the whole screen).
- `setup.sh` installs into a project `.venv`; the proxy re-execs itself into it.

### Fixed

- BSS is zeroed at startup (flags used to start as whatever memory held).
- Applesoft's zero page (CHRGET, vectors) is initialized at startup and before every BASIC launch.
- Remote close (`$FFFF` callback length) no longer parses 64K of garbage; dead connections are detected, reconnected, and the message is resent. The network is re-initialized if reconnecting fails.
- Oversized packet lengths no longer overrun `pkt_buffer`; no more NACK sent from inside the TCP callback.
- The screen save buffer could overlap BSS; it is now a BSS reservation.
- `/MODEL` now tells the proxy; the default model is Opus.
- Tokenizer: digits no longer block keywords (`GOTO10`, `1THEN`), lines are sorted, and duplicate line numbers replace earlier ones.
- Bobbin (canonical source in the bobbin-ai repo): virtual TCP honors RX buffer space (no more silently dropped data); W5100 TX buffer size follows TMSR (IP65 uses 4KB - frames past 2KB were corrupted); `\uXXXX`/`\b` JSON escapes for key injection; Open/Closed-Apple read as not pressed in `--simple` mode (Ctrl-Reset ran the self-test).
- The proxy and its test emulator no longer inherit the MCP server's stdin (Bobbin made it non-blocking and crashed the MCP server).

## [Unreleased]

### Added

- **Natural Language at BASIC Prompt (Phase 2b)**: Type anything at the `]` prompt - if BASIC can't parse it, the error is intercepted and the original text is sent to Claude automatically. No special prefix or command needed.

  ```
  ] MAKE A PROGRAM THAT COUNTS TO 10
    → Intercepted SYNTAX ERROR
    → "MAKE A PROGRAM THAT COUNTS TO 10" sent to Claude
    → Claude generates and injects code
    → Press any key → back to ] prompt
  ] RUN
    → Program runs!
  ```

  **How it works:** Applesoft ROM is copied to Language Card bank 2 RAM, then the error handler at $D412 is patched to jump to our code. When BASIC hits a SYNTAX ERROR in immediate mode, we save the user's original input from the $200 buffer, set a flag, and restart BASIC. A KSWL keyboard hook auto-stuffs `&` + CR to trigger the agent, which detects the flag and sends the saved text to Claude. Valid BASIC commands and program errors pass through normally.

- **Smart Error Detection (Phase 1)**: When `&` is typed after a BASIC error, the agent scans the screen for error messages (lines starting with `?`) and automatically sends them to Claude for help.

- **`/PROMPT` command**: Set a custom system prompt for Claude (`/PROMPT talk like a pirate`). Empty `/PROMPT` clears it back to default.

- **`/RESET` command**: Reset the conversation and connection state.

- **Session persistence**: Agent reconnects to existing proxy sessions after network interruptions.

- **Bobbin Control Socket**: Added Unix domain socket control interface to Bobbin emulator for reliable AI/MCP integration. This completely bypasses the pexpect/PTY/signal issues that caused debugger operations to fail.

  **Socket Protocol v2.0** (JSON over `/tmp/bobbin.sock`):

  *Basic Commands:*
  - `ping` - Get version, machine type, and paused state
  - `quit` - Exit emulator

  *Memory Commands:*
  - `peek` - Read memory (addr, len) → returns byte array
  - `poke` - Write memory (addr, data[]) → writes bytes
  - `load` - Load hex data into memory at address
  - `screen` - Read text screen as 24 decoded ASCII lines
  - `screen_raw` - Read raw screen memory $0400-$07FF

  *CPU Commands:*
  - `cpu` - Get CPU state (PC, A, X, Y, SP, P, cycles, instructions, frames)
  - `step` - Single-step 1-1000 instructions
  - `reset` - Reset CPU (warm or cold boot)
  - `pause` - Pause emulation
  - `resume` - Resume emulation
  - `call` - Call subroutine (JSR equivalent)
  - `disasm` - Disassemble memory

  *Breakpoint Commands:*
  - `break_set` - Set breakpoint at address
  - `break_clear` - Clear breakpoint by ID or address
  - `break_list` - List all breakpoints
  - `break_enable` - Enable breakpoint
  - `break_disable` - Disable breakpoint
  - `watch_set` - Set watchpoint (break on memory change)

  *Disk Commands:*
  - `disk_status` - Get active drive and spinning status
  - `disk_insert` - Insert disk image into drive 1 or 2
  - `disk_eject` - Eject disk from drive

  *Graphics Commands:*
  - `hgr` - Capture HGR (280x192) to PPM file
  - `gr` - Capture GR (40x48) to PPM file
  - `dhgr` - Capture DHGR (560x192) to PPM file
  - `dgr` - Capture DGR (80x48) to PPM file

  *State Commands:*
  - `save_state` - Save full emulator state to file
  - `load_state` - Load emulator state from file

  *System Commands:*
  - `keys` - Inject keystrokes into keyboard buffer
  - `mouse` - Control mouse position and button
  - `slots` - Get peripheral slot configuration
  - `softswitches` - Get display/memory soft switch states
  - `speed` - Set turbo mode
  - `cycles` - Get cycle/instruction/frame counts
  - `trace` - Enable/disable instruction tracing

  **Files created**:
  - `bobbin/src/control_socket.c` - Socket server implementation
  - `src/apple2_mcp/control_socket.py` - Python client library
  - `bobbin_socket.md` - Design document

  **Files modified in Bobbin**:
  - `bobbin-internal.h` - Added socket declarations and config option
  - `config.c` - Added `--control-socket PATH` command line option
  - `bobbin.c` - Integrated socket init/poll into main loop
  - `Makefile` - Added control_socket.c to build

  **MCP Integration**:
  - `emulator.py` now uses socket for peek/poke/screen/keys when available
  - Falls back to pexpect/debugger method if socket unavailable
  - Boot automatically connects to socket after emulator starts

### Fixed

- **Screen save buffer overlapping BSS/IOBUF**: `SCREEN_SAVE` at $A000 overlapped with BSS (extends to $A19E) and IOBUF (to $A5FF). Calling `save_screen` corrupted TCP connection state, causing the `&` return from BASIC to fail every time. Fixed by moving `SCREEN_SAVE` to $A600 and `RECV_BUFFER` to $AA00.

- **prodos_delete.py not freeing disk space**: The ProDOS delete tool was marking directory entries as deleted but not freeing blocks in the volume bitmap, causing "disk full" errors even after deleting files. Fixed by adding `mark_block_free()` and `free_file_blocks()` functions to properly reclaim storage.

- **Blank screen on /HELP and /MODEL commands**: The `print_multiline` function was corrupted by `CLREOL` destroying the Y register. Fixed by saving/restoring Y around the `scroll_output` call.

- **Output appearing on wrong screen row**: The `output_row` variable was uninitialized in BSS, causing text to appear on row 0 instead of the output area. Fixed by initializing `output_row` to `OUTPUT_START-1` in `draw_ui`.

- **Output starting at wrong column**: After calling `VTAB`, the horizontal cursor position `CH` was not reset, causing text to start at the previous cursor column instead of column 0. Fixed by adding `CH=0` in `scroll_output` and `status_msg`.

- **/CLEAR command not recognized**: The command parser checked for 'C' commands but only handled `/CODE` (checking for 'O' at position 2). `/CLEAR` (with 'L' at position 2) fell through to "UNKNOWN COMMAND". Fixed by adding a check for 'L' to handle `/CLEAR`.

- **ESC menu key input not working**: The menu's RDKEY handler used `and #$DF` which doesn't clear the high bit that RDKEY sets. This caused key comparisons to fail (e.g., '1' = $B1 & $DF = $91, not $31). Fixed by using `and #$7F` to properly clear the high bit.

- **Memory layout collision with IP65**: The agent's `RECV_BUFFER` ($8000) and `SCREEN_SAVE` ($9000) addresses overlapped with IP65's BSS segment (which extends to $9D40, including ethernet buffers at $8ED7 and $94C5). When IP65 sent packets, it corrupted these buffers. Fixed by moving `SCREEN_SAVE` to $A000 and `RECV_BUFFER` to $A400.

### Verified Working

All slash commands tested and verified functional:
- `/IP`, `/HELP`, `/MODEL`, `/CLEAR`, `/SETIP`, `/PORT` - all working correctly
- Network connection failure handled gracefully (displays "CONNECTION FAILED", agent continues)
- Agent remains stable after any operation

### Known Limitations

- **MCP testing during network operations**: The MCP debugger interface has timing issues when the agent is performing network operations. The screen may appear blank via MCP tools even when the agent is functioning correctly. Test network features interactively or via direct stdin/stdout.
- **Disk config persistence disabled**: `/SAVE` command currently reports success but does not persist to disk. ProDOS MLI pathname operations (OPEN, CREATE) return error $40 (Invalid pathname) when called after IP65 network initialization, even though GET_PREFIX works correctly. Config changes are kept in memory for the session. This appears to be a Bobbin/IP65 interaction issue requiring further investigation.

### Network Testing

TCP networking works correctly in Bobbin with Uthernet II emulation:
- Agent connects to proxy at configured IP:port
- A2P protocol packets are exchanged successfully
- Proxy responds with AI messages (requires `ANTHROPIC_API_KEY` environment variable)
- Virtual network redirects 192.168.64.x and 192.168.65.x to localhost

## [1.0.0] - 2025-01-26

### Added

- Initial release of Apple II Agent
- A2P protocol for reliable TCP communication
- Full-screen chat interface with 40/80 column support
- Commands: /HELP, /IP, /SETIP, /PORT, /MODEL, /SAVE, /CODE, /CLEAR
- IP configuration with save/load to disk
- BASIC code injection from AI-generated responses
- Uthernet II network card support
- Ampersand hook for returning to agent from BASIC
