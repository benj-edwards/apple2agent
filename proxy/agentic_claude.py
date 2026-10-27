#!/usr/bin/env python3
"""
Agentic Claude for Apple II

The loop behind the AGENT> prompt. Claude writes a program, tests it in a
Bobbin emulator launched exactly the way the user's Apple II will run it,
looks at the real screen (text, or color HGR/GR screenshots), fixes what's
wrong, and deploys it to the Apple II ready to run.

Everything streams to the Apple II while it happens: Claude's progress
notes, each tool step, the code scrolling by as it's written, emulator
output, and live HGR previews of what the game looks like.

The proxy session (unified_proxy.AppleIISession) supplies the Apple II side:
    send_status(msg)        status line (row 22)
    send_stream_line(text)  scrolling output area
    deploy_program(prog)    DEPLOY/LOAD/RUN packets -> READY on the Apple II
    send_preview(hgr8k)     show an HGR screenshot on the Apple II
    has_aux, can_deploy     client capabilities
"""

import base64
import json
import os
import re
import shutil
import socket
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import anthropic
    from jiter import from_json     # the SDK's own partial-JSON parser
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

import deploy
from deploy import BuildError

# Model selection byte from the Apple II (CONFIG_MODEL) -> model ID
MODEL_SONNET = 0
MODEL_OPUS = 1
MODEL_HAIKU = 2
MODEL_IDS = {
    MODEL_SONNET: "claude-sonnet-5-5",
    MODEL_OPUS: "claude-opus-5-5",
    MODEL_HAIKU: "claude-haiku-5-5",
}
MODEL_NAMES = {MODEL_SONNET: "SONNET", MODEL_OPUS: "OPUS", MODEL_HAIKU: "HAIKU"}

EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_EFFORT = "medium"
MAX_TOKENS = 128000            # Opus 5.5's cap (streaming); a big game's first plan used all of 64K
MAX_TOKEN_RETRIES = 2

WORKSPACE = Path(__file__).resolve().parent.parent / "programs"
BUILD_DIR = WORKSPACE / "build"
HISTORY_DIR = WORKSPACE / "history"

MAX_IMAGES_PER_RESULT = 3
THINK_MAX_LINES = 3             # screen lines per paragraph of the thinking summary
CARD_MAX_ROWS = 15              # closing card: leaves room for the READY banner below
MAX_WAIT_PER_CALL = 30.0
NAME_RE = re.compile(r'^[A-Z0-9][A-Z0-9._-]{0,29}$')
SOURCE_EXTS = (".BAS", ".S", ".ASM")

# Optional API features, dropped one by one if the API rejects them
BETA_FALLBACK = "server-side-fallback-2026-07-01"
BETA_COMPACT = "compact-2026-01-12"


