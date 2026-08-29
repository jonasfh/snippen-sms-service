import hashlib
import sys
from pathlib import Path

# Add scripts directory to path to import build_release module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from build_release import calculate_sha256, generate_checksums


def test_calculate_sha256(tmp_path: Path):
    test_file = tmp_path / "test.whl"
    content = b"sample wheel content for hashing"
    test_file.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()
    assert calculate_sha256(test_file) == expected


def test_generate_checksums(tmp_path: Path):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    file1 = dist_dir / "pkg-1.0.whl"
    file1.write_bytes(b"content 1")
    file2 = dist_dir / "pkg-1.0.tar.gz"
    file2.write_bytes(b"content 2")

    checksums_file = generate_checksums(dist_dir=dist_dir)
    assert checksums_file.exists()

    content = checksums_file.read_text(encoding="utf-8")
    lines = content.strip().splitlines()
    assert len(lines) == 2

    assert f"{hashlib.sha256(b'content 1').hexdigest()}  pkg-1.0.whl" in lines
    assert f"{hashlib.sha256(b'content 2').hexdigest()}  pkg-1.0.tar.gz" in lines
