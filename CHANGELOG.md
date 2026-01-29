# Changelog

All notable changes to the Apple II Agent project.

## [Unreleased]

### Added

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
