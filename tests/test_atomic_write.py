"""lib.common.atomic_write 的單元測試。"""

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.common.atomic_write import atomic_write_text  # noqa: E402


def test_writes_content_correctly():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "file.txt"
        atomic_write_text(p, "hello world\n")
        assert p.read_text(encoding="utf-8") == "hello world\n"


def test_overwrites_existing_file():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "file.txt"
        p.write_text("old content", encoding="utf-8")
        atomic_write_text(p, "new content")
        assert p.read_text(encoding="utf-8") == "new content"


def test_no_leftover_tmp_files_after_success():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "file.txt"
        atomic_write_text(p, "content")
        remaining = list(Path(d).iterdir())
        assert remaining == [p]  # 只留下目標檔案，沒有暫存檔殘留
