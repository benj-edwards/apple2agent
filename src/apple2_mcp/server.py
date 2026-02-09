"""Apple II MCP Server.

An MCP server for autonomous experimentation with Apple II via Bobbin emulator.
"""

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from PIL import Image
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
)

from .emulator import Emulator, BobbinError
from .screen import format_screen
from .encoding import APPLESOFT_TOKENS, detokenize_byte
from .disktools import DOS33Disk, tokenize_basic, detect_disk_format
from .assembler import assemble, get_template, list_templates
from . import proxy_control

# Global emulator instance
_emulator: Optional[Emulator] = None

# Path to knowledge base
KNOWLEDGE_DIR = Path(__file__).parent.parent.parent / "knowledge"

# Create MCP server
server = Server("apple2-mcp")


def get_emulator() -> Emulator:
    """Get or create the emulator instance."""
    global _emulator
    if _emulator is None:
        _emulator = Emulator()
    return _emulator


def convert_ppm_to_png(ppm_path: str, png_path: str = None) -> str:
    """Convert a PPM file to PNG format.

    Args:
        ppm_path: Path to the PPM file
        png_path: Output PNG path (default: replace .ppm with .png)

    Returns:
        Path to the PNG file
    """
    if png_path is None:
        png_path = ppm_path.rsplit('.', 1)[0] + '.png'

    img = Image.open(ppm_path)
    img.save(png_path, 'PNG')
    os.unlink(ppm_path)  # Remove the temporary PPM
    return png_path


