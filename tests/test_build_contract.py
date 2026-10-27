#!/usr/bin/env python3
"""
The test harness must launch programs exactly the way AGENT.SYSTEM does:
its copy of the page-3 hooks has to be the bytes the agent installs.
"""

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'proxy'))

from emulator_bridge import PAGE3_HOOKS, PAGE3_START, KSW_HOOK, RETURN_ENTRY  # noqa: E402

AGENT = os.path.join(ROOT, 'build', 'AGENT.SYSTEM')


@pytest.mark.skipif(not os.path.exists(AGENT), reason="run make agent first")
def test_page3_hooks_match_the_agent():
    image = open(AGENT, 'rb').read()
    assert image.count(PAGE3_HOOKS) == 1, \
        "emulator_bridge.PAGE3_HOOKS differs from page3_code in agent_deploy.s"


def test_page3_layout():
    assert PAGE3_START + len(PAGE3_HOOKS) <= 0x03F0          # BRK vector
    assert PAGE3_HOOKS[RETURN_ENTRY - PAGE3_START:][:3] == b'\0\0\0'  # filled at launch
    assert PAGE3_HOOKS[KSW_HOOK - PAGE3_START:][:3] == bytes([0x20, 0x1B, 0xFD])  # JSR KEYIN first
