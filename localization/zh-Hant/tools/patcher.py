from __future__ import annotations

import csv
import gc
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
import zlib
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import UnityPy
from UnityPy.enums import ArchiveFlags, TextureFormat
from UnityPy.export import Texture2DConverter
from UnityPy.helpers import CompressionHelper
from UnityPy.streams.EndianBinaryReader import EndianBinaryReader

APP_ID = "4019220"
BUNDLE_REL = Path(
    "Dressmaker_Data/StreamingAssets/aa/StandaloneWindows64/"
    "localization-string-tables-chinese(simplified)(zh-hans)_assets_all.bundle"
)
IMAGE_BUNDLE_REL = Path(
    "Dressmaker_Data/StreamingAssets/aa/StandaloneWindows64/"
    "localization-assets-chinese(simplified)(zh-hans)_assets_all.bundle"
)
CATALOG_REL = Path("Dressmaker_Data/StreamingAssets/aa/catalog.bin")
SHARED_ASSETS_REL = Path("Dressmaker_Data/sharedassets1.assets")
SHARED_RES_S_REL = Path("Dressmaker_Data/sharedassets1.assets.resS")
SHARED_TEXTURE_NAME = "gamelogo_scn"
APPDATA_GAME = (
    Path(os.environ.get("USERPROFILE", str(Path.home())))
    / "AppData/LocalLow/Cozy Lives/Dressmaker"
)
OPTIONS = APPDATA_GAME / "options.json"
TOOL_STATE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DressmakerZHant"
OPTIONS_BACKUP = TOOL_STATE_DIR / "options.json.original"
OPTIONS_WAS_ABSENT = TOOL_STATE_DIR / "options-was-absent"
TRANSLATIONS = (
    Path(sys._MEIPASS) / "translations.csv"
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[1] / "translations.csv"
)
IMAGES_DIR = (
    Path(sys._MEIPASS) / "images"
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[1] / "images"
)
IMAGE_REPLACEMENTS = {
    "flyerFull_scn": "flyer_zh-Hant.png",
    "gamelogo_scn": "gamelogo_zh-Hant.png",
    "newspaperTitle_scn": "newspaperTitle_zh-Hant.png",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def default_game_path() -> Path | None:
    candidates = [Path(r"C:\Program Files (x86)\Steam\steamapps\common\Dressmaker")]
    steam_root = Path(r"C:\Program Files (x86)\Steam")
    vdf = steam_root / "steamapps/libraryfolders.vdf"
    if vdf.exists():
        values = re.findall(r'"path"\s*"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore"))
        candidates.extend(Path(value.replace("\\\\", "\\")) / "steamapps/common/Dressmaker" for value in values)
    for path in candidates:
        if (path / "Dressmaker.exe").is_file() and (path / BUNDLE_REL).is_file():
            return path
    return None


def load_translations() -> dict[str, dict[int, str]]:
    tables: dict[str, dict[int, str]] = {}
    with TRANSLATIONS.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            tables.setdefault(row["table"], {})[int(row["id"])] = row["text"]
    return tables


def decompress_block(data: bytes, size: int, flags: int) -> bytes:
    compression = flags & int(ArchiveFlags.CompressionTypeMask)
    try:
        function = CompressionHelper.DECOMPRESSION_MAP[compression]
    except KeyError as exc:
        raise RuntimeError(f"不支援的 AssetBundle 壓縮格式：{compression}") from exc
    return function(data, size)


def bundle_crc(path: Path) -> int:
    """Unity Addressables CRC: CRC-32 of the concatenated uncompressed blocks."""
    raw = path.read_bytes()
    reader = EndianBinaryReader(raw)
    signature = reader.read_string_to_null()
    if signature != "UnityFS":
        raise RuntimeError(f"不是預期的 UnityFS 檔：{path.name}")
    version = reader.read_u_int()
    reader.read_string_to_null()
    reader.read_string_to_null()
    reader.read_long()
    compressed_info_size = reader.read_u_int()
    uncompressed_info_size = reader.read_u_int()
    flags = reader.read_u_int()
    if version >= 7:
        reader.align_stream(16)
    archive_flags = ArchiveFlags(flags)
    position = reader.Position
    if archive_flags & ArchiveFlags.BlocksInfoAtTheEnd:
        reader.Position = reader.Length - compressed_info_size
        info_raw = reader.read_bytes(compressed_info_size)
        reader.Position = position
    else:
        info_raw = reader.read_bytes(compressed_info_size)
    info = decompress_block(info_raw, uncompressed_info_size, flags)
    info_reader = EndianBinaryReader(info)
    info_reader.read_bytes(16)
    block_count = info_reader.read_int()
    blocks = [
        (info_reader.read_u_int(), info_reader.read_u_int(), info_reader.read_u_short())
        for _ in range(block_count)
    ]
    node_count = info_reader.read_int()
    for _ in range(node_count):
        info_reader.read_long()
        info_reader.read_long()
        info_reader.read_u_int()
        info_reader.read_string_to_null()
    if archive_flags & ArchiveFlags.BlockInfoNeedPaddingAtStart:
        reader.align_stream(16)
    crc = 0
    for uncompressed_size, compressed_size, block_flags in blocks:
        chunk = reader.read_bytes(compressed_size)
        crc = zlib.crc32(decompress_block(chunk, uncompressed_size, block_flags), crc)
    return crc & 0xFFFFFFFF


def catalog_lookup(data: bytes | bytearray, filename: str) -> tuple[int, int, int]:
    name = filename.encode("ascii")
    if data.count(name) != 1:
        raise RuntimeError(f"Addressables 目錄中的記錄不是唯一一筆：{filename}")
    start = data.find(name)
    crc_offset = start + len(name) + 60
    if crc_offset + 8 > len(data):
        raise RuntimeError("Addressables 目錄格式與預期不同，已停止修改。")
    return (
        int.from_bytes(data[crc_offset:crc_offset + 4], "little"),
        int.from_bytes(data[crc_offset + 4:crc_offset + 8], "little"),
        crc_offset,
    )


def file_matches_catalog(catalog_data: bytes | bytearray, filename: str, path: Path) -> bool:
    try:
        stored_crc, stored_size, _ = catalog_lookup(catalog_data, filename)
    except RuntimeError:
        return False
    return stored_size == path.stat().st_size and stored_crc == bundle_crc(path)


def make_patched_bundle(
    source: Path, destination: Path, translations: dict[str, dict[int, str]]
) -> tuple[int, int, int]:
    env = UnityPy.load(str(source))
    expected = sum(map(len, translations.values()))
    found = 0
    tables = 0
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        table = obj.read()
        entries = translations.get(table.m_Name)
        if entries is None:
            continue
        tables += 1
        changed = 0
        for entry in table.m_TableData:
            text = entries.get(int(entry.m_Id))
            if text is None:
                continue
            entry.m_Localized = text
            found += 1
            changed += 1
        if changed != len(entries):
            raise RuntimeError(f"語言表 {table.m_Name} 的 ID 數不符：翻譯檔 {len(entries)}，遊戲檔 {changed}")
        table.save()
    if found != expected or tables != len(translations):
        raise RuntimeError(f"覆蓋率檢查失敗：找到 {found}/{expected} 筆、{tables}/{len(translations)} 個語言表")
    destination.write_bytes(env.file.save())

    verify = UnityPy.load(str(destination))
    verified: set[str] = set()
    for obj in verify.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        table = obj.read()
        expected_table = translations.get(table.m_Name)
        if expected_table is None:
            continue
        actual = {int(row.m_Id): row.m_Localized for row in table.m_TableData}
        for row_id, text in expected_table.items():
            if actual.get(row_id) != text:
                raise RuntimeError(f"輸出驗證失敗：{table.m_Name} / {row_id}")
        verified.add(table.m_Name)
    if len(verified) != len(translations):
        raise RuntimeError("輸出檔缺少語言表")
    crc = bundle_crc(destination)
    del obj, table, verify, env
    gc.collect()
    return found, tables, crc


def make_patched_images_bundle(source: Path, destination: Path) -> tuple[int, int]:
    from PIL import Image

    env = UnityPy.load(str(source))
    seen: set[str] = set()
    texture_updates: dict[int, tuple[object, Image.Image]] = {}
    for obj in env.objects:
        if obj.type.name != "Sprite":
            continue
        sprite = obj.read()
        image_name = IMAGE_REPLACEMENTS.get(sprite.m_Name)
        if image_name is None:
            continue
        texture_ptr = sprite.m_RD.texture
        texture_id = texture_ptr.path_id
        if texture_id in texture_updates:
            texture, atlas = texture_updates[texture_id]
            atlas = atlas.copy()
        else:
            texture = texture_ptr.deref_parse_as_object()
            atlas = texture.image.convert("RGBA")
        replacement = Image.open(IMAGES_DIR / image_name).convert("RGBA")
        rect = sprite.m_RD.textureRect
        x, y, width, height = map(round, (rect.x, rect.y, rect.width, rect.height))
        replacement = replacement.resize((width, height), Image.Resampling.LANCZOS)
        atlas.paste(replacement, (x, atlas.height - y - height))
        texture_updates[texture_id] = (texture, atlas)
        seen.add(sprite.m_Name)
    if seen != set(IMAGE_REPLACEMENTS):
        raise RuntimeError(f"圖片資產不完整：找到 {sorted(seen)}，預期 {sorted(IMAGE_REPLACEMENTS)}")
    for texture, atlas in texture_updates.values():
        texture.image = atlas
        texture.save()
    destination.write_bytes(env.file.save())
    verify = UnityPy.load(str(destination))
    verified: set[str] = set()
    for obj in verify.objects:
        if obj.type.name != "Sprite":
            continue
        sprite = obj.read()
        if sprite.m_Name in IMAGE_REPLACEMENTS:
            verified.add(sprite.m_Name)
    if verified != set(IMAGE_REPLACEMENTS):
        raise RuntimeError("圖片資產輸出驗證失敗。")
    crc = bundle_crc(destination)
    del obj, sprite, verify, env
    gc.collect()
    return len(seen), crc


def make_patched_shared_res(assets: Path, source: Path, destination: Path) -> tuple[int, int]:
    from PIL import Image

    env = UnityPy.load(str(assets))
    texture = None
    texture_id = None
    sprite = None
    for obj in env.objects:
        if obj.type.name == "Texture2D":
            candidate = obj.read()
            if candidate.m_Name == SHARED_TEXTURE_NAME:
                texture = candidate
                texture_id = obj.path_id
        elif obj.type.name == "Sprite":
            candidate = obj.read()
            if candidate.m_Name == SHARED_TEXTURE_NAME:
                sprite = candidate
    if texture is None or sprite is None:
        raise RuntimeError("找不到遊戲內建標題圖片，遊戲版本可能已改變。")
    if sprite.m_RD.texture.path_id != texture_id:
        raise RuntimeError("遊戲內建標題圖片的關聯與預期不同，已停止修改。")
    stream = texture.m_StreamData
    if Path(stream.path).name != SHARED_RES_S_REL.name:
        raise RuntimeError(f"遊戲內建標題圖片的資料檔與預期不同：{stream.path}")
    if int(texture.m_TextureFormat) != int(TextureFormat.DXT5) or int(texture.m_MipCount) != 1:
        raise RuntimeError("遊戲內建標題圖片的格式與預期不同，已停止修改。")
    offset = int(stream.offset)
    size = int(stream.size)
    data = source.read_bytes()
    if offset + size > len(data):
        raise RuntimeError("遊戲內建標題圖片的資料範圍超出檔案，已停止修改。")
    width = int(texture.m_Width)
    height = int(texture.m_Height)
    atlas = Texture2DConverter.parse_image_data(
        data[offset:offset + size], width, height, TextureFormat.DXT5, (0, 0, 0, 0), 0, flip=True
    ).convert("RGBA")
    rect = sprite.m_RD.textureRect
    x, y, rect_width, rect_height = map(round, (rect.x, rect.y, rect.width, rect.height))
    if x < 0 or y < 0 or x + rect_width > width or y + rect_height > height:
        raise RuntimeError("遊戲內建標題圖片的位置與預期不同，已停止修改。")
    replacement = Image.open(IMAGES_DIR / "gamelogo_zh-Hant.png").convert("RGBA")
    replacement = replacement.resize((rect_width, rect_height), Image.Resampling.LANCZOS)
    atlas.paste(replacement, (x, height - y - rect_height))
    encoded, encoded_format = Texture2DConverter.image_to_texture2d(atlas, TextureFormat.DXT5)
    if encoded_format != TextureFormat.DXT5 or len(encoded) != size:
        raise RuntimeError("無法重新編碼遊戲內建標題圖片。")
    output = bytearray(data)
    output[offset:offset + size] = encoded
    destination.write_bytes(output)
    if destination.read_bytes()[offset:offset + size] != encoded:
        raise RuntimeError("遊戲內建標題圖片輸出驗證失敗。")
    del env, texture, sprite
    gc.collect()
    return offset, size


def make_patched_catalog_multi(source: Path, destination: Path, bundles: dict[Path, tuple[int, int]]) -> dict[str, int]:
    data = bytearray(source.read_bytes())
    original_crcs: dict[str, int] = {}
    original_data = bytearray(data)
    for relative, (crc, bundle_size) in bundles.items():
        stored_crc, stored_size, crc_offset = catalog_lookup(data, relative.name)
        if stored_size != bundle_size:
            raise RuntimeError(f"Addressables 目錄的檔案大小與遊戲檔不符：{relative.name}")
        original_crcs[relative.name] = stored_crc
        data[crc_offset:crc_offset + 4] = crc.to_bytes(4, "little")
    destination.write_bytes(data)
    check = bytearray(destination.read_bytes())
    for relative, (crc, _) in bundles.items():
        crc_offset = check.find(relative.name.encode("ascii")) + len(relative.name) + 60
        if int.from_bytes(check[crc_offset:crc_offset + 4], "little") != crc:
            raise RuntimeError("Addressables CRC 輸出驗證失敗。")
        check[crc_offset:crc_offset + 4] = original_crcs[relative.name].to_bytes(4, "little")
    if check != original_data:
        raise RuntimeError("Addressables 目錄中除了 CRC 之外還有資料改變。")
    return original_crcs


def set_language_to_simplified() -> None:
    TOOL_STATE_DIR.mkdir(parents=True, exist_ok=True)
    if OPTIONS.exists() and not OPTIONS_BACKUP.exists() and not OPTIONS_WAS_ABSENT.exists():
        shutil.copy2(OPTIONS, OPTIONS_BACKUP)
    elif not OPTIONS.exists() and not OPTIONS_WAS_ABSENT.exists():
        OPTIONS_WAS_ABSENT.write_text("", encoding="utf-8")
    APPDATA_GAME.mkdir(parents=True, exist_ok=True)
    data = json.loads(OPTIONS.read_text(encoding="utf-8-sig")) if OPTIONS.exists() else {}
    data["preferredLanguage"] = "zh-Hans"
    temp = OPTIONS.with_suffix(".zh-hant.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, OPTIONS)


def restore_options() -> None:
    if OPTIONS_BACKUP.exists():
        shutil.copy2(OPTIONS_BACKUP, OPTIONS)
        OPTIONS_BACKUP.unlink()
    elif OPTIONS_WAS_ABSENT.exists():
        if OPTIONS.exists():
            OPTIONS.unlink()
        OPTIONS_WAS_ABSENT.unlink()


def ensure_game_closed() -> None:
    result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Dressmaker.exe"], capture_output=True, text=True)
    if "dressmaker.exe" in result.stdout.lower():
        raise RuntimeError("請先關閉 Dressmaker，再套用或還原繁中補丁。")


def require_backup(backup: Path, expected_hash: str | None, label: str) -> None:
    if not backup.exists() or sha256(backup) != expected_hash:
        raise RuntimeError(f"{label}備份不存在或校驗失敗，為保護遊戲檔案已停止操作。")


def install(game: Path) -> str:
    if not (game / "Dressmaker.exe").is_file():
        raise RuntimeError("選取的資料夾不是 Dressmaker 遊戲目錄。")
    ensure_game_closed()
    target = game / BUNDLE_REL
    image_target = game / IMAGE_BUNDLE_REL
    catalog = game / CATALOG_REL
    shared_assets = game / SHARED_ASSETS_REL
    shared_target = game / SHARED_RES_S_REL
    for path in (target, image_target, catalog, shared_assets, shared_target):
        if not path.is_file():
            raise RuntimeError(f"找不到遊戲檔案：{path.name}")
    backup = target.with_name(target.name + ".zh-hant-backup")
    image_backup = image_target.with_name(image_target.name + ".zh-hant-backup")
    catalog_backup = catalog.with_name(catalog.name + ".zh-hant-backup")
    shared_backup = shared_target.with_name(shared_target.name + ".zh-hant-backup")
    state = target.with_name(target.name + ".zh-hant-state.json")
    backups = (backup, image_backup, catalog_backup, shared_backup)
    prior_state = None
    if state.exists():
        prior_state = json.loads(state.read_text(encoding="utf-8"))
    elif any(path.exists() for path in backups):
        raise RuntimeError("發現既有備份但沒有工具狀態檔。請先手動確認備份狀態。")

    catalog_data = catalog.read_bytes()
    text_hash = sha256(target)
    image_hash = sha256(image_target)
    shared_hash = sha256(shared_target)
    shared_assets_hash = sha256(shared_assets)

    # 判斷每個檔案目前是原始檔還是舊補丁；遊戲更新可能只重設其中一部分。
    if prior_state is not None:
        if text_hash == prior_state.get("patched_sha256"):
            require_backup(backup, prior_state.get("original_sha256"), "文字")
            text_base, text_was_patched = backup, True
        elif text_hash == prior_state.get("original_sha256") or file_matches_catalog(
            catalog_data, target.name, target
        ):
            text_base, text_was_patched = target, False
        else:
            raise RuntimeError("遊戲文字檔在套用補丁後又被修改。請先驗證 Steam 遊戲檔案，再重新安裝。")

        if image_hash == prior_state.get("image_patched_sha256"):
            require_backup(image_backup, prior_state.get("image_original_sha256"), "圖片")
            image_base, image_was_patched = image_backup, True
        elif image_hash == prior_state.get("image_original_sha256") or file_matches_catalog(
            catalog_data, image_target.name, image_target
        ):
            image_base, image_was_patched = image_target, False
        else:
            raise RuntimeError("遊戲圖片包在套用補丁後又被修改。請先驗證 Steam 遊戲檔案，再重新安裝。")

        if "shared_patched_sha256" in prior_state:
            if shared_hash == prior_state.get("shared_patched_sha256"):
                require_backup(shared_backup, prior_state.get("shared_original_sha256"), "標題圖")
                shared_base, shared_was_patched = shared_backup, True
            elif shared_hash == prior_state.get("shared_original_sha256"):
                shared_base, shared_was_patched = shared_target, False
            elif shared_assets_hash != prior_state.get("shared_assets_sha256"):
                shared_base, shared_was_patched = shared_target, False
            else:
                raise RuntimeError("遊戲標題檔在套用補丁後又被修改。請先驗證 Steam 遊戲檔案，再重新安裝。")
        else:
            if shared_backup.exists():
                raise RuntimeError("發現標題圖備份但狀態檔不完整，已停止操作。")
            shared_base, shared_was_patched = shared_target, False
    else:
        if not file_matches_catalog(catalog_data, target.name, target) or not file_matches_catalog(
            catalog_data, image_target.name, image_target
        ):
            raise RuntimeError("遊戲檔案與 Addressables 目錄不符。請先驗證 Steam 遊戲檔案，再重新安裝。")
        text_base, text_was_patched = target, False
        image_base, image_was_patched = image_target, False
        shared_base, shared_was_patched = shared_target, False

    catalog_hash = sha256(catalog)
    if prior_state is not None and catalog_hash == prior_state.get("catalog_patched_sha256"):
        require_backup(catalog_backup, prior_state.get("catalog_original_sha256"), "Addressables 目錄")
        catalog_base, catalog_was_patched = catalog_backup, True
    else:
        catalog_matches_bases = (
            file_matches_catalog(catalog_data, target.name, text_base)
            and file_matches_catalog(catalog_data, image_target.name, image_base)
        )
        if catalog_matches_bases or (
            prior_state is not None and catalog_hash == prior_state.get("catalog_original_sha256")
        ):
            catalog_base, catalog_was_patched = catalog, False
        else:
            raise RuntimeError("Addressables 目錄與遊戲檔案不符。請先驗證 Steam 遊戲檔案，再重新安裝。")

    translations = load_translations()
    fd, temp_name = tempfile.mkstemp(prefix="dressmaker-zh-hant-", suffix=".bundle", dir=str(target.parent))
    os.close(fd)
    temp = Path(temp_name)
    fd, catalog_temp_name = tempfile.mkstemp(prefix="dressmaker-zh-hant-", suffix=".catalog", dir=str(catalog.parent))
    os.close(fd)
    catalog_temp = Path(catalog_temp_name)
    fd, image_temp_name = tempfile.mkstemp(prefix="dressmaker-zh-hant-", suffix=".bundle", dir=str(image_target.parent))
    os.close(fd)
    image_temp = Path(image_temp_name)
    fd, shared_temp_name = tempfile.mkstemp(prefix="dressmaker-zh-hant-", suffix=".resS", dir=str(shared_target.parent))
    os.close(fd)
    shared_temp = Path(shared_temp_name)
    state_temp = state.with_name(state.name + ".tmp")
    try:
        count, table_count, crc = make_patched_bundle(text_base, temp, translations)
        image_count, image_crc = make_patched_images_bundle(image_base, image_temp)
        shared_offset, shared_size = make_patched_shared_res(shared_assets, shared_base, shared_temp)
        original_crcs = make_patched_catalog_multi(catalog_base, catalog_temp, {
            BUNDLE_REL: (crc, text_base.stat().st_size),
            IMAGE_BUNDLE_REL: (image_crc, image_base.stat().st_size),
        })
        original_hash = sha256(text_base)
        patched_hash = sha256(temp)
        image_original_hash = sha256(image_base)
        image_patched_hash = sha256(image_temp)
        catalog_original_hash = sha256(catalog_base)
        catalog_patched_hash = sha256(catalog_temp)
        shared_original_hash = sha256(shared_base)
        shared_patched_hash = sha256(shared_temp)
    except Exception:
        for path in (temp, catalog_temp, image_temp, shared_temp, state_temp):
            path.unlink(missing_ok=True)
        raise
    rollback_target = target.with_name(target.name + ".zh-hant-rollback")
    rollback_image = image_target.with_name(image_target.name + ".zh-hant-rollback")
    rollback_catalog = catalog.with_name(catalog.name + ".zh-hant-rollback")
    rollback_shared = shared_target.with_name(shared_target.name + ".zh-hant-rollback")
    backup_created: list[Path] = []
    replaced: list[tuple[Path, Path]] = []
    state_written = False
    try:
        for backup_path, source, was_patched, label in (
            (backup, text_base, text_was_patched, "文字"),
            (image_backup, image_base, image_was_patched, "圖片"),
            (catalog_backup, catalog_base, catalog_was_patched, "Addressables 目錄"),
            (shared_backup, shared_base, shared_was_patched, "標題圖"),
        ):
            if was_patched:
                continue
            existed = backup_path.exists()
            shutil.copy2(source, backup_path)
            if not existed:
                backup_created.append(backup_path)
            if sha256(backup_path) != sha256(source):
                raise RuntimeError(f"{label}備份寫入驗證失敗。")
        pairs = (
            (target, rollback_target, temp),
            (image_target, rollback_image, image_temp),
            (catalog, rollback_catalog, catalog_temp),
            (shared_target, rollback_shared, shared_temp),
        )
        for current, rollback, _ in pairs:
            shutil.copy2(current, rollback)
        for current, rollback, patch in pairs:
            os.replace(patch, current)
            replaced.append((current, rollback))
        new_state = {
            "schema": 2,
            "appid": APP_ID,
            "original_sha256": original_hash,
            "patched_sha256": patched_hash,
            "image_original_sha256": image_original_hash,
            "image_patched_sha256": image_patched_hash,
            "catalog_original_sha256": catalog_original_hash,
            "catalog_patched_sha256": catalog_patched_hash,
            "catalog_original_crcs": original_crcs,
            "catalog_patched_crc": crc,
            "shared_original_sha256": shared_original_hash,
            "shared_patched_sha256": shared_patched_hash,
            "shared_assets_sha256": shared_assets_hash,
            "shared_texture_offset": shared_offset,
            "shared_texture_size": shared_size,
            "image_count": image_count,
            "translation_count": count,
            "table_count": table_count,
        }
        state_temp.write_text(json.dumps(new_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(state_temp, state)
        state_written = True
        set_language_to_simplified()
        return (
            f"已套用繁中：{count} 筆文字、{table_count} 個語言表、{image_count} 張圖片"
            f"及標題圖，並更新 CRC。請重新啟動遊戲。"
        )
    except Exception as exc:
        if not state_written:
            for current, rollback in reversed(replaced):
                try:
                    shutil.copy2(rollback, current)
                except OSError:
                    pass
            for backup_path in backup_created:
                try:
                    backup_path.unlink(missing_ok=True)
                except OSError:
                    pass
        if isinstance(exc, PermissionError):
            raise RuntimeError(
                "無法替換遊戲檔案。請確認遊戲已關閉；若資料夾權限不足，請以系統管理員身分重試。"
            ) from exc
        raise
    finally:
        for path in (
            temp, catalog_temp, image_temp, shared_temp, state_temp,
            rollback_target, rollback_image, rollback_catalog, rollback_shared,
        ):
            path.unlink(missing_ok=True)

def restore(game: Path) -> str:
    ensure_game_closed()
    target = game / BUNDLE_REL
    image_target = game / IMAGE_BUNDLE_REL
    catalog = game / CATALOG_REL
    shared_assets = game / SHARED_ASSETS_REL
    shared_target = game / SHARED_RES_S_REL
    backup = target.with_name(target.name + ".zh-hant-backup")
    image_backup = image_target.with_name(image_target.name + ".zh-hant-backup")
    catalog_backup = catalog.with_name(catalog.name + ".zh-hant-backup")
    shared_backup = shared_target.with_name(shared_target.name + ".zh-hant-backup")
    state = target.with_name(target.name + ".zh-hant-state.json")
    if not backup.exists() or not state.exists():
        raise RuntimeError("找不到這個工具建立的備份。")
    saved = json.loads(state.read_text(encoding="utf-8"))
    if sha256(target) != saved.get("patched_sha256"):
        raise RuntimeError("遊戲語言檔已被更新或修改。為避免覆蓋新版本，請先在 Steam 驗證遊戲檔案。")
    require_backup(backup, saved.get("original_sha256"), "文字")
    if saved.get("image_patched_sha256"):
        require_backup(image_backup, saved.get("image_original_sha256"), "圖片")
        if sha256(image_target) != saved.get("image_patched_sha256"):
            raise RuntimeError("遊戲圖片包已被更新或修改。為避免覆蓋遊戲更新，請先在 Steam 驗證遊戲檔案。")
    if saved.get("catalog_patched_sha256"):
        require_backup(catalog_backup, saved.get("catalog_original_sha256"), "Addressables 目錄")
        if sha256(catalog) != saved.get("catalog_patched_sha256"):
            raise RuntimeError("Addressables 目錄已被修改。為避免覆蓋遊戲更新，已停止還原。")
    if saved.get("shared_patched_sha256"):
        require_backup(shared_backup, saved.get("shared_original_sha256"), "標題圖")
        if sha256(shared_target) != saved.get("shared_patched_sha256"):
            raise RuntimeError("遊戲標題檔已被更新或修改。為避免覆蓋遊戲更新，請先在 Steam 驗證遊戲檔案。")
        if sha256(shared_assets) != saved.get("shared_assets_sha256"):
            raise RuntimeError("遊戲標題資產已被更新。請先在 Steam 驗證遊戲檔案，再還原。")
    gc.collect()
    pairs = [(target, backup)]
    if saved.get("image_patched_sha256"):
        pairs.append((image_target, image_backup))
    if saved.get("catalog_patched_sha256"):
        pairs.append((catalog, catalog_backup))
    if saved.get("shared_patched_sha256"):
        pairs.append((shared_target, shared_backup))
    temps: list[tuple[Path, Path, Path]] = []
    replaced: list[tuple[Path, Path]] = []
    try:
        for current, source_backup in pairs:
            restore_temp = current.with_name(current.name + ".zh-hant-restore")
            rollback = current.with_name(current.name + ".zh-hant-rollback")
            shutil.copy2(source_backup, restore_temp)
            shutil.copy2(current, rollback)
            temps.append((current, restore_temp, rollback))
        for current, restore_temp, rollback in temps:
            os.replace(restore_temp, current)
            replaced.append((current, rollback))
        for _, source_backup in pairs:
            source_backup.unlink(missing_ok=True)
        state.unlink()
        restore_options()
        return "繁中補丁已移除，原始文字、圖片、標題圖與遊戲語言設定已還原。"
    except Exception as exc:
        for current, rollback in reversed(replaced):
            try:
                shutil.copy2(rollback, current)
            except OSError:
                pass
        if isinstance(exc, PermissionError):
            raise RuntimeError(
                "無法還原遊戲檔案。請確認遊戲已關閉；若資料夾權限不足，請以系統管理員身分重試。"
            ) from exc
        raise
    finally:
        for _, restore_temp, rollback in temps:
            restore_temp.unlink(missing_ok=True)
            rollback.unlink(missing_ok=True)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Dressmaker 繁體中文化")
        self.geometry("590x220")
        self.resizable(False, False)
        default = default_game_path()
        self.game_var = tk.StringVar(value=str(default or ""))
        ttk.Label(self, text="遊戲安裝資料夾").pack(anchor="w", padx=18, pady=(18, 4))
        row = ttk.Frame(self)
        row.pack(fill="x", padx=18)
        ttk.Entry(row, textvariable=self.game_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="瀏覽…", command=self.browse).pack(side="left", padx=(8, 0))
        ttk.Label(self, text="安裝會備份原始文字、圖片與標題圖，並將遊戲語言切換為簡體中文（顯示繁體文字）。").pack(anchor="w", padx=18, pady=(12, 0))
        ttk.Label(self, text="支援 Steam Windows 版 Dressmaker。使用前請先關閉遊戲。", foreground="#555").pack(anchor="w", padx=18, pady=(4, 0))
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=18, pady=18)
        ttk.Button(buttons, text="一鍵繁體中文化", command=lambda: self.run_action(install)).pack(side="left")
        ttk.Button(buttons, text="還原原狀", command=lambda: self.run_action(restore)).pack(side="left", padx=10)
        ttk.Button(buttons, text="關閉", command=self.destroy).pack(side="right")

    def browse(self):
        path = filedialog.askdirectory(title="選取 Dressmaker 遊戲資料夾")
        if path:
            self.game_var.set(path)

    def run_action(self, action):
        try:
            result = action(Path(self.game_var.get().strip()))
            messagebox.showinfo("完成", result)
        except Exception as exc:
            messagebox.showerror("無法完成", str(exc))


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] in ("--install", "--restore"):
        action = install if sys.argv[1] == "--install" else restore
        log = Path(tempfile.gettempdir()) / "DressmakerZHant-cli.log"
        try:
            result = action(Path(sys.argv[2]))
        except Exception as exc:
            log.write_text(f"ERROR\n{exc}", encoding="utf-8")
            raise SystemExit(1)
        log.write_text(f"OK\n{result}", encoding="utf-8")
        raise SystemExit(0)
    App().mainloop()


if __name__ == "__main__":
    main()
