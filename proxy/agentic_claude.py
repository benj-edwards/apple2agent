#!/usr/bin/env python3
"""
Agentic Claude for Apple II

Provides an agentic loop where Claude can use tools to:
1. Develop and test code in the Bobbin emulator (fast iteration)
2. Control the real Apple II via A2P protocol (deployment)
3. Stream results back to the user

The agent can work in the emulator for speed, then deploy to real hardware.
"""

import os
import json
import subprocess
from typing import Optional, Callable, Dict, List, Any

# Try to import anthropic
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# Tool definitions for Claude
APPLE2_TOOLS = [
    {
        "name": "emulator_boot",
        "description": "SLOW: Cold boot the emulator. Use emulator_load_env instead for instant start!",
        "input_schema": {
            "type": "object",
            "properties": {
                "disk": {
                    "type": "string",
                    "description": "Optional path to disk image to boot"
                }
            },
            "required": []
        }
    },
    {
        "name": "emulator_load_env",
        "description": "INSTANT: Load pre-saved BASIC environment. Much faster than boot! Use this for testing.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "emulator_type",
        "description": "Type text into the emulator as if from keyboard. Text will be uppercased.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to type"
                },
                "press_return": {
                    "type": "boolean",
                    "description": "Press RETURN after typing (default: true)"
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "emulator_read_screen",
        "description": "Read the current 40x24 text screen from the emulator.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "emulator_run_basic",
        "description": "Execute a BASIC command in the emulator and wait for the prompt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "BASIC command to execute"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "emulator_inject_basic",
        "description": "Inject a tokenized BASIC program into emulator memory. Program becomes ready to RUN.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "BASIC source code with line numbers"
                },
                "auto_run": {
                    "type": "boolean",
                    "description": "Automatically RUN after injection (default: false)"
                }
            },
            "required": ["source"]
        }
    },
    {
        "name": "emulator_capture_graphics",
        "description": "Capture the graphics screen (lo-res or hi-res) as ASCII art.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["gr", "hgr"],
                    "description": "Graphics mode: gr=lo-res 40x48, hgr=hi-res 280x192"
                }
            },
            "required": ["mode"]
        }
    },
    {
        "name": "emulator_peek",
        "description": "Read bytes from emulator memory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "integer",
                    "description": "Memory address (0-65535)"
                },
                "count": {
                    "type": "integer",
                    "description": "Number of bytes to read (default: 1)"
                }
            },
            "required": ["address"]
        }
    },
    {
        "name": "emulator_poke",
        "description": "Write bytes to emulator memory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "integer",
                    "description": "Memory address (0-65535)"
                },
                "data": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Bytes to write (0-255 each)"
                }
            },
            "required": ["address", "data"]
        }
    },
    {
        "name": "apple2_send_code",
        "description": "Send BASIC code to the REAL Apple II via A2P protocol. Use this to deploy tested code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "BASIC source code with line numbers"
                }
            },
            "required": ["source"]
        }
    },
    {
        "name": "apple2_send_message",
        "description": "Send a text message to display on the REAL Apple II.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message to display"
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "apple2_send_status",
        "description": "Send a status update to the REAL Apple II status line.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Status message"
                }
            },
            "required": ["status"]
        }
    },
    {
        "name": "emulator_assemble",
        "description": "Assemble 6502 assembly code and inject into emulator. Returns the load address. Use this for machine language programs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "6502 assembly source code (ca65 format)"
                },
                "load_address": {
                    "type": "integer",
                    "description": "Load address (default: $6000 = 24576)"
                }
            },
            "required": ["source"]
        }
    },
    {
        "name": "emulator_call",
        "description": "Call a machine language routine at an address. The routine should end with RTS.",
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "integer",
                    "description": "Address to call (JSR)"
                }
            },
            "required": ["address"]
        }
    },
    {
        "name": "apple2_send_binary",
        "description": "Send assembled machine code to the REAL Apple II. Specify load address.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hex_data": {
                    "type": "string",
                    "description": "Assembled binary as hex string"
                },
                "load_address": {
                    "type": "integer",
                    "description": "Address to load code (default: $6000)"
                }
            },
            "required": ["hex_data"]
        }
    },
    {
        "name": "disk_save_basic",
        "description": "Save a BASIC program to disk. The program will be tokenized and saved so the user can BLOAD or RUN it later. Requires user permission.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename on disk (max 15 chars, will be uppercased)"
                },
                "source": {
                    "type": "string",
                    "description": "BASIC source code with line numbers"
                }
            },
            "required": ["filename", "source"]
        }
    },
    {
        "name": "disk_save_binary",
        "description": "Save a binary file to disk. Use this to save assembled machine code. Requires user permission.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename on disk (max 15 chars, will be uppercased)"
                },
                "hex_data": {
                    "type": "string",
                    "description": "Binary data as hex string"
                },
                "load_address": {
                    "type": "integer",
                    "description": "Load address for the binary (default: $6000)"
                }
            },
            "required": ["filename", "hex_data"]
        }
    },
    {
        "name": "disk_save_text",
        "description": "Save a text file to disk. Use this to save documentation, data files, or source code. Requires user permission.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename on disk (max 15 chars, will be uppercased)"
                },
                "content": {
                    "type": "string",
                    "description": "Text content to save"
                }
            },
            "required": ["filename", "content"]
        }
    },
    {
        "name": "disk_list",
        "description": "List files on the current disk. Shows filename, type, and size.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "emulator_read_basic_program",
        "description": "Read the current BASIC program from emulator memory and detokenize it. Use this when the user reports an error or you need to see what's in memory.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


class AgenticClaude:
    """
    Agentic Claude that can use tools to interact with Apple II.

    Supports two targets:
    - Emulator (Bobbin via MCP): Fast development and testing
    - Real Apple II (via A2P): Deployment and live interaction
    """

    def __init__(self,
                 send_to_apple2: Callable[[str], None],
                 send_status: Callable[[str], None],
                 send_code: Callable[[str], None],
                 mcp_call: Optional[Callable[[str, dict], Any]] = None,
                 send_binary: Optional[Callable[[str, int], None]] = None):
        """
        Args:
            send_to_apple2: Function to send response text to real Apple II
            send_status: Function to send status updates to real Apple II
            send_code: Function to send BASIC code to real Apple II
            mcp_call: Function to call MCP tools (for emulator)
            send_binary: Function to send machine code to real Apple II
        """
        self.send_to_apple2 = send_to_apple2
        self.send_status = send_status
        self.send_code = send_code
        self.mcp_call = mcp_call
        self.send_binary = send_binary

        self.client = None
        if HAS_ANTHROPIC:
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)

        self.conversation: List[Dict] = []
        self.emulator_running = False

        # Store last assembled binary for deployment
        self.last_binary: Optional[str] = None
        self.last_binary_addr: int = 0x6000

        # Context management - compact when approaching limit
        self.max_context_tokens = 150000  # Leave headroom for 200k context
        self.compact_threshold = 100000   # Start compacting at this level

        # Custom prompt - user can set additional context/instructions
        self.custom_prompt: Optional[str] = None

    def set_custom_prompt(self, prompt: Optional[str]) -> None:
        """Set a custom prompt that will be appended to the system prompt."""
        self.custom_prompt = prompt

    def clear_custom_prompt(self) -> None:
        """Clear the custom prompt."""
        self.custom_prompt = None

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool and return the result."""

        # Emulator tools (via MCP if available)
        if tool_name.startswith("emulator_"):
            if not self.mcp_call:
                return "ERROR: Emulator not available (no MCP connection)"

            # Map tool names to MCP tool names
            mcp_map = {
                "emulator_boot": "mcp__apple2-mcp__boot",
                "emulator_load_env": "mcp__apple2-mcp__load_basic_env",
                "emulator_type": "mcp__apple2-mcp__type_text",
                "emulator_read_screen": "mcp__apple2-mcp__read_screen",
                "emulator_run_basic": "mcp__apple2-mcp__run_basic",
                "emulator_inject_basic": "mcp__apple2-mcp__inject_tokenized_basic",
                "emulator_capture_graphics": "mcp__apple2-mcp__read_gr_ascii",
                "emulator_peek": "mcp__apple2-mcp__peek",
                "emulator_poke": "mcp__apple2-mcp__poke",
            }

            mcp_name = mcp_map.get(tool_name)
            if not mcp_name:
                return f"ERROR: Unknown emulator tool: {tool_name}"

            try:
                # Handle instant environment loading
                if tool_name == "emulator_load_env":
                    self.send_status("LOADING EMULATOR...")
                    self.emulator_running = True
                    result = self.mcp_call("mcp__apple2-mcp__load_basic_env", {})
                    self.send_status("EMULATOR READY")
                    return "Emulator ready (instant load)"

                # Special handling for some tools
                elif tool_name == "emulator_inject_basic":
                    # Need to tokenize first
                    self.send_status("TOKENIZING BASIC...")
                    source = tool_input.get("source", "")
                    result = self.mcp_call("mcp__apple2-mcp__tokenize", {"source": source})
                    if "error" in str(result).lower():
                        return f"Tokenization error: {result}"
                    # Then inject
                    self.send_status("INJECTING PROGRAM...")
                    hex_data = result.get("hex", "") if isinstance(result, dict) else str(result)
                    inject_input = {
                        "hex_data": hex_data,
                        "auto_run": tool_input.get("auto_run", False)
                    }
                    result = self.mcp_call("mcp__apple2-mcp__inject_tokenized_basic", inject_input)
                    self.send_status("PROGRAM LOADED")
                    return str(result)

                elif tool_name == "emulator_capture_graphics":
                    mode = tool_input.get("mode", "gr")
                    self.send_status(f"CAPTURING {mode.upper()} SCREEN...")
                    if mode == "hgr":
                        result = self.mcp_call("mcp__apple2-mcp__read_hgr_ascii", {})
                    else:
                        result = self.mcp_call("mcp__apple2-mcp__read_gr_ascii", {})
                    return str(result)

                elif tool_name == "emulator_boot":
                    self.send_status("BOOTING EMULATOR...")
                    self.emulator_running = True
                    boot_input = {"machine": "enhanced", "uthernet2": True}
                    if "disk" in tool_input:
                        boot_input["disk"] = tool_input["disk"]
                    result = self.mcp_call(mcp_name, boot_input)
                    self.send_status("EMULATOR READY")
                    return str(result)

                elif tool_name == "emulator_run_basic":
                    cmd = tool_input.get("command", "")[:20]
                    self.send_status(f"RUNNING: {cmd}...")
                    result = self.mcp_call(mcp_name, tool_input)
                    self.send_status("READING OUTPUT...")
                    screen = self.mcp_call("mcp__apple2-mcp__read_screen", {})
                    # Return screen content to Claude for analysis (not shown to user)
                    return str(result) + "\n\nScreen:\n" + str(screen)

                elif tool_name == "emulator_read_screen":
                    self.send_status("READING SCREEN...")
                    result = self.mcp_call(mcp_name, tool_input)
                    # Return to Claude for analysis (not shown to user)
                    return str(result)

                elif tool_name == "emulator_type":
                    text = tool_input.get("text", "")[:15]
                    self.send_status(f"TYPING: {text}...")
                    result = self.mcp_call(mcp_name, tool_input)
                    return str(result)

                elif tool_name == "emulator_peek":
                    addr = tool_input.get("address", 0)
                    self.send_status(f"PEEK ${addr:04X}...")
                    result = self.mcp_call(mcp_name, tool_input)
                    return str(result)

                elif tool_name == "emulator_poke":
                    addr = tool_input.get("address", 0)
                    self.send_status(f"POKE ${addr:04X}...")
                    result = self.mcp_call(mcp_name, tool_input)
                    return str(result)

                else:
                    result = self.mcp_call(mcp_name, tool_input)
                    return str(result)

            except Exception as e:
                self.send_status(f"ERROR: {str(e)[:20]}")
                return f"ERROR: {str(e)}"

        # Real Apple II tools (via A2P protocol)
        elif tool_name == "apple2_send_code":
            self.send_status("DEPLOYING TO APPLE II...")
            source = tool_input.get("source", "")
            self.send_code(source)
            self.send_status("CODE DEPLOYED!")
            return "Code sent to Apple II"

        elif tool_name == "apple2_send_message":
            message = tool_input.get("message", "")
            self.send_to_apple2(message)
            return "Message sent to Apple II"

        elif tool_name == "apple2_send_status":
            status = tool_input.get("status", "")
            self.send_status(status)
            return "Status sent to Apple II"

        elif tool_name == "apple2_send_binary":
            self.send_status("DEPLOYING BINARY...")
            hex_data = tool_input.get("hex_data", "")
            load_addr = tool_input.get("load_address", 0x6000)
            if self.send_binary:
                self.send_binary(hex_data, load_addr)
                self.send_status(f"BINARY AT ${load_addr:04X}")
                return f"Binary sent to Apple II at ${load_addr:04X}"
            else:
                return "ERROR: Binary send not available"

        elif tool_name == "emulator_assemble":
            if not self.mcp_call:
                return "ERROR: Emulator not available (no MCP connection)"
            source = tool_input.get("source", "")
            load_addr = tool_input.get("load_address", 0x6000)
            try:
                # Assemble the code
                self.send_status("ASSEMBLING 6502...")
                result = self.mcp_call("mcp__apple2-mcp__assemble", {
                    "source": source,
                    "load_address": load_addr
                })
                if isinstance(result, dict) and "hex" in result:
                    hex_data = result["hex"]
                    size = len(hex_data.replace(" ", "")) // 2
                    self.send_status(f"LOADING {size} BYTES...")
                    # Load into emulator memory
                    self.mcp_call("mcp__apple2-mcp__load_binary", {
                        "address": load_addr,
                        "hex_data": hex_data
                    })
                    # Store for later deployment
                    self.last_binary = hex_data
                    self.last_binary_addr = load_addr
                    self.send_status(f"ASSEMBLED ${load_addr:04X}")
                    return f"Assembled {size} bytes at ${load_addr:04X}. Use CALL {load_addr} to run."
                else:
                    self.send_status("ASSEMBLY FAILED")
                    return f"Assembly error: {result}"
            except Exception as e:
                self.send_status("ASSEMBLY ERROR")
                return f"ERROR: {str(e)}"

        elif tool_name == "emulator_call":
            if not self.mcp_call:
                return "ERROR: Emulator not available (no MCP connection)"
            address = tool_input.get("address", 0x6000)
            try:
                self.send_status(f"CALL ${address:04X}...")
                result = self.mcp_call("mcp__apple2-mcp__call", {"address": address})
                self.send_status("EXECUTED")
                return f"Called ${address:04X}: {result}"
            except Exception as e:
                self.send_status("CALL FAILED")
                return f"ERROR: {str(e)}"

        elif tool_name == "disk_save_basic":
            filename = tool_input.get("filename", "PROGRAM").upper()[:15]
            source = tool_input.get("source", "")
            # Notify user we're saving to disk
            self.send_status(f"SAVING {filename} TO DISK...")
            try:
                # Use the MCP tool if available
                if self.mcp_call:
                    result = self.mcp_call("mcp__apple2-mcp__save_basic_to_disk", {
                        "disk_filename": "disks/agent_contiguous.dsk",
                        "program_name": filename,
                        "source": source
                    })
                    return f"Saved BASIC program '{filename}' to disk. User can BRUN {filename} or - {filename}"
                else:
                    return "ERROR: Disk operations not available (no MCP connection)"
            except Exception as e:
                return f"Disk save error: {str(e)}"

        elif tool_name == "disk_save_binary":
            filename = tool_input.get("filename", "PROGRAM").upper()[:15]
            hex_data = tool_input.get("hex_data", "")
            load_addr = tool_input.get("load_address", 0x6000)
            self.send_status(f"SAVING {filename} TO DISK...")
            try:
                if self.mcp_call:
                    # First write hex to temp file, then add to disk
                    import tempfile
                    hex_clean = hex_data.replace(" ", "").replace("\n", "")
                    binary = bytes.fromhex(hex_clean)
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f:
                        f.write(binary)
                        temp_path = f.name
                    result = self.mcp_call("mcp__apple2-mcp__prodos_add", {
                        "disk": "disks/agent_contiguous.dsk",
                        "file": temp_path,
                        "name": filename,
                        "type": "BIN",
                        "addr": f"{load_addr:04X}"
                    })
                    import os
                    os.unlink(temp_path)
                    return f"Saved binary '{filename}' to disk at ${load_addr:04X}. User can BRUN {filename}"
                else:
                    return "ERROR: Disk operations not available (no MCP connection)"
            except Exception as e:
                return f"Disk save error: {str(e)}"

        elif tool_name == "disk_save_text":
            filename = tool_input.get("filename", "FILE").upper()[:15]
            content = tool_input.get("content", "")
            self.send_status(f"SAVING {filename} TO DISK...")
            try:
                if self.mcp_call:
                    import tempfile
                    # Convert to Apple II text (CR line endings, high bit set)
                    apple_text = content.replace("\n", "\r").upper()
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w') as f:
                        f.write(apple_text)
                        temp_path = f.name
                    result = self.mcp_call("mcp__apple2-mcp__prodos_add", {
                        "disk": "disks/agent_contiguous.dsk",
                        "file": temp_path,
                        "name": filename,
                        "type": "TXT"
                    })
                    import os
                    os.unlink(temp_path)
                    return f"Saved text file '{filename}' to disk."
                else:
                    return "ERROR: Disk operations not available (no MCP connection)"
            except Exception as e:
                return f"Disk save error: {str(e)}"

        elif tool_name == "disk_list":
            try:
                if self.mcp_call:
                    result = self.mcp_call("mcp__apple2-mcp__prodos_list", {
                        "disk": "disks/agent_contiguous.dsk"
                    })
                    return str(result)
                else:
                    return "ERROR: Disk operations not available (no MCP connection)"
            except Exception as e:
                return f"Disk list error: {str(e)}"

        elif tool_name == "emulator_read_basic_program":
            if not self.mcp_call:
                return "ERROR: Emulator not available (no MCP connection)"
            try:
                self.send_status("READING PROGRAM...")
                # Read VARTAB pointer ($69-$6A) to find end of program
                vartab_result = self.mcp_call("mcp__apple2-mcp__peek", {
                    "address": 0x69,
                    "count": 2,
                    "format": "decimal"
                })
                # Parse the result to get the address
                if isinstance(vartab_result, dict) and "bytes" in vartab_result:
                    vartab_bytes = vartab_result["bytes"]
                    vartab = vartab_bytes[0] + (vartab_bytes[1] << 8)
                elif isinstance(vartab_result, str):
                    # Try to parse from string
                    import re
                    nums = re.findall(r'\d+', vartab_result)
                    if len(nums) >= 2:
                        vartab = int(nums[0]) + (int(nums[1]) << 8)
                    else:
                        return f"ERROR: Could not parse VARTAB: {vartab_result}"
                else:
                    return f"ERROR: Unexpected VARTAB format: {vartab_result}"

                # Calculate program size
                prog_start = 0x0801
                prog_size = vartab - prog_start
                if prog_size <= 0 or prog_size > 48000:
                    return f"No program in memory (VARTAB=${vartab:04X})"

                # Read program bytes in chunks
                self.send_status(f"READING {prog_size} BYTES...")
                all_bytes = []
                offset = 0
                while offset < prog_size:
                    chunk_size = min(256, prog_size - offset)
                    result = self.mcp_call("mcp__apple2-mcp__peek", {
                        "address": prog_start + offset,
                        "count": chunk_size,
                        "format": "decimal"
                    })
                    if isinstance(result, dict) and "bytes" in result:
                        all_bytes.extend(result["bytes"])
                    offset += chunk_size

                # Detokenize the program
                self.send_status("DETOKENIZING...")
                from basic_tokenizer_streaming import detokenize_program
                try:
                    source = detokenize_program(bytes(all_bytes))
                    return f"Current BASIC program ({prog_size} bytes):\n\n{source}"
                except Exception as e:
                    return f"Detokenize error: {str(e)}\nRaw bytes: {all_bytes[:50]}..."

            except Exception as e:
                self.send_status("READ FAILED")
                return f"ERROR reading program: {str(e)}"

        else:
            return f"ERROR: Unknown tool: {tool_name}"

    def _estimate_tokens(self, messages: List[Dict]) -> int:
        """Estimate token count for messages (rough: ~4 chars per token)."""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if "text" in block:
                            total_chars += len(block["text"])
                        elif "content" in block:
                            total_chars += len(str(block["content"]))
                        elif "input" in block:
                            total_chars += len(json.dumps(block["input"]))
        return total_chars // 4

    def _compact_conversation(self, model: str) -> bool:
        """
        Compact conversation by summarizing older messages.
        Returns True if compaction was performed.
        """
        if not self.client:
            return False

        estimated = self._estimate_tokens(self.conversation)
        if estimated < self.compact_threshold:
            return False

        self.send_status("COMPACTING MEMORY...")
        print(f"[Agent] Compacting conversation: ~{estimated} tokens")

        # Keep the most recent messages (last 10 or so)
        keep_recent = 10
        if len(self.conversation) <= keep_recent:
            return False

        old_messages = self.conversation[:-keep_recent]
        recent_messages = self.conversation[-keep_recent:]

        # Summarize the old messages
        summary_prompt = """Summarize this conversation history concisely.
