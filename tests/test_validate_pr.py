"""Unit tests for the PR validator script."""

import sys
from pathlib import Path

import pytest
from packaging.version import Version

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import validate_pr


def test_get_current_version(tmp_path: Path):
    pkg_dir = tmp_path / "src" / "snippen_sms"
    pkg_dir.mkdir(parents=True)
    init_file = pkg_dir / "__init__.py"
    init_file.write_text('"""Doc"""\n__version__ = "0.2.1"\n', encoding="utf-8")

    version = validate_pr.get_current_version(tmp_path)
    assert version == "0.2.1"


def test_validate_semver_valid():
    v = validate_pr.validate_semver("1.2.3")
    assert isinstance(v, Version)
    assert str(v) == "1.2.3"


def test_validate_semver_invalid():
    with pytest.raises(ValueError, match="not a valid semantic version"):
        validate_pr.validate_semver("invalid-version")


def test_check_version_bump_no_tags():
    assert validate_pr.check_version_bump(Version("0.1.0"), (None, None)) is True


def test_check_version_bump_higher_version():
    latest_tag = ("v0.1.0", Version("0.1.0"))
    assert validate_pr.check_version_bump(Version("0.2.0"), latest_tag) is True
    assert validate_pr.check_version_bump(Version("0.1.1"), latest_tag) is True
    assert validate_pr.check_version_bump(Version("1.0.0"), latest_tag) is True


def test_check_version_bump_same_or_lower_version():
    latest_tag = ("v0.2.0", Version("0.2.0"))

    with pytest.raises(ValueError, match="strictly greater than latest release tag"):
        validate_pr.check_version_bump(Version("0.2.0"), latest_tag)

    with pytest.raises(ValueError, match="strictly greater than latest release tag"):
        validate_pr.check_version_bump(Version("0.1.9"), latest_tag)


def test_check_changelog_found(tmp_path: Path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [0.1.0] - 2026-08-29\n- Some note\n", encoding="utf-8")

    assert validate_pr.check_changelog(tmp_path, "0.1.0") is True


def test_check_changelog_missing_version(tmp_path: Path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [0.0.9] - 2026-08-28\n- Old note\n", encoding="utf-8")

    with pytest.raises(
        ValueError, match=r"CHANGELOG.md does not contain an entry for version \[0.1.0\]"
    ):
        validate_pr.check_changelog(tmp_path, "0.1.0")


def test_check_formatting_hygiene_clean(tmp_path: Path):
    test_file = tmp_path / "clean.md"
    test_file.write_text("# Header\n\nLine 1\n", encoding="utf-8")

    assert validate_pr.check_formatting_hygiene(tmp_path) is True


def test_check_formatting_hygiene_trailing_whitespace(tmp_path: Path):
    test_file = tmp_path / "dirty.md"
    test_file.write_text("# Header  \nLine 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="trailing whitespace detected"):
        validate_pr.check_formatting_hygiene(tmp_path)


def test_check_formatting_hygiene_duplicate_eof_newline(tmp_path: Path):
    test_file = tmp_path / "double_newline.py"
    test_file.write_text("x = 1\n\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate trailing newlines at end of file"):
        validate_pr.check_formatting_hygiene(tmp_path)
