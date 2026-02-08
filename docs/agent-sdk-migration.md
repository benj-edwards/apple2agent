# Migration Plan: Agentic Loop to Claude Agent SDK

## Overview

Replace the hand-rolled agentic loop in `proxy/agentic_claude.py` with the [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview) (`claude-agent-sdk` Python package). The SDK provides built-in multi-turn orchestration, tool dispatch, context management, hooks, and MCP integration — eliminating ~500 lines of loop/retry/compaction code while preserving all Apple II-specific functionality.

## Why Migrate

| Current (hand-rolled) | Agent SDK |
|---|---|
| Manual tool dispatch switch statement | Automatic tool dispatch via MCP |
| Manual context compaction at 100K tokens | Built-in context management |
| Manual retry/error handling | Built-in retries and rate limit handling |
| Single tool per API response processed | Parallel tool execution support |
| Manual conversation history management | Automatic session/conversation management |
| Custom heartbeat thread safety | Hook-based event system |
| ~1400 lines in agentic_claude.py | Estimated ~600 lines after migration |

## Prerequisites

- **Node.js** installed (SDK wraps Claude Code CLI)
- **Claude Code CLI**: `npm install -g @anthropic-ai/claude-code`
- **Python SDK**: `pip install claude-agent-sdk`
- `ANTHROPIC_API_KEY` in environment (SDK reads it automatically)

## Architecture Comparison

### Current Flow
```
User message → unified_proxy.py → AgenticClaude.run_agentic()
  → manual API call (client.messages.create)
  → manual content block parsing
  → manual tool dispatch (_execute_tool)
  → manual conversation append
  → loop up to max_turns
  → manual context compaction
```

### Target Flow
```
User message → unified_proxy.py → AgenticClaude.run_agentic()
  → ClaudeSDKClient.query(message)
  → SDK handles: API calls, tool dispatch, context, retries
  → Hooks intercept: PreToolUse, PostToolUse, Stop
  → Hooks stream status/output to Apple II
  → ResultMessage returned when done
```

## SDK Entry Point: `ClaudeSDKClient`

The SDK provides two interfaces. **`ClaudeSDKClient`** is the right choice because:
- Multi-turn conversation (user sends multiple messages over time)
- Stateful — preserves context across `query()` calls
- Supports hooks for real-time status streaming
- Supports MCP servers for custom tools
- Supports interruption (`client.interrupt()`)

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

async with ClaudeSDKClient(options=options) as client:
    await client.query("Make a hello world program")
    async for message in client.receive_response():
        # Process messages, stream to Apple II
        pass
```

## Migration Plan by Component

---

### Phase 1: Tool Migration (MCP Server)

**Goal**: Expose all 20 emulator/deployment/disk tools as an in-process MCP server.

The SDK's `@tool` decorator and `create_sdk_mcp_server()` let us define tools in-process, which is ideal because the tools need access to the proxy's callback functions (send_code, send_status, etc.).

#### 1.1 Create `proxy/agent_tools.py`

New file that wraps the existing tool implementations as SDK MCP tools:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

# Emulator tools — delegate to emulator_bridge.mcp_call
@tool("emulator_boot", "Boot the Apple II emulator", {
    "machine": str,  # "enhanced", "plus", etc.
})
async def emulator_boot(args):
    result = mcp_call('mcp__apple2-mcp__boot', {
        'machine': args.get('machine', 'enhanced'),
        'uthernet2': True
    })
    return {"content": [{"type": "text", "text": str(result)}]}

@tool("emulator_read_screen", "Read the 40x24 text screen", {})
async def emulator_read_screen(args):
    result = mcp_call('mcp__apple2-mcp__read_screen', {})
    return {"content": [{"type": "text", "text": result}]}

# ... all 20 tools wrapped similarly

def create_apple2_mcp_server(mcp_call_fn, send_code_fn, send_binary_fn,
                              send_to_apple2_fn, send_status_fn, send_stream_fn):
    """Create the in-process MCP server with injected callbacks."""
    # Bind callbacks into tool closures
    nonlocal mcp_call  # or use a module-level setter
    mcp_call = mcp_call_fn

    return create_sdk_mcp_server(
        name="apple2",
        version="1.0.0",
        tools=[
            emulator_boot, emulator_load_env, emulator_type,
            emulator_read_screen, emulator_run_basic, emulator_inject_basic,
            emulator_capture_graphics, emulator_peek, emulator_poke,
            emulator_assemble, emulator_call, emulator_read_basic_program,
            apple2_send_code, apple2_send_message, apple2_send_status,
            apple2_send_binary,
            disk_save_basic, disk_save_binary, disk_save_text, disk_list,
        ]
    )
```

