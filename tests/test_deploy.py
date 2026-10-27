#!/usr/bin/env python3
"""
deploy.py's notes to Claude: a hi-res program whose own bytes sit in a page
it draws on wipes itself out - warn, but not for a .res gap or another page.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'proxy'))

import deploy  # noqa: E402

CODE_TO_2800 = bytes([0xEA]) * 0x2000                                    # $0800-$27FF
GAP_FOR_PAGE1 = bytes([0xEA]) * 0x1800 + bytes(0x2000) + bytes([0xEA]) * 0x100  # page 1 left as .res


@pytest.mark.parametrize("data,load,source,warned", [
    (CODE_TO_2800, 0x0800, "sta $C057", True),                # code runs into page 1
    (GAP_FOR_PAGE1, 0x0800, "sta $C057", False),              # .res keeps page 1 clear
    (GAP_FOR_PAGE1, 0x0800, "sta $C057\nsta $C055", True),    # ...but page 2 is drawn on too
    (CODE_TO_2800, 0x0800, "rts", False),                     # no hi-res at all
    (bytes([0xEA]) * 0x4000, 0x6000, "sta $c057\nsta $c055", False),  # above both pages
])
def test_hires_overlap_warning(data, load, source, warned):
    program = deploy.build_binary(data, load, None, "T", True, source)
    assert ("WARNING" in program.summary()) == warned


def test_binary_past_the_top_is_refused():
    with pytest.raises(deploy.BuildError):
        deploy.build_binary(bytes(0x100), 0xBE80, None, "T", True)