Focus on:
- What the user originally requested
- Key decisions made
- Code that was written/tested
- Current state of the Apple II and emulator
- Any errors encountered and how they were resolved

Be concise but preserve important technical details."""

        try:
            # Format old messages for summarization
            old_text = ""
            for msg in old_messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if isinstance(content, str):
                    old_text += f"{role.upper()}: {content}\n\n"
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            if "text" in block:
                                old_text += f"{role.upper()}: {block['text']}\n\n"
                            elif block.get("type") == "tool_use":
                                old_text += f"{role.upper()}: [Used tool: {block.get('name')}]\n\n"
                            elif block.get("type") == "tool_result":
                                result = block.get("content", "")[:500]
                                old_text += f"TOOL RESULT: {result}...\n\n"

            response = self.client.messages.create(
                model=model,
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": f"{summary_prompt}\n\n---\n\n{old_text}"
                }]
            )

            summary = response.content[0].text

            # Replace conversation with summary + recent messages
            self.conversation = [
                {
                    "role": "user",
                    "content": f"[CONVERSATION SUMMARY]\n{summary}\n[END SUMMARY - Recent messages follow]"
                },
                {
                    "role": "assistant",
                    "content": "I understand the context from our previous conversation. Let me continue from where we left off."
                }
            ] + recent_messages

            new_estimate = self._estimate_tokens(self.conversation)
            print(f"[Agent] Compacted: ~{estimated} -> ~{new_estimate} tokens")
            self.send_status("MEMORY COMPACTED")
            return True

        except Exception as e:
            print(f"[Agent] Compaction failed: {e}")
            return False

    def run_agentic(self, user_message: str, model: str = "claude-sonnet-4-20250514",
                    max_turns: int = 20) -> str:
        """
        Run the agentic loop.

        Args:
            user_message: The user's request
            model: Model to use
            max_turns: Maximum number of agentic turns

        Returns:
            Final response text
        """
        if not self.client:
            return "ERROR: No API key. Export ANTHROPIC_API_KEY."

        # Add user message to conversation
        self.conversation.append({
            "role": "user",
            "content": user_message
        })

        system_prompt = """You are Apple II Agent - an expert AI programmer that creates code for Apple II.

