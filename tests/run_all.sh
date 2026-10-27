#!/bin/bash
# Every automated test that needs no API calls, one after another.
# (They can't run in parallel: their proxies all answer discovery on UDP 6502.)
cd "$(dirname "$0")/.."
PY=.venv/bin/python
status=0
run() { echo "=== $*"; "$@" || status=1; }
run $PY -m pytest -q tests/test_protocol.py tests/test_stream_display.py tests/test_build_contract.py tests/test_deploy.py tests/test_resync.py
run $PY tests/e2e_display.py
run $PY tests/e2e_setup.py
run $PY tests/e2e_agent.py
run env E2E_DISPLAY=80 $PY tests/e2e_agent.py
run env BOBBIN_U2_CORRUPT_EVERY=5 BOBBIN_U2_CORRUPT_LEN_EVERY=7 $PY tests/e2e_agent.py   # a flaky bus: garbled segments, misread frame lengths
run $PY tests/soak_agent.py 25
[ "$1" = "--real-speed" ] && run env E2E_REAL_SPEED=1 $PY tests/e2e_agent.py
exit $status
