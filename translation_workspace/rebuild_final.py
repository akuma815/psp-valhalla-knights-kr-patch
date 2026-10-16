"""Rebuild release-current payloads from source, preserving its frozen ISO layout."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

import pycdlib
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = '6f62cbe6fcab9a35146245a85025725782ad060a2b1f47a400e1477f9b445360'
FINAL = 'eaeeee9f4b7cc587ed870a33d9b3cb6fdd18d424566b05e805641756eb147db9'
ZIP_SHA = '2cd0819acf3fb67331e557cdf10757eadf2380db358998dc64d9179359248c70'
PATCH_SHA = '9544dfcc0b4a62087f9282f20823524e3b0baf3f2188f25bbc668dc4dee10b67'
FONT_SHA = '8eae3d64050446b2094c62b64a8793bc3a163d1881edddf88993210fd915f700'
URL = 'https://github.com/akuma815/psp-valhalla-knights-kr-patch/releases/download/release-current/psp-valhalla-knights-kr-patch-release-current.zip'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def merge_final_tables(workspace):
    """Only the 17 named tables are authoritative; keep significant whitespace."""
    path = workspace / 'total_translation.csv'
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    overrides = {}
    tables = sorted(workspace.glob('tbldata_tbldata_extracted_*.csv'))
    require(len(tables) == 17, 'Expected 17 individual translation tables')
    for table in tables:
        with table.open(encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                if row.get('Translated', '').strip():
                    key = (row['File Path'], row['Index'])
                    require(key not in overrides, 'Duplicate individual table row')
                    overrides[key] = row['Translated']
    for row in rows:
        key = (row['File Path'], row['Index'])
        if key in overrides:
            row['Translated'] = overrides[key]
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-iso', required=True, type=Path)
    p.add_argument('--font', required=True, type=Path)
    p.add_argument('--gimconv-dir', required=True, type=Path)
    p.add_argument('--xdelta', required=True, type=Path)
    p.add_argument('--release-zip', type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    a = p.parse_args()
    require(a.source_iso.stat().st_size == 687964160 and sha(a.source_iso) == SOURCE, 'Unsupported original ISO')
    require(sha(a.font) == FONT_SHA, 'Expected the pinned LeeSeoyun font')
    require((a.gimconv_dir / 'GimConv.exe').is_file(), 'GimConv directory missing')
    require(a.xdelta.is_file(), 'xdelta3 executable missing')
    require(not a.output_dir.resolve().is_relative_to((ROOT / 'translation_workspace').resolve()), 'Output must be outside translation_workspace')
    a.output_dir.mkdir(parents=True, exist_ok=False)
    out = a.output_dir.resolve()
    project = out / 'project'
    workspace = project / 'translation_workspace'
    # Work in a separate snapshot; never rewrite the checkout's translation ledgers.
    shutil.copytree(ROOT / 'translation_workspace', workspace,
                    ignore=shutil.ignore_patterns('backups', '__pycache__', '*.bin', '*.res', '*.gim', '*.png', '*.pyc'))
    shutil.copytree(a.gimconv_dir, project / 'tool/GimConv')
    shutil.copy2(a.font, project / 'font.ttf')
    archive = a.release_zip
    if archive is None:
        archive = out / 'public_release.zip'
        with urllib.request.urlopen(URL) as source, archive.open('wb') as dest:
            shutil.copyfileobj(source, dest)
    require(sha(archive) == ZIP_SHA, 'Public release ZIP hash differs')
    with zipfile.ZipFile(archive) as z:
        require(z.testzip() is None, 'Public release CRC failure')
        names = [n for n in z.namelist() if n.endswith('.xdelta')]
        require(len(names) == 1, 'Expected one release patch')
        patch = out / 'bootstrap.xdelta'
        patch.write_bytes(z.read(names[0]))
    require(sha(patch) == PATCH_SHA, 'Public patch hash differs')
    layout = out / 'frozen_layout.iso'
    subprocess.run([str(a.xdelta.resolve()), '-d', '-s', str(a.source_iso.resolve()), str(patch), str(layout)], check=True)
    require(sha(layout) == FINAL, 'Public patch application differs')
    original = pycdlib.PyCdlib()
    original.open(str(a.source_iso.resolve()))
    extracted = 0
    for root, _, files in original.walk(iso_path='/'):
        for name in files:
            iso_path = root.rstrip('/') + '/' + name
            dest = project / 'Original' / iso_path.lstrip('/')
            require(dest.resolve().is_relative_to((project / 'Original').resolve()), 'Unsafe ISO filename')
            dest.parent.mkdir(parents=True, exist_ok=True)
            original.get_file_from_iso(str(dest), iso_path=iso_path)
            extracted += 1
    original.close()
    shutil.copytree(project / 'Original/PSP_GAME', project / 'PSP_GAME')
    shutil.copy2(project / 'Original/UMD_DATA.BIN', project / 'UMD_DATA.BIN')
    sys.path.insert(0, str(workspace))
    from in_place_patcher import parse_res_header
    raw = (project / 'Original/PSP_GAME/USRDIR/Resource/global/global.res').read_bytes()
    record = next(r for r in parse_res_header(raw) if r['name'] == 'font')
    gim = workspace / 'font_real.gim'
    gim.write_bytes(raw[record['offset']:record['offset'] + record['size']])
    rgba_path = workspace / 'font_rgba.png'
    tool = project / 'tool/GimConv/GimConv.exe'
    subprocess.run([str(tool), str(gim), '-o', str(rgba_path)], cwd=tool.parent, check=True)
    rgba = Image.open(rgba_path).convert('RGBA')
    alpha = list(rgba.getchannel('A').get_flattened_data())
    levels = sorted(set(alpha))
    require(len(levels) == 16, 'Expected 16 original font alpha levels')
    lookup = {v: k for k, v in enumerate(levels)}
    indexed = Image.new('P', rgba.size)
    indexed.putpalette([255] * 48 + [0] * 720)
    indexed.putdata([lookup[v] for v in alpha])
    indexed.save(workspace / 'font_real.png', transparency=bytes(levels) + bytes(240))
    merge_final_tables(workspace)
    env = dict(os.environ, VK_FINAL_RELEASE_PROFILE='1', PYTHONDONTWRITEBYTECODE='1')
    for script in ['extract_r02_battle_ui.py', 'build_full_translation.py']:
        subprocess.run([sys.executable, '-X', 'utf8', '-B', str(workspace / script)], cwd=project, env=env, check=True)
    # All file payloads must be independently rebuilt or copied from the original.
    # Only the released ISO's filesystem layout and padding are frozen inputs.
    iso = pycdlib.PyCdlib()
    iso.open(str(layout))
    extents = []
    for root, _, files in iso.walk(iso_path='/'):
        for name in files:
            ip = root.rstrip('/') + '/' + name
            payload = (project / ip.lstrip('/')).read_bytes()
            reference = io.BytesIO()
            iso.get_file_from_iso_fp(reference, iso_path=ip)
            require(payload == reference.getvalue(), 'Rebuilt payload differs: ' + ip)
            rec = iso.get_record(iso_path=ip)
            extents.append((rec.extent_location() * 2048, project / ip.lstrip('/')))
    iso.close()
    require(len(extents) == extracted == 3125, 'Logical file count differs')
    final = out / 'Valhalla_Knights_Korean_Rebuilt.iso'
    shutil.copy2(layout, final)
    with final.open('r+b') as f:
        for offset, path in extents:
            f.seek(offset)
            f.write(path.read_bytes())
    require(final.stat().st_size == 602060800 and sha(final) == FINAL, 'Final ISO hash differs')
    require(sha(a.source_iso) == SOURCE, 'Original ISO changed')
    report = {'status': 'PASS', 'logicalFilesVerified': len(extents), 'finalSHA256': FINAL,
              'textAndFontRebuiltFromSource': True, 'layoutRecoveredFromPinnedPublicRelease': True,
              'originalUnchanged': True, 'runtime': 'not newly performed'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
