#!/usr/bin/env python3
"""PR Validator script.

Validates:
1. Valid semantic versioning in package.
2. Version is incremented from latest release tag in git.
3. CHANGELOG.md contains an entry for the current version.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from packaging.version import InvalidVersion, Version


def get_current_version(repo_root: Path) -> str:
    """Read __version__ from src/snippen_sms/__init__.py."""
    init_file = repo_root / "src" / "snippen_sms" / "__init__.py"
    if not init_file.exists():
        raise FileNotFoundError(f"Package init file not found at {init_file}")

    content = init_file.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        raise ValueError(f"Could not find __version__ string in {init_file}")
    return match.group(1).strip()


def validate_semver(version_str: str) -> Version:
    """Verify version string conforms to semantic versioning."""
    try:
        ver = Version(version_str)
    except InvalidVersion as exc:
        raise ValueError(f"Version '{version_str}' is not a valid semantic version.") from exc
    return ver


def get_latest_git_tag(repo_root: Path) -> tuple[str | None, Version | None]:
    """Retrieve the highest semantic version tag from git."""
    try:
        result = subprocess.run(
            ["git", "tag", "-l"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return None, None

    tags = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    valid_tagged_versions: list[tuple[str, Version]] = []

    for tag in tags:
        clean_tag = tag.removeprefix("v")
        try:
            v = Version(clean_tag)
            valid_tagged_versions.append((tag, v))
        except InvalidVersion:
            continue

    if not valid_tagged_versions:
        return None, None

    valid_tagged_versions.sort(key=lambda item: item[1])
    return valid_tagged_versions[-1]


def check_version_bump(
    current_version: Version, latest_tag: tuple[str | None, Version | None]
) -> bool:
    """Ensure current version is strictly greater than the latest release tag."""
    tag_name, tag_version = latest_tag
    if tag_version is None:
        print(f"ℹ️  No release tags found in repository. Initial version: {current_version}")
        return True

    if current_version <= tag_version:
        raise ValueError(
            f"Current version '{current_version}' must be strictly greater than latest release tag '{tag_name}' ({tag_version})."
        )

    print(f"✅ Version check passed: {current_version} > {tag_name} ({tag_version})")
    return True


def check_changelog(repo_root: Path, current_version_str: str, base_ref: str | None = None) -> bool:
    """Ensure CHANGELOG.md contains an entry for current version."""
    changelog_path = repo_root / "CHANGELOG.md"
    if not changelog_path.exists():
        raise FileNotFoundError(f"CHANGELOG.md not found at {changelog_path}")

    content = changelog_path.read_text(encoding="utf-8")
    version_pattern = rf"##\s*\[\s*{re.escape(current_version_str)}\s*\]"
    if not re.search(version_pattern, content):
        raise ValueError(
            f"CHANGELOG.md does not contain an entry for version [{current_version_str}]. "
            f"Please add '## [{current_version_str}] - YYYY-MM-DD' to CHANGELOG.md."
        )

    # If base_ref is specified, verify CHANGELOG.md was updated in diff
    if base_ref:
        try:
            diff_res = subprocess.run(
                ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if diff_res.returncode == 0:
                changed_files = [f.strip() for f in diff_res.stdout.splitlines()]
                if "CHANGELOG.md" not in changed_files:
                    print(
                        f"⚠️  Note: CHANGELOG.md has entry for [{current_version_str}] "
                        f"but was not changed in diff against {base_ref}."
                    )
        except (subprocess.SubprocessError, OSError) as e:
            print(f"⚠️  Could not run git diff against {base_ref}: {e}")

    print(f"✅ CHANGELOG.md contains entry for version [{current_version_str}]")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PR version and changelog")
    parser.add_argument(
        "--repo-root", type=Path, default=Path.cwd(), help="Path to repository root"
    )
    parser.add_argument(
        "--base", type=str, default=None, help="Base git ref for diff check (e.g. origin/main)"
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()

    try:
        version_str = get_current_version(repo_root)
        current_version = validate_semver(version_str)
        print(f"Current package version: {current_version}")

        latest_tag = get_latest_git_tag(repo_root)
        check_version_bump(current_version, latest_tag)

        check_changelog(repo_root, version_str, base_ref=args.base)

        print("🎉 All PR validation checks passed successfully!")
        return 0
    except (ValueError, FileNotFoundError, OSError) as exc:
        print(f"❌ Validation Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
