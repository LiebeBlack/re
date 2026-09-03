"""
Build Script - Script de compilación para Musik Player
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def clean_build_dirs():
    """Limpia directorios de compilación anteriores"""
    dirs_to_clean = ['build', 'dist']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"Limpiando directorio {dir_name}...")
            shutil.rmtree(dir_name)
            print(f"Directorio {dir_name} limpiado")


def install_pyinstaller():
    """Instala PyInstaller si no está instalado"""
    try:
        import PyInstaller
        print("PyInstaller ya está instalado")
    except ImportError:
        print("Instalando PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("PyInstaller instalado exitosamente")


def build_executable():
    """Construye el ejecutable usando PyInstaller"""
    print("Iniciando compilación...")
    
    # Comando de PyInstaller
    cmd = [
        "pyinstaller",
        "--name=MusikPlayer",
        "--windowed",
        "--onedir",
        "--icon=assets/icon.ico" if os.path.exists("assets/icon.ico") else "",
        "--add-data=src:src",
        "--hidden-import=customtkinter",
        "--hidden-import=pygame",
        "--hidden-import=mutagen",
        "--clean",
        "src/main.py"
    ]
    
    # Filtrar argumentos vacíos
    cmd = [arg for arg in cmd if arg]
    
    try:
        subprocess.check_call(cmd)
        print("Compilación exitosa!")
        print("El ejecutable se encuentra en: dist/MusikPlayer/MusikPlayer.exe")
        print("Para crear el instalador: makensis installer.nsi")
    except subprocess.CalledProcessError as e:
        print(f"Error durante la compilación: {e}")
        sys.exit(1)


def build_mac_app():
    """Construye la aplicación para macOS"""
    print("Iniciando compilación para macOS...")
    
    cmd = [
        "pyinstaller",
        "--name=MusikPlayer",
        "--windowed",
        "--onedir",
        "--icon=assets/icon.icns" if os.path.exists("assets/icon.icns") else "",
        "--add-data=src:src",
        "--hidden-import=customtkinter",
        "--hidden-import=pygame",
        "--hidden-import=mutagen",
        "--clean",
        "src/main.py"
    ]
    
    cmd = [arg for arg in cmd if arg]
    
    try:
        subprocess.check_call(cmd)
        print("Compilación exitosa!")
        print("El ejecutable se encuentra en: dist/MusikPlayer/MusikPlayer")
    except subprocess.CalledProcessError as e:
        print(f"Error durante la compilación: {e}")
        sys.exit(1)


def build_linux_app():
    """Construye la aplicación para Linux"""
    print("Iniciando compilación para Linux...")
    
    cmd = [
        "pyinstaller",
        "--name=musikplayer",
        "--windowed",
        "--onedir",
        "--icon=assets/icon.png" if os.path.exists("assets/icon.png") else "",
        "--add-data=src:src",
        "--hidden-import=customtkinter",
        "--hidden-import=pygame",
        "--hidden-import=mutagen",
        "--clean",
        "src/main.py"
    ]
    
    cmd = [arg for arg in cmd if arg]
    
    try:
        subprocess.check_call(cmd)
        print("Compilación exitosa!")
        print("El ejecutable se encuentra en: dist/musikplayer/musikplayer")
    except subprocess.CalledProcessError as e:
        print(f"Error durante la compilación: {e}")
        sys.exit(1)


def create_spec_file():
    """Crea un archivo .spec personalizado"""
    spec_content = """# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=[],
    datas=[('src', 'src')],
    hiddenimports=[
        'customtkinter',
        'pygame',
        'mutagen',
        'PIL',
        'PIL._tkinter_finder'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MusikPlayer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
)
"""
    
    with open("musikplayer.spec", "w") as f:
        f.write(spec_content)
    
    print("Archivo musikplayer.spec creado")


def main():
    """Función principal"""
    print("=== Musik Player Build Script ===")
    print()
    
    # Detectar sistema operativo
    platform = sys.platform
    
    if platform == "win32":
        print("Sistema detectado: Windows")
        build_choice = input("¿Desea compilar para Windows? (y/n): ").lower()
        if build_choice == 'y':
            clean_build_dirs()
            install_pyinstaller()
            build_executable()
    
    elif platform == "darwin":
        print("Sistema detectado: macOS")
        build_choice = input("¿Desea compilar para macOS? (y/n): ").lower()
        if build_choice == 'y':
            clean_build_dirs()
            install_pyinstaller()
            build_mac_app()
    
    elif platform.startswith("linux"):
        print("Sistema detectado: Linux")
        build_choice = input("¿Desea compilar para Linux? (y/n): ").lower()
        if build_choice == 'y':
            clean_build_dirs()
            install_pyinstaller()
            build_linux_app()
    
    else:
        print(f"Sistema no soportado: {platform}")
        sys.exit(1)
    
    print()
    print("=== Build completado ===")


if __name__ == "__main__":
    main()