SESSION PERSISTENCE:
- You have MEMORY! Conversation history is preserved across reconnects.
- When user says "& to return" and comes back, you remember what you discussed.
- If user reports an error, you remember what code you wrote!
- Use emulator_read_basic_program to see EXACTLY what's in memory if needed.
- /RESET command clears your memory and starts fresh.

CHOOSING LANGUAGE:
- If user says "BASIC" or doesn't specify: use Applesoft BASIC
- If user says "assembly", "machine language", "ML", "6502", "fast": use 6502 assembly
- For games that need speed (shooters, action): suggest assembly
- For utilities, demos, simple programs: BASIC is fine

ERROR HANDLING:
- If user reports "SYNTAX ERROR IN LINE XX", you remember the code you wrote!
- First try to fix from memory. If unclear, use emulator_read_basic_program.
- Common errors: missing quotes, wrong keyword, NEXT without FOR, etc.

WORKFLOW - SIMPLE vs COMPLEX programs:

FOR SIMPLE PROGRAMS (counting, hello world, basic math, simple loops, INPUT/PRINT):
1. Write the code
2. Deploy directly with apple2_send_code - NO EMULATOR NEEDED!
3. Tell user: "TYPE /EXIT THEN RUN"
Simple programs don't need testing - just send them!

FOR COMPLEX PROGRAMS (graphics, games, multi-screen, tricky logic, assembly):
1. Use emulator_load_env (instant!) - NOT emulator_boot (slow!)
2. Inject and test the code
3. Read screen to verify output - USER SEES THIS OUTPUT!
4. Fix bugs if needed
5. Deploy to Apple II
6. Tell user it's ready

