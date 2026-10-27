"""Build the portable Windows x64 v0.1 release with Windows Python."""
import hashlib
import importlib.metadata
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'XiaoMan_theCalicoCat'
VERSION = 'v0.1'


def main():
    if sys.platform != 'win32' or platform.machine().upper() not in ('AMD64', 'X86_64'):
        raise SystemExit('Build using 64-bit Windows Python.')
    command = [
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--onedir', '--windowed', '--noupx', '--name', NAME,
        '--paths', str(ROOT), '--specpath', str(ROOT / 'build'),
        '--workpath', str(ROOT / 'build' / 'pyinstaller'),
        '--distpath', str(ROOT / 'dist'),
        '--add-data', str(ROOT / 'output/imagegen') + ':output/imagegen',
        '--add-data', str(ROOT / 'assets') + ':assets',
        str(ROOT / 'tools/frozen_entry.py'),
    ]
    if '--package-only' not in sys.argv:
        subprocess.run(command, cwd=ROOT, check=True)
    bundle = ROOT / 'dist' / NAME
    licenses = bundle / 'licenses'
    licenses.mkdir(exist_ok=True)
    shutil.copy2(Path(sys.base_prefix) / 'LICENSE.txt', licenses / 'Python-LICENSE.txt')
    shutil.copytree(ROOT / 'release-notices', licenses, dirs_exist_ok=True)
    versions = {}
    for package in ('PySide6', 'PySide6_Essentials', 'shiboken6', 'PyInstaller'):
        distribution = importlib.metadata.distribution(package)
        versions[package] = distribution.version
        for file in distribution.files or []:
            if '/licenses/' in str(file).replace('\\', '/') or file.name in ('LICENSE', 'COPYING.txt'):
                source = Path(distribution.locate_file(file))
                target = licenses / package / file.name
                target.parent.mkdir(exist_ok=True)
                shutil.copy2(source, target)
    (bundle / 'BUILD-INFO.txt').write_text(
        f'{NAME} {VERSION}\nPython {platform.python_version()}\n' +
        '\n'.join(f'{key} {value}' for key, value in versions.items()) + '\n', encoding='utf-8')
    shutil.copy2(ROOT / '使用说明.txt', bundle / '使用说明.txt')
    (bundle / '开始使用.txt').write_text(
        '小满 · 三花桌宠 v0.1\n\n'
        '适用 Windows 11 x64。完整解压 ZIP 后，双击 XiaoMan_theCalicoCat.exe。\n'
        '无需安装 Python，无需联网。请保留同目录下的 _internal 文件夹。\n'
        '左键拖动抱起猫咪；右键猫咪或托盘图标调整行为或退出。\n'
        '详细操作见 使用说明.txt。\n\n'
        '本版本未进行代码签名，Windows 可能提示未知发布者。\n'
        '项目：https://github.com/skylinenzo/XiaoMan_theCalicoCat\n', encoding='utf-8-sig')
    release = ROOT / 'release'
    release.mkdir(exist_ok=True)
    archive = release / f'{NAME}-{VERSION}-windows-x64.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for file in sorted(bundle.rglob('*')):
            if file.is_file():
                output.write(file, file.relative_to(bundle.parent))
    with archive.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    (release / 'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(f'Built {archive} ({archive.stat().st_size / 1024**2:.1f} MiB)')


if __name__ == '__main__':
    main()