SYSTEM_PROMPT = """You are the Apple II Agent. You run inside a small proxy connected over Ethernet to a real Apple IIe. The person you're talking to is sitting at that Apple II, typing on its keyboard and reading its text screen. They ask for programs in plain English; you build them, test them in an emulator, and deliver them to their Apple II ready to run. Make it feel like magic: they type a wish, watch you work, and a minute later press RETURN and play.

HOW YOU WORK
1. Decide BASIC or machine code. Applesoft BASIC is great for text programs, utilities, simple graphics and turn-based games. For anything fast or animated (action games, smooth hi-res animation) write 6502 assembly.
2. Write the program with write_file: NAME.BAS for Applesoft (numbered lines) or NAME.S for ca65 assembly.
3. Test it with run_in_emulator. That boots an Apple IIe emulator at real 1 MHz speed, launches your program exactly the way the user's Apple II will, types the keys you give it, and shows you the screen. Graphics come back as images: look at them like a player would. Is it drawn where you expect? Colors right? Does it look good?
4. Fix what's wrong (edit_file for small changes) and test again until it works. For games, play a little: press the controls, check that things move, collisions and scoring work, and that ESC quits.
5. Call deploy_to_apple. Their Apple II loads it and shows a READY screen; they press RETURN to run it.
6. End with a short message for their screen: what you made and how to use it (the controls), and that ESC brings them back here.

Big programs (a deluxe game, thousands of lines): don't design the whole thing in your head first - one response holds only so much, and planning everything up front can use it all up before a line is written. Sketch the plan briefly, write a first playable version (the main loop, drawing, controls), test it, then add the rest in pieces with edit_file, testing as you go. Write a long file in parts: write_file the first part, then edit_file to append the rest.

Even small programs get one quick emulator run before deploying - a typo should never reach the user. If the user just asks a question or chats, answer briefly without building anything. If they report a problem ("FIX: ..."), it came from their real Apple II: read the file, fix it, test, redeploy.

WHAT THE USER SEES WHILE YOU WORK
They watch a live log on their Apple II: your short notes between steps, each tool step, your code scrolling by as you write it, emulator output, and your hi-res test screenshots as previews. Before each major step write one short plain sentence about what you're doing ("Drawing the city skyline next."). Keep notes friendly and brief.

YOUR FINAL MESSAGE
It appears on a {cols}-column screen. Keep it under 10 short lines. Plain text only: no markdown, no asterisks, no backticks, no headings, no emoji; use "-" for lists. {case_rule}

THE MACHINE YOUR PROGRAM RUNS ON
- {machine}
- Text screen 40x24 at $0400. Lo-res GR uses $0400-$07FF. Hi-res HGR page 1 is $2000-$3FFF, page 2 is $4000-$5FFF.
- Your program owns {memory}. Page 3 from $0300 to $03C6 is also free.
- Never touch $03C7-$03FF (the hooks and vectors that bring the user back to you), $BF00-$BFFF (ProDOS), language card RAM ($D000-$FFFF), or aux memory $6000-$BEFF. Don't change the reset or BRK vectors.
- No disk access: BASIC.SYSTEM commands (PRINT CHR$(4)...) are not available.
- Memory is NOT cleared before your program starts - it holds leftovers, on the real machine and in the emulator alike. Initialize every variable and table you use, and clear any screen you draw on (HGR clears page 1, HGR2 page 2; in machine code clear the hi-res page yourself).
- Keyboard: $C000 (bit 7 set = key waiting), clear it by touching $C010. Open/Closed Apple keys: $C061/$C062 (bit 7). Speaker: each access to $C030 clicks it. Vertical blank: $C019 bit 7 is 0 during VBL, 60 times a second - wait for it to pace a game at a steady speed.

GETTING BACK HERE (every program must do this)
- ESC quits back to the agent.
- Applesoft: on ESC do TEXT : HOME : & (the & statement returns to the agent). ESC typed at an INPUT prompt (or at ]) comes back to the agent by itself, so INPUT is fine for typed commands.
- For typed input don't clear the keyboard first: POKE -16368,0 before reading a line throws away a key the user already pressed. Clear it only where stale keys matter (the start of an action game).
- Machine code: on ESC switch to text (STA $C051, STA $C054) and RTS with the stack balanced, or JMP $03D0.
- Ctrl-Reset also comes back here, and a crash into BRK comes back with the crash address.

APPLESOFT NOTES
- The deployer places your program for you: with HGR it keeps the hi-res page(s) clear and puts variables above them. Don't use HIMEM:, LOMEM:, or POKE 103, 104, 115 or 116.
- Only the first two letters of a variable name count (SCORE and SC are the same variable). Never use names that contain a keyword (TO, OR, AND, AT, FN, ON, IF, GR...): use SC not SCORE, LV not LEVEL.
- Applesoft is slow (roughly 1000 simple statements a second). For anything real-time keep the loop tiny, avoid redrawing everything, read keys with K = PEEK(-16384): IF K > 127 THEN POKE -16368,0 (GET waits for a key).
- Small machine-code helpers (sound, fast fills) can be POKEd into $0300-$03C6 from DATA statements and CALLed.

6502 ASSEMBLY NOTES (ca65 syntax)
- Begin with .org $0800 (any address from $0800 up works). Execution starts at the label start if you define one, otherwise at the first byte.
- Code and data must stay out of the hi-res pages you draw on: from $0800 a program reaches $2000 after 6K. Big hi-res programs: .org $6000 (room up to $BEFF), or $0800-$1FFF plus $4000 up when you only use page 1.
- One file, no .include. Labels end with a colon; .byte, .word, .res, .proc, .macro and @local labels all work.
- Prefer plain 6502 instructions; the 65C02 extras (BRA, PHX, STZ...) do work on this enhanced //e.
- ROM: COUT $FDED (character in A with bit 7 set), HOME $FC58, WAIT $FCA8 (delay ~ A*A*2.5 cycles), RDKEY $FD0C.
- Display switches: $C050 graphics, $C051 text, $C052 full screen, $C053 mixed, $C054 page 1, $C055 page 2, $C056 lo-res, $C057 hi-res.
- HGR row Y starts at $2000 + (Y AND 7)*$400 + ((Y/8) AND 7)*$80 + (Y/64)*$28; 7 pixels per byte, low bit = leftmost, bit 7 picks the color group (violet/green or blue/orange). Use a precomputed row table. Double-buffer by drawing on the hidden page and flipping $C054/$C055.

TESTING
- run_in_emulator(file, wait, steps): steps type keys - plain characters plus {LEFT} {RIGHT} {UP} {DOWN} {SPACE} {RETURN} {ESC} {CTRL-C} - then wait some seconds and optionally look. Keys arrive with the real //e codes (LEFT 8, RIGHT 21, UP 11, DOWN 10, RETURN 13, ESC 27; bit 7 set at $C000) at a quick typist's pace, about 12 a second. Waits are real seconds; keep a call under about 15 seconds.
- emulator_input keeps playing the program that is already running; emulator_memory dumps memory and registers for debugging.
- If a result reports that the program wrote into agent memory or the hooks, fix that before deploying: it would crash their real Apple II."""


def apple_text(text: str, uppercase: bool) -> str:
    """Make text safe and readable on an Apple II screen."""
    replacements = {
        "‘": "'", "’": "'", "“": '"', "”": '"',
        "–": "-", " — ": " - ", "—": " - ", "…": "...", "•": "-",
        "×": "x", "→": "->", "←": "<-", "↑": "^",
        "↓": "v", " ": " ",
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r'^\s*#+\s*', '', text, flags=re.MULTILINE)
    text = text.encode("ascii", errors="replace").decode("ascii")
    return text.upper() if uppercase else text


def word_wrap(text: str, width: int) -> List[str]:
    """Wrap one line of text to the screen width (indent preserved)."""
    indent = len(text) - len(text.lstrip(" "))
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = " " * indent + words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = " " * indent + word
    lines.append(current)
    return [l[:width] for l in lines]


