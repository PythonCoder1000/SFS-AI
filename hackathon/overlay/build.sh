#!/bin/bash
# Builds the standalone JudgmentOverlay binary. No Xcode project needed.
set -e
cd "$(dirname "$0")"
swiftc -O JudgmentOverlay.swift -o JudgmentOverlay
echo "Built ./JudgmentOverlay"
echo "Run with:   ./JudgmentOverlay"
echo "Custom TCP port or screen:   ./JudgmentOverlay --port 47822 --screen 1"
