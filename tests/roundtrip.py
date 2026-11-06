"""Validate the public installer without changing the installed game/profile."""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--game', type=Path, required=True)
parser.add_argument('--exe', type=Path)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('patcher', repo / 'localization/zh-Hant/tools/patcher.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
rels = [p.BUNDLE_REL, p.IMAGE_BUNDLE_REL, p.CATALOG_REL, p.SHARED_ASSETS_REL, p.SHARED_RES_S_REL]
with tempfile.TemporaryDirectory(prefix='dressmaker-public-') as temp:
    work = Path(temp)
    game = work / 'game'
    game.mkdir()
    (game / 'Dressmaker.exe').write_bytes(b'Test fixture; not a game executable')
    hashes = {}
    for rel in rels:
        src = args.game / rel
        backup = src.with_name(src.name + '.zh-hant-backup')
        if backup.exists():
            src = backup
        target = game / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        hashes[str(rel)] = p.sha256(target)

    profile = work / 'profile'
    local = work / 'local'
    options = profile / 'AppData/LocalLow/Cozy Lives/Dressmaker/options.json'
    options.parent.mkdir(parents=True)
    options.write_text('{"language": "English", "public_test": true}', encoding='utf-8')
    original_options = options.read_bytes()
    p.APPDATA_GAME = options.parent
    p.OPTIONS = options
    p.TOOL_STATE_DIR = local / 'DressmakerZHant'
    p.OPTIONS_BACKUP = p.TOOL_STATE_DIR / 'options.json.original'
    p.OPTIONS_WAS_ABSENT = p.TOOL_STATE_DIR / 'options-was-absent'
    # Fixture is not running and has no executable. Keep the production guard unchanged.
    p.ensure_game_closed = lambda: None

    def action(mode):
        if args.exe:
            env = dict(os.environ, USERPROFILE=str(profile), LOCALAPPDATA=str(local), TEMP=str(work), TMP=str(work))
            result = subprocess.run([str(args.exe.resolve()), '--' + mode, str(game)], env=env, timeout=180, capture_output=True)
            log = work / 'DressmakerZHant-cli.log'
            message = log.read_text(encoding='utf-8') if log.exists() else result.stderr.decode(errors='replace')
            assert result.returncode == 0 and message.startswith('OK\n'), message
            print(message, flush=True)
        else:
            print(getattr(p, mode)(game), flush=True)

    action('install')
    assert p.sha256(game / p.BUNDLE_REL) != hashes[str(p.BUNDLE_REL)]
    assert p.sha256(game / p.SHARED_RES_S_REL) != hashes[str(p.SHARED_RES_S_REL)]
    installed = {str(rel): p.sha256(game / rel) for rel in rels}
    action('install')
    assert installed == {str(rel): p.sha256(game / rel) for rel in rels}, 'Repeat installation changed files'
    action('restore')
    for rel in rels:
        assert p.sha256(game / rel) == hashes[str(rel)], str(rel)
    assert options.read_bytes() == original_options, 'Language preference did not restore exactly'
    assert not list(game.rglob('*.zh-hant-*')), 'Backup/state residue remained'
    print('PASS: install, repeat install, title stream, exact file/profile restoration; isolated temporary fixture', flush=True)