# =============================================================================
# Tool Definitions
# =============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        # Machine Control
        Tool(
            name="boot",
            description="Start the Apple II emulator. Returns when at BASIC prompt.",
            inputSchema={
                "type": "object",
                "properties": {
                    "machine": {
                        "type": "string",
                        "enum": ["plus", "enhanced"],
                        "default": "enhanced",
                        "description": "Machine type (plus=Apple II+, enhanced=Apple //e)"
                    },
                    "disk": {
                        "type": "string",
                        "description": "Optional path to disk image"
                    },
                    "uthernet2": {
                        "type": "boolean",
                        "default": False,
                        "description": "Enable Uthernet II network card in slot 3"
                    },
                    "mouse": {
                        "type": "boolean",
                        "default": False,
                        "description": "Enable AppleMouse card in slot 4"
                    },
                    "timeout": {
                        "type": "number",
                        "default": 60,
                        "description": "Timeout in seconds waiting for BASIC prompt (default: 60)"
                    },
                    "wait_for_prompt": {
                        "type": "boolean",
                        "default": True,
                        "description": "Wait for BASIC prompt (set False for ProDOS disks that boot to selector)"
                    }
                }
            }
        ),
        Tool(
            name="shutdown",
            description="Stop the emulator.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="pause",
            description="Pause emulation to save CPU. The emulator stays loaded but stops executing. Use resume to continue.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="resume",
            description="Resume emulation after pause.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="reset",
            description="Reset the emulator.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cold": {
                        "type": "boolean",
                        "default": False,
                        "description": "Cold reset (full reboot) vs warm reset"
                    }
                }
            }
        ),

        # Memory Access
        Tool(
            name="peek",
            description="Read bytes from Apple II memory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "address": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 65535,
                        "description": "Starting address (0-65535)"
                    },
                    "count": {
                        "type": "integer",
                        "default": 1,
                        "minimum": 1,
                        "maximum": 256,
                        "description": "Number of bytes to read"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["hex", "decimal", "ascii"],
                        "default": "hex",
                        "description": "Output format"
                    }
                },
                "required": ["address"]
            }
        ),
        Tool(
            name="poke",
            description="Write bytes to Apple II memory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "address": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 65535,
                        "description": "Starting address"
                    },
                    "data": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 0, "maximum": 255},
                        "description": "Bytes to write"
                    }
                },
                "required": ["address", "data"]
            }
        ),
        Tool(
            name="load_binary",
            description="Load binary data into memory from hex string. Prefer load_file instead to avoid wasting tokens on hex strings.",
            inputSchema={
                "type": "object",
                "properties": {
                    "address": {
                        "type": "integer",
                        "description": "Load address"
                    },
                    "hex_data": {
                        "type": "string",
                        "description": "Binary data as hex string (e.g., 'A9 00 8D 00 C0')"
                    }
                },
                "required": ["address", "hex_data"]
            }
        ),
        Tool(
            name="load_file",
            description="Load a binary file from the local filesystem directly into emulator memory. Much more token-efficient than load_binary — the file contents never pass through the conversation. Use this for sprite data, font tables, pre-built binaries, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the binary file on the local filesystem"
                    },
                    "address": {
                        "type": "integer",
                        "description": "Address to load the file into emulator memory"
                    }
                },
                "required": ["path", "address"]
            }
        ),

        # Screen/Display
        Tool(
            name="read_screen",
            description="Read the current 40x24 text screen contents.",
            inputSchema={
                "type": "object",
                "properties": {
                    "annotated": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include line numbers"
                    },
                    "nonblocking": {
                        "type": "boolean",
                        "default": False,
                        "description": "Use non-blocking capture (preserves network connections)"
                    }
                }
            }
        ),

        # Graphics Capture
        Tool(
            name="capture_hgr",
            description="Capture HGR (hi-res graphics) screen. Returns file path. Use 'png' format for Claude to view the image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {
                        "type": "integer",
                        "enum": [1, 2],
                        "default": 1,
                        "description": "HGR page (1 or 2)"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["png", "ppm", "ascii"],
                        "default": "png",
                        "description": "Output format (png=image for Claude, ppm=raw image, ascii=text art)"
                    },
                    "color": {
                        "type": "boolean",
                        "default": False,
                        "description": "Use Apple II color artifacts (ppm only)"
                    },
                    "filename": {
                        "type": "string",
                        "description": "Optional custom filename (default: auto-generated in /tmp)"
                    }
                }
            }
        ),
        Tool(
            name="read_hgr_ascii",
            description="Capture HGR screen as ASCII art and return it directly (no file). NOTE: Fails if BASIC is waiting for GET input - use display-only test programs that END.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {
                        "type": "integer",
                        "enum": [1, 2],
                        "default": 1,
                        "description": "HGR page (1 or 2)"
                    }
                }
            }
        ),

        # GR (Lo-Res) Graphics - 40x48, 16 colors
        Tool(
            name="capture_gr",
            description="Capture GR (lo-res graphics) screen. Returns file path. Use 'png' format for Claude to view the image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {
                        "type": "integer",
                        "enum": [1, 2],
                        "default": 1,
                        "description": "GR page (1 or 2)"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["png", "ppm", "ascii"],
                        "default": "png",
                        "description": "Output format (png=image for Claude, ppm=raw image, ascii=hex digits)"
                    },
                    "native": {
                        "type": "boolean",
                        "default": False,
                        "description": "Save at native 40x48 resolution (default: scaled to 280x192)"
                    },
                    "filename": {
                        "type": "string",
                        "description": "Optional custom filename (default: auto-generated in /tmp)"
                    }
                }
            }
        ),
        Tool(
            name="read_gr_ascii",
            description="Capture GR screen as ASCII art (hex digits 0-F for colors) and return directly. NOTE: Fails if BASIC is waiting for GET input - use display-only test programs that END.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {
                        "type": "integer",
                        "enum": [1, 2],
                        "default": 1,
                        "description": "GR page (1 or 2)"
                    }
                }
            }
        ),

        # DHGR (Double Hi-Res) Graphics - 560x192, //e only
        Tool(
            name="capture_dhgr",
            description="Capture DHGR (double hi-res) screen (560x192, //e with aux memory). Use 'png' for Claude to view.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {
                        "type": "integer",
                        "enum": [1, 2],
                        "default": 1,
                        "description": "DHGR page (1 or 2)"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["png", "ppm", "ascii"],
                        "default": "png",
                        "description": "Output format (png=image for Claude, ppm=raw image, ascii=text art)"
                    },
                    "filename": {
                        "type": "string",
                        "description": "Optional custom filename (default: auto-generated in /tmp)"
                    }
                }
            }
        ),
        Tool(
            name="read_dhgr_ascii",
            description="Capture DHGR screen as ASCII art and return directly (//e with aux memory).",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {
                        "type": "integer",
                        "enum": [1, 2],
                        "default": 1,
                        "description": "DHGR page (1 or 2)"
                    }
                }
            }
        ),

        # DGR (Double Lo-Res) Graphics - 80x48, 16 colors, //e only
        Tool(
            name="capture_dgr",
            description="Capture DGR (double lo-res) screen (80x48, 16 colors, //e with aux memory). Use 'png' for Claude to view.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {
                        "type": "integer",
                        "enum": [1, 2],
                        "default": 1,
                        "description": "DGR page (1 or 2)"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["png", "ppm", "ascii"],
                        "default": "png",
                        "description": "Output format (png=image for Claude, ppm=raw image, ascii=hex digits)"
                    },
                    "native": {
                        "type": "boolean",
                        "default": False,
                        "description": "Save at native 80x48 resolution (default: scaled to 560x192)"
                    },
                    "filename": {
                        "type": "string",
                        "description": "Optional custom filename (default: auto-generated in /tmp)"
                    }
                }
            }
        ),
        Tool(
            name="read_dgr_ascii",
            description="Capture DGR screen as ASCII art (hex digits 0-F for colors) and return directly.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {
                        "type": "integer",
                        "enum": [1, 2],
                        "default": 1,
                        "description": "DGR page (1 or 2)"
                    }
                }
            }
        ),

        # Input
        Tool(
            name="type_text",
            description="Type text into the Apple II as if from keyboard.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to type (will be uppercased)"
                    },
                    "press_return": {
                        "type": "boolean",
                        "default": True,
                        "description": "Press RETURN after text"
                    }
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="send_key",
            description="Send a special key.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "enum": ["RETURN", "ESCAPE", "CTRL-C", "CTRL-RESET"],
                        "description": "Special key to send"
                    }
                },
                "required": ["key"]
            }
        ),

        # BASIC/Programs
        Tool(
            name="run_basic",
            description="Execute a BASIC command and wait for prompt.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "BASIC command to execute"
                    },
                    "timeout": {
                        "type": "number",
                        "default": 30,
                        "description": "Timeout in seconds"
                    }
                },
                "required": ["command"]
            }
        ),
        Tool(
            name="run_and_capture",
            description="Run a BASIC program and capture the screen after it ends. Perfect for testing display code - the program should END so capture can work. Returns both program output and ASCII screen capture.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "default": "RUN",
                        "description": "Command to execute (default: RUN)"
                    },
                    "timeout": {
                        "type": "number",
                        "default": 30,
                        "description": "Timeout in seconds"
                    },
                    "capture_mode": {
                        "type": "string",
                        "enum": ["gr", "hgr", "text"],
                        "default": "gr",
                        "description": "Screen mode to capture (gr=lo-res, hgr=hi-res, text=40x24 text)"
                    }
                }
            }
        ),
        Tool(
            name="send_keys_and_capture",
            description="Send keystrokes to break out of a GET loop, wait briefly, then capture the screen. Useful for testing interactive programs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "string",
                        "description": "Keys to send (e.g., 'K' to move cursor down)"
                    },
                    "delay_ms": {
                        "type": "integer",
                        "default": 100,
                        "minimum": 10,
                        "maximum": 5000,
                        "description": "Delay in milliseconds before capture (default: 100ms)"
                    },
                    "capture_mode": {
                        "type": "string",
                        "enum": ["gr", "hgr", "text"],
                        "default": "gr",
                        "description": "Screen mode to capture"
                    }
                },
                "required": ["keys"]
            }
        ),
        Tool(
            name="clear_gr",
            description="Clear the GR (lo-res) screen to a solid color. Convenience tool to avoid garbage in graphics memory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "color": {
                        "type": "integer",
                        "default": 0,
                        "minimum": 0,
                        "maximum": 15,
                        "description": "Fill color (0-15, default: 0=black)"
                    }
                }
            }
        ),
        Tool(
            name="clear_hgr",
            description="Clear the HGR (hi-res) screen to black. Convenience tool to avoid garbage in graphics memory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {
                        "type": "integer",
                        "enum": [1, 2],
                        "default": 1,
                        "description": "HGR page to clear (1 or 2)"
                    }
                }
            }
        ),

        # Tokenization
        Tool(
            name="type_and_capture",
            description="Type a BASIC line and capture how Apple II tokenizes it.",
            inputSchema={
                "type": "object",
                "properties": {
                    "basic_line": {
                        "type": "string",
                        "description": "BASIC line to type (e.g., '10 FOR I=1 TO 10')"
                    }
                },
                "required": ["basic_line"]
            }
        ),
        Tool(
            name="tokenize",
            description="Tokenize BASIC source using Bobbin's built-in tokenizer.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "BASIC source code (with line numbers)"
                    }
                },
                "required": ["source"]
            }
        ),
        Tool(
            name="compare_tokenization",
            description="Compare your tokenization against Apple II native tokenization.",
            inputSchema={
                "type": "object",
                "properties": {
                    "basic_line": {
                        "type": "string",
                        "description": "BASIC source line"
                    },
                    "your_hex": {
                        "type": "string",
                        "description": "Your tokenized output as hex string"
                    }
                },
                "required": ["basic_line", "your_hex"]
            }
        ),

        # Injection
        Tool(
            name="inject_tokenized_basic",
            description="Inject a BASIC program into memory and update pointers. Provide EITHER source (preferred, auto-tokenizes) OR hex_data (pre-tokenized). Using source avoids hex tokens in the conversation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "BASIC source code with line numbers (preferred - auto-tokenizes server-side)"
                    },
                    "hex_data": {
                        "type": "string",
                        "description": "Pre-tokenized BASIC as hex string (use source instead to save tokens)"
                    },
                    "load_address": {
                        "type": "integer",
                        "default": 2049,
                        "description": "Load address ($0801 = 2049)"
                    },
                    "auto_run": {
                        "type": "boolean",
                        "default": False,
                        "description": "Automatically RUN after injection"
                    }
                }
            }
        ),

        # Observation
        Tool(
            name="get_registers",
            description="Get current 6502 CPU register state.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="get_basic_pointers",
            description="Get Applesoft BASIC memory pointers (TXTTAB, VARTAB, etc.).",
            inputSchema={"type": "object", "properties": {}}
        ),

        # Knowledge Base
        Tool(
            name="record_technique",
            description="Save a discovered technique to the knowledge base.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Technique name"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["injection", "tokenization", "execution", "memory", "other"],
                        "description": "Category"
                    },
                    "description": {
                        "type": "string",
                        "description": "What this technique does"
                    },
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Step-by-step instructions"
                    },
                    "success": {
                        "type": "boolean",
                        "description": "Did this technique work?"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Additional notes"
                    }
                },
                "required": ["name", "category", "description"]
            }
        ),
        Tool(
            name="query_techniques",
            description="Search the knowledge base for techniques.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter by category"
                    },
                    "search": {
                        "type": "string",
                        "description": "Search term"
                    }
                }
            }
        ),

        # Disk Image Tools
        Tool(
            name="create_disk",
            description="Create a new DOS 3.3 disk image (.dsk file).",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Path for the disk image file"
                    },
                    "volume": {
                        "type": "integer",
                        "default": 254,
                        "minimum": 1,
                        "maximum": 254,
                        "description": "Volume number (1-254)"
                    },
                    "from_template": {
                        "type": "string",
                        "description": "Optional: path to DOS 3.3 master disk to copy (for bootable disks)"
                    }
                },
                "required": ["filename"]
            }
        ),
        Tool(
            name="disk_catalog",
            description="List files on a DOS 3.3 disk image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Path to the disk image file"
                    }
                },
                "required": ["filename"]
            }
        ),
        Tool(
            name="save_basic_to_disk",
            description="Save an Applesoft BASIC program to a disk image. Tokenizes the source automatically.",
            inputSchema={
                "type": "object",
                "properties": {
                    "disk_filename": {
                        "type": "string",
                        "description": "Path to the disk image file"
                    },
                    "program_name": {
                        "type": "string",
                        "description": "Name for the program on disk (max 30 chars, will be uppercased)"
                    },
                    "source": {
                        "type": "string",
                        "description": "BASIC source code with line numbers"
                    }
                },
                "required": ["disk_filename", "program_name", "source"]
            }
        ),
        Tool(
            name="save_file_to_disk",
            description="Save a .bas text file to a disk image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "disk_filename": {
                        "type": "string",
                        "description": "Path to the disk image file"
                    },
                    "bas_filename": {
                        "type": "string",
                        "description": "Path to the .bas source file"
                    },
                    "program_name": {
                        "type": "string",
                        "description": "Optional name for the program on disk (default: derived from filename)"
                    }
                },
                "required": ["disk_filename", "bas_filename"]
            }
        ),

        # ProDOS Disk Tools
        Tool(
            name="prodos_list",
            description="List files on a ProDOS disk image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "disk": {
                        "type": "string",
                        "description": "Path to the ProDOS disk image (.dsk or .po)"
                    }
                },
                "required": ["disk"]
            }
        ),
        Tool(
            name="prodos_add",
            description="Add a binary file to a ProDOS disk image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "disk": {
                        "type": "string",
                        "description": "Path to the ProDOS disk image"
                    },
                    "file": {
                        "type": "string",
                        "description": "Path to the local file to add"
                    },
                    "name": {
                        "type": "string",
                        "description": "Name for the file on disk (max 15 chars)"
                    },
                    "type": {
                        "type": "string",
                        "default": "BIN",
                        "description": "File type: BIN, SYS, BAS, or TXT"
                    },
                    "addr": {
                        "type": "string",
                        "default": "0000",
                        "description": "Load address in hex (for BIN files)"
                    }
                },
                "required": ["disk", "file", "name"]
            }
        ),
        Tool(
            name="prodos_del",
            description="Delete a file from a ProDOS disk image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "disk": {
                        "type": "string",
                        "description": "Path to the ProDOS disk image"
                    },
                    "name": {
                        "type": "string",
                        "description": "Name of the file to delete"
                    }
                },
                "required": ["disk", "name"]
            }
        ),

        # Assembly Language Tools
        Tool(
            name="assemble",
            description="Assemble 6502 source code and load binary into emulator memory. Returns size and load address. Use call() to execute it.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "6502 assembly source code (ca65 format)"
                    },
                    "load_address": {
                        "type": "integer",
                        "default": 24576,
                        "description": "Load address for the code (default: $6000 = 24576)"
                    }
                },
                "required": ["source"]
            }
        ),
        Tool(
            name="call",
            description="Execute machine code at an address. The code should end with RTS to return cleanly.",
            inputSchema={
                "type": "object",
                "properties": {
                    "address": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 65535,
                        "description": "Address to call (JSR)"
                    }
                },
                "required": ["address"]
            }
        ),
        Tool(
            name="asm_templates",
            description="List available assembly code templates, or get a specific template by name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Template name to retrieve (omit to list all)"
                    }
                }
            }
        ),

        # Mouse Tools
        Tool(
            name="init_mouse",
            description="Initialize AppleMouse card in slot 4. Call once at startup. Returns success/failure. Note: Requires mouse card (works on real hardware or MAME with mouse, not Bobbin).",
            inputSchema={
                "type": "object",
                "properties": {
                    "slot": {
                        "type": "integer",
                        "default": 4,
                        "minimum": 1,
                        "maximum": 7,
                        "description": "Slot number where mouse card is installed (default: 4)"
                    }
                }
            }
        ),
        Tool(
            name="read_mouse",
            description="Read current mouse position and button state. Returns X (0-1023), Y (0-1023), and button pressed status. Call init_mouse first.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="set_mouse",
            description="Set the emulated mouse position and button state. Use this to control the mouse in Bobbin. Requires boot with mouse=true.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 1023,
                        "description": "X position (0-1023)"
                    },
                    "y": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 1023,
                        "description": "Y position (0-1023)"
                    },
                    "button": {
                        "type": "boolean",
                        "default": False,
                        "description": "Button pressed state"
                    }
                },
                "required": ["x", "y"]
            }
        ),

        # State Snapshots
        Tool(
            name="save_state",
            description="Save emulator state (CPU, 128KB RAM, soft switches) to a file. Use this to create snapshots for instant environment loading.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to save state file (e.g., '/tmp/basic.state')"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="load_state",
            description="Load emulator state from a file. Instantly restores CPU, 128KB RAM, and soft switches.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to state file to load"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="load_basic_env",
            description="Instantly load a pre-baked BASIC environment (Apple //e at ] prompt). Much faster than boot.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="load_prodos_env",
            description="Instantly load a pre-baked ProDOS BASIC environment. Much faster than boot with disk.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="load_dos33_env",
            description="Instantly load a pre-baked DOS 3.3 BASIC environment. Much faster than boot with disk.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),

        # Proxy Control
        Tool(
            name="proxy_start",
            description="Start the Apple II agent proxy server. The proxy bridges the Apple II to Claude API.",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {
                        "type": "integer",
                        "default": 8080,
                        "description": "Port to listen on (default: 8080)"
                    }
                }
            }
        ),
        Tool(
            name="proxy_stop",
            description="Stop the Apple II agent proxy server.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="proxy_status",
            description="Get the status of the Apple II agent proxy server.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="proxy_log",
            description="Get recent proxy server log output.",
            inputSchema={
                "type": "object",
                "properties": {
                    "lines": {
                        "type": "integer",
                        "default": 50,
                        "description": "Number of log lines to return"
                    }
                }
            }
        ),

        # Help
        Tool(
            name="help",
            description="Get the Apple II MCP development guide — tool reference, tips, gotchas, disk image instructions, memory map, and common workflows. Call this first if you're new to Apple II development.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Optional: filter to a specific topic (e.g., 'basic', 'assembly', 'disk', 'graphics', 'memory', 'quick start')"
                    }
                }
            }
        ),
    ]


