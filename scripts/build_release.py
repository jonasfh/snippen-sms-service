"""Release packaging and checksum generation utility for Snippen SMS Service."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path


def calculate_sha256(file_path: Path) -> str:
    """Compute the SHA-256 hexadecimal digest of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


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
        description="Build Snippen SMS release artifacts and checksums."
    )
    parser.add_argument(
        "--dist-dir",
        type=str,
        default="dist",
        help="Target distribution output directory (default: dist)",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not clean dist directory before build",
    )
    args = parser.parse_args()

    dist_path = Path(args.dist_dir)
    try:
        build_distributions(dist_dir=dist_path, clean=not args.no_clean)
        generate_checksums(dist_dir=dist_path)
        print("\n✅ Release artifacts successfully built and hashed.")
        return 0
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        print(f"\n❌ Build failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