TOOLS = [
    {
        "name": "write_file",
        "description": "Create or replace a source file in the workspace. NAME.BAS = Applesoft BASIC "
                       "(numbered lines), NAME.S = ca65 6502 assembly. Name: letters, digits, '.', '-', "
                       "up to 30 characters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "File name, e.g. INVADERS.S"},
                "content": {"type": "string", "description": "The complete file contents"},
            },
            "required": ["name", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace one exact snippet of a workspace file. old_text must appear exactly "
                       "once (include a few surrounding characters to make it unique). Use for "
                       "small fixes instead of rewriting the whole file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["name", "old_text", "new_text"],
        },
    },
    {
        "name": "read_file",
        "description": "Show a workspace file with line numbers. With no name, list the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        },
    },
    {
        "name": "run_in_emulator",
        "description": "Build a workspace file and run it in a fresh Apple //e emulator, launched "
                       "exactly as the user's Apple II will launch it (same memory layout, same ESC "
                       "and return hooks), at real 1 MHz speed. Lets it run `wait` seconds, looks, "
                       "then performs `steps`. Reports build info, what the program is doing "
                       "(running, ended, error, crashed, or exited to the agent), the text screen, "
                       "and screenshots when it's in a graphics mode. Your hi-res screenshots also "
                       "show up on the user's Apple II as live previews.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Workspace file to build and run"},
                "wait": {"type": "number", "description": "Seconds to run before the first look (default 2)"},
                "steps": {
                    "type": "array",
                    "description": "Interaction after the first look. The final state is always captured.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "keys": {"type": "string", "description": "Keys to type: characters plus "
                                     "{LEFT} {RIGHT} {UP} {DOWN} {SPACE} {RETURN} {ESC} {CTRL-X}"},
                            "wait": {"type": "number", "description": "Seconds to wait after typing (default 0.5)"},
                            "look": {"type": "boolean", "description": "Capture the screen after this step"},
                        },
                    },
                },
            },
            "required": ["file"],
        },
    },
    {
        "name": "emulator_input",
        "description": "Keep interacting with the program already running in the emulator (started by "
                       "run_in_emulator). Same steps format; the final state is always captured.",
        "input_schema": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "keys": {"type": "string"},
                            "wait": {"type": "number"},
                            "look": {"type": "boolean"},
                        },
                    },
                },
            },
            "required": ["steps"],
        },
    },
    {
        "name": "emulator_memory",
        "description": "Debugging: hex dump of emulator main memory plus the CPU registers and the "
                       "labels from the last assembly.",
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "integer", "description": "Start address (0-65535)"},
                "count": {"type": "integer", "description": "Bytes to dump (1-512, default 64)"},
            },
            "required": ["address"],
        },
    },
    {
        "name": "deploy_to_apple",
        "description": "Send a tested program to the user's real Apple II. It loads into memory and "
                       "the Apple II shows a READY screen with the title; the user presses RETURN to "
                       "run it. Call this when the program works.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "title": {"type": "string", "description": "Short name for the READY screen, e.g. SPACE RESCUE"},
            },
            "required": ["file", "title"],
        },
    },
]

TOOL_LABELS = {
    "write_file": "WRITING",
    "edit_file": "EDITING",
    "read_file": "READING",
    "run_in_emulator": "TESTING",
    "emulator_input": "PLAYING",
    "emulator_memory": "DEBUGGING",
    "deploy_to_apple": "SENDING TO YOUR APPLE II",
}


class StopRequested(Exception):
    """The user pressed ESC on the Apple II while waiting."""


def _shut_down_stream_socket(stream) -> bool:
    """Wake a thread blocked reading this API stream.

    stream.close() from another thread can block on the connection the
    reader holds; shutting the socket down takes no locks and makes the
    blocked read fail at once (the reader then closes the stream itself).
    """
    try:
        network_stream = stream.response.extensions.get("network_stream")
        sock = network_stream.get_extra_info("socket") if network_stream else None
        if sock is None:
            return False
        sock.shutdown(socket.SHUT_RDWR)
        return True
    except Exception as e:
        print(f"[Agent] couldn't interrupt the stream: {e!r}")
        return False


