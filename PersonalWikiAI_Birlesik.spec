# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('app/static', 'app/static')]
binaries = []
hiddenimports = ['aiosqlite']
hiddenimports += collect_submodules('chromadb')
tmp_ret = collect_all('pymupdf')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pymupdf4llm')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pydantic')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pydantic_core')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# collect_all('torch'): pyinstaller-hooks-contrib'deki hook-torch.py
# torch'un DLL'lerini zaten topluyor, ama bunu ACIKCA da cagirmak,
# olasi eksik-toplama ihtimaline karsi bir GUVENLIK AGI - torch'un
# TUM veri/binary/gizli-import'larinin PAKETE dahil oldugundan emin
# oluyoruz. Asil DLL YUKLEME hatasi (shm.dll) icin asagidaki
# runtime_hooks'a bkz.
tmp_ret = collect_all('torch')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['paket_baslat.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    # pyi_rth_torch_dll.py: torch/lib/ altindaki DLL'lerin (orn.
    # shm.dll) birbirini/bagimliliklarini BULABILMESI icin, uygulama
    # baslarken _internal/ ve _internal/torch/lib/ klasorlerini
    # Windows'un DLL arama yoluna ACIKCA ekler - bkz. o dosyadaki
    # detayli aciklama.
    runtime_hooks=['pyi_rth_torch_dll.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Asistan',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Asistan',
)
