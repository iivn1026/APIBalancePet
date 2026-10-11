"""Build on Windows for an EXE, or on macOS for an app and portable ZIP."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import os


def mac_icon(source):
    """A padded Dock tile, with an undistorted head-and-shoulders portrait."""
    from PIL import Image, ImageDraw
    canvas = Image.new('RGBA', (512, 512))
    tile = Image.new('RGBA', (416, 416), '#EEEAF8')
    mask = Image.new('L', tile.size)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 415, 415), radius=92, fill=255)
    tile.putalpha(mask)
    canvas.alpha_composite(tile, (48, 48))
    portrait = source.convert('RGBA')
    side = min(portrait.width, portrait.height)
    left = (portrait.width-side)//2
    portrait = portrait.crop((left, 0, left+side, side))
    portrait = portrait.resize((352, 352), Image.Resampling.LANCZOS)
    canvas.alpha_composite(portrait, (80, 80))
    return canvas


def main():
    if sys.platform not in ('win32', 'darwin'):
        raise SystemExit('Build on Windows or macOS.')
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist-dir', default='dist')
    parser.add_argument('--work-dir', default='build')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    dist = Path(args.dist_dir).resolve()
    work = Path(args.work_dir).resolve()
    dist.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    mac = sys.platform == 'darwin'
    icon = root / 'pet.ico'
    if mac:
        from PIL import Image
        icon = work / 'pet.icns'
        with Image.open(root / 'avatar.png') as source:
            artwork = mac_icon(source)
            artwork.save(work / 'pet-icon-preview.png')
            artwork.save(icon, format='ICNS')
    command = [
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--onedir' if mac else '--onefile', '--windowed', '--name', 'APIBalancePet',
        '--icon', str(icon), '--add-data', str(root / 'avatar.png') + (':.' if mac else ';.'),
        '--distpath', str(dist), '--workpath', str(work),
        '--specpath', str(work),
    ]
    if mac:
        command += ['--osx-bundle-identifier', 'com.iivn.apibalancepet',
                    '--hidden-import', 'keyring.backends.macOS']
    command.append('mac_pet.py' if mac else 'balance_pet.py')
    subprocess.run(command, cwd=root, check=True,
                   env=dict(os.environ, PYINSTALLER_CONFIG_DIR=str(work / 'cache')))
    if mac:
        import platform
        exe = dist / ('APIBalancePet-macOS-' + platform.machine() + '.zip')
        if exe.exists():
            exe.unlink()
        subprocess.run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                        str(dist / 'APIBalancePet.app'), str(exe)], check=True)
    else:
        exe = dist / 'APIBalancePet.exe'
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    (dist / 'SHA256SUMS.txt').write_text(digest + '  ' + exe.name + '\n', encoding='utf-8')
    print('Built:', exe)


if __name__ == '__main__':
    main()
