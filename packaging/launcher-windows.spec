# -*- mode: python ; coding: utf-8 -*-
import glob
import os

block_cipher = None
# 在 build/obf 目录下执行 pyinstaller，以当前工作目录为根
root = os.path.abspath(os.curdir)


def _data(src, dest):
    return (os.path.join(root, src), dest)


datas = [
    _data('static/dy_ab.js', 'static'),
    _data('static/dy_live_sign.js', 'static'),
    _data('static/login.js', 'static'),
    _data('static/Live_pb2.py', 'static'),
    _data('static/Response_pb2.py', 'static'),
    _data('static/Request_pb2.py', 'static'),
    _data('config/redis.conf', 'config'),
]

for runtime_dir in glob.glob(os.path.join(root, 'pyarmor_runtime_*')):
    datas.append((runtime_dir, os.path.basename(runtime_dir)))

jsrsasign = os.path.join(root, 'node_modules', 'jsrsasign')
if os.path.isdir(jsrsasign):
    datas.append((jsrsasign, 'node_modules/jsrsasign'))

hiddenimports = [
    'redis',
    'websocket',
    'google.protobuf',
    'protobuf_to_dict',
    'execjs',
    'bs4',
    'static.Live_pb2',
    'static.Response_pb2',
    'static.Request_pb2',
    'dy_live.live_manager',
    'dy_live.server',
    'utils.redis_bootstrap',
    'utils.redis_util',
    'utils.app_bootstrap',
    'utils.launcher_gui',
    'utils.log_redirect',
    'utils.redis_config',
    'utils.dy_util',
    'builder.auth',
    'builder.header',
    'builder.params',
    'builder.proto',
    'dy_apis.douyin_api',
]

runtime_hook = os.path.join(root, 'dy_live', 'runtime_hook.py')
if not os.path.isfile(runtime_hook):
    runtime_hook = os.path.join(root, '..', '..', 'dy_live', 'runtime_hook.py')

a = Analysis(
    [os.path.join(root, 'launcher.py')],
    pathex=[root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[runtime_hook] if os.path.isfile(runtime_hook) else [],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DouyinLive',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DouyinLive',
)
