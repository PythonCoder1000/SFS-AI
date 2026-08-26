#!/bin/bash
# Build and install the SFS probe mod. Run from this folder.
set -e

GAME="/Users/christianjin/Library/Application Support/Steam/steamapps/common/Spaceflight Simulator/SpaceflightSimulatorGame.app"
MANAGED="$GAME/Contents/Resources/Data/Managed"

if ! command -v mcs >/dev/null 2>&1; then
  echo "mcs not found. Install with:  brew install mono"
  exit 1
fi

echo "== building =="
mcs -target:library -out:SFSProbe.dll \
    -noconfig -nostdlib \
    -r:"$MANAGED/mscorlib.dll" \
    -r:"$MANAGED/netstandard.dll" \
    -r:"$MANAGED/System.dll" \
    -r:"$MANAGED/System.Core.dll" \
    -r:"$MANAGED/Assembly-CSharp.dll" \
    -r:"$MANAGED/UnityEngine.dll" \
    -r:"$MANAGED/UnityEngine.CoreModule.dll" \
    -r:"$MANAGED/UnityEngine.InputLegacyModule.dll" \
    SFSProbe.cs

echo "== installing =="
mkdir -p "$GAME/Mods"
cp SFSProbe.dll "$GAME/Mods/SFSProbe/" 2>/dev/null || cp SFSProbe.dll "$GAME/Mods/"

echo "done. Launch SFS, enable 'SFS Probe' in the Mod Loader, wait ~10s on the menu."
echo "Output lands in: $GAME/Mods/SFSProbe/"
