"""Assemble release bundles with MPL license and documentation."""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import tarfile
import tempfile
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument('--platform', choices=['windows', 'linux'], required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
release = root / 'release'
release.mkdir(exist_ok=True)
binary = root / 'dist' / ('WarpCoil.exe' if args.platform == 'windows' else 'WarpCoil')
if not binary.is_file():
    raise SystemExit(f'Missing binary: {binary}')
name = 'WarpCoil-Windows-x64' if args.platform == 'windows' else 'WarpCoil-Linux-x64'
with tempfile.TemporaryDirectory() as tmp:
    folder = Path(tmp) / name
    folder.mkdir()
    shutil.copy2(binary, folder / binary.name)
    for document in ('BINARY_INSTALL.md', 'LICENSE', 'NOTICE.md', 'SECURITY.md'):
        shutil.copy2(root / document, folder / document)
    if args.platform == 'windows':
        dest = release / f'{name}.zip'
        with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for item in folder.iterdir():
                archive.write(item, arcname=f'{name}/{item.name}')
    else:
        dest = release / f'{name}.tar.gz'
        with tarfile.open(dest, 'w:gz') as archive:
            archive.add(folder, arcname=name, recursive=True)
print(f'Created: {dest} ({dest.stat().st_size:,} bytes)')
