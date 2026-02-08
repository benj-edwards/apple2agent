#!/usr/bin/env python3
"""
Create pre-baked environment snapshots for instant loading.

This script boots the emulator in different configurations and saves
state snapshots that can be instantly loaded later.

Snapshots created:
  - states/basic.state: Apple //e at BASIC ] prompt (no disk)
  - states/prodos.state: ProDOS 2.4 with BASIC.SYSTEM at ] prompt

Usage:
    python3 tools/create_snapshots.py
"""

import os
import sys
import time
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from apple2_mcp.control_socket import BobbinControlSocket, ControlSocketError
from apple2_mcp.emulator import Emulator, BobbinError

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
STATES_DIR = PROJECT_ROOT / "states"
DISKS_DIR = PROJECT_ROOT / "disks"

# Snapshot configurations
SNAPSHOTS = [
    {
        "name": "basic",
        "description": "Apple //e at BASIC ] prompt (no disk)",
        "machine": "enhanced",
        "disk": None,
        "output": STATES_DIR / "basic.state",
    },
    # ProDOS and DOS 3.3 snapshots are created manually because they require
    # interactive menu navigation (ProDOS BITSY.BOOT selector) or a DOS 3.3
    # boot disk. Use the MCP tools to create them:
    #
    #   ProDOS:  boot with ProDOS_2_4.dsk, select BASIC.SYSTEM, save_state
    #   DOS 3.3: boot with any DOS 3.3 disk, save_state
    #
    # Or use the pre-created states in states/ directory.
]


def create_snapshot(config: dict, verbose: bool = True) -> bool:
    """Create a single snapshot.

    Args:
        config: Snapshot configuration dict
        verbose: Print progress messages

    Returns:
        True if successful
    """
    name = config["name"]
    output_path = config["output"]

    if verbose:
        print(f"\n{'='*60}")
        print(f"Creating snapshot: {name}")
        print(f"Description: {config['description']}")
        print(f"Output: {output_path}")
        print(f"{'='*60}")

    # Create emulator instance
    emu = Emulator()

    try:
        # Boot the emulator
        if verbose:
            print(f"Booting emulator (machine={config['machine']})...")

        boot_kwargs = {
            "machine": config["machine"],
            "timeout": 120.0,  # Longer timeout for disk boots
        }
        if config.get("disk"):
            boot_kwargs["disk"] = config["disk"]
            # ProDOS disks may take longer to boot
            boot_kwargs["timeout"] = 120.0
            if verbose:
                print(f"With disk: {config['disk']}")

        emu.boot(**boot_kwargs)

        if verbose:
            print("Boot complete. Waiting for system to settle...")

        # Wait for system to stabilize
        time.sleep(1.0)

        # Verify we're at the BASIC prompt
        lines = emu.read_screen()
        screen_text = '\n'.join(lines)
        if verbose:
            print(f"Screen contents:")
            for i, line in enumerate(lines):
                print(f"  {i:2d}: {line.rstrip()}")

        # Check for BASIC prompt
        if ']' not in screen_text:
            print(f"WARNING: BASIC prompt not found on screen")

        # Save state
        if verbose:
            print(f"\nSaving state to: {output_path}")

        result = emu.save_state(str(output_path))

        if result.get("ok"):
            if verbose:
                print(f"SUCCESS: State saved ({output_path.stat().st_size} bytes)")
            return True
        else:
            print(f"ERROR: {result.get('error', 'unknown error')}")
            return False

    except BobbinError as e:
        print(f"ERROR: {e}")
        return False

    finally:
        # Always shutdown cleanly
        if verbose:
            print("Shutting down emulator...")
        emu.shutdown()


def verify_snapshot(config: dict, verbose: bool = True) -> bool:
    """Verify a snapshot can be loaded.

    Args:
        config: Snapshot configuration dict
        verbose: Print progress messages

    Returns:
        True if verification successful
    """
    name = config["name"]
    state_path = config["output"]

    if not state_path.exists():
        print(f"SKIP: Snapshot {state_path} does not exist")
        return False

    if verbose:
        print(f"\nVerifying snapshot: {name}")

    # Create emulator instance
    emu = Emulator()

    try:
        # Boot minimally (we'll load state immediately)
        if verbose:
            print("Booting emulator...")
        emu.boot(machine="enhanced", timeout=30.0)

        # Load the state
        if verbose:
            print(f"Loading state from: {state_path}")
        result = emu.load_state(str(state_path))

        if not result.get("ok"):
            print(f"ERROR loading state: {result.get('error', 'unknown')}")
            return False

        version = result.get("version", 1)
        if verbose:
            print(f"State loaded (version {version})")

        # Give time for state to apply
        time.sleep(0.5)

        # Read screen to verify
        lines = emu.read_screen()
        screen_text = '\n'.join(lines)

        if verbose:
            print("Screen after load:")
            for i, line in enumerate(lines):
                print(f"  {i:2d}: {line.rstrip()}")

        # Verify BASIC prompt
        if ']' not in screen_text:
            print("WARNING: BASIC prompt not found after load")
            return False

        if verbose:
            print(f"VERIFIED: {name} snapshot loads correctly")
        return True

    except BobbinError as e:
        print(f"ERROR: {e}")
        return False

    finally:
        emu.shutdown()


def main():
    """Create all environment snapshots."""
    print("Apple II Environment Snapshot Creator")
    print("=====================================")

    # Ensure states directory exists
    STATES_DIR.mkdir(exist_ok=True)

    # Create each snapshot
    created = 0
    verified = 0

    for config in SNAPSHOTS:
        if create_snapshot(config):
            created += 1

            # Verify the snapshot
            if verify_snapshot(config):
                verified += 1
        else:
            print(f"FAILED to create snapshot: {config['name']}")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Snapshots created: {created}/{len(SNAPSHOTS)}")
    print(f"Snapshots verified: {verified}/{len(SNAPSHOTS)}")

    if created == len(SNAPSHOTS) and verified == len(SNAPSHOTS):
        print("\nAll snapshots created and verified successfully!")
        print("\nYou can now use these tools:")
        print("  - load_basic_env: Instant BASIC environment")
        print("  - load_prodos_env: Instant ProDOS environment")
        return 0
    else:
        print("\nSome snapshots failed. Check output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