STATUS UPDATES - User sees these in real-time:
- "WRITING: COUNTING LOOP"
- "DEPLOYING TO APPLE II..."
- "READY! TYPE /EXIT THEN RUN"
For complex programs:
- "LOADING EMULATOR..."
- "TESTING..."
- "--- EMULATOR OUTPUT ---" (show what you see!)
- "TEST PASSED!"

BASIC TOOLS:
- apple2_send_code: Deploy BASIC to Apple II (USE THIS FOR SIMPLE PROGRAMS!)
- emulator_inject_basic: Load BASIC into emulator (for testing)
- emulator_run_basic: Run BASIC commands in emulator

ASSEMBLY/MACHINE LANGUAGE TOOLS:
- emulator_assemble: Assemble 6502 code, load into emulator
- emulator_call: Execute machine code routine
- apple2_send_binary: Deploy binary to Apple II

EMULATOR TOOLS (only for complex programs!):
- emulator_load_env: INSTANT emulator ready (use this, not boot!)
- emulator_boot: SLOW cold boot (avoid unless needed)
- emulator_read_screen: Check text output - SHOWS OUTPUT TO USER!
- emulator_capture_graphics: See graphics (gr/hgr)

OTHER TOOLS:
- apple2_send_status: Update status line
- disk_save_basic: Save program to disk
- disk_list: List files on disk

