#!/usr/bin/env bash
set -e

echo "=== Building Todo Bird Standalone Debian Package (.deb) ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
STAGING="${SCRIPT_DIR}/staging"
DEB_NAME="todo-bird_1.0.1_amd64.deb"

# Clean previous build
rm -rf "${STAGING}" "${SCRIPT_DIR}/${DEB_NAME}" "${REPO_ROOT}/${DEB_NAME}"
mkdir -p "${STAGING}/DEBIAN"
mkdir -p "${STAGING}/usr/bin"
mkdir -p "${STAGING}/usr/share/applications"
mkdir -p "${STAGING}/usr/share/icons/hicolor/512x512/apps"
mkdir -p "${STAGING}/usr/share/metainfo"
mkdir -p "${STAGING}/opt/todo-bird"

# 1. DEBIAN/control
cat << 'EOF' > "${STAGING}/DEBIAN/control"
Package: todo-bird
Version: 1.0.1
Architecture: amd64
Maintainer: Duvorixen <duvorixen@gmail.com>
Section: utils
Priority: optional
Depends: python3 (>= 3.10), libgl1, libegl1, libpulse0, libgssapi-krb5-2
Homepage: https://snapcraft.io/todo-bird
Description: Offline desktop personal assistant, task manager & Gantt scheduler
 TODO BIRD is a high-performance, offline-first personal assistant,
 task manager, and Gantt scheduler designed for focus, privacy,
 and data sovereignty. It runs 100% locally with zero cloud telemetry.
EOF

# 2. Desktop launcher and Icons
cp "${REPO_ROOT}/todo-bird-icon.png" "${STAGING}/usr/share/icons/hicolor/512x512/apps/todo-bird.png"
cp "${REPO_ROOT}/flatpak/io.github.duvorixen.TodoBird.metainfo.xml" "${STAGING}/usr/share/metainfo/todo-bird.metainfo.xml"

cat << 'EOF' > "${STAGING}/usr/share/applications/todo-bird.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=TODO BIRD
GenericName=Task Manager & Gantt Scheduler
Comment=Offline Desktop Personal Assistant & Task Manager
Exec=/usr/bin/todo-bird %U
Icon=todo-bird
Terminal=false
Categories=Utility;Office;ProjectManagement;
StartupWMClass=TODO BIRD
Keywords=todo;task;gantt;assistant;productivity;
StartupNotify=true
EOF

# 3. Wrapper script in /usr/bin
cat << 'EOF' > "${STAGING}/usr/bin/todo-bird"
#!/bin/sh
exec /opt/todo-bird/bin/python3 -m todo_bird_app.app "$@"
EOF
chmod 755 "${STAGING}/usr/bin/todo-bird"

# 4. Standalone bundled environment in /opt/todo-bird
echo "Creating isolated runtime environment in /opt/todo-bird..."
python3 -m venv "${STAGING}/opt/todo-bird"
"${STAGING}/opt/todo-bird/bin/pip" install --upgrade pip setuptools wheel
echo "Installing Todo Bird application and dependencies..."
"${STAGING}/opt/todo-bird/bin/pip" install "${REPO_ROOT}"

# Fix shebangs for /opt/todo-bird
echo "Fixing runtime shebangs..."
find "${STAGING}/opt/todo-bird/bin" -type f -exec sed -i "s|${STAGING}/opt/todo-bird|/opt/todo-bird|g" {} + 2>/dev/null || true

# Clean cache to save package size
find "${STAGING}/opt/todo-bird" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
rm -rf "${STAGING}/opt/todo-bird/share"

# 5. Fix permissions
find "${STAGING}" -type d -exec chmod 755 {} +
find "${STAGING}/usr/bin" -type f -exec chmod 755 {} +
chmod 644 "${STAGING}/DEBIAN/control"
chmod 644 "${STAGING}/usr/share/applications/todo-bird.desktop"
chmod 644 "${STAGING}/usr/share/icons/hicolor/512x512/apps/todo-bird.png"
chmod 644 "${STAGING}/usr/share/metainfo/todo-bird.metainfo.xml"

# 6. Build debian package
echo "Packaging ${DEB_NAME} with xz compression..."
dpkg-deb --build -Zxz "${STAGING}" "${REPO_ROOT}/${DEB_NAME}"

echo ""
echo "=== Debian Package Built Successfully! ==="
ls -lh "${REPO_ROOT}/${DEB_NAME}"
echo "You can test installing it with: sudo dpkg -i ${DEB_NAME}"
