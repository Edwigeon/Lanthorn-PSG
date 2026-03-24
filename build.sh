#!/usr/bin/env bash
# ============================================================
# Lanthorn PSG v0.3.3 — Linux/macOS Build Script
# Builds standalone executables with interactive menu
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VERSION="0.3.3"

echo ""
echo "  ========================================"
echo "    Lanthorn PSG v${VERSION} - Build System"
echo "  ========================================"
echo ""
echo "    1.  Portable          (single standalone binary)"
echo "    2.  AppImage/Install  (multi-file + desktop integration)"
echo "    3.  Both"
echo ""
read -rp "  Select option [1-3]: " BUILD_CHOICE

# ============================================================
# Shared setup
# ============================================================
check_python() {
    if ! command -v python3 &> /dev/null; then
        echo "  ERROR: Python 3 not found. Install python3 from your package manager."
        exit 1
    fi
}

install_deps() {
    echo ""
    echo "  Installing Python dependencies..."
    pip3 install --user -r requirements.txt
    pip3 install --user pyinstaller
}

# ============================================================
# Portable build (one-file)
# ============================================================
build_portable() {
    echo ""
    echo "  Cleaning build cache..."
    rm -rf build/

    echo "  Building portable executable (one-file)..."
    echo "  This may take a few minutes..."
    python3 -m PyInstaller lanthorn_psg_portable.spec --clean

    if [ ! -f "dist/LanthornPSG_Portable" ]; then
        echo ""
        echo "  ❌ Portable build failed - check errors above."
        exit 1
    fi

    chmod +x "dist/LanthornPSG_Portable"
    rm -rf build/

    SIZE=$(du -h "dist/LanthornPSG_Portable" | cut -f1)
    echo ""
    echo "  ============================================="
    echo "    PORTABLE BUILD COMPLETE!"
    echo "    Output: dist/LanthornPSG_Portable  ($SIZE)"
    echo "  ============================================="
}

# ============================================================
# Install build (multi-file + desktop integration)
# ============================================================
build_install() {
    echo ""
    echo "  Cleaning build cache..."
    rm -rf build/

    echo "  Building executable..."
    python3 -m PyInstaller lanthorn_psg.spec --clean

    if [ ! -d "dist/LanthornPSG" ] || [ ! -f "dist/LanthornPSG/LanthornPSG" ]; then
        echo ""
        echo "  ❌ Build failed - check errors above."
        exit 1
    fi

    # Copy supporting files into the dist folder
    echo "  Copying supporting files..."
    mkdir -p dist/LanthornPSG/projects
    cp -f Bazaar.csv     dist/LanthornPSG/projects/ 2>/dev/null || true
    cp -f Lanthorn.csv   dist/LanthornPSG/projects/ 2>/dev/null || true
    cp -f Iron_Waltz.csv dist/LanthornPSG/projects/ 2>/dev/null || true

    chmod +x "dist/LanthornPSG/LanthornPSG"
    rm -rf build/

    SIZE=$(du -sh "dist/LanthornPSG" | cut -f1)
    echo ""
    echo "  ============================================="
    echo "    BUILD COMPLETE!"
    echo "    Output: dist/LanthornPSG/  ($SIZE)"
    echo "  ============================================="
}

# ============================================================
# Desktop integration (Linux only)
# ============================================================
install_desktop() {
    if [[ "$OSTYPE" != "linux-gnu"* ]]; then
        return
    fi

    echo ""
    read -rp "  Install desktop shortcut & icon? [y/N]: " INSTALL_DESKTOP
    if [[ "$INSTALL_DESKTOP" != "y" && "$INSTALL_DESKTOP" != "Y" ]]; then
        return
    fi

    FULL_EXE="$(realpath dist/LanthornPSG/LanthornPSG)"
    FULL_ICON="$(realpath lanthorn.png)"

    ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
    DESKTOP_DIR="$HOME/.local/share/applications"
    mkdir -p "$ICON_DIR" "$DESKTOP_DIR"

    cp lanthorn.png "$ICON_DIR/lanthorn.png"
    sed "s|^Exec=.*|Exec=$FULL_EXE|;s|^Icon=.*|Icon=$FULL_ICON|" \
        lanthornpsg.desktop > "$DESKTOP_DIR/lanthornpsg.desktop"
    chmod +x "$DESKTOP_DIR/lanthornpsg.desktop"

    echo "    ✅ Icon installed to $ICON_DIR"
    echo "    ✅ Desktop entry installed to $DESKTOP_DIR"
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
}

# ============================================================
# Run selected option
# ============================================================
case "$BUILD_CHOICE" in
    1)
        check_python
        install_deps
        build_portable
        ;;
    2)
        check_python
        install_deps
        build_install
        install_desktop
        ;;
    3)
        check_python
        install_deps
        build_portable
        build_install
        install_desktop
        echo ""
        echo "  ============================================="
        echo "    ALL BUILDS COMPLETE!"
        echo "    Portable: dist/LanthornPSG_Portable"
        echo "    Install:  dist/LanthornPSG/"
        echo "  ============================================="
        ;;
    *)
        echo "  Invalid choice."
        exit 1
        ;;
esac

echo ""
echo "  Done."
