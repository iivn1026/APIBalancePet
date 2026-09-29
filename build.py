"""Build a portable Windows executable without machine-specific path literals."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys


def main():
    if sys.platform != 'win32':
        raise SystemExit('Build on Windows to produce the Windows executable.')
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist-dir', default='dist')
    parser.add_argument('--work-dir', default='build')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    dist = Path(args.dist_dir).resolve()
    work = Path(args.work_dir).resolve()
    dist.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--onefile', '--windowed', '--name', 'APIBalancePet',
        '--icon', 'pet.ico', '--add-data', 'avatar.png;.',
        '--distpath', str(dist), '--workpath', str(work),
        '--specpath', '.', 'balance_pet.py',
    ], cwd=root, check=True)
    exe = dist / 'APIBalancePet.exe'
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    (dist / 'SHA256SUMS.txt').write_text(digest + '  APIBalancePet.exe\n', encoding='utf-8')
    print('Built:', exe)


if __name__ == '__main__':
    main()
