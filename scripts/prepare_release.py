"""Validate a release tag and archive only the validated executable and license."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def validate_tag(tag, version):
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", tag) or tag != "v" + version:
        raise ValueError("Release tag must be v<Cargo.toml package.version> (SemVer)")


def main():
    from check import binary, require_implemented
    require_implemented()
    ref = os.environ.get("GITHUB_REF", "")
    if ref.startswith("refs/tags/"):
        manifest = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
        validate_tag(ref.removeprefix("refs/tags/"), manifest["package"]["version"])
        subprocess.run(["git", "merge-base", "--is-ancestor", "HEAD", "origin/main"], cwd=ROOT, check=True)
    output = ROOT / ".test-results" / "release"
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"webhook-lab-{os.environ['RUNNER_OS']}-{os.environ['RUNNER_ARCH']}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.write(binary("release"), binary("release").name)
        package.write(ROOT / "LICENSE", "LICENSE")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(digest + "  " + archive.name + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