6502 ASSEMBLY TIPS (ca65 format):
- Use .org $6000 for load address
- End with RTS to return cleanly
- Key addresses: $400=text screen, $2000=HGR page 1
- COUT=$FDED, HOME=$FC58, GR=$FB40, HGR=$F3E2

SYSTEM ARTIFACTS vs USER REQUESTS:
- You are connected to a real Apple II via Ethernet. Messages come from whatever the user types.
- Sometimes you'll receive system artifacts that are NOT user requests. Examples:
  - "RUN AGENT.BIN", "BRUN AGENT.BIN", "CALL 24576" - these are boot artifacts
  - "BLOAD ...", "CATALOG", "PREFIX" - ProDOS commands, not requests for you
  - Any message that looks like a DOS/ProDOS command rather than natural language
- For these, respond briefly: "READY! WHAT WOULD YOU LIKE TO BUILD?" - do NOT try to execute them!
- NEVER generate code that runs AGENT.BIN, CALL 24576, or BLOAD AGENT - this re-enters the agent recursively!
- Real user requests are natural language: "make a game", "draw a circle", "fix this error"

CRITICAL RULES:
1. SIMPLE PROGRAMS: Skip emulator! Just deploy with apple2_send_code
2. COMPLEX PROGRAMS: Use emulator_load_env (instant), not emulator_boot (slow)
3. When you read emulator screen, the user sees it too!
4. After deploy: "TYPE /EXIT THEN RUN" (BASIC) or "TYPE /EXIT THEN CALL 24576" (ML)
5. Keep messages UPPERCASE
6. NEVER re-launch AGENT.BIN - you ARE the agent!

