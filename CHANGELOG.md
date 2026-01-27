# Changelog

All notable changes to the Apple II Agent project.

## [Unreleased]

### Fixed

- **Blank screen on /HELP and /MODEL commands**: The `print_multiline` function was corrupted by `CLREOL` destroying the Y register. Fixed by saving/restoring Y around the `scroll_output` call.

- **Output appearing on wrong screen row**: The `output_row` variable was uninitialized in BSS, causing text to appear on row 0 instead of the output area. Fixed by initializing `output_row` to `OUTPUT_START-1` in `draw_ui`.

- **Output starting at wrong column**: After calling `VTAB`, the horizontal cursor position `CH` was not reset, causing text to start at the previous cursor column instead of column 0. Fixed by adding `CH=0` in `scroll_output` and `status_msg`.

- **/CLEAR command not recognized**: The command parser checked for 'C' commands but only handled `/CODE` (checking for 'O' at position 2). `/CLEAR` (with 'L' at position 2) fell through to "UNKNOWN COMMAND". Fixed by adding a check for 'L' to handle `/CLEAR`.

### Verified Working

All slash commands tested and verified functional:
- `/IP`, `/HELP`, `/MODEL`, `/CLEAR`, `/SETIP`, `/PORT` - all working correctly
- Network connection failure handled gracefully (displays "CONNECTION FAILED", agent continues)
- Agent remains stable after any operation

### Known Limitations

- ESC menu displays but key input may not process in some emulator configurations (MCP/RDKEY timing)
- Network connectivity requires proper Uthernet II emulation configuration
- `/SAVE` may fail in emulator environments with disk write restrictions

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
