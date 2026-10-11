"""Release packaging and checksum generation utility for Snippen SMS Service."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Files or patterns that must never be packaged into production firmware bundles
EXCLUDED_PATTERNS = {
    "config.json",
    "config_local.py",
    "config.local.py",
}


def calculate_sha256(file_path: Path) -> str:
    """Compute the SHA-256 hexadecimal digest of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def resolve_version(repo_root: Path | None = None, fallback_dir: Path | None = None) -> str:
    """Resolve project version from package or firmware version file."""
    search_dirs = [repo_root] if repo_root is not None else [Path("."), fallback_dir]
    for base in search_dirs:
        if base is None:
            continue

        fw_version = base / "firmware" / "version.py"
        if fw_version.exists():
            match = re.search(
                r'FIRMWARE_VERSION\s*=\s*["\']([^"\']+)["\']',
                fw_version.read_text(encoding="utf-8"),
            )
            if match:
                return match.group(1).strip()

        pkg_init = base / "src" / "snippen_sms" / "__init__.py"
        if pkg_init.exists():
            match = re.search(
                r'__version__\s*=\s*["\']([^"\']+)["\']', pkg_init.read_text(encoding="utf-8")
            )
            if match:
                return match.group(1).strip()

    return "0.0.0"


def is_production_firmware_file(file_path: Path) -> bool:
    """Determine whether a file in firmware/ is an included production firmware file.

    Excludes sensitive files (e.g. config.json, config_local.py), diagnostic/test
    scripts (e.g. test_*.py), template files (*.example.*), and temp/hidden files.
    """
    name = file_path.name
    if not file_path.is_file():
        return False
    if name.startswith("."):
        return False
    if not name.endswith(".py"):
        return False
    if name in EXCLUDED_PATTERNS:
        return False
    lower_name = name.lower()
    if lower_name.startswith("test_") or lower_name.endswith("_test.py"):
        return False
    if "local" in lower_name:
        return False
    return "example" not in lower_name


def build_firmware_bundle(
    firmware_dir: Path = Path("firmware"),
    dist_dir: Path = Path("dist"),
    version: str | None = None,
    tag: str | None = None,
) -> Path:
    """Package production firmware files into a unified JSON bundle for OTA deployment.

    Constructs a JSON file with metadata (version, tag, created_at, file count,
    total byte size) and an alphabetically sorted mapping of files containing their
    individual SHA-256 checksum, size in bytes, and UTF-8 content.
    """
    if not firmware_dir.exists():
        raise FileNotFoundError(f"Firmware directory not found at {firmware_dir}")

    resolved_version = version or resolve_version(fallback_dir=firmware_dir.parent)
    resolved_tag = tag or f"v{resolved_version}"
    created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    dist_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = dist_dir / "firmware_bundle.json"

    production_files: list[Path] = [
        p
        for p in sorted(firmware_dir.iterdir(), key=lambda p: p.name)
        if is_production_firmware_file(p)
    ]

    if not production_files:
        raise ValueError(f"No production firmware files found in {firmware_dir}")

    files_dict: dict[str, dict[str, Any]] = {}
    total_bytes = 0

    for file_path in production_files:
        raw_bytes = file_path.read_bytes()
        content = raw_bytes.decode("utf-8")
        file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        file_size = len(raw_bytes)
        total_bytes += file_size

        files_dict[file_path.name] = {
            "sha256": file_sha256,
            "size": file_size,
            "content": content,
        }

    bundle: dict[str, Any] = {
        "version": resolved_version,
        "tag": resolved_tag,
        "created_at": created_at,
        "total_files": len(files_dict),
        "total_bytes": total_bytes,
        "files": files_dict,
    }

    bundle_json = json.dumps(bundle, indent=2, ensure_ascii=False) + "\n"
    bundle_path.write_text(bundle_json, encoding="utf-8")

    print(
        f"Generated firmware bundle: {bundle_path} "
        f"({len(files_dict)} files, {total_bytes} bytes, total bundle {len(bundle_json.encode('utf-8'))} bytes)"
    )
    return bundle_path


def build_distributions(dist_dir: Path = Path("dist"), clean: bool = True) -> list[Path]:
    """Build Python wheel and sdist packages using build (PEP 517/518)."""
    if clean and dist_dir.exists():
        shutil.rmtree(dist_dir)

    dist_dir.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "-m", "build", "--outdir", str(dist_dir)]
    print(f"Building package distributions into {dist_dir}...")
    result = subprocess.run(cmd, check=True)
    if result.returncode != 0:
        raise RuntimeError("Package build failed.")

    artifacts = [p for p in dist_dir.iterdir() if p.suffix in (".whl", ".gz")]
    if not artifacts:
        raise RuntimeError("No package distribution artifacts produced in dist/")

    return artifacts


def generate_checksums(dist_dir: Path = Path("dist")) -> Path:
    """Generate SHA-256 checksums file (checksums.txt) for all artifacts in dist/."""
    checksums_file = dist_dir / "checksums.txt"
    entries: list[str] = []

    for file_path in sorted(dist_dir.iterdir()):
        if file_path.name == "checksums.txt" or file_path.is_dir():
            continue
        digest = calculate_sha256(file_path)
        entries.append(f"{digest}  {file_path.name}")
        print(f"  {digest}  {file_path.name}")

    checksums_file.write_text("\n".join(entries) + "\n", encoding="utf-8")
    print(f"\nGenerated checksums file: {checksums_file}")
    return checksums_file


def main() -> int:
    """CLI entry point for release packaging."""
    parser = argparse.ArgumentParser(
        description="Build Snippen SMS release artifacts, firmware bundle, and checksums."
    )
    parser.add_argument(
        "--dist-dir",
        type=str,
        default="dist",
        help="Target distribution output directory (default: dist)",
    )
    parser.add_argument(
        "--firmware-dir",
        type=str,
        default="firmware",
        help="Path to firmware directory (default: firmware)",
    )
    parser.add_argument(
        "--version",
        type=str,
        default=None,
        help="Release version string (e.g. 0.31.20)",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="Release git tag string (e.g. v0.31.20)",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not clean dist directory before build",
    )
    parser.add_argument(
        "--skip-firmware",
        action="store_true",
        help="Skip building firmware bundle",
    )
    parser.add_argument(
        "--skip-package",
        action="store_true",
        help="Skip building Python wheel and sdist distributions",
    )
    args = parser.parse_args()

    dist_path = Path(args.dist_dir)
    firmware_path = Path(args.firmware_dir)
    try:
        clean_dist = not args.no_clean
        if clean_dist and dist_path.exists():
            shutil.rmtree(dist_path)
        dist_path.mkdir(parents=True, exist_ok=True)

        if not args.skip_package:
            build_distributions(dist_dir=dist_path, clean=False)

        if not args.skip_firmware:
            build_firmware_bundle(
                firmware_dir=firmware_path,
                dist_dir=dist_path,
                version=args.version,
                tag=args.tag,
            )

        generate_checksums(dist_dir=dist_path)
        print("\n✅ Release artifacts and firmware bundle successfully built and hashed.")
        return 0
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        print(f"\n❌ Build failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
