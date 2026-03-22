#!/usr/bin/env bash
# ============================================================
# Lanthorn PSG v0.3.3 — Build Script
# Builds standalone executables for the current platform
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🕯️  Lanthorn PSG Build System"
echo "================================"

# Check for pyinstaller
if ! command -v pyinstaller &> /dev/null; then
    echo "📦 Installing PyInstaller..."
    pip install pyinstaller
fi

# Detect platform
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    PLATFORM="windows"
    EXT=".exe"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PLATFORM="linux"
    EXT=""
else
    PLATFORM="unknown"
    EXT=""
fi

echo "🖥️  Platform: $PLATFORM"
echo ""

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build/ dist/

# Build using spec file
echo "🔨 Building standalone executable..."
pyinstaller lanthorn_psg.spec --clean

# Check result
if [ -f "dist/LanthornPSG${EXT}" ]; then
    echo ""
    echo "📂 Copying supporting files to dist/..."
    cp -r presets/ dist/presets/
    cp ENGINE_SPEC.md dist/
    cp LICENSE dist/
    cp lanthorn.png dist/
    cp lanthornpsg.desktop dist/
    mkdir -p dist/projects
    cp Bazaar.csv dist/projects/
    cp Lanthorn.csv dist/projects/
    cp Iron_Waltz.csv dist/projects/

    # Linux desktop integration — install icon & .desktop entry
    if [[ "$PLATFORM" == "linux" ]]; then
        echo ""
        echo "🐧 Installing Linux desktop integration..."
        ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
        DESKTOP_DIR="$HOME/.local/share/applications"
        mkdir -p "$ICON_DIR" "$DESKTOP_DIR"
        cp lanthorn.png "$ICON_DIR/lanthorn.png"

        # Write .desktop with absolute path to binary
        FULL_EXE="$(realpath dist/LanthornPSG)"
        FULL_ICON="$(realpath dist/lanthorn.png)"
        sed "s|^Exec=.*|Exec=$FULL_EXE|;s|^Icon=.*|Icon=$FULL_ICON|" lanthornpsg.desktop > "$DESKTOP_DIR/lanthornpsg.desktop"
        chmod +x "$DESKTOP_DIR/lanthornpsg.desktop"
        echo "   ✅ Icon installed to $ICON_DIR"
        echo "   ✅ Desktop entry installed to $DESKTOP_DIR"
        # Refresh icon cache
        gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    fi

    SIZE=$(du -h "dist/LanthornPSG${EXT}" | cut -f1)
    echo ""
    echo "✅ Build complete!"
    echo "📁 Output: dist/LanthornPSG${EXT}"
    echo "📊 Size: $SIZE"
    echo ""
    echo "Contents of dist/:"
    ls -1 dist/
    echo ""
    echo "To run:  ./dist/LanthornPSG${EXT}"
else
    echo ""
    echo "❌ Build failed. Check the output above for errors."
    exit 1
fi
