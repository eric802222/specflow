"""lib.common.frontmatter 的單元測試：--- 子字串邊界情況、write_frontmatter_field 格式保留。"""

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.common import frontmatter as fm  # noqa: E402


def test_dash_substring_in_value_does_not_break_split():
    text = (
        "---\n"
        'id: PROP-1\n'
        'title: "before---after"\n'
        "impact_surface:\n"
        "  - x\n"
        "---\n"
        "\nbody\n"
    )
    data, body, error = fm.load_frontmatter_data(text)
    assert error is None, error
    assert data["title"] == "before---after"
    assert body.strip() == "body"


def test_horizontal_rule_in_body_is_left_alone():
    text = (
        "---\nid: PROP-1\ntitle: t\nimpact_surface:\n  - x\n---\n"
        "\n## section\n\n---\n\nmore text\n"
    )
    data, body, error = fm.load_frontmatter_data(text)
    assert error is None, error
    assert "---" in body  # body 裡原本就有的水平線不該被吃掉


def test_missing_frontmatter_reports_error():
    data, body, error = fm.load_frontmatter_data("no frontmatter here\n")
    assert data is None
    assert error is not None


def test_write_frontmatter_field_preserves_quotes_and_indent():
    text = (
        "---\n"
        'id: PROP-1\n'
        'title: "換貨折扣申請新增理由欄位"\n'
        "impact_surface:\n"
        "  - .spec/db/schema.dbml\n"
        "  - .spec/api/main.tsp\n"
        "status: draft\n"
        "refs:\n"
        "  - CP-153\n"
        "---\n"
        "\n## 3. 非目標 (Non-Goals)\n\n- ok\n"
    )
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "proposal.md"
        p.write_text(text, encoding="utf-8")
        fm.write_frontmatter_field(p, "status", "delivered")
        out = p.read_text(encoding="utf-8")

    assert 'title: "換貨折扣申請新增理由欄位"' in out  # 引號沒被吃掉
    assert "  - .spec/db/schema.dbml" in out  # 縮排沒被拿掉
    assert "  - CP-153" in out
    assert "status: delivered" in out
    assert "status: draft" not in out


def test_write_frontmatter_field_missing_key_raises():
    text = "---\nid: PROP-1\n---\nbody\n"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "proposal.md"
        p.write_text(text, encoding="utf-8")
        try:
            fm.write_frontmatter_field(p, "status", "delivered")
            assert False, "應該要 raise ValueError"
        except ValueError:
            pass