**Multi-step tools** (inject_basic, assemble, read_basic_program) keep their orchestration logic inside the `@tool` function — the SDK just calls the tool, the tool internally chains multiple MCP calls.

**Deployment tools** (send_code, send_binary, send_message) call the injected callbacks directly — these bypass the emulator and go straight to the Apple II via A2P protocol.

#### 1.2 Tool Naming

SDK MCP tools follow `mcp__<server>__<tool>` naming. With server name `"apple2"`:
- `mcp__apple2__emulator_boot`
- `mcp__apple2__emulator_read_screen`
- `mcp__apple2__apple2_send_code`
- etc.

Configure with wildcard: `allowed_tools=["mcp__apple2__*"]`

---

### Phase 2: Hooks for Apple II Streaming

**Goal**: Replace the manual status streaming, heartbeat, and output formatting with SDK hooks.

#### 2.1 PreToolUse Hook — Status Updates

Replaces the inline "TOOL: emulator_boot" status messages:

```python
async def pre_tool_hook(input_data, tool_use_id, context):
    tool_name = input_data.get('tool_name', '')
    tool_input = input_data.get('tool_input', {})

    # Stream status to Apple II
    short_name = tool_name.replace('mcp__apple2__', '')
    hint = _tool_param_hint(short_name, tool_input)
    send_status(f"TOOL: {short_name} {hint}")

    # Stream to scrolling area
    send_stream(f"  [{short_name}]")

    # Pause heartbeat for code deployment tools
    if short_name in ('apple2_send_code', 'apple2_send_binary'):
        heartbeat_pause()

    return {}  # Allow tool execution
```

#### 2.2 PostToolUse Hook — Result Preview

```python
async def post_tool_hook(input_data, tool_use_id, context):
    tool_name = input_data.get('tool_name', '')
    result = input_data.get('tool_result', '')

    short_name = tool_name.replace('mcp__apple2__', '')

    # Stream abbreviated result to Apple II
    preview = format_text(result.strip().split('\n')[0][:37])
    send_stream(f"  -> {preview}")

    # Resume heartbeat after code deployment
    if short_name in ('apple2_send_code', 'apple2_send_binary'):
        heartbeat_resume()

    return {}
```

#### 2.3 Stop Hook — Completion

```python
async def stop_hook(input_data, tool_use_id, context):
    send_stream("--- COMPLETE ---")
    shutdown_test_emulator()
    return {}
```

#### 2.4 Hook Configuration

```python
from claude_agent_sdk import HookMatcher

hooks = {
    'PreToolUse': [
        HookMatcher(matcher='^mcp__apple2__', hooks=[pre_tool_hook])
    ],
    'PostToolUse': [
        HookMatcher(matcher='^mcp__apple2__', hooks=[post_tool_hook])
    ],
    'Stop': [
        HookMatcher(hooks=[stop_hook])
    ]
}
```

---

### Phase 3: Message Stream Processing

**Goal**: Process SDK message stream to display Claude's text output on the Apple II.

#### 3.1 Response Processing Loop

Replace `_run_agentic_loop` with:

```python
async def run_agentic(self, user_message: str) -> str:
    self._start_heartbeat()
    try:
        await self.client.query(user_message)

        final_text = ""
        async for message in self.client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        # Stream text to Apple II
                        wrapped = self._word_wrap(block.text)
                        for line in wrapped:
                            self._stream(self._format_text(line))
                        final_text += block.text
                    elif isinstance(block, ThinkingBlock):
                        # Stream thinking preview to status line
                        snippet = self._format_text(block.thinking[:35])
                        self.send_status(f"THINKING: {snippet}")

            elif isinstance(message, ResultMessage):
                if message.is_error:
                    self.send_status("ERROR")
                break

        return self._format_text(final_text) if final_text else ""
    finally:
        self._stop_heartbeat()
        self._shutdown_test_emulator()
```

