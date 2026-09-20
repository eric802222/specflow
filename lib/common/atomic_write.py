"""原子寫入工具：寫到同目錄下的暫存檔案，成功後才用 os.replace() 換過去。

避免寫到一半被中斷（Ctrl-C、斷電、磁碟滿）時，目標檔案留下寫一半的殘骸——
這是設定檔管理工具的老問題，標準解法就是先寫暫存檔、再原子性地換過去，
中途失敗時目標檔案永遠維持在「換之前」或「換之後」兩種完整狀態的其中一種。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