You are the user's AI programming partner. Be FAST for simple stuff!"""

        # Append custom prompt if set
        if self.custom_prompt:
            system_prompt += f"\n\nUSER CONTEXT/INSTRUCTIONS:\n{self.custom_prompt}"

        self.send_status("THINKING...")

        for turn in range(max_turns):
            # Show turn progress
            if turn > 0:
                self.send_status(f"TURN {turn+1}/{max_turns}...")

            # Check if we need to compact the conversation
            self._compact_conversation(model)

            try:
                # Include Anthropic's native web search tool
                all_tools = APPLE2_TOOLS + [
                    {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
                ]
                response = self.client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system_prompt,
                    tools=all_tools,
                    messages=self.conversation,
                    extra_headers={"anthropic-beta": "web-search-2025-03-05"}
                )

                # Process response
                assistant_content = []
                final_text = ""

                for block in response.content:
                    if block.type == "text":
                        final_text += block.text
                        assistant_content.append({
                            "type": "text",
                            "text": block.text
                        })

                    elif block.type == "server_tool_use":
                        # Server-side web search - handled automatically by API
                        self.send_status("SEARCHING WEB...")
                        assistant_content.append(block)

                    elif block.type == "web_search_tool_result":
                        # Web search results - handled automatically by API
                        self.send_status("GOT SEARCH RESULTS")
                        assistant_content.append(block)

                    elif block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_id = block.id

                        # Update status with friendly name
                        # Skip showing status for apple2_send_status since it sends its own
                        if tool_name != "apple2_send_status":
                            friendly_names = {
                                "emulator_boot": "BOOTING (SLOW)",
                                "emulator_load_env": "LOADING EMULATOR",
                                "emulator_type": "TYPING",
                                "emulator_read_screen": "READING SCREEN",
                                "emulator_run_basic": "RUNNING BASIC",
                                "emulator_inject_basic": "LOADING PROGRAM",
                                "emulator_capture_graphics": "CAPTURING GRAPHICS",
                                "emulator_peek": "READING MEMORY",
                                "emulator_poke": "WRITING MEMORY",
                                "emulator_assemble": "ASSEMBLING",
                                "emulator_call": "EXECUTING CODE",
                                "apple2_send_code": "DEPLOYING CODE",
                                "apple2_send_binary": "DEPLOYING BINARY",
                                "apple2_send_message": "SENDING MESSAGE",
                                "disk_save_basic": "SAVING TO DISK",
                                "disk_save_binary": "SAVING BINARY",
                                "disk_list": "LISTING DISK",
                            }
                            friendly = friendly_names.get(tool_name, tool_name.upper())
                            self.send_status(f"{friendly}...")

                        assistant_content.append({
                            "type": "tool_use",
                            "id": tool_id,
                            "name": tool_name,
                            "input": tool_input
                        })

                        # Execute tool
                        result = self._execute_tool(tool_name, tool_input)

                        # Add assistant message and tool result
                        self.conversation.append({
                            "role": "assistant",
                            "content": assistant_content
                        })
                        self.conversation.append({
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": result
                            }]
                        })

                        # Continue the loop
                        assistant_content = []
                        break

                # If no tool use, we're done
                if response.stop_reason == "end_turn":
                    self.conversation.append({
                        "role": "assistant",
                        "content": assistant_content
                    })
                    self.send_status("DONE")
                    return final_text.upper()

                # If stop reason is tool_use, continue loop
                if response.stop_reason != "tool_use":
                    break

            except Exception as e:
                error_msg = str(e)
                # Provide clean error messages for common API errors
                if "credit" in error_msg.lower() or "balance" in error_msg.lower():
                    self.send_status("NO API CREDITS")
                    return "ERROR: API CREDITS DEPLETED. ADD CREDITS TO YOUR ANTHROPIC ACCOUNT."
                elif "rate" in error_msg.lower() and "limit" in error_msg.lower():
                    self.send_status("RATE LIMITED")
                    return "ERROR: API RATE LIMIT. PLEASE WAIT A MOMENT."
                elif "authentication" in error_msg.lower() or "api_key" in error_msg.lower():
                    self.send_status("BAD API KEY")
                    return "ERROR: INVALID API KEY. CHECK ANTHROPIC_API_KEY."
                else:
                    self.send_status(f"ERROR: {error_msg[:20]}")
                    return f"ERROR: {error_msg[:100]}"

        return "MAX TURNS REACHED"

    def clear_conversation(self):
        """Clear conversation history."""
        self.conversation = []


# Singleton for use in unified_proxy
_agentic_instance: Optional[AgenticClaude] = None

def get_agentic_claude(send_to_apple2, send_status, send_code, mcp_call=None) -> AgenticClaude:
    """Get or create the agentic Claude instance."""
    global _agentic_instance
    if _agentic_instance is None:
        _agentic_instance = AgenticClaude(send_to_apple2, send_status, send_code, mcp_call)
    return _agentic_instance
