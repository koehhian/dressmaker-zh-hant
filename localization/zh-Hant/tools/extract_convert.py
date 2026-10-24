from __future__ import annotations

import argparse
import csv
from pathlib import Path

import UnityPy
from opencc import OpenCC

GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Dressmaker")
BUNDLE_REL = Path(
    "Dressmaker_Data/StreamingAssets/aa/StandaloneWindows64/"
    "localization-string-tables-chinese(simplified)(zh-hans)_assets_all.bundle"
)
LOCALE = Path(__file__).resolve().parents[1]
DEFAULT_OUT = LOCALE / "opencc-draft.csv"
MASTER = LOCALE / "translations.csv"


def extract(bundle: Path) -> list[tuple[str, str, str]]:
    env = UnityPy.load(str(bundle))
    rows: list[tuple[str, str, str]] = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        table = obj.read()
        table_name = table.m_Name
        for entry in table.m_TableData:
            rows.append((table_name, str(entry.m_Id), str(entry.m_Localized)))
    rows.sort(key=lambda row: (row[0], int(row[1])))
    return rows


def write_csv(path: Path, header: list[str], rows: list[tuple[str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract Simplified Chinese strings and write an OpenCC Traditional draft."
    )
    parser.add_argument("--game", type=Path, default=GAME, help="Dressmaker installation folder")
    parser.add_argument("--bundle", type=Path, help="Override the localization text bundle path")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Converted draft CSV path (default: opencc-draft.csv)",
    )
    parser.add_argument("--source-out", type=Path, help="Raw Simplified source CSV path for update diffing")
    args = parser.parse_args()

    if args.out.resolve() == MASTER.resolve():
        raise SystemExit("拒絕直接覆寫 translations.csv；請先輸出到更新工作區，校對後再升為主檔。")

    bundle = args.bundle or args.game / BUNDLE_REL
    if not bundle.is_file():
        raise SystemExit(f"找不到文字包：{bundle}")

    rows = extract(bundle)
    converter = OpenCC("s2twp")

    if args.source_out:
        write_csv(args.source_out, ["table", "id", "source"], rows)
        print(f"Wrote {len(rows)} source strings to {args.source_out}")

    draft = [(table, string_id, converter.convert(text)) for table, string_id, text in rows]
    write_csv(args.out, ["table", "id", "text"], draft)
    print(f"Wrote {len(rows)} converted strings to {args.out}")


if __name__ == "__main__":
    main()
