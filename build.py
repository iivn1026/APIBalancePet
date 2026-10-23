"""Build on Windows for an EXE, or on macOS for an app and portable ZIP."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import os
import plistlib
import tempfile


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
    parser.add_argument('--dmg', action='store_true', help='Also create a macOS drag-to-install DMG')
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
        # The bundled Python runtime loads this trust policy in SSLContext.__new__.
        # Include it beside ssl.py so frozen HTTPS retains the runtime policy.
        import ssl
        trust_policy = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
        if trust_policy.is_file():
            command += ['--add-data', str(trust_policy) + ':.']
        command += ['--osx-bundle-identifier', 'com.iivn.apibalancepet',
                    '--hidden-import', 'keyring.backends.macOS']
    command.append('mac_pet.py' if mac else 'balance_pet.py')
    subprocess.run(command, cwd=root, check=True,
                   env=dict(os.environ, PYINSTALLER_CONFIG_DIR=str(work / 'cache')))
    if mac:
        import platform
        app = dist / 'APIBalancePet.app'
        plist_path = app / 'Contents' / 'Info.plist'
        plist = plistlib.loads(plist_path.read_bytes())
        plist.update(LSUIElement=True, CFBundleShortVersionString='1.2.1',
                     CFBundleVersion='1.2.1', NSHighResolutionCapable=True)
        plist_path.write_bytes(plistlib.dumps(plist))
        subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(app)], check=True)
        exe = dist / ('APIBalancePet-macOS-' + platform.machine() + '.zip')
        if exe.exists():
            exe.unlink()
        subprocess.run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                        str(dist / 'APIBalancePet.app'), str(exe)], check=True)
        if args.dmg:
            dmg = dist / ('APIBalancePet-v1.2.1-macOS-' + platform.machine() + '.dmg')
            with tempfile.TemporaryDirectory(prefix='dmg-', dir=work) as folder:
                stage = Path(folder)
                subprocess.run(['/usr/bin/ditto', str(app), str(stage / app.name)], check=True)
                (stage / 'Applications').symlink_to('/Applications')
                (stage / 'LICENSE.txt').write_text((root / 'LICENSE').read_text(), encoding='utf-8')
                (stage / '安装说明.txt').write_text(
                    'APIBalancePet 1.2.1 菜单栏版\n\n将应用拖入 Applications 后启动。'
                    '点击屏幕右上角的钱包图标查看余额，在“管理连接”中添加多个 API 地址和密钥。'
                    '\n本应用常驻菜单栏，不显示 Dock 图标或桌面角色。'
                    '\n适用 macOS 14+，架构：' + platform.machine() +
                    '\n未做 Apple Developer ID 签名或公证。\n', encoding='utf-8')
                subprocess.run(['/usr/bin/hdiutil', 'create', '-volname', 'APIBalancePet',
                                '-srcfolder', str(stage), '-ov', '-format', 'UDZO', str(dmg)], check=True)
    else:
        exe = dist / 'APIBalancePet.exe'
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    (dist / 'SHA256SUMS.txt').write_text(digest + '  ' + exe.name + '\n', encoding='utf-8')
    if mac and args.dmg:
        with (dist / 'SHA256SUMS.txt').open('a', encoding='utf-8') as checksum:
            checksum.write(hashlib.sha256(dmg.read_bytes()).hexdigest() + '  ' + dmg.name + '\n')
    print('Built:', exe)


if __name__ == '__main__':
    main()
