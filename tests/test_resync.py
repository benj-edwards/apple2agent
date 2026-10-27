#!/usr/bin/env python3
"""
/RESYNC: the Apple II's stall watchdog reconnected and asks for what may never
have arrived. No sockets or API calls.
"""

import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'proxy'))

import unified_proxy  # noqa: E402


def make_session(agent):
    s = unified_proxy.AppleIISession.__new__(unified_proxy.AppleIISession)
    s.proxy = NS(agentic_claude=agent)
    s.sent = []
    s._send_status = lambda text: s.sent.append(("status", text))
    s.send_done = lambda: s.sent.append(("done",))
    s.deploy_program = lambda p: s.sent.append(("deploy", p))
    return s


def make_agent(**kw):
    agent = NS(busy=False, session=None, deploy_history=["PROGRAM"], _final_text="IT'S READY.",
               _last_request_deployed=True, _resynced=False)
    agent._closing_card = lambda text: agent.session.sent.append(("card", text))
    for k, v in kw.items():
        setattr(agent, k, v)
    return agent


def test_idle_resync_sends_the_final_message_and_the_program_again():
    agent = make_agent()
    s = make_session(agent)
    s._handle_resync()
    assert [x[0] for x in s.sent] == ["status", "card", "deploy", "done"]
    assert ("deploy", "PROGRAM") in s.sent and agent.session is s


def test_idle_resync_after_a_chat_sends_no_program():
    agent = make_agent(_last_request_deployed=False)
    s = make_session(agent)
    s._handle_resync()
    assert [x[0] for x in s.sent] == ["status", "card", "done"]


def test_resync_while_claude_works_takes_over_the_session():
    agent = make_agent(busy=True)
    s = make_session(agent)
    s._handle_resync()
    assert s.sent == [("status", "RECONNECTED - STILL WORKING")]
    assert agent.session is s and agent._resynced is True


def test_the_stall_report_is_decoded_and_logged(tmp_path, monkeypatch):
    monkeypatch.setenv("APPLE2_LOG_DIR", str(tmp_path))
    s = make_session(make_agent())
    s.addr = ("192.168.1.50", 1234)
    s._log_stall_report(" N=0005 T=1A2B B=0003 H=0001 A=00 S=42 Q=0000 E=12AB L=12AB")
    log = (tmp_path / "stall_reports.log").read_text()
    assert "stall reported by 192.168.1.50" in log
    assert "B=0003 (3)  ...with a bad checksum" in log
    assert "S=  42 (66)  W5100 socket 0 status" in log


def test_an_old_client_resync_has_no_report(tmp_path, monkeypatch):
    monkeypatch.setenv("APPLE2_LOG_DIR", str(tmp_path))
    s = make_session(make_agent())
    s.addr = ("10.0.0.2", 1)
    s._log_stall_report("")
    assert "(no report: an older client)" in (tmp_path / "stall_reports.log").read_text()
