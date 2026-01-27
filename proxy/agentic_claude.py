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
        "description": "Start the Bobbin Apple II emulator. Use this before any emulator operations.",
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
                 mcp_call: Optional[Callable[[str, dict], Any]] = None):
        """
        Args:
            send_to_apple2: Function to send response text to real Apple II
            send_status: Function to send status updates to real Apple II
            send_code: Function to send BASIC code to real Apple II
            mcp_call: Function to call MCP tools (for emulator)
        """
        self.send_to_apple2 = send_to_apple2
        self.send_status = send_status
        self.send_code = send_code
        self.mcp_call = mcp_call

        self.client = None
        if HAS_ANTHROPIC:
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)

        self.conversation: List[Dict] = []
        self.emulator_running = False

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool and return the result."""

        # Emulator tools (via MCP if available)
        if tool_name.startswith("emulator_"):
            if not self.mcp_call:
                return "ERROR: Emulator not available (no MCP connection)"

            # Map tool names to MCP tool names
            mcp_map = {
                "emulator_boot": "mcp__apple2-mcp__boot",
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
                # Special handling for some tools
                if tool_name == "emulator_inject_basic":
                    # Need to tokenize first
                    source = tool_input.get("source", "")
                    result = self.mcp_call("mcp__apple2-mcp__tokenize", {"source": source})
                    if "error" in str(result).lower():
                        return f"Tokenization error: {result}"
                    # Then inject
                    hex_data = result.get("hex", "") if isinstance(result, dict) else str(result)
                    inject_input = {
                        "hex_data": hex_data,
                        "auto_run": tool_input.get("auto_run", False)
                    }
                    result = self.mcp_call("mcp__apple2-mcp__inject_tokenized_basic", inject_input)
                    return str(result)

                elif tool_name == "emulator_capture_graphics":
                    mode = tool_input.get("mode", "gr")
                    if mode == "hgr":
                        result = self.mcp_call("mcp__apple2-mcp__read_hgr_ascii", {})
                    else:
                        result = self.mcp_call("mcp__apple2-mcp__read_gr_ascii", {})
                    return str(result)

                elif tool_name == "emulator_boot":
                    self.emulator_running = True
                    boot_input = {"machine": "enhanced", "uthernet2": True}
                    if "disk" in tool_input:
                        boot_input["disk"] = tool_input["disk"]
                    result = self.mcp_call(mcp_name, boot_input)
                    return str(result)

                else:
                    result = self.mcp_call(mcp_name, tool_input)
                    return str(result)

            except Exception as e:
                return f"ERROR: {str(e)}"

        # Real Apple II tools (via A2P protocol)
        elif tool_name == "apple2_send_code":
            source = tool_input.get("source", "")
            self.send_code(source)
            return "Code sent to Apple II"

        elif tool_name == "apple2_send_message":
            message = tool_input.get("message", "")
            self.send_to_apple2(message)
            return "Message sent to Apple II"

        elif tool_name == "apple2_send_status":
            status = tool_input.get("status", "")
            self.send_status(status)
            return "Status sent to Apple II"

        else:
            return f"ERROR: Unknown tool: {tool_name}"

    def run_agentic(self, user_message: str, model: str = "claude-sonnet-4-latest",
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

        system_prompt = """You are an expert Apple II programmer with access to both a Bobbin emulator and a real Apple II.

WORKFLOW:
1. Use the EMULATOR tools to develop and test code quickly
2. Once code works in the emulator, use apple2_send_code to deploy to the real Apple II
3. Send status updates to keep the user informed

EMULATOR TOOLS (fast, use for development):
- emulator_boot: Start the emulator
- emulator_type: Type commands
- emulator_read_screen: See what's on screen
- emulator_run_basic: Run BASIC commands
- emulator_inject_basic: Load a BASIC program
- emulator_capture_graphics: See graphics output
- emulator_peek/poke: Read/write memory

REAL APPLE II TOOLS (for deployment):
- apple2_send_code: Deploy tested BASIC code
- apple2_send_message: Show text to user
- apple2_send_status: Update status line

Always test in the emulator first, then deploy to real hardware.
Keep responses UPPERCASE for Apple II display compatibility.
Be concise - the Apple II has limited screen space."""

        self.send_status("THINKING...")

        for turn in range(max_turns):
            try:
                response = self.client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system_prompt,
                    tools=APPLE2_TOOLS,
                    messages=self.conversation
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

                    elif block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_id = block.id

                        # Update status
                        self.send_status(f"USING: {tool_name.upper()}")

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
                self.send_status(f"ERROR: {str(e)[:20]}")
                return f"ERROR: {str(e)}"

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
