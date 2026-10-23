"""
Build and package TODO BIRD into an official Microsoft Store MSIX package with resources.pri.
Designed to run on Windows (e.g. GitHub Actions windows-latest or local Windows machine).
"""
import sys
import os
import shutil
import subprocess
import urllib.request
import urllib.error
import json
from pathlib import Path

def build_msix():
    if sys.platform != 'win32':
        print(f"build_msix: Current platform is {sys.platform}. This script is designed for Windows SDK tools.")
        return False

    project_root = Path(__file__).resolve().parent.parent
    dist_dir = project_root / "dist" / "TodoBird"
    if not dist_dir.exists():
        print(f"Error: Dist directory {dist_dir} does not exist.")
        return False

    layout_dir = project_root / "msix_layout"
    if layout_dir.exists():
        shutil.rmtree(layout_dir)
    layout_dir.mkdir(parents=True, exist_ok=True)

    print(f"Copying files from {dist_dir} to {layout_dir}...")
    for item in dist_dir.iterdir():
        dest = layout_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    manifest_src = project_root / "windows" / "AppxManifest.xml"
    assets_src = project_root / "windows" / "msix_assets"

    shutil.copy2(manifest_src, layout_dir / "AppxManifest.xml")
    assets_dest = layout_dir / "Assets"
    assets_dest.mkdir(parents=True, exist_ok=True)
    for asset in assets_src.glob("*.png"):
        shutil.copy2(asset, assets_dest / asset.name)

    # Locate makepri.exe and makeappx.exe
    kits_base = Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
    makepri_path = None
    makeappx_path = None

    if kits_base.exists():
        for p in kits_base.rglob("makepri.exe"):
            if "x64" in str(p).lower():
                makepri_path = p
                break
        for p in kits_base.rglob("makeappx.exe"):
            if "x64" in str(p).lower():
                makeappx_path = p
                break

    if not makepri_path or not makeappx_path:
        print(f"Error: Could not find Windows SDK tools in {kits_base}")
        print(f"makepri: {makepri_path}, makeappx: {makeappx_path}")
        return False

    print(f"Found MakePri: {makepri_path}")
    print(f"Found MakeAppx: {makeappx_path}")

    # Generate priconfig.xml
    priconfig_path = layout_dir / "priconfig.xml"
    print("Generating priconfig.xml...")
    subprocess.run([
        str(makepri_path), "createconfig",
        "/cf", str(priconfig_path),
        "/dq", "en-US",
        "/o"
    ], check=True)

    # Generate resources.pri with package root and resource map DUVORIXEN.TODOBIRD
    pri_dest = layout_dir / "resources.pri"
    print(f"Generating {pri_dest}...")
    subprocess.run([
        str(makepri_path), "new",
        "/pr", str(layout_dir),
        "/cf", str(priconfig_path),
        "/of", str(pri_dest),
        "/in", "DUVORIXEN.TODOBIRD",
        "/o"
    ], check=True)

    if priconfig_path.exists():
        priconfig_path.unlink()

    # Package with MakeAppx
    out_msix = project_root / "dist" / "TodoBird-1.0.1.msix"
    out_msix.parent.mkdir(parents=True, exist_ok=True)
    print(f"Packing MSIX to {out_msix}...")
    subprocess.run([
        str(makeappx_path), "pack",
        "/d", str(layout_dir),
        "/p", str(out_msix),
        "/o"
    ], check=True)

    size_mb = round(out_msix.stat().st_size / (1024 * 1024), 2)
    print(f"SUCCESS: Created {out_msix} ({size_mb} MB)")

    # Also place a copy inside dist/TodoBird so it gets bundled into TodoBird-Portable-x64.zip
    portable_dest = dist_dir / "TodoBird-1.0.1.msix"
    try:
        shutil.copy2(out_msix, portable_dest)
        print(f"Copied MSIX to portable folder: {portable_dest}")
    except Exception as e:
        print(f"Notice: Could not copy to portable folder: {e}")


    # Upload to GitHub Release if token is available in environment
    token = os.environ.get("GITHUB_TOKEN")
    repo = "DUVORIXEN/TodoBird"
    tag = "v1.0.1"

    if token:
        try:
            print("Uploading MSIX to GitHub Releases...")
            # Get release id
            req = urllib.request.Request(
                f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
                headers={"Authorization": f"token {token}", "User-Agent": "TodoBird-MSIX-Packer"}
            )
            with urllib.request.urlopen(req) as resp:
                rel_info = json.loads(resp.read().decode())
                release_id = rel_info["id"]

            # Check if asset already exists and delete it
            for asset in rel_info.get("assets", []):
                if asset["name"] == "TodoBird-1.0.1.msix":
                    print(f"Deleting existing asset {asset['id']}...")
                    del_req = urllib.request.Request(
                        f"https://api.github.com/repos/{repo}/releases/assets/{asset['id']}",
                        headers={"Authorization": f"token {token}", "User-Agent": "TodoBird-MSIX-Packer"},
                        method="DELETE"
                    )
                    urllib.request.urlopen(del_req)

            # Upload new asset
            upload_url = f"https://uploads.github.com/repos/{repo}/releases/{release_id}/assets?name=TodoBird-1.0.1.msix"
            with open(out_msix, "rb") as f:
                msix_bytes = f.read()

            up_req = urllib.request.Request(
                upload_url,
                data=msix_bytes,
                headers={
                    "Authorization": f"token {token}",
                    "Content-Type": "application/octet-stream",
                    "User-Agent": "TodoBird-MSIX-Packer"
                },
                method="POST"
            )
            with urllib.request.urlopen(up_req) as resp:
                print("Successfully uploaded TodoBird-1.0.1.msix to GitHub Release v1.0.1!")

        except Exception as e:
            print(f"Notice: Release upload skipped or encountered error: {e}")

    return True

if __name__ == "__main__":
    build_msix()
