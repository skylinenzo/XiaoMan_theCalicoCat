"""Extract the actual ZIP, then run its EXE without source/Python search paths."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    archive = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else
               ROOT / 'release/XiaoMan_theCalicoCat-v0.1.1-windows-x64.zip')
    with tempfile.TemporaryDirectory(prefix='xiaoman-release-') as temporary:
        folder = Path(temporary)
        with zipfile.ZipFile(archive) as bundle:
            if bundle.testzip() is not None:
                raise RuntimeError('ZIP integrity check failed')
            bundle.extractall(folder)
        executable = folder / 'XiaoMan_theCalicoCat/XiaoMan_theCalicoCat.exe'
        report = folder / 'smoke.json'
        env = dict(os.environ)
        for key in list(env):
            if key.upper().startswith(('PYTHON', 'QT_')):
                del env[key]
        env['PATH'] = os.path.join(os.environ['SystemRoot'], 'System32')
        subprocess.run([str(executable), '--smoke-test', str(report)],
                       cwd=folder, env=env, check=True, timeout=90)
        result = json.loads(report.read_text(encoding='utf-8'))
        if not result.get('ok') or not result.get('frozen') or not result.get('eye_annotations'):
            raise RuntimeError(result)
        (ROOT / 'release/verification.json').write_text(
            json.dumps(result, indent=2), encoding='utf-8')
        print('PASS extracted Windows EXE:', result)


if __name__ == '__main__':
    main()
