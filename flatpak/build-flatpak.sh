#!/usr/bin/env bash
set -e

echo "=== Building Todo Bird Flatpak ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if ! command -v flatpak-builder &> /dev/null; then
    echo "flatpak-builder is not installed."
    echo "Installing flatpak-builder requires sudo apt install -y flatpak-builder"
    exit 1
fi

echo "Ensuring Flathub remote is configured..."
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

echo "Installing missing runtime/SDK dependencies if needed..."
flatpak install -y --user --noninteractive flathub org.kde.Platform//6.11 org.kde.Sdk//6.11

echo "Building and installing local Flatpak..."
flatpak-builder --user --install --force-clean --install-deps-from=flathub build-dir io.github.duvorixen.TodoBird.yaml

echo ""
echo "=== Build Complete! ==="
echo "You can now run Todo Bird Flatpak with:"
echo "flatpak run io.github.duvorixen.TodoBird"