# =============================================================================
# Tool Implementations
# =============================================================================

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    """Handle tool calls."""
    try:
        result = await _call_tool_impl(name, arguments)
        return CallToolResult(content=[TextContent(type="text", text=result)])
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")],
            isError=True
        )


async def _call_tool_impl(name: str, args: dict[str, Any]) -> str:
    """Implement tool calls."""
    emu = get_emulator()

    # --- Machine Control ---
    if name == "boot":
        machine = args.get("machine", "enhanced")
        disk = args.get("disk")
        uthernet2 = args.get("uthernet2", False)
        mouse = args.get("mouse", False)
        timeout = args.get("timeout", 60)
        wait_for_prompt = args.get("wait_for_prompt", True)
        output = emu.boot(machine=machine, disk=disk, uthernet2=uthernet2, mouse=mouse,
                          timeout=timeout, wait_for_prompt=wait_for_prompt)
        extras = []
        if uthernet2:
            extras.append("uthernet2 in slot 3")
        if mouse:
            extras.append("mouse in slot 4")
        extra_str = f" [{', '.join(extras)}]" if extras else ""
        return f"Emulator started ({machine}{extra_str}). Output:\n{output}"

    elif name == "shutdown":
        emu.shutdown()
        return "Emulator stopped."

    elif name == "pause":
        emu.pause()
        return "Emulation paused. CPU usage reduced. Call resume before next operation."

    elif name == "resume":
        emu.resume()
        return "Emulation resumed."

    elif name == "reset":
        cold = args.get("cold", False)
        emu.reset(cold=cold)
        return f"{'Cold' if cold else 'Warm'} reset complete."

    # --- Memory Access ---
    elif name == "peek":
        address = args["address"]
        count = args.get("count", 1)
        fmt = args.get("format", "hex")

        data = emu.peek(address, count)

        if fmt == "hex":
            result = ' '.join(f"{b:02X}" for b in data)
        elif fmt == "decimal":
            result = ' '.join(str(b) for b in data)
        else:  # ascii
            result = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)

        return f"${address:04X}: {result}"

    elif name == "poke":
        address = args["address"]
        data = args["data"]
        emu.poke(address, data)
        return f"Wrote {len(data)} bytes at ${address:04X}"

    elif name == "load_binary":
        address = args["address"]
        hex_data = args["hex_data"]
        # Parse hex string
        data = bytes.fromhex(hex_data.replace(' ', ''))
        # Load in chunks to avoid overflowing Bobbin's 8KB socket receive buffer
        CHUNK = 2048
        for offset in range(0, len(data), CHUNK):
            chunk = data[offset:offset + CHUNK]
            emu.load(address + offset, chunk.hex())
        return f"Loaded {len(data)} bytes at ${address:04X}"

    elif name == "load_file":
        filepath = args["path"]
        address = args["address"]
        p = Path(filepath)
        if not p.exists():
            return f"ERROR: File not found: {filepath}"
        data = p.read_bytes()
        if len(data) == 0:
            return f"ERROR: File is empty: {filepath}"
        if address + len(data) > 0x10000:
            return f"ERROR: File too large ({len(data)} bytes) for address ${address:04X} — would exceed 64KB"
        # Load in chunks using hex format to avoid overflowing Bobbin's 8KB socket receive buffer
        # (poke sends JSON array ~4-5 chars/byte; load sends hex ~2 chars/byte; 2KB chunks stay well under 8KB)
        CHUNK = 2048
        for offset in range(0, len(data), CHUNK):
            chunk = data[offset:offset + CHUNK]
            emu.load(address + offset, chunk.hex())
        return f"Loaded {len(data)} bytes from {p.name} at ${address:04X} (${address:04X}-${address + len(data) - 1:04X})"

    # --- Screen ---
    elif name == "read_screen":
        annotated = args.get("annotated", False)
        # Default to nonblocking (SIGUSR1) since debugger entry via pexpect is unreliable
        nonblocking = args.get("nonblocking", True)

        if nonblocking:
            # Use SIGUSR1-based capture (doesn't pause emulation)
            lines = emu.read_screen_nonblocking()
        else:
            # Use debugger-based method (pauses emulation briefly)
            # WARNING: This can cause EOF errors due to pexpect/signal issues
            lines = emu.read_screen()

        return format_screen(lines, include_line_numbers=annotated)

    # --- Graphics ---
    elif name == "capture_hgr":
        page = args.get("page", 1)
        fmt = args.get("format", "png")
        color = args.get("color", False)
        filename = args.get("filename")

        import time
        timestamp = int(time.time())

        if fmt == "png":
            # Capture as PPM first, then convert to PNG
            ppm_file = f"/tmp/hgr{page}_{timestamp}.ppm"
            success = emu.capture_hgr(ppm_file, page=page, format="ppm", color=color)
            if success:
                if filename:
                    png_file = filename if filename.endswith('.png') else filename + '.png'
                else:
                    png_file = f"/tmp/hgr{page}_{timestamp}.png"
                filename = convert_ppm_to_png(ppm_file, png_file)
        else:
            if not filename:
                ext = "txt" if fmt == "ascii" else "ppm"
                filename = f"/tmp/hgr{page}_{timestamp}.{ext}"
            success = emu.capture_hgr(filename, page=page, format=fmt, color=color)

        if success:
            result = f"Captured HGR{page} to: {filename}\n"
            result += f"Format: {fmt}" + (" (color)" if color else " (mono)")
            result += f"\n\nUse the Read tool to view this file."
            return result
        else:
            return f"Failed to capture HGR{page}"

    elif name == "read_hgr_ascii":
        page = args.get("page", 1)
        import tempfile

        # Use temp file
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            filepath = f.name

        success = emu.capture_hgr(filepath, page=page, format="ascii")

        if success:
            with open(filepath, 'r') as f:
                ascii_art = f.read()
            import os
            os.unlink(filepath)
            return f"HGR Page {page} (280x192 as ASCII art):\n\n{ascii_art}"
        else:
            return f"Failed to capture HGR{page}"

    # --- GR (Lo-Res) Graphics ---
    elif name == "capture_gr":
        page = args.get("page", 1)
        fmt = args.get("format", "png")
        native = args.get("native", False)
        filename = args.get("filename")

        import time
        timestamp = int(time.time())
        res = "native" if native else "scaled"

        if fmt == "png":
            # Capture as PPM first, then convert to PNG
            ppm_file = f"/tmp/gr{page}_{res}_{timestamp}.ppm"
            success = emu.capture_gr(ppm_file, page=page, format="ppm", native=native)
            if success:
                if filename:
                    png_file = filename if filename.endswith('.png') else filename + '.png'
                else:
                    png_file = f"/tmp/gr{page}_{res}_{timestamp}.png"
                filename = convert_ppm_to_png(ppm_file, png_file)
        else:
            if not filename:
                ext = "txt" if fmt == "ascii" else "ppm"
                filename = f"/tmp/gr{page}_{res}_{timestamp}.{ext}"
            success = emu.capture_gr(filename, page=page, format=fmt, native=native)

        if success:
            if native:
                result = f"Captured GR{page} to: {filename}\nFormat: {fmt} (40x48 native)"
            else:
                result = f"Captured GR{page} to: {filename}\nFormat: {fmt} (280x192 scaled)"
            result += f"\n\nUse the Read tool to view this file."
            return result
        else:
            return f"Failed to capture GR{page}"

    elif name == "read_gr_ascii":
        page = args.get("page", 1)
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            filepath = f.name

        success = emu.capture_gr(filepath, page=page, format="ascii")

        if success:
            with open(filepath, 'r') as f:
                ascii_art = f.read()
            import os
            os.unlink(filepath)
            return f"GR Page {page} (40x48, hex digits = colors 0-F):\n\n{ascii_art}"
        else:
            return f"Failed to capture GR{page}"

    # --- DHGR (Double Hi-Res) Graphics ---
    elif name == "capture_dhgr":
        page = args.get("page", 1)
        fmt = args.get("format", "png")
        filename = args.get("filename")

        import time
        timestamp = int(time.time())

        if fmt == "png":
            # Capture as PPM first, then convert to PNG
            ppm_file = f"/tmp/dhgr{page}_{timestamp}.ppm"
            success = emu.capture_dhgr(ppm_file, page=page, format="ppm")
            if success:
                if filename:
                    png_file = filename if filename.endswith('.png') else filename + '.png'
                else:
                    png_file = f"/tmp/dhgr{page}_{timestamp}.png"
                filename = convert_ppm_to_png(ppm_file, png_file)
        else:
            if not filename:
                ext = "txt" if fmt == "ascii" else "ppm"
                filename = f"/tmp/dhgr{page}_{timestamp}.{ext}"
            success = emu.capture_dhgr(filename, page=page, format=fmt)

        if success:
            result = f"Captured DHGR{page} to: {filename}\n"
            result += f"Format: {fmt} (560x192 mono)"
            result += f"\n\nUse the Read tool to view this file."
            return result
        else:
            return f"Failed to capture DHGR{page} (requires //e with aux memory)"

    elif name == "read_dhgr_ascii":
        page = args.get("page", 1)
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            filepath = f.name

        success = emu.capture_dhgr(filepath, page=page, format="ascii")

        if success:
            with open(filepath, 'r') as f:
                ascii_art = f.read()
            import os
            os.unlink(filepath)
            return f"DHGR Page {page} (560x192 as ASCII art):\n\n{ascii_art}"
        else:
            return f"Failed to capture DHGR{page} (requires //e with aux memory)"

    # --- DGR (Double Lo-Res) Graphics ---
    elif name == "capture_dgr":
        page = args.get("page", 1)
        fmt = args.get("format", "png")
        native = args.get("native", False)
        filename = args.get("filename")

        import time
        timestamp = int(time.time())
        res = "native" if native else "scaled"

        if fmt == "png":
            # Capture as PPM first, then convert to PNG
            ppm_file = f"/tmp/dgr{page}_{res}_{timestamp}.ppm"
            success = emu.capture_dgr(ppm_file, page=page, format="ppm", native=native)
            if success:
                if filename:
                    png_file = filename if filename.endswith('.png') else filename + '.png'
                else:
                    png_file = f"/tmp/dgr{page}_{res}_{timestamp}.png"
                filename = convert_ppm_to_png(ppm_file, png_file)
        else:
            if not filename:
                ext = "txt" if fmt == "ascii" else "ppm"
                filename = f"/tmp/dgr{page}_{res}_{timestamp}.{ext}"
            success = emu.capture_dgr(filename, page=page, format=fmt, native=native)

        if success:
            if native:
                result = f"Captured DGR{page} to: {filename}\nFormat: {fmt} (80x48 native)"
            else:
                result = f"Captured DGR{page} to: {filename}\nFormat: {fmt} (560x192 scaled)"
            result += f"\n\nUse the Read tool to view this file."
            return result
        else:
            return f"Failed to capture DGR{page} (requires //e with aux memory)"

    elif name == "read_dgr_ascii":
        page = args.get("page", 1)
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            filepath = f.name

        success = emu.capture_dgr(filepath, page=page, format="ascii")

        if success:
            with open(filepath, 'r') as f:
                ascii_art = f.read()
            import os
            os.unlink(filepath)
            return f"DGR Page {page} (80x48, hex digits = colors 0-F):\n\n{ascii_art}"
        else:
            return f"Failed to capture DGR{page} (requires //e with aux memory)"

    # --- Input ---
    elif name == "type_text":
        text = args["text"]
        press_return = args.get("press_return", True)
        # Use stdin-based typing - more reliable than debugger key injection
        emu.type_text(text, include_return=press_return, use_inject=False)
        return f"Typed: {text}" + (" + RETURN" if press_return else "")

    elif name == "send_key":
        key = args["key"]
        if key == "RETURN":
            emu.send_return()
        elif key == "ESCAPE":
            emu.process.send('\x1b')
        elif key == "CTRL-C":
            emu.send_control('c')
        elif key == "CTRL-RESET":
            emu.reset(cold=False)
        return f"Sent: {key}"

    # --- BASIC ---
    elif name == "run_basic":
        command = args["command"]
        timeout = args.get("timeout", 60)
        output = emu.run_basic_command(command, timeout=timeout)
        return output

    elif name == "run_and_capture":
        command = args.get("command", "RUN")
        timeout = args.get("timeout", 60)
        capture_mode = args.get("capture_mode", "gr")

        # Run the command
        output = emu.run_basic_command(command, timeout=timeout)

        # Capture the screen
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            filepath = f.name

        if capture_mode == "gr":
            success = emu.capture_gr(filepath, page=1, format="ascii")
            mode_name = "GR (40x48)"
        elif capture_mode == "hgr":
            success = emu.capture_hgr(filepath, page=1, format="ascii")
            mode_name = "HGR (280x192)"
        else:  # text
            lines = emu.read_screen()
            screen = format_screen(lines, include_line_numbers=False)
            return f"Command: {command}\nOutput: {output}\n\nText Screen:\n{screen}"

        if success:
            with open(filepath, 'r') as f:
                ascii_art = f.read()
            import os
            os.unlink(filepath)
            return f"Command: {command}\nOutput: {output}\n\n{mode_name} Screen:\n{ascii_art}"
        else:
            return f"Command: {command}\nOutput: {output}\n\nScreen capture failed (program may still be running or waiting for input)"

    elif name == "send_keys_and_capture":
        keys = args["keys"]
        delay_ms = args.get("delay_ms", 100)
        capture_mode = args.get("capture_mode", "gr")

        # Send the keystrokes
        for key in keys.upper():
            emu.process.send(key)

        # Wait for the delay
        import time
        time.sleep(delay_ms / 1000.0)

        # Capture the screen
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            filepath = f.name

        if capture_mode == "gr":
            success = emu.capture_gr(filepath, page=1, format="ascii")
            mode_name = "GR (40x48)"
        elif capture_mode == "hgr":
            success = emu.capture_hgr(filepath, page=1, format="ascii")
            mode_name = "HGR (280x192)"
        else:  # text
            lines = emu.read_screen()
            screen = format_screen(lines, include_line_numbers=False)
            return f"Sent keys: {keys}\n\nText Screen:\n{screen}"

        if success:
            with open(filepath, 'r') as f:
                ascii_art = f.read()
            import os
            os.unlink(filepath)
            return f"Sent keys: {keys}\n\n{mode_name} Screen:\n{ascii_art}"
        else:
            return f"Sent keys: {keys}\n\nScreen capture failed"

    elif name == "clear_gr":
        color = args.get("color", 0)
        # Enter GR mode and clear with the specified color
        emu.run_basic_command(f"GR:COLOR={color}:FOR I=0 TO 39:VLIN 0,39 AT I:NEXT")
        return f"Cleared GR screen to color {color}"

    elif name == "clear_hgr":
        page = args.get("page", 1)
        # Enter HGR mode and clear
        if page == 1:
            emu.run_basic_command("HGR:HCOLOR=0:FOR Y=0 TO 191:HPLOT 0,Y TO 279,Y:NEXT")
        else:
            emu.run_basic_command("HGR2:HCOLOR=0:FOR Y=0 TO 191:HPLOT 0,Y TO 279,Y:NEXT")
        return f"Cleared HGR page {page} to black"

    # --- Tokenization ---
    elif name == "type_and_capture":
        basic_line = args["basic_line"]

        # Clear any existing program
        emu.run_basic_command("NEW")

        # Type the line
        emu.type_text(basic_line, include_return=True, use_inject=False)
        emu.wait_for_prompt("]")

        # Read memory at $0801 to see tokenized form
        data = emu.peek(0x0801, 128)

        # Find end of program (00 00)
        end = 0
        for i in range(len(data) - 1):
            if data[i] == 0 and data[i+1] == 0:
                end = i + 2
                break

        tokenized = data[:end] if end > 0 else data[:32]
        hex_str = ' '.join(f"{b:02X}" for b in tokenized)

        # Annotate the tokens
        annotations = annotate_tokenized(tokenized)

        return f"Typed: {basic_line}\nTokenized ({len(tokenized)} bytes):\n{hex_str}\n\nAnnotation:\n{annotations}"

    elif name == "tokenize":
        source = args["source"]
        # Use pure Python tokenizer
        tokenized = tokenize_basic(source)
        hex_str = ' '.join(f"{b:02X}" for b in tokenized)
        return f"Tokenized {len(tokenized)} bytes\nHex: {hex_str}"

    elif name == "compare_tokenization":
        basic_line = args["basic_line"]
        your_hex = args["your_hex"].replace(' ', '').upper()

        # Get Apple II's tokenization
        emu.run_basic_command("NEW")
        emu.type_text(basic_line, include_return=True, use_inject=False)
        emu.wait_for_prompt("]")

        data = emu.peek(0x0801, 128)
        end = 0
        for i in range(len(data) - 1):
            if data[i] == 0 and data[i+1] == 0:
                end = i + 2
                break

        apple_tokenized = data[:end] if end > 0 else data[:32]
        apple_hex = ''.join(f"{b:02X}" for b in apple_tokenized)

        # Compare
        match = apple_hex == your_hex

        if match:
            return f"MATCH! Both produce:\n{' '.join(apple_hex[i:i+2] for i in range(0, len(apple_hex), 2))}"
        else:
            # Find differences
            diffs = []
            max_len = max(len(apple_hex), len(your_hex))
            for i in range(0, max_len, 2):
                a = apple_hex[i:i+2] if i < len(apple_hex) else "--"
                y = your_hex[i:i+2] if i < len(your_hex) else "--"
                if a != y:
                    diffs.append(f"  Offset {i//2}: Apple={a}, Yours={y}")

            return f"MISMATCH!\nApple: {' '.join(apple_hex[i:i+2] for i in range(0, len(apple_hex), 2))}\nYours: {' '.join(your_hex[i:i+2] for i in range(0, len(your_hex), 2))}\n\nDifferences:\n" + '\n'.join(diffs)

    # --- Injection ---
    elif name == "inject_tokenized_basic":
        load_addr = args.get("load_address", 0x0801)
        auto_run = args.get("auto_run", False)

        # Accept source (preferred) or hex_data
        if "source" in args and args["source"]:
            source = args["source"]
            data = bytes(tokenize_basic(source))
        elif "hex_data" in args and args["hex_data"]:
            hex_data = args["hex_data"]
            data = bytes.fromhex(hex_data.replace(' ', ''))
        else:
            return "ERROR: Provide either 'source' (BASIC code) or 'hex_data' (pre-tokenized hex)"

        # Calculate end address
        end_addr = load_addr + len(data)

        # Write tokenized BASIC to memory in chunks using load (hex string).
        # The control socket has an 8KB command buffer. Using load with hex
        # strings is much more compact than poke with JSON integer arrays.
        # 2KB of binary = 4KB hex string + ~40 bytes overhead = fits in 8KB.
        CHUNK_SIZE = 2048
        for offset in range(0, len(data), CHUNK_SIZE):
            chunk = data[offset:offset + CHUNK_SIZE]
            chunk_hex = chunk.hex()
            emu.load(load_addr + offset, chunk_hex)

        # Update BASIC pointers using poke
        # TXTTAB ($67-68) = start of program
        emu.poke(0x67, [load_addr & 0xFF, (load_addr >> 8) & 0xFF])

        # VARTAB, ARYTAB, STREND ($69-6E) = end of program
        emu.poke(0x69, [end_addr & 0xFF, (end_addr >> 8) & 0xFF])
        emu.poke(0x6B, [end_addr & 0xFF, (end_addr >> 8) & 0xFF])
        emu.poke(0x6D, [end_addr & 0xFF, (end_addr >> 8) & 0xFF])

        # PRGEND ($AF-B0) = end of program
        emu.poke(0xAF, [end_addr & 0xFF, (end_addr >> 8) & 0xFF])

        result = f"Injected {len(data)} bytes at ${load_addr:04X}\n"
        result += f"Updated pointers: TXTTAB=${load_addr:04X}, VARTAB=${end_addr:04X}"

        if auto_run:
            # Type RUN and wait for output
            emu.type_text("RUN", include_return=True)
            import time
            time.sleep(0.5)
            lines = emu.read_screen()
            output = '\n'.join(line.rstrip() for line in lines).strip()
            result += f"\n\nRUN output:\n{output}"

        return result

    # --- Observation ---
    elif name == "get_registers":
        regs = emu.get_registers()
        return json.dumps(regs, indent=2)

    elif name == "get_basic_pointers":
        # Read all the important BASIC pointers
        pointers = {}

        txttab = emu.peek(0x67, 2)
        pointers["TXTTAB"] = f"${txttab[0] + txttab[1]*256:04X} (program start)"

        vartab = emu.peek(0x69, 2)
        pointers["VARTAB"] = f"${vartab[0] + vartab[1]*256:04X} (variables start)"

        arytab = emu.peek(0x6B, 2)
        pointers["ARYTAB"] = f"${arytab[0] + arytab[1]*256:04X} (arrays start)"

        strend = emu.peek(0x6D, 2)
        pointers["STREND"] = f"${strend[0] + strend[1]*256:04X} (string storage end)"

        fretop = emu.peek(0x6F, 2)
        pointers["FRETOP"] = f"${fretop[0] + fretop[1]*256:04X} (free space top)"

        himem = emu.peek(0x73, 2)
        pointers["HIMEM"] = f"${himem[0] + himem[1]*256:04X} (highest address)"

        prgend = emu.peek(0xAF, 2)
        pointers["PRGEND"] = f"${prgend[0] + prgend[1]*256:04X} (program end)"

        return json.dumps(pointers, indent=2)

    # --- Knowledge Base ---
    elif name == "record_technique":
        KNOWLEDGE_DIR.mkdir(exist_ok=True)
        techniques_file = KNOWLEDGE_DIR / "techniques.json"

        # Load existing techniques
        if techniques_file.exists():
            with open(techniques_file) as f:
                techniques = json.load(f)
        else:
            techniques = {"techniques": [], "version": 1}

        # Add new technique
        technique = {
            "name": args["name"],
            "category": args["category"],
            "description": args["description"],
            "steps": args.get("steps", []),
            "success": args.get("success", True),
            "notes": args.get("notes", ""),
        }
        techniques["techniques"].append(technique)

        # Save
        with open(techniques_file, 'w') as f:
            json.dump(techniques, f, indent=2)

        return f"Recorded technique: {args['name']}"

    elif name == "query_techniques":
        techniques_file = KNOWLEDGE_DIR / "techniques.json"

        if not techniques_file.exists():
            return "No techniques recorded yet."

        with open(techniques_file) as f:
            data = json.load(f)

        results = data["techniques"]

        # Filter by category
        if "category" in args:
            results = [t for t in results if t["category"] == args["category"]]

        # Filter by search term
        if "search" in args:
            search = args["search"].lower()
            results = [t for t in results if search in t["name"].lower() or search in t["description"].lower()]

        if not results:
            return "No matching techniques found."

        output = []
        for t in results:
            output.append(f"- {t['name']} [{t['category']}] {'✓' if t.get('success', True) else '✗'}")
            output.append(f"  {t['description']}")

        return '\n'.join(output)

    # --- Disk Image Tools ---
    elif name == "create_disk":
        filename = args["filename"]
        volume = args.get("volume", 254)
        template = args.get("from_template")

        if template:
            # Copy from template (for bootable disk)
            import shutil
            shutil.copy(template, filename)
            disk = DOS33Disk(filename)
            return f"Created bootable disk from {template}: {filename}"
        else:
            # Create empty formatted disk
            disk = DOS33Disk()
            disk.format(volume_num=volume)
            disk.save(filename)
            return f"Created blank DOS 3.3 disk: {filename} (Volume {volume})"

    elif name == "disk_catalog":
        filename = args["filename"]
        disk = DOS33Disk(filename)
        files = disk.catalog()

        output = [f"\nDISK VOLUME 254\n"]
        for f in files:
            lock = '*' if f['locked'] else ' '
            output.append(f"{lock}{f['type']} {f['sectors']:03d} {f['name']}")
        output.append(f"\n{len(files)} FILES")

        return '\n'.join(output)

    elif name == "save_basic_to_disk":
        disk_filename = args["disk_filename"]
        program_name = args["program_name"]
        source = args["source"]

        # Auto-detect disk format
        disk_format = detect_disk_format(disk_filename)

        if disk_format == 'prodos':
            # ProDOS: tokenize and use prodos_add
            tokenized = tokenize_basic(source)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f:
                f.write(tokenized)
                temp_path = f.name
            try:
                # Use the prodos_add tool - type FC = BAS, aux 0801 = BASIC start
                tools_dir = Path(__file__).parent.parent.parent / "tools"
                result = subprocess.run(
                    ["python3", str(tools_dir / "prodos_add.py"),
                     disk_filename, temp_path, program_name.upper()[:15], "FC", "0801"],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    return f"Error saving to ProDOS disk: {result.stderr}"
                return f"Saved {program_name.upper()} to ProDOS disk {disk_filename}"
            finally:
                os.unlink(temp_path)

        elif disk_format == 'dos33':
            # DOS 3.3: use native DOS33Disk
            disk = DOS33Disk(disk_filename)
            sectors = disk.save_basic_program(program_name, source)
            disk.save()
            return f"Saved {program_name.upper()} ({sectors} sectors) to DOS 3.3 disk {disk_filename}"

        else:
            return f"Error: Unknown disk format for {disk_filename}. Expected DOS 3.3 or ProDOS."

    elif name == "save_file_to_disk":
        disk_filename = args["disk_filename"]
        bas_filename = args["bas_filename"]
        program_name = args.get("program_name")

        if not program_name:
            # Derive from filename
            program_name = os.path.splitext(os.path.basename(bas_filename))[0]

        with open(bas_filename, 'r') as f:
            source = f.read()

        # Auto-detect disk format
        disk_format = detect_disk_format(disk_filename)

        if disk_format == 'prodos':
            # ProDOS: tokenize and use prodos_add - type FC = BAS, aux 0801 = BASIC start
            tokenized = tokenize_basic(source)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f:
                f.write(tokenized)
                temp_path = f.name
            try:
                tools_dir = Path(__file__).parent.parent.parent / "tools"
                result = subprocess.run(
                    ["python3", str(tools_dir / "prodos_add.py"),
                     disk_filename, temp_path, program_name.upper()[:15], "FC", "0801"],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    return f"Error saving to ProDOS disk: {result.stderr}"
                return f"Saved {program_name.upper()} from {bas_filename} to ProDOS disk {disk_filename}"
            finally:
                os.unlink(temp_path)

        elif disk_format == 'dos33':
            disk = DOS33Disk(disk_filename)
            sectors = disk.save_basic_program(program_name, source)
            disk.save()
            return f"Saved {program_name.upper()} ({sectors} sectors) from {bas_filename} to DOS 3.3 disk {disk_filename}"

        else:
            return f"Error: Unknown disk format for {disk_filename}. Expected DOS 3.3 or ProDOS."

    # --- ProDOS Disk Tools ---
    elif name == "prodos_list":
        disk = args["disk"]
        # Use the Python prodos tools from this project
        tools_dir = Path(__file__).parent.parent.parent / "tools"
        result = subprocess.run(
            ["python3", str(tools_dir / "prodos_delete.py"), disk, "list"],
            capture_output=True, text=True
        )
        return result.stdout or result.stderr

    elif name == "prodos_add":
        disk = args["disk"]
        file = args["file"]
        name_on_disk = args["name"]
        file_type = args.get("type", "BIN").upper()
        addr = args.get("addr", "0000")

        type_map = {"BIN": "06", "SYS": "FF", "BAS": "FC", "TXT": "04"}
        type_code = type_map.get(file_type, "06")

        tools_dir = Path(__file__).parent.parent.parent / "tools"
        result = subprocess.run(
            ["python3", str(tools_dir / "prodos_add.py"), disk, file, name_on_disk, type_code, addr],
            capture_output=True, text=True
        )
        return result.stdout or result.stderr

    elif name == "prodos_del":
        disk = args["disk"]
        name_to_del = args["name"]

        tools_dir = Path(__file__).parent.parent.parent / "tools"
        result = subprocess.run(
            ["python3", str(tools_dir / "prodos_delete.py"), disk, "delete", name_to_del],
            capture_output=True, text=True
        )
        return result.stdout or result.stderr or "Deleted"

    # --- Assembly Language Tools ---
    elif name == "assemble":
        source = args["source"]
        load_address = args.get("load_address", 0x6000)

        result = assemble(source, load_address)

        if result["success"]:
            # Auto-load into emulator memory (avoids hex going through Claude tokens)
            hex_data = result["hex_data"].replace(' ', '')
            emu.load(load_address, hex_data)
            return (
                f"Assembly successful! Loaded {result['size']} bytes at ${load_address:04X}\n"
                f"Use call(address={load_address}) to execute."
            )
        else:
            return (
                f"Assembly failed at {result['stage']} stage:\n"
                f"{result['error']}"
            )

    elif name == "call":
        address = args["address"]

        # Use BASIC's CALL command to execute the code
        # This works because CALL does a JSR to the address
        output = emu.run_basic_command(f"CALL {address}", timeout=10)

        return f"Called ${address:04X}\nOutput: {output}"

    elif name == "asm_templates":
        name_arg = args.get("name")

        if name_arg:
            template = get_template(name_arg)
            if template:
                return f"Template: {name_arg}\n\n```asm\n{template}\n```"
            else:
                available = ", ".join(list_templates())
                return f"Unknown template: {name_arg}\nAvailable: {available}"
        else:
            templates = list_templates()
            return f"Available assembly templates:\n" + "\n".join(f"  - {t}" for t in templates)

    # --- Mouse Tools ---
    elif name == "init_mouse":
        slot = args.get("slot", 4)

        # Generate mouse init code for the specified slot
        # Slot ROM is at $Cn00 where n=slot, e.g., slot 4 = $C400
        slot_page = 0xC0 + slot  # e.g., $C4 for slot 4
        mouse_init_source = f"""
; Initialize AppleMouse card in slot {slot}
MOUSE_SLOT = {slot}
SLOT_PAGE  = ${slot_page:02X}
MOUSE_ROM  = $C{slot}00
SETMOUSE   = MOUSE_ROM + $12
INITMOUSE  = MOUSE_ROM + $19
SLOT_BYTE  = $07F8 + MOUSE_SLOT

    ; Store slot ID byte (required by firmware)
    lda #SLOT_PAGE
    sta SLOT_BYTE

    ; Check for mouse card signature
    ; AppleMouse signature: $38 at $Cn05, $18 at $Cn07
    lda MOUSE_ROM + $05
    cmp #$38
    bne no_mouse
    lda MOUSE_ROM + $07
    cmp #$18
    bne no_mouse

    ; Initialize mouse
    ldx #MOUSE_SLOT * $10
    jsr INITMOUSE

    ; Set mouse mode: enable, no interrupts
    lda #$01
    jsr SETMOUSE

    ; Store success flag at $0305
    lda #$00
    sta $0305
    rts

no_mouse:
    lda #$FF
    sta $0305
    rts
"""
        # Assemble the init code
        result = assemble(mouse_init_source, load_address=0x6000)

        if not result["success"]:
            return f"Assembly failed: {result['error']}"

        # Inject and run
        emu.poke(0x6000, result["bytes"])
        emu.run_basic_command(f"CALL 24576", timeout=5)

        # Check result at $0305
        status = emu.peek(0x0305, 1)[0]

        if status == 0:
            return f"Mouse initialized successfully in slot {slot}\nMouse position will be available at $0300-$0304 after read_mouse"
        else:
            return f"No mouse card found in slot {slot}\nNote: Mouse requires real hardware or MAME with mouse card emulation"

    elif name == "read_mouse":
        # Generate mouse read code
        mouse_read_source = """
; Read mouse position and button
MOUSE_SLOT = 4
MOUSE_READ = $C400 + 2
SLOT_BYTE  = $07FC

MOUSE_XL   = $047C
MOUSE_XH   = $057C
MOUSE_YL   = $04FC
MOUSE_YH   = $05FC
MOUSE_BTN  = $077C

RESULT_XL  = $0300
RESULT_XH  = $0301
RESULT_YL  = $0302
RESULT_YH  = $0303
RESULT_BTN = $0304

    ; Call firmware
    jsr MOUSE_READ

    ; Copy results
    lda MOUSE_XL
    sta RESULT_XL
    lda MOUSE_XH
    sta RESULT_XH
    lda MOUSE_YL
    sta RESULT_YL
    lda MOUSE_YH
    sta RESULT_YH
    lda MOUSE_BTN
    sta RESULT_BTN

    rts
"""
        # Assemble the read code
        result = assemble(mouse_read_source, load_address=0x6000)

        if not result["success"]:
            return f"Assembly failed: {result['error']}"

        # Inject and run
        emu.poke(0x6000, result["bytes"])
        emu.run_basic_command(f"CALL 24576", timeout=5)

        # Read results from $0300-$0304
        data = emu.peek(0x0300, 5)
        x = data[0] + (data[1] * 256)
        y = data[2] + (data[3] * 256)
        button = (data[4] & 0x80) != 0

        return json.dumps({
            "x": x,
            "y": y,
            "button": button,
            "raw": {
                "x_low": data[0],
                "x_high": data[1],
                "y_low": data[2],
                "y_high": data[3],
                "button_byte": data[4]
            }
        }, indent=2)

    elif name == "set_mouse":
        x = args.get("x", 0)
        y = args.get("y", 0)
        button = args.get("button", False)

        # Set mouse position directly in screen holes (slot 4)
        # $047C = X low (1148), $057C = X high (1404)
        # $04FC = Y low (1276), $05FC = Y high (1532)
        # $077C = button status (1916)
        x_lo = x & 0xFF
        x_hi = (x >> 8) & 0xFF
        y_lo = y & 0xFF
        y_hi = (y >> 8) & 0xFF
        btn = 0x80 if button else 0x00

        # Use BASIC POKE commands - more reliable than debugger for state sync
        # Combine into one FOR loop to minimize roundtrips
        pokes = f"FOR I=0 TO 0:POKE 1148,{x_lo}:POKE 1404,{x_hi}:POKE 1276,{y_lo}:POKE 1532,{y_hi}:POKE 1916,{btn}:NEXT"
        emu.run_basic_command(pokes)

        return f"Mouse set to X={x}, Y={y}, button={'pressed' if button else 'released'}"

    # --- State Snapshots ---
    elif name == "save_state":
        path = args["path"]
        result = emu.save_state(path)
        if result.get("ok"):
            return f"State saved to: {path}"
        else:
            return f"Failed to save state: {result.get('error', 'unknown error')}"

    elif name == "load_state":
        path = args["path"]
        result = emu.load_state(path)
        if result.get("ok"):
            version = result.get("version", 1)
            return f"State loaded from: {path} (version {version})"
        else:
            return f"Failed to load state: {result.get('error', 'unknown error')}"

    elif name == "load_basic_env":
        # Load pre-baked BASIC environment
        states_dir = Path(__file__).parent.parent.parent / "states"
        basic_state = states_dir / "basic.state"
        if not basic_state.exists():
            return f"BASIC environment snapshot not found at {basic_state}. Run tools/create_snapshots.py first."
        # Auto-boot if not running
        if not emu.is_running:
            emu.boot(machine="enhanced", timeout=30.0)
        result = emu.load_state(str(basic_state))
        if result.get("ok"):
            return "BASIC environment loaded. Ready at ] prompt."
        else:
            return f"Failed to load BASIC environment: {result.get('error', 'unknown error')}"

    elif name == "load_prodos_env":
        # Load pre-baked ProDOS BASIC environment
        states_dir = Path(__file__).parent.parent.parent / "states"
        prodos_state = states_dir / "prodos.state"
        if not prodos_state.exists():
            return f"ProDOS environment snapshot not found at {prodos_state}. Run tools/create_snapshots.py first."
        # Auto-boot if not running
        if not emu.is_running:
            emu.boot(machine="enhanced", timeout=30.0)
        result = emu.load_state(str(prodos_state))
        if result.get("ok"):
            return "ProDOS BASIC environment loaded. Ready at ] prompt."
        else:
            return f"Failed to load ProDOS environment: {result.get('error', 'unknown error')}"

    elif name == "load_dos33_env":
        # Load pre-baked DOS 3.3 BASIC environment
        states_dir = Path(__file__).parent.parent.parent / "states"
        dos33_state = states_dir / "dos33.state"
        if not dos33_state.exists():
            return f"DOS 3.3 environment snapshot not found at {dos33_state}. Run tools/create_snapshots.py first."
        # Auto-boot if not running
        if not emu.is_running:
            emu.boot(machine="enhanced", timeout=30.0)
        result = emu.load_state(str(dos33_state))
        if result.get("ok"):
            return "DOS 3.3 BASIC environment loaded. Ready at ] prompt."
        else:
            return f"Failed to load DOS 3.3 environment: {result.get('error', 'unknown error')}"

    # --- Proxy Control ---
    elif name == "proxy_start":
        port = args.get("port", 8080)
        result = proxy_control.start(port=port)
        if result["success"]:
            return f"Proxy started (PID: {result['pid']}, port: {result['port']})\nLog: {result['log_file']}"
        else:
            return f"Failed to start proxy: {result['error']}"

    elif name == "proxy_stop":
        result = proxy_control.stop()
        return result["message"]

    elif name == "proxy_status":
        result = proxy_control.status()
        if result["running"]:
            return f"Proxy is running (PID: {result['pid']})\nLog: {result['log_file']}"
        else:
            return "Proxy is not running"

    elif name == "proxy_log":
        lines = args.get("lines", 50)
        return proxy_control.get_log(lines=lines)

    elif name == "help":
        readme_path = Path(__file__).parent / "README.md"
        if not readme_path.exists():
            return "Help file not found. Check apple2_mcp installation."
        content = readme_path.read_text()
        topic = args.get("topic", "").lower().strip()
        if topic:
            # Filter to relevant section(s)
            sections = content.split("\n## ")
            matches = []
            for section in sections:
                heading = section.split("\n")[0].lower()
                if topic in heading:
                    matches.append("## " + section)
                else:
                    # Check subsections too
                    subsections = section.split("\n### ")
                    for sub in subsections[1:]:
                        sub_heading = sub.split("\n")[0].lower()
                        if topic in sub_heading:
                            matches.append("### " + sub)
            if matches:
                return "\n".join(matches)
            return f"No section matching '{topic}'. Call help() without a topic to see all sections."
        return content

    else:
        return f"Unknown tool: {name}"


def annotate_tokenized(data: list[int]) -> str:
    """Annotate tokenized BASIC bytes."""
    if len(data) < 4:
        return "Too short to be valid BASIC"

    lines = []
    offset = 0

    while offset < len(data) - 1:
        # Check for end of program
        if data[offset] == 0 and data[offset + 1] == 0:
            lines.append(f"  {offset:3d}: 00 00 = End of program")
            break

        if offset + 3 >= len(data):
            break

        # Next line pointer
        next_ptr = data[offset] + data[offset + 1] * 256
        lines.append(f"  {offset:3d}: {data[offset]:02X} {data[offset+1]:02X} = Next line pointer (${next_ptr:04X})")
        offset += 2

        # Line number
        if offset + 1 >= len(data):
            break
        line_num = data[offset] + data[offset + 1] * 256
        lines.append(f"  {offset:3d}: {data[offset]:02X} {data[offset+1]:02X} = Line number {line_num}")
        offset += 2

        # Line contents until null
        line_content = []
        while offset < len(data) and data[offset] != 0:
            b = data[offset]
            if b in APPLESOFT_TOKENS:
                line_content.append(f"{b:02X}={APPLESOFT_TOKENS[b]}")
            elif 0x20 <= b <= 0x7F:
                line_content.append(f"{b:02X}='{chr(b)}'")
            else:
                line_content.append(f"{b:02X}")
            offset += 1

        lines.append(f"        Content: {' '.join(line_content)}")

        # End of line null
        if offset < len(data):
            lines.append(f"  {offset:3d}: 00 = End of line")
            offset += 1

    return '\n'.join(lines)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Run the MCP server."""
    import asyncio

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
