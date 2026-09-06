#!/bin/bash
# Build and install the SFS probe mod. Run from this folder.
set -e

GAME="/Users/christianjin/Library/Application Support/Steam/steamapps/common/Spaceflight Simulator/SpaceflightSimulatorGame.app"
MANAGED="$GAME/Contents/Resources/Data/Managed"

# HarmonyX 2.16.0 + its MonoMod dependency chain -- bundled here, NOT the
# game's own (older, arm64-macOS-broken) $MANAGED/0Harmony.dll. Confirmed
# via monodis (2026-08-27): the game's bundled 0Harmony.dll is HarmonyX
# 2.10.1.0 with MonoMod 22.3.23.4, which predates real Apple Silicon
# macOS support (added in MonoMod PR #241, merged 2025-08-15). See
# docs/sfs_physics_reference.md / mod_changelog.md for the full story.
#
# KNOWN RISK, untested as of this build: the game's own Managed/Mono.Cecil.dll
# is 0.10.4 (not strongly-named); this bundle needs 0.11.6. If the older one
# is already loaded by the time our code runs, ours may be silently ignored,
# which could cause a MissingMethodException from MonoMod.Core. Only a live
# test tells us for sure.
HARMONYX="$PWD/lib/harmonyx_2.16.0"

if ! command -v mcs >/dev/null 2>&1; then
  echo "mcs not found. Install with:  brew install mono"
  exit 1
fi

if [ ! -f "$HARMONYX/0Harmony.dll" ]; then
  echo "Bundled HarmonyX not found at $HARMONYX -- expected 0Harmony.dll and friends there."
  exit 1
fi

echo "== building =="
mcs -target:library -out:SFSProbe.dll \
    -noconfig -nostdlib \
    -r:"$MANAGED/mscorlib.dll" \
    -r:"$MANAGED/netstandard.dll" \
    -r:"$MANAGED/System.dll" \
    -r:"$MANAGED/System.Core.dll" \
    -r:"$MANAGED/System.IO.Compression.dll" \
    -r:"$MANAGED/Assembly-CSharp.dll" \
    -r:"$MANAGED/UnityEngine.dll" \
    -r:"$MANAGED/UnityEngine.CoreModule.dll" \
    -r:"$MANAGED/UnityEngine.InputLegacyModule.dll" \
    -r:"$HARMONYX/0Harmony.dll" \
    SFSProbe.cs

echo "== installing =="
mkdir -p "$GAME/Mods/SFSProbe"
cp SFSProbe.dll "$GAME/Mods/SFSProbe/" 2>/dev/null || cp SFSProbe.dll "$GAME/Mods/"
# All 7 DLLs need to sit next to SFSProbe.dll at runtime -- 0Harmony.dll
# pulls in the rest of this chain via Mono's normal assembly probing of
# the loading assembly's own directory.
cp "$HARMONYX"/*.dll "$GAME/Mods/SFSProbe/"

echo "done. Launch SFS, enable 'SFS Probe' in the Mod Loader, wait ~10s on the menu."
echo "Output lands in: $GAME/Mods/SFSProbe/"
