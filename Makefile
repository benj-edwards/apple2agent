# Apple II Agent - Build System
# Builds the remote shell and agent for real Apple IIe hardware

# Paths
ASM_DIR = asm
BUILD_DIR = build
LIBS_DIR = libs/ip65
DISKS_DIR = disks
TOOLS_DIR = tools
PROXY_DIR = proxy

# Files - Remote Shell
REMOTE_SRC = $(ASM_DIR)/remote_shell.s
REMOTE_OBJ = $(BUILD_DIR)/remote_shell.o
REMOTE_BIN = $(BUILD_DIR)/REMOTE.BIN

# Files - Claude Code UI
CLAUDE_SRC = $(ASM_DIR)/claude_code_ui.s
CLAUDE_OBJ = $(BUILD_DIR)/claude_code_ui.o
CLAUDE_BIN = $(BUILD_DIR)/CLAUDE.CODE

# Files - Unified Agent (A2P Protocol)
AGENT_SRC = $(ASM_DIR)/agent.s
AGENT_OBJ = $(BUILD_DIR)/agent.o
AGENT_BIN = $(BUILD_DIR)/AGENT.BIN

CONFIG = $(ASM_DIR)/agent.cfg
DISK = $(DISKS_DIR)/agent.dsk
TEST_DISK = $(DISKS_DIR)/agent_test.dsk
CLAUDE_DISK = $(DISKS_DIR)/claude_code.dsk

# Tools
CA65 = ca65
LD65 = ld65
PYTHON = python3

# Default target
all: $(REMOTE_BIN) $(CLAUDE_BIN) $(AGENT_BIN)

# Assemble
$(REMOTE_OBJ): $(REMOTE_SRC)
	@mkdir -p $(BUILD_DIR)
	$(CA65) --cpu 6502 -I $(LIBS_DIR)/inc -o $@ $<

# Link (loads at $6000, no header)
$(REMOTE_BIN): $(REMOTE_OBJ) $(CONFIG)
	$(LD65) -C $(CONFIG) -o $@ $(REMOTE_OBJ) \
		$(LIBS_DIR)/ip65_tcp.lib \
		$(LIBS_DIR)/drivers/a2uther2.lib \
		apple2.lib

# Assemble Claude Code
$(CLAUDE_OBJ): $(CLAUDE_SRC)
	@mkdir -p $(BUILD_DIR)
	$(CA65) --cpu 6502 -I $(LIBS_DIR)/inc -o $@ $<

# Link Claude Code
$(CLAUDE_BIN): $(CLAUDE_OBJ) $(CONFIG)
	$(LD65) -C $(CONFIG) -o $@ $(CLAUDE_OBJ) \
		$(LIBS_DIR)/ip65_tcp.lib \
		$(LIBS_DIR)/drivers/a2uther2.lib \
		apple2.lib

# Assemble Agent (A2P Protocol)
$(AGENT_OBJ): $(AGENT_SRC)
	@mkdir -p $(BUILD_DIR)
	$(CA65) --cpu 6502 -I $(LIBS_DIR)/inc -o $@ $<

# Link Agent
$(AGENT_BIN): $(AGENT_OBJ) $(CONFIG)
	$(LD65) -C $(CONFIG) -o $@ $(AGENT_OBJ) \
		$(LIBS_DIR)/ip65_tcp.lib \
		$(LIBS_DIR)/drivers/a2uther2.lib \
		apple2.lib

# Build only the unified agent
agent: $(AGENT_BIN)

# Install to production disk
install: $(REMOTE_BIN)
	$(PYTHON) $(TOOLS_DIR)/prodos.py add $(DISK) $(REMOTE_BIN) REMOTE.BIN BIN 6000

# Install to test disk (emulator)
install-test: $(REMOTE_BIN)
	$(PYTHON) $(TOOLS_DIR)/prodos.py add $(TEST_DISK) $(REMOTE_BIN) REMOTE.BIN BIN 6000

# Install agent to production disk
install-agent: $(AGENT_BIN)
	$(PYTHON) $(TOOLS_DIR)/prodos.py add $(DISK) $(AGENT_BIN) AGENT.BIN BIN 6000

# Install agent to test disk (emulator)
install-agent-test: $(AGENT_BIN)
	$(PYTHON) $(TOOLS_DIR)/prodos.py add $(TEST_DISK) $(AGENT_BIN) AGENT.BIN BIN 6000

# Clean build artifacts
clean:
	rm -f $(BUILD_DIR)/*.o $(BUILD_DIR)/*.BIN

# Show disk catalog
catalog:
	$(PYTHON) $(TOOLS_DIR)/prodos.py list $(DISK)

catalog-test:
	$(PYTHON) $(TOOLS_DIR)/prodos.py list $(TEST_DISK)

# Start the proxy server
proxy:
	cd proxy && $(PYTHON) remote_proxy.py

# Start the agentic proxy
agentic:
	cd proxy && $(PYTHON) agentic_proxy.py

# Start the Claude streaming proxy
stream-proxy:
	cd proxy && $(PYTHON) claude_streaming_proxy.py

# Start the unified proxy (A2P Protocol)
unified-proxy:
	cd $(PROXY_DIR) && $(PYTHON) unified_proxy.py

# Start unified proxy in test mode (with Bobbin)
unified-proxy-test:
	cd $(PROXY_DIR) && $(PYTHON) unified_proxy.py --test

# Install Claude Code to disk
install-claude: $(CLAUDE_BIN)
	$(PYTHON) $(TOOLS_DIR)/prodos.py add $(CLAUDE_DISK) $(CLAUDE_BIN) CLAUDE.CODE BIN 6000

# Run protocol tests
test:
	cd tests && $(PYTHON) -c "from test_protocol import *; import unittest; unittest.main(module='test_protocol', exit=False)" 2>/dev/null || $(PYTHON) test_protocol.py

.PHONY: all agent install install-test install-agent install-agent-test clean catalog catalog-test proxy agentic stream-proxy unified-proxy unified-proxy-test install-claude test
