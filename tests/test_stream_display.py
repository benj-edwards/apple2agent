"""
What the Apple II shows while Claude streams - no API calls.

    .venv/bin/python -m pytest tests/test_stream_display.py -q
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proxy"))
import agentic_claude  # noqa: E402


class FakeSession:
    def __init__(self):
        self.lines, self.statuses = [], []

    def send_stream_line(self, line):
        self.lines.append(line)

    def send_status(self, text):
        self.statuses.append(text)

    def send_page_break(self):
        self.lines.append("<FF>")


def make_agent():
    agent = agentic_claude.AgenticClaude.__new__(agentic_claude.AgenticClaude)
    agent.session = FakeSession()
    agent.display_width = 39
    agent.display_uppercase = True
    agent._last_status = 0.0
    agent._phase = "THINKING"
    agent._session_start = 0.0
    agent._text_buf = agent._think_buf = agent._tool_streaming = agent._tool_json = ""
    agent._think_shown = False
    agent._code_lines_shown = 0
    agent._code_last_show = 0.0
    agent._writing_name = ""
    agent.deploy_history = []
    return agent


def test_progress_notes_appear_as_they_stream():
    a = make_agent()
    a._think_shown = False
    a._feed_thinking("Planning the brick layout first.\nThen the")
    assert a.session.lines == ["", "- PLANNING THE BRICK LAYOUT FIRST."]   # before the block ends
    a._feed_thinking(" paddle.")
    a._flush_thinking()
    assert a.session.lines[-1] == "- THEN THE PADDLE."


def test_long_thinking_paragraphs_are_cut_to_three_lines():
    a = make_agent()
    a._think_shown = False
    a._feed_thinking("**Planning the waves**\n" + "The enemies fly in from the top in a loop. " * 8 + "\n")
    shown = a.session.lines[1:]
    assert shown[0] == "- PLANNING THE WAVES"
    assert shown[1].startswith("- THE ENEMIES") and shown[2].startswith("  ")
    assert len(shown) == 4 and shown[-1].endswith("...")
    assert all(len(l) <= a.display_width for l in shown)


def test_interrupted_marker_is_hidden():
    a = make_agent()
    a._feed_thinking("This part of the response was interrupted before it finished.")
    a._flush_thinking()
    assert a.session.lines == []


def test_code_scrolls_by_while_the_file_streams(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(agentic_claude.time, "time", lambda: clock[0])
    a = make_agent()
    a._on_tool_start("write_file")
    program = "".join(f"  LDA #${i:02X}\n" for i in range(200))
    raw = json.dumps({"name": "GAME.S", "content": program})
    shown_before_end = 0
    for i in range(0, len(raw), 50):              # deltas, like the API sends
        clock[0] += 0.5
        a._on_tool_input(raw[i:i + 50])
        if i + 50 < len(raw):
            shown_before_end = sum(1 for l in a.session.lines if "LDA" in l)
    assert shown_before_end > 20                   # not just one line at the very end
    assert any("WRITING GAME.S" in s for s in a.session.statuses)


def test_other_tools_do_not_print_code():
    a = make_agent()
    a._on_tool_start("edit_file")
    a._on_tool_input(json.dumps({"name": "X.S", "old": "a\nb\n", "new": "c\nd\n"}))
    assert not any(l.strip().startswith(("A", "B", "C", "D")) and len(l.strip()) == 1 for l in a.session.lines)


def test_stop_mid_stream_drops_the_unfinished_turn():
    a = make_agent()
    a._stop_requested = True

    class FakeStream:
        def __enter__(self):
            return iter([type("E", (), {"type": "text", "text": "HI"})()])

        def __exit__(self, *exc):
            return False

    a.client = type("C", (), {"beta": type("B", (), {"messages": type("M", (), {
        "stream": staticmethod(lambda **kw: FakeStream())})()})()})()
    import pytest
    with pytest.raises(agentic_claude.StopRequested):
        a._consume_stream({})


def test_next_request_after_a_stop_merges_into_the_user_turn(monkeypatch):
    a = make_agent()
    a.client = object()
    a.conversation = [
        {"role": "user", "content": "make a game"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "stopped"}]},
    ]
    a._machine_note = lambda: ""
    for name in ("_loop", "_start_heartbeat", "_stop_heartbeat", "_wait_preview", "_shutdown_test_emulator"):
        monkeypatch.setattr(a, name, lambda *args, **kw: None)
    a.run_agentic("make it faster")
    assert [m["role"] for m in a.conversation] == ["user", "assistant", "user"]
    assert a.conversation[-1]["content"][-1] == {"type": "text", "text": "make it faster"}
    assert a._stop_requested is False


def test_a_turn_cut_off_while_planning_is_retried_not_the_end():
    from types import SimpleNamespace as NS
    a = make_agent()
    a._stop_requested = False
    a.conversation = [{"role": "user", "content": "make a huge game"}]
    replies = [
        NS(content=[NS(type="thinking", thinking="")], stop_reason="max_tokens", usage=None),
        NS(content=[NS(type="text", text="Done.")], stop_reason="end_turn", usage=None),
    ]
    sent = []

    def fake_turn(model):
        sent.append(list(a.conversation))
        return replies.pop(0)
    a._stream_turn = fake_turn
    a._loop("claude-opus-5-5", 10)
    assert not replies                                   # it asked again
    retry = sent[1]
    assert retry[0]["content"] == "make a huge game"     # the cut-off turn left out...
    assert retry[1]["role"] == "user" and "first playable version" in retry[1]["content"][0]["text"]
    assert len(retry) == 2                               # ...and nothing else touched
    assert any("TOO BIG" in l for l in a.session.lines)


def test_the_closing_card_starts_a_fresh_page_and_fits_above_ready():
    a = make_agent()
    a._closing_card("GALAXIA - a Galaga-style shooter.\n\nControls:\n- arrows move\n- space fires\n" + "x " * 400)
    assert a.session.lines[0] == "<FF>"
    card = a.session.lines[1:]
    assert card[:2] == ["GALAXIA - A GALAGA-STYLE SHOOTER.", ""]
    assert "- SPACE FIRES" in card
    assert len(card) == agentic_claude.CARD_MAX_ROWS
    assert all(len(r) <= a.display_width for r in card)