#### 3.2 StreamEvent for Real-Time Output

Enable `include_partial_messages=True` in options to get `StreamEvent` messages for real-time token-by-token streaming (optional enhancement — the above block-level processing may be sufficient).

---

### Phase 4: Client Lifecycle

**Goal**: Manage the `ClaudeSDKClient` lifecycle within `AgenticClaude`.

#### 4.1 Client Creation

```python
class AgenticClaude:
    def __init__(self, ...):
        self.client = None
        self._options = None
        # ... existing callback storage

    async def _ensure_client(self):
        """Create or reconfigure the SDK client."""
        if self.client is None:
            apple2_server = create_apple2_mcp_server(
                self.mcp_call, self.send_code, self.send_binary,
                self.send_to_apple2, self.send_status, self.send_stream
            )

            self._options = ClaudeAgentOptions(
                model=self._get_model_id(),
                max_turns=self.max_turns,
                system_prompt=self._build_system_prompt(),
                mcp_servers={"apple2": apple2_server},
                allowed_tools=["mcp__apple2__*"],
                permission_mode="bypassPermissions",
                hooks=self._build_hooks(),
                include_partial_messages=True,
                env={"ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", "")},
            )

            self.client = ClaudeSDKClient(options=self._options)
            await self.client.connect()
```

#### 4.2 Model Switching

When `/MODEL` changes the model, disconnect and recreate the client:

```python
    def set_model(self, model_name: str):
        self.model = model_name
        if self.client:
            # Force recreation on next query
            asyncio.create_task(self.client.disconnect())
            self.client = None
```

#### 4.3 Conversation Clear

```python
    async def clear_conversation(self):
        if self.client:
            await self.client.disconnect()
            self.client = None
        # Client will be recreated fresh on next query
```

#### 4.4 Session Persistence Across TCP Reconnects

The `AgenticClaude` singleton pattern is preserved — the `ClaudeSDKClient` lives on the singleton. When the Apple II reconnects, only the callbacks are updated (same as today). The SDK client maintains conversation context internally.

---

### Phase 5: Heartbeat Adaptation

**Goal**: Keep the heartbeat mechanism working with the async SDK.

The heartbeat thread sends STATUS packets every ~2 seconds to keep the TCP connection alive. This is independent of the SDK and should continue working as-is, with minor changes:

1. **Start/stop** around `run_agentic()` — same as today
2. **Thread safety** — the `_send_lock` pattern continues to work since hooks and message processing happen in the same async context
3. **Pause during code deployment** — triggered from `PreToolUse` hook instead of inline in `_execute_tool()`

No fundamental changes needed — the heartbeat is a transport-layer concern that operates below the SDK level.

---

### Phase 6: Remove Hand-Rolled Code

**Goal**: Delete code that the SDK replaces.

Remove from `agentic_claude.py`:
- `APPLE2_TOOLS` list (tool definitions) — replaced by `agent_tools.py`
- `_execute_tool()` method — replaced by SDK + MCP tool dispatch
- `_run_agentic_loop()` method — replaced by SDK orchestration
- `_compact_conversation()` method — replaced by SDK context management
- `_estimate_tokens()` method — no longer needed
- Direct `anthropic.Client` usage — SDK manages the API client
- Web search tool injection — configure as SDK option or keep as Anthropic beta feature
- Manual conversation list management — SDK handles this

Keep in `agentic_claude.py`:
- `_stream()`, `_word_wrap()`, `_format_text()` — display formatting
- `_start_heartbeat()`, `_stop_heartbeat()`, `_heartbeat_loop()` — TCP keepalive
- `_tool_param_hint()` — status line formatting
- `_build_system_prompt()` — custom system prompt construction
- `_checkpoint_program()` — program versioning
- All callback wiring (`send_code`, `send_status`, etc.)
- Display mode state (`display_width`, `display_uppercase`)

