"""Install pinned development tools; portable binaries stay in ignored .tools/."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def install_binaries():
    manifest = json.loads((ROOT / "scripts/tool-versions.json").read_text(encoding="utf-8"))
    machine = {"x86_64": "amd64", "AMD64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine())
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "darwin"}.get(platform.system())
    key = f"{system}_{machine}"
    destination = ROOT / ".tools"
    destination.mkdir(exist_ok=True)
    for tool, config in manifest.items():
        asset = config["assets"].get(key)
        if asset is None:
            raise ValueError(f"Unsupported platform for {tool}: {key}")
        url = f"https://github.com/{config['repository']}/releases/download/v{config['version']}/{asset['name']}"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != asset["sha256"]:
            raise ValueError(f"SHA256 mismatch for {tool}; refusing installation")
        name = tool + (".exe" if system == "windows" else "")
        if asset["name"].endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                payload = archive.read(name)
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                member = archive.extractfile(name)
                if member is None:
                    raise ValueError(f"Missing binary: {name}")
                payload = member.read()
        output = destination / name
        output.write_bytes(payload)
        output.chmod(0o755)
        subprocess.run([str(output), "--version"], check=True, timeout=30)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binaries-only", action="store_true", help="Install only actionlint and gitleaks")
    args = parser.parse_args()
    install_binaries()
    if not args.binaries_only:
        for tool, version in (("cargo-deny", "0.20.2"), ("cargo-audit", "0.22.2")):
            subprocess.run(["cargo", "install", "--locked", tool, "--version", version], check=True)
        subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], check=True)
        python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), "-m", "pip", "install", "pre-commit==4.7.0"], check=True)
    print("Tools installed. See docs/development.md for hooks and checks.")


if __name__ == "__main__":
    main()
