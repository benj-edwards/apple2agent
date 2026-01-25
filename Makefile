# Apple II Agent - Build System
# Builds the remote shell for real Apple IIe hardware

# Paths
ASM_DIR = asm
BUILD_DIR = build
LIBS_DIR = libs/ip65
DISKS_DIR = disks
TOOLS_DIR = tools

# Files
REMOTE_SRC = $(ASM_DIR)/remote_shell.s
REMOTE_OBJ = $(BUILD_DIR)/remote_shell.o
REMOTE_BIN = $(BUILD_DIR)/REMOTE.BIN
CONFIG = $(ASM_DIR)/agent.cfg
DISK = $(DISKS_DIR)/agent.dsk
TEST_DISK = $(DISKS_DIR)/agent_test.dsk

# Tools
CA65 = ca65
LD65 = ld65
PYTHON = python3

# Default target
all: $(REMOTE_BIN)

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

# Install to production disk
install: $(REMOTE_BIN)
	$(PYTHON) $(TOOLS_DIR)/prodos.py add $(DISK) $(REMOTE_BIN) REMOTE.BIN BIN 6000

# Install to test disk (emulator)
install-test: $(REMOTE_BIN)
	$(PYTHON) $(TOOLS_DIR)/prodos.py add $(TEST_DISK) $(REMOTE_BIN) REMOTE.BIN BIN 6000

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

.PHONY: all install install-test clean catalog catalog-test proxy agentic