---

## Web Search Integration

The current implementation uses Anthropic's server-side `web_search_20250305` tool with a beta header. Two options:

**Option A**: Keep the web search as a native Anthropic tool. The SDK may support this via `ClaudeAgentOptions` or it may already be available as a built-in Claude Code tool (`WebSearch`).

**Option B**: If the SDK's built-in `WebSearch` tool works, just add it to `allowed_tools`. This is likely the better path since Claude Code already has web search built in.

---

## Risk Assessment

### High Risk
- **SDK requires Claude Code CLI (Node.js)** — adds a runtime dependency. The proxy currently only needs Python. Mitigation: document the requirement, add to setup instructions.
- **SDK spawns a subprocess** — the SDK wraps the CLI, not the API directly. This adds latency and complexity vs direct API calls. Need to measure performance impact.
- **Callback injection into MCP tools** — the deployment tools need access to proxy callbacks (send_code, send_binary). The `@tool` decorator + `create_sdk_mcp_server()` approach should support this via closures, but needs validation.

### Medium Risk
- **Context management conflict** — the SDK has its own context management. Need to verify it handles the 100K+ token conversations that occur during complex multi-turn development sessions.
- **Web search compatibility** — the server-side web search tool may need special handling in the SDK.
- **Heartbeat thread safety** — the async SDK + sync heartbeat thread need careful coordination. The existing `_send_lock` pattern should work but needs testing.

### Low Risk
- **Display formatting** — `_format_text()`, `_word_wrap()` are independent of the SDK and will work unchanged.
- **A2P protocol** — the transport layer is completely separate from the agentic loop.
- **Session persistence** — the SDK's `ClaudeSDKClient` instance lives on the `AgenticClaude` singleton, same lifecycle as today.

---

## Implementation Order

1. **Phase 1**: Create `agent_tools.py` with all 20 tools as MCP tools. Test that tools work via `create_sdk_mcp_server()`.
2. **Phase 2**: Add hooks for status streaming. Verify Apple II sees tool status updates.
3. **Phase 3**: Replace `_run_agentic_loop` with SDK message processing. This is the core migration.
4. **Phase 4**: Wire up `ClaudeSDKClient` lifecycle (create, reconnect, clear, model switch).
5. **Phase 5**: Verify heartbeat works with async SDK. Adjust thread safety if needed.
6. **Phase 6**: Remove dead code. Clean up imports.

Each phase can be tested independently by running the proxy and connecting from the Apple II (or Bobbin emulator).

---

## Estimated Complexity

| Phase | Files Modified | New Files | Lines Changed (est.) |
|-------|---------------|-----------|---------------------|
| 1 | — | `proxy/agent_tools.py` | +400 |
| 2 | `proxy/agentic_claude.py` | — | +80 |
| 3 | `proxy/agentic_claude.py` | — | +60, -200 |
| 4 | `proxy/agentic_claude.py` | — | +80, -40 |
| 5 | `proxy/agentic_claude.py` | — | +20, -10 |
| 6 | `proxy/agentic_claude.py` | — | -500 |
| **Total** | 1 | 1 | +640, -750 |

Net reduction: ~110 lines, but the real win is replacing fragile hand-rolled orchestration with a maintained SDK.

---

## Open Questions

1. **Does the SDK support Anthropic's server-side web search tool?** If not, we need to find an alternative or keep a hybrid approach.
2. **What's the latency overhead of the CLI subprocess vs direct API calls?** Need to benchmark — the Apple II user is watching in real-time.
3. **Can `create_sdk_mcp_server()` tools be async and call sync functions?** The emulator bridge uses synchronous socket I/O. May need `asyncio.to_thread()` wrappers.
4. **Does the SDK's context management handle tool_result blocks correctly?** The current compaction summarizes tool results — need to verify the SDK does something equivalent.
5. **Rate limiting** — does the SDK automatically handle per-minute rate limits with backoff? This would fix the rate limit crashes the user has experienced.
