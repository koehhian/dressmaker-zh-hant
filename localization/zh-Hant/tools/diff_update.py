from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime
from pathlib import Path

from opencc import OpenCC

ROOT = Path(__file__).resolve().parents[1]
BACKUPS = ROOT / "backups"
MASTER = ROOT / "translations.csv"
REPORT_LIMIT = 50


def read_table(path: Path, value_column: str) -> dict[tuple[str, str], str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        if not {"table", "id", value_column} <= fields:
            raise SystemExit(f"{path} 缺少必要欄位：table, id, {value_column}")
        rows: dict[tuple[str, str], str] = {}
        for row in reader:
            key = (row["table"], row["id"])
            if key in rows:
                raise SystemExit(f"{path} 有重複字串：{key[0]} / {key[1]}")
            rows[key] = row[value_column]
    return rows


def write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def sort_key(key: tuple[str, str]) -> tuple[str, int]:
    return (key[0], int(key[1]))


def latest_snapshot() -> Path | None:
    files = sorted(BACKUPS.glob("source-*.csv"))
    return files[-1] if files else None


def snippet(text: str, limit: int = 240) -> str:
    text = text.replace("\r", " ").replace("\n", "\n")
    return text if len(text) <= limit else text[:limit] + "…"


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare a new game text extraction with the translation master.")
    parser.add_argument("--new-source", type=Path, required=True, help="Raw Simplified source CSV from extract_convert.py")
    parser.add_argument("--master", type=Path, default=MASTER, help="Current translations.csv")
    parser.add_argument("--old-source", type=Path, help="Previous source snapshot; defaults to newest backups/source-*.csv")
    parser.add_argument("--out-dir", type=Path, required=True, help="Folder for report.md, review.csv and draft.csv")
    args = parser.parse_args()

    new_source = read_table(args.new_source, "source")
    master = read_table(args.master, "text")
    old_source_path = args.old_source or latest_snapshot()
    if old_source_path is None:
        print("警告：找不到舊原文快照，只能判斷新增與移除，無法偵測原文變更。")
        old_source: dict[tuple[str, str], str] = {}
    else:
        old_source = read_table(old_source_path, "source")

    added = sorted((key for key in new_source if key not in master), key=sort_key)
    removed = sorted((key for key in master if key not in new_source), key=sort_key)
    changed = sorted(
        (
            key
            for key in new_source
            if key in master and key in old_source and old_source[key] != new_source[key]
        ),
        key=sort_key,
    )
    unverified = sorted(
        (key for key in new_source if key in master and old_source and key not in old_source),
        key=sort_key,
    )
    unchanged = len(new_source) - len(added) - len(changed) - len(unverified)

    converter = OpenCC("s2twp")
    # draft must match the new source exactly; removed IDs are archived in review.csv only.
    draft = {key: master[key] for key in new_source if key in master}
    for key in added:
        draft[key] = converter.convert(new_source[key])

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        out_dir / "draft.csv",
        ["table", "id", "text"],
        [
            {"table": table, "id": string_id, "text": draft[(table, string_id)]}
            for table, string_id in sorted(draft, key=sort_key)
        ],
    )

    review: list[dict[str, str]] = []
    for key in added:
        review.append(
            {
                "kind": "added",
                "table": key[0],
                "id": key[1],
                "old_source": "",
                "new_source": new_source[key],
                "existing_translation": "",
                "draft": draft[key],
            }
        )
    for key in changed:
        review.append(
            {
                "kind": "changed",
                "table": key[0],
                "id": key[1],
                "old_source": old_source[key],
                "new_source": new_source[key],
                "existing_translation": master[key],
                "draft": master[key],
            }
        )
    for key in unverified:
        review.append(
            {
                "kind": "unverified",
                "table": key[0],
                "id": key[1],
                "old_source": "",
                "new_source": new_source[key],
                "existing_translation": master[key],
                "draft": master[key],
            }
        )
    for key in removed:
        review.append(
            {
                "kind": "removed",
                "table": key[0],
                "id": key[1],
                "old_source": old_source.get(key, ""),
                "new_source": "",
                "existing_translation": master[key],
                "draft": master[key],
            }
        )
    write_csv(
        out_dir / "review.csv",
        ["kind", "table", "id", "old_source", "new_source", "existing_translation", "draft"],
        review,
    )

    lines = [
        "# Dressmaker 更新差異報告",
        "",
        f"- 產生時間：{datetime.now():%Y-%m-%d %H:%M}",
        f"- 新原文：`{args.new_source}`",
        f"- 舊原文快照：`{old_source_path}`" if old_source_path else "- 舊原文快照：無",
        f"- 翻譯主檔：`{args.master}`",
        f"- 新原文筆數：{len(new_source)}",
        f"- 翻譯主檔筆數：{len(master)}",
        "",
        f"新增 **{len(added)}**、原文變更 **{len(changed)}**、移除 **{len(removed)}**、原文無法比對 **{len(unverified)}**、未變更 **{unchanged}**。",
        "",
        "## 各語言表",
        "",
        "| 語言表 | 新原文 | 新增 | 原文變更 | 移除 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    tables = sorted({key[0] for key in new_source} | {key[0] for key in master})
    for table in tables:
        lines.append(
            f"| {table} | {sum(1 for key in new_source if key[0] == table)} | "
            f"{sum(1 for key in added if key[0] == table)} | "
            f"{sum(1 for key in changed if key[0] == table)} | "
            f"{sum(1 for key in removed if key[0] == table)} |"
        )

    def add_section(title: str, keys: list[tuple[str, str]], show_source: bool) -> None:
        lines.extend(["", f"## {title}（{len(keys)}）", ""])
        if not keys:
            lines.append("無。")
            return
        for key in keys[:REPORT_LIMIT]:
            lines.append(f"- `{key[0]} / {key[1]}`")
            if show_source:
                lines.append(f"  - 原文：{snippet(new_source[key])}")
                lines.append(f"  - 初稿：{snippet(draft[key])}")
            else:
                lines.append(f"  - 舊原文：{snippet(old_source.get(key, ''))}")
                lines.append(f"  - 新原文：{snippet(new_source.get(key, ''))}")
                lines.append(f"  - 現有譯文：{snippet(master[key])}")
        if len(keys) > REPORT_LIMIT:
            lines.append(f"- 其餘 {len(keys) - REPORT_LIMIT} 筆請見 `review.csv`。")

    add_section("新增字串", added, show_source=True)
    add_section("原文變更", changed, show_source=False)
    add_section("已移除字串", removed, show_source=False)
    if unverified:
        add_section("原文基準缺少、需人工確認", unverified, show_source=True)

    lines.extend(
        [
            "",
            "## 後續處理",
            "",
            "1. 以 `review.csv` 逐筆校對新增與原文變更的項目。",
            "2. 編輯 `draft.csv`，保留既有譯文、補上人工用語與格式標籤；它只包含本次原文的 ID。",
            "3. 確認無誤後，以 `draft.csv` 取代 `translations.csv`，再重建並測試工具。",
            "4. 將本次的 `source.csv` 保存為 `backups/source-YYYYMMDD.csv`，供下次比對。",
            "",
        ]
    )
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")

    source_copy = out_dir / "source.csv"
    if args.new_source.resolve() != source_copy.resolve():
        shutil.copyfile(args.new_source, source_copy)

    print(
        f"新增 {len(added)}、原文變更 {len(changed)}、移除 {len(removed)}、"
        f"原文無法比對 {len(unverified)}、未變更 {unchanged}"
    )
    print(f"報告：{out_dir / 'report.md'}")
    print(f"校對清單：{out_dir / 'review.csv'}")
    print(f"合併草稿：{out_dir / 'draft.csv'}")
    print(f"原文快照：{source_copy}")


if __name__ == "__main__":
    main()
