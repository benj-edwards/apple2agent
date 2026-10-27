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