class AgenticClaude:
    """Conversation + tools for one Apple II. Survives reconnects."""

    def __init__(self, session=None, mcp_call=None, **_legacy):
        self.session = session
        self.client = None
        if HAS_ANTHROPIC and os.environ.get('ANTHROPIC_API_KEY'):
            self.client = anthropic.Anthropic(max_retries=4)

        self.conversation: List[Dict[str, Any]] = []
        self.custom_prompt: Optional[str] = None
        self.effort = DEFAULT_EFFORT
        self.display_width = 39
        self.display_uppercase = True
        self.deploy_history: List[deploy.Program] = []
        self._disabled = set()          # optional API features the API refused
        self._machine_note_sent = None
        self._labels: Dict[str, int] = {}
        self._emulator_ready = False

        # Live status
        self._phase = "THINKING"
        self._turn = 0
        self._session_start = 0.0
        self._last_status = 0.0
        self._heartbeat_running = False
        self._heartbeat_thread = None

        # Streaming display state
        self._text_buf = ""
        self._think_buf = ""
        self._think_shown = False
        self._tool_streaming = ""
        self._tool_json = ""
        self._code_lines_shown = 0
        self._code_last_show = 0.0
        self._writing_name = ""

        # Previews run in the background; deploys wait for them
        self._preview_thread: Optional[threading.Thread] = None
        self._previews_allowed = True

        # ESC on the Apple II while it waits -> /STOP -> request_stop()
        self._stop_requested = False
        self._active_stream = None
        self.busy = False               # a request is running (set by the proxy)

        WORKSPACE.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Apple II output helpers
    # ------------------------------------------------------------------

    def _status(self, msg: str):
        if self.session:
            try:
                self.session.send_status(apple_text(msg, True)[:self.display_width])
            except Exception:
                pass
        self._last_status = time.time()

    def _line(self, text: str):
        """Send text to the scrolling output area, word-wrapped."""
        if not self.session:
            print(f"[A2] {text}")
            return
        width = self.display_width
        for raw in apple_text(text, self.display_uppercase).split("\n"):
            for line in word_wrap(raw, width):
                try:
                    self.session.send_stream_line(line)
                except Exception:
                    return
        self._last_status = time.time()

    def _closing_card(self, text: str):
        """The final message again on a fresh page, so what the program is and
        its controls sit right above the READY banner (streamed, its start may
        have scrolled off with the last page of the log)."""
        page_break = getattr(self.session, "send_page_break", None)
        if not page_break:
            return
        rows = []
        for raw in apple_text(text.strip(), self.display_uppercase).split("\n"):
            rows += word_wrap(raw, self.display_width) if raw.strip() else [""]
        try:
            page_break()
            for row in rows[:CARD_MAX_ROWS]:
                self.session.send_stream_line(row)
        except Exception:
            pass

    def _set_phase(self, phase: str):
        if getattr(self, "_stop_requested", False):
            phase = "STOPPING"      # what the user asked for, until it's done
        self._phase = phase
        self._status(f"{phase} {self._elapsed()}")

    def _elapsed(self) -> str:
        total = int(time.time() - self._session_start) if self._session_start else 0
        return f"{total // 60}M{total % 60:02d}S" if total >= 60 else f"{total}S"

    def _start_heartbeat(self):
        self._heartbeat_running = True
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat(self):
        self._heartbeat_running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
            self._heartbeat_thread = None

    def _heartbeat_loop(self):
        """Keep the status line ticking (and the TCP connection busy)."""
        while self._heartbeat_running:
            time.sleep(1.0)
            if self._heartbeat_running and time.time() - self._last_status > 1.8:
                self._status(f"{self._phase} {self._elapsed()}")

    # ------------------------------------------------------------------
    # Public API used by the proxy
    # ------------------------------------------------------------------

    def set_custom_prompt(self, prompt: Optional[str]):
        self.custom_prompt = prompt

    def clear_custom_prompt(self):
        self.custom_prompt = None

    def clear_conversation(self):
        self.conversation = []
        self._machine_note_sent = None

    def request_stop(self):
        """Stop the current request (called from the session's thread).

        Closing the stream ends a long silent think at once; otherwise the
        loop stops at its next stream event or between tool steps.
        """
        self._stop_requested = True
        self._phase = "STOPPING"
        stream = self._active_stream
        if stream is not None:
            interrupted = _shut_down_stream_socket(stream)
            print(f"[Agent] stop requested ({'stream interrupted' if interrupted else 'stops at the next event'})")
        else:
            print("[Agent] stop requested")

    def run_agentic(self, user_message: str, model: str = MODEL_IDS[MODEL_OPUS],
                    max_turns: int = 50) -> None:
        """Handle one user message end to end. Output goes to the Apple II."""
        if not self.client:
            self._line("NO API KEY - PUT ANTHROPIC_API_KEY IN PROXY/.ENV")
            return

        self._session_start = time.time()
        self._previews_allowed = True
        self._stop_requested = False
        self._final_text = ""
        deploys_before = len(self.deploy_history)
        text = self._machine_note() + user_message
        last = self.conversation[-1] if self.conversation else None
        if last and last["role"] == "user":
            # A stopped request left the conversation on a user turn
            content = last["content"]
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            last["content"] = list(content) + [{"type": "text", "text": text}]
        else:
            self.conversation.append({"role": "user", "content": text})
        self._start_heartbeat()
        try:
            self._loop(model, max_turns)
            self._last_request_deployed = len(self.deploy_history) > deploys_before
            if self._last_request_deployed and self._final_text.strip():
                self._closing_card(self._final_text)
        finally:
            self._stop_heartbeat()
            self._wait_preview()
            self._shutdown_test_emulator()

    # ------------------------------------------------------------------
    # The loop
    # ------------------------------------------------------------------

    def _machine_note(self) -> str:
        """Tell Claude about this Apple II when it changes (rides in the user turn)."""
        has_aux = self._has_aux()
        note = (f"Apple II: {'128K' if has_aux else '64K'}, "
                f"{self.display_width + 1}-column {'uppercase' if self.display_uppercase else 'mixed-case'} display"
                + (" for this log (programs still start in 40-column text)" if self.display_width > 39 else "")
                + ("" if self._can_deploy() else ", OLD AGENT.BIN (BASIC deploys only)"))
        if note == self._machine_note_sent:
            return ""
        self._machine_note_sent = note
        return f"[{note}]\n"

    def _system(self) -> List[Dict[str, Any]]:
        has_aux = self._has_aux()
        machine = ("Apple //e enhanced with 128K, 65C02 CPU. While your program runs the agent waits "
                   "in aux memory, so main memory is yours."
                   if has_aux else
                   "Apple //e with 64K. The agent stays in memory at $6000-$BFFF while your program runs.")
        memory = "$0800-$BEFF" if has_aux else "$0800-$5FFF only (this machine has no room above)"
        case_rule = ("The screen shows UPPERCASE only." if self.display_uppercase
                     else "Mixed case displays fine.")
        text = SYSTEM_PROMPT
        for key, value in (("{cols}", str(self.display_width + 1)), ("{case_rule}", case_rule),
                           ("{machine}", machine), ("{memory}", memory)):
            text = text.replace(key, value)
        if self.custom_prompt:
            text += f"\n\nTHE USER'S STANDING INSTRUCTIONS\n{self.custom_prompt}"
        return [{"type": "text", "text": text}]

    def _tools(self, streaming: bool) -> List[Dict[str, Any]]:
        tools = [dict(t, eager_input_streaming=True) if streaming else dict(t) for t in TOOLS]
        tools.append({"type": "web_search_20260209", "name": "web_search", "max_uses": 3})
        return tools

    def _loop(self, model: str, max_turns: int):
        json_retries = 0
        max_token_retries = 0
        for turn in range(max_turns):
            self._turn = turn + 1
            if self._stop_requested:
                self._line("STOPPED.")
                break
            self._set_phase("THINKING")
            if self._stop_requested:            # stopped while the phase was set
                self._line("STOPPED.")
                break
            try:
                response = self._stream_turn(model)
                json_retries = 0
            except StopRequested:
                print("[Agent] stopped")
                self._line("")
                self._line("STOPPED.")
                break
            except ValueError as e:
                # Tool input JSON the SDK couldn't parse at all - ask again
                json_retries += 1
                print(f"[Agent] bad tool JSON ({e}), retry {json_retries}")
                if json_retries > 2:
                    self._line("SORRY - SOMETHING WENT WRONG. TRY AGAIN?")
                    break
                continue
            except anthropic.AuthenticationError:
                self._line("THE API KEY WAS REJECTED. CHECK PROXY/.ENV")
                break
            except anthropic.RateLimitError:
                self._line("CLAUDE IS RATE LIMITED RIGHT NOW. WAIT A MINUTE AND TRY AGAIN.")
                break
            except anthropic.APIStatusError as e:
                msg = str(getattr(e, "message", e))
                if "credit" in msg.lower() or "balance" in msg.lower():
                    self._line("OUT OF API CREDITS - ADD CREDITS TO YOUR ANTHROPIC ACCOUNT.")
                else:
                    self._line(f"API ERROR {e.status_code}: {msg[:120]}")
                print(f"[Agent] API error: {e}")
                break
            except anthropic.APIConnectionError:
                self._line("CAN'T REACH CLAUDE - IS THE INTERNET UP?")
                break

            self.conversation.append({"role": "assistant", "content": response.content})
            self._log_usage(response)
            stop = response.stop_reason

            if stop == "pause_turn":
                continue
            if stop == "refusal":
                self._line("SORRY, I CAN'T HELP WITH THAT ONE.")
                break

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses and stop == "max_tokens" and max_token_retries < MAX_TOKEN_RETRIES:
                # Cut off before doing anything (a long think): leave that turn
                # out (a half-finished thinking block can't go back) and ask
                # for a shorter plan and the program in parts
                max_token_retries += 1
                self.conversation.pop()
                print(f"[Agent] T{self._turn} hit max_tokens with nothing done - retry {max_token_retries}")
                self._line("")
                self._line("(THAT PLAN GOT TOO BIG - STARTING SMALLER)")
                self.conversation.append({"role": "user", "content": [{"type": "text", "text": (
                    "(From the proxy: your last response ran out of output tokens while you were still "
                    "planning, before you called any tool, so it was discarded. Keep the plan short: write "
                    "a first playable version now with write_file, then grow it with edit_file and test "
                    "as you go.)")}]})
                continue
            if not tool_uses:
                if stop == "max_tokens":
                    self._line("(MY REPLY GOT CUT OFF)")
                else:
                    self._final_text = "".join(b.text for b in response.content if b.type == "text")
                break

            results = []
            for block in tool_uses:
                if self._stop_requested:
                    results.append(self._error_result(block.id, "Not run: the user stopped this request."))
                elif stop == "max_tokens":
                    results.append(self._error_result(
                        block.id, "Not run: your response hit max_tokens and this tool call was cut off. "
                                  "Write large programs in parts (write_file the first part, then "
                                  "edit_file to append the rest)."))
                else:
                    results.append(self._run_tool(block))
            self.conversation.append({"role": "user", "content": results})
            if self._stop_requested:
                self._line("STOPPED.")
                break
        else:
            self._line("(I RAN OUT OF STEPS - SAY 'CONTINUE' TO KEEP GOING)")

    def _request_params(self, model: str) -> Dict[str, Any]:
        is_haiku = "haiku" in model
        betas = []
        params: Dict[str, Any] = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "system": self._system(),
            "tools": self._tools(streaming=True),
            "messages": self.conversation,
            "output_config": {"effort": self.effort},
            "thinking": {"type": "adaptive"},
        }
        if "cache" not in self._disabled:
            params["cache_control"] = {"type": "ephemeral"}
        if "updates" not in self._disabled and not is_haiku:
            # "summarized", not "updates": under "updates" the up-front
            # reasoning comes back empty, and a big request's first think can
            # run ten minutes with nothing on the Apple II but a timer
            params["thinking"] = {"type": "adaptive", "display": "summarized"}
        if "fallbacks" not in self._disabled and not is_haiku:
            params["fallbacks"] = "default"
            betas.append(BETA_FALLBACK)
        if "compaction" not in self._disabled:
            params["context_management"] = {"edits": [{"type": "compact_20260112"}]}
            betas.append(BETA_COMPACT)
        if betas:
            params["betas"] = betas
        return params

    def _stream_turn(self, model: str):
        """One API call, streamed to the Apple II as it arrives."""
        for attempt in range(4):
            params = self._request_params(model)
            try:
                return self._consume_stream(params)
            except anthropic.BadRequestError as e:
                # An optional feature this model/account doesn't take? Drop it, retry.
                msg = str(getattr(e, "message", e)).lower()
                for feature, words in (("fallbacks", ("fallback",)),
                                       ("compaction", ("context_management", "compact")),
                                       ("updates", ("display", "thinking-display")),
                                       ("cache", ("cache_control",))):
                    if feature not in self._disabled and any(w in msg for w in words):
                        print(f"[Agent] API refused {feature}: {msg[:160]} - retrying without it")
                        self._disabled.add(feature)
                        break
                else:
                    raise
        raise RuntimeError("API kept refusing the request")

    def _consume_stream(self, params: Dict[str, Any]):
        self._text_buf = ""
        self._think_buf = ""
        try:
            return self._consume_open_stream(params)
        except StopRequested:
            raise
        except Exception as e:
            if self._stop_requested:            # request_stop() closed the stream
                print(f"[Agent] stream ended by the stop: {type(e).__name__}")
                raise StopRequested()
            raise
        finally:
            self._active_stream = None

    def _consume_open_stream(self, params: Dict[str, Any]):
        with self.client.beta.messages.stream(**params) as stream:
            self._active_stream = stream
            if self._stop_requested:
                raise StopRequested()
            for event in stream:
                if self._stop_requested:
                    raise StopRequested()       # leaves the unfinished turn out
                etype = event.type
                if etype == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        self._on_tool_start(block.name)
                    elif block.type == "server_tool_use":
                        self._set_phase("SEARCHING THE WEB")
                        self._line("* SEARCHING THE WEB")
                    elif block.type == "text":
                        self._set_phase("WRITING A REPLY")
                    elif block.type == "thinking":
                        self._think_buf = ""
                        self._think_shown = False
                elif etype == "text":
                    self._feed_text(event.text)
                elif etype == "thinking":
                    self._feed_thinking(event.thinking)
                elif etype == "input_json":
                    self._on_tool_input(event.partial_json)
                elif etype == "content_block_stop":
                    block = event.content_block
                    if block.type == "thinking":
                        self._flush_thinking()
                    elif block.type == "text":
                        self._flush_text()
            return stream.get_final_message()

    def _log_usage(self, response):
        u = getattr(response, "usage", None)
        if u:
            print(f"[Agent] T{self._turn} {response.stop_reason}: in={u.input_tokens} "
                  f"cache_read={getattr(u, 'cache_read_input_tokens', 0)} "
                  f"cache_write={getattr(u, 'cache_creation_input_tokens', 0)} out={u.output_tokens}")

    # ------------------------------------------------------------------
    # Live display of the stream
    # ------------------------------------------------------------------

    # Progress notes (thinking display "updates") scroll by line by line as
    # they stream in - a long think must not look like a hang
    def _feed_thinking(self, chunk: str):
        self._think_buf += chunk
        while "\n" in self._think_buf:
            line, self._think_buf = self._think_buf.split("\n", 1)
            self._progress_line(line)

    def _flush_thinking(self):
        self._progress_line(self._think_buf)
        self._think_buf = ""

    def _progress_line(self, line: str):
        line = line.strip()
        if not line or line == "This part of the response was interrupted before it finished.":
            return
        if not self._think_shown:
            self._line("")
            self._think_shown = True
        # Each paragraph of the thinking summary gets a few lines at most,
        # "- " and a hanging indent: easy to follow, not a wall of text (tool
        # steps are "* ")
        wrapped = word_wrap(apple_text(line, False), self.display_width - 2)
        if len(wrapped) > THINK_MAX_LINES:
            wrapped = wrapped[:THINK_MAX_LINES]
            wrapped[-1] = wrapped[-1][:self.display_width - 5].rstrip() + "..."
        for i, row in enumerate(wrapped):
            self._line(("- " if i == 0 else "  ") + row)

    def _feed_text(self, chunk: str):
        self._text_buf += chunk
        while "\n" in self._text_buf:
            line, self._text_buf = self._text_buf.split("\n", 1)
            self._line(line)

    def _flush_text(self):
        if self._text_buf.strip():
            self._line(self._text_buf)
        self._text_buf = ""

    def _on_tool_start(self, name: str):
        label = TOOL_LABELS.get(name, name.upper())
        self._set_phase(label)
        self._code_lines_shown = 0
        self._code_last_show = 0.0
        self._writing_name = ""
        self._tool_streaming = name
        self._tool_json = ""
        if name == "write_file":
            self._line("")
            self._line("* WRITING CODE")

    def _on_tool_input(self, partial_json: str):
        """While write_file streams in, scroll some of the code past the user.

        Parses the raw JSON so far with trailing strings kept: the SDK's own
        snapshot leaves out a string until its closing quote, which for a
        program means until the whole file has arrived.
        """
        if self._tool_streaming != "write_file":
            return
        self._tool_json += partial_json
        now = time.time()
        if now - self._code_last_show < 0.35:
            return
        try:
            snapshot = from_json(self._tool_json.encode(), partial_mode="trailing-strings")
        except ValueError:
            return
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("content"), str):
            return
        name = snapshot.get("name") if isinstance(snapshot.get("name"), str) else ""
        lines = snapshot["content"].split("\n")
        complete = len(lines) - 1
        if complete > self._code_lines_shown:
            newest = lines[complete - 1].rstrip()
            if newest.strip():
                self._line("  " + newest.strip()[:self.display_width - 2])
            self._code_lines_shown = complete
            self._code_last_show = now
            self._status(f"WRITING {name} {complete} LINES")

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _error_result(self, tool_id: str, message: str) -> Dict[str, Any]:
        return {"type": "tool_result", "tool_use_id": tool_id, "is_error": True, "content": message}

    def _run_tool(self, block) -> Dict[str, Any]:
        args = block.input if isinstance(block.input, dict) else None
        if args is None:
            return self._error_result(block.id, json.dumps({"INVALID_JSON": str(block.input)}))
        handler = {
            "write_file": self._tool_write_file,
            "edit_file": self._tool_edit_file,
            "read_file": self._tool_read_file,
            "run_in_emulator": self._tool_run,
            "emulator_input": self._tool_input,
            "emulator_memory": self._tool_memory,
            "deploy_to_apple": self._tool_deploy,
        }.get(block.name)
        if not handler:
            return self._error_result(block.id, f"Unknown tool {block.name}")
        try:
            content = handler(args)
        except ToolError as e:
            self._line(f"  {str(e).splitlines()[0][:self.display_width - 2]}")
            return self._error_result(block.id, str(e))
        except Exception as e:
            print(f"[Agent] tool {block.name} crashed: {e!r}")
            return self._error_result(block.id, f"Tool failed: {e}")
        return {"type": "tool_result", "tool_use_id": block.id, "content": content}

    @staticmethod
    def _need(args: dict, key: str, kind=str):
        value = args.get(key)
        if not isinstance(value, kind):
            raise ToolError(f"Missing or invalid '{key}'.")
        return value

    def _path(self, name: str) -> Path:
        name = name.strip().upper()
        if not NAME_RE.match(name):
            raise ToolError(f"Bad file name {name!r}: use letters, digits, '.', '-' (max 30), "
                            "e.g. GAME.BAS or GAME.S")
        return WORKSPACE / name

    def _tool_write_file(self, args):
        path = self._path(self._need(args, "name"))
        content = self._need(args, "content")
        path.write_text(content)
        lines = content.count("\n") + 1
        self._line(f"  WROTE {path.name} ({lines} LINES)")
        return f"Wrote {path.name}: {lines} lines, {len(content)} bytes."

    def _tool_edit_file(self, args):
        path = self._path(self._need(args, "name"))
        old = self._need(args, "old_text")
        new = self._need(args, "new_text")
        if not path.exists():
            raise ToolError(f"{path.name} doesn't exist.")
        text = path.read_text()
        count = text.count(old)
        if count == 0:
            raise ToolError(f"old_text not found in {path.name}. Use read_file to see the current text.")
        if count > 1:
            raise ToolError(f"old_text appears {count} times in {path.name}; include more context.")
        at_line = text[:text.index(old)].count("\n") + 1
        path.write_text(text.replace(old, new))
        self._line(f"* EDITED {path.name} LINE {at_line}")
        return f"Edited {path.name} at line {at_line}."

    def _tool_read_file(self, args):
        name = args.get("name")
        if not name:
            files = sorted(p.name for p in WORKSPACE.iterdir() if p.is_file() and p.suffix.upper() in SOURCE_EXTS)
            return "Workspace files: " + (", ".join(files) if files else "(none)")
        path = self._path(name)
        if not path.exists():
            raise ToolError(f"{path.name} doesn't exist.")
        lines = path.read_text().split("\n")
        self._line(f"* READING {path.name}")
        return "\n".join(f"{i + 1:5}| {l}" for i, l in enumerate(lines[:3000]))

    # --- building -------------------------------------------------------

    def _has_aux(self) -> bool:
        return bool(getattr(self.session, "has_aux", True)) if self.session else True

    def _can_deploy(self) -> bool:
        return bool(getattr(self.session, "can_deploy", True)) if self.session else True

    def _build(self, name: str, title: Optional[str] = None) -> deploy.Program:
        path = self._path(name)
        if not path.exists():
            raise ToolError(f"{path.name} doesn't exist - write it first.")
        source = path.read_text()
        title = (title or path.stem).strip()[:deploy.NAME_MAX]
        ext = path.suffix.upper()
        try:
            if ext == ".BAS":
                program = deploy.build_basic(source, title, self._has_aux())
            elif ext in (".S", ".ASM"):
                BUILD_DIR.mkdir(exist_ok=True)
                data, load_addr, labels, _ = deploy.assemble(source, str(BUILD_DIR), path.stem)
                self._labels = {k: v for k, v in labels.items() if not k.startswith("__")}
                entry = next((labels[k] for k in ("start", "START", "main", "MAIN") if k in labels), None)
                program = deploy.build_binary(data, load_addr, entry, title, self._has_aux(), source)
            else:
                raise ToolError(f"Don't know how to build {path.name} (use .BAS or .S).")
        except BuildError as e:
            raise ToolError(f"Build failed for {path.name}:\n{e}")
        program.source_name = path.name
        return program

    # --- emulator ---------------------------------------------------------

    def _bridge(self):
        from emulator_bridge import get_bridge
        return get_bridge()

    def _tool_run(self, args):
        name = self._need(args, "file")
        wait = args.get("wait", 2.0)
        wait = min(max(float(wait), 0.2), MAX_WAIT_PER_CALL) if isinstance(wait, (int, float)) else 2.0
        steps = args.get("steps") or []
        if not isinstance(steps, list):
            raise ToolError("steps must be a list.")

        program = self._build(name)
        self._line("")
        self._line(f"* TESTING {program.source_name} IN EMULATOR")
        self._set_phase("TESTING")
        bridge = self._bridge()
        started = bridge.run_program(program)
        if "error" in started:
            raise ToolError(f"Emulator problem: {started['error']}")
        self._emulator_ready = True

        looks = []
        time.sleep(wait)
        looks.append(("after %.1fs" % wait, bridge.observe()))
        looks.extend(self._play_steps(bridge, steps))
        header = f"Built OK. {program.summary()}"
        return self._report(header, looks)

    def _tool_input(self, args):
        steps = args.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ToolError("steps must be a non-empty list.")
        if not self._emulator_ready:
            raise ToolError("Nothing is running - use run_in_emulator first.")
        self._line("* PLAYING")
        self._set_phase("PLAYING")
        looks = self._play_steps(self._bridge(), steps)
        return self._report("Continued the running program.", looks)

    def _play_steps(self, bridge, steps) -> list:
        looks = []
        budget = MAX_WAIT_PER_CALL
        for i, step in enumerate(steps[:30]):
            if not isinstance(step, dict):
                continue
            keys = step.get("keys") or ""
            if keys:
                bridge.send_input(str(keys))
            wait = step.get("wait", 0.5)
            wait = min(max(float(wait), 0.0), budget) if isinstance(wait, (int, float)) else 0.5
            budget -= wait
            time.sleep(wait)
            last = i == len(steps) - 1
            if step.get("look") or last:
                label = f"after step {i + 1}" + (f" (typed {keys})" if keys else "")
                looks.append((label, bridge.observe()))
            if budget <= 0:
                looks.append(("time budget used up", bridge.observe()))
                break
        return looks

    def _report(self, header: str, looks: list) -> list:
        """Tool result: text for every look, images for the last few."""
        blocks: List[Dict[str, Any]] = []
        text = [header]
        final = looks[-1][1] if looks else None
        with_images = [i for i, (_, obs) in enumerate(looks) if obs.get("image")]
        with_images = with_images[-MAX_IMAGES_PER_RESULT:]
        for i, (label, obs) in enumerate(looks):
            text.append(f"\n[{label}] {obs['status']} Display: {obs['mode']}.")
            if obs["mode"].startswith("text") or obs["mode"].endswith("+text"):
                rows = obs["screen"] if obs["mode"].startswith("text") else obs["screen"][20:]
                shown = "\n".join(r.rstrip() for r in rows).rstrip()
                text.append("Text screen:\n" + (shown if shown.strip() else "(blank)"))
            for p in obs["problems"]:
                text.append("PROBLEM: " + p)
            if i in with_images:
                text.append("(screenshot follows)")
        blocks.append({"type": "text", "text": "\n".join(text)})
        for label, obs in (looks[i] for i in with_images):
            blocks.append({"type": "text", "text": f"Screenshot {label}:"})
            blocks.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/png",
                "data": base64.standard_b64encode(obs["image"]).decode("ascii")}})

        if final:
            self._show_observation(final)
        latest_hgr = next((obs["hgr_page"] for _, obs in reversed(looks) if obs.get("hgr_page")), None)
        if latest_hgr:
            self._send_preview(latest_hgr)
        return blocks

    def _show_observation(self, obs: dict):
        """Let the user peek at what the test machine shows."""
        self._line("  " + obs["status"])
        if obs["mode"].startswith("text"):
            rows = [r.rstrip() for r in obs["screen"] if r.strip()]
            for r in rows[:6]:
                self._line("  | " + r[:self.display_width - 4])
            if len(rows) > 6:
                self._line(f"  | ({len(rows) - 6} MORE LINES)")
        elif not obs.get("hgr_page"):
            self._line(f"  ({obs['mode'].upper()} SCREEN CAPTURED)")
        for p in obs["problems"]:
            self._line("  ! " + p)

    def _send_preview(self, hgr_page: bytes):
        """Push an HGR screenshot to the Apple II (background, newest wins)."""
        if not self.session or not self._previews_allowed:
            return
        if not getattr(self.session, "can_deploy", False):
            return
        self._wait_preview()
        self._line("  (PREVIEW ON YOUR SCREEN - ANY KEY = LOG)")
        self._preview_thread = threading.Thread(
            target=self._preview_worker, args=(hgr_page,), daemon=True)
        self._preview_thread.start()

    def _preview_worker(self, hgr_page: bytes):
        try:
            self.session.send_preview(hgr_page)
        except Exception as e:
            print(f"[Agent] preview failed: {e}")

    def _wait_preview(self):
        if self._preview_thread:
            self._preview_thread.join(timeout=60)
            self._preview_thread = None

    def _tool_memory(self, args):
        address = self._need(args, "address", int)
        count = args.get("count", 64)
        count = min(max(int(count), 1), 512) if isinstance(count, int) else 64
        if not 0 <= address <= 0xFFFF:
            raise ToolError("address must be 0-65535.")
        if not self._emulator_ready:
            raise ToolError("Nothing is running - use run_in_emulator first.")
        bridge = self._bridge()
        data = bridge.peek_memory(address, count)
        lines = []
        for off in range(0, len(data), 16):
            chunk = data[off:off + 16]
            lines.append(f"{address + off:04X}: " + " ".join(f"{b:02X}" for b in chunk))
        cpu = bridge.sock.get_cpu_state()
        regs = (f"PC=${cpu.get('pc', 0):04X} A=${cpu.get('a', 0):02X} X=${cpu.get('x', 0):02X} "
                f"Y=${cpu.get('y', 0):02X} SP=${cpu.get('sp', 0):02X} P=${cpu.get('p', 0):02X}")
        labels = ""
        if self._labels:
            near = sorted(self._labels.items(), key=lambda kv: kv[1])[:60]
            labels = "\nLabels: " + ", ".join(f"{k}=${v:04X}" for k, v in near)
        self._line(f"* MEMORY ${address:04X}")
        return regs + "\n" + "\n".join(lines) + labels

    # --- deploy ------------------------------------------------------------

    def _tool_deploy(self, args):
        name = self._need(args, "file")
        title = self._need(args, "title")
        program = self._build(name, title)
        if not self.session:
            raise ToolError("No Apple II is connected right now.")
        self._wait_preview()
        self._line("")
        self._line(f"* SENDING {program.name.upper()} TO YOUR APPLE II")
        self._set_phase("SENDING")
        result = self.session.deploy_program(program)
        if program.mode == deploy.MODE_RESIDENT:
            self._previews_allowed = False   # previews would land on the program
        self.deploy_history.append(program)
        self._save_history(program)
        self._line("  " + result.split(".")[0])
        return result

    def _save_history(self, program: deploy.Program):
        try:
            HISTORY_DIR.mkdir(exist_ok=True)
            n = len(list(HISTORY_DIR.iterdir())) + 1
            src = WORKSPACE / program.source_name
            shutil.copy(src, HISTORY_DIR / f"{n:03d}_{program.source_name}")
        except Exception as e:
            print(f"[Agent] history save failed: {e}")

    def _shutdown_test_emulator(self):
        """Free the test emulator's CPU between requests."""
        if not self._emulator_ready:
            return
        try:
            bridge = self._bridge()
            if bridge.emulator_running:
                bridge.shutdown()
        except Exception:
            pass
        self._emulator_ready = False


class ToolError(Exception):
    """A tool failed in a way Claude can fix. The message goes back to Claude."""


# Kept for older imports
_agentic_instance: Optional[AgenticClaude] = None


def get_agentic_claude(*_args, **_kwargs) -> AgenticClaude:
    global _agentic_instance
    if _agentic_instance is None:
        _agentic_instance = AgenticClaude()
    return _agentic_instance
