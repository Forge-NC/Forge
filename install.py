"""Install Forge — creates venv, installs all deps, creates desktop shortcut.

Run: python install.py

Users never need to manually pip install anything. This script handles it all.
"""

import os
import sys
import subprocess
import venv
from pathlib import Path


def main():
    project_dir = Path(__file__).parent.resolve()
    venv_dir = project_dir / ".venv"

    print("\n  Forge Installer")
    print("  " + "=" * 40)

    # 1. Create venv if it doesn't exist
    print("\n  [1/4] Setting up Python environment...")
    if not (venv_dir / "Scripts" / "python.exe").exists() and \
       not (venv_dir / "bin" / "python").exists():
        print("  [..] Creating virtual environment...")
        venv.create(str(venv_dir), with_pip=True)
        print("  [OK] Virtual environment created")
    else:
        print("  [OK] Virtual environment exists")

    # Find venv python
    if os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    if not venv_python.exists():
        print(f"  [ERROR] Venv python not found at {venv_python}")
        print("  Try deleting .venv/ and running install.py again")
        return

    # Upgrade pip
    print("  [..] Upgrading pip...")
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--upgrade",
         "pip", "setuptools", "wheel", "--quiet"],
        capture_output=True,
    )

    # 2. Install Forge with all dependencies (core + voice)
    print("\n  [2/4] Installing Forge + all dependencies...")
    try:
        result = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-e",
             f"{project_dir}[voice]", "--quiet"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print("  [OK] Forge + dependencies installed")
        else:
            # Try without voice deps if that failed
            print("  [..] Voice deps failed, installing core only...")
            subprocess.run(
                [str(venv_python), "-m", "pip", "install", "-e",
                 str(project_dir), "--quiet"],
                check=True,
            )
            print("  [OK] Forge installed (voice deps skipped)")
    except subprocess.CalledProcessError:
        print("  [WARN] pip install failed — try running manually:")
        print(f"    {venv_python} -m pip install -e \"{project_dir}[voice]\"")

    # 3. Verify installation
    print("\n  [3/4] Verifying installation...")
    try:
        result = subprocess.run(
            [str(venv_python), "-c",
             "import forge; print(forge.__version__)"],
            capture_output=True, text=True, check=True,
        )
        print(f"  [OK] Forge v{result.stdout.strip()}")
    except subprocess.CalledProcessError:
        print("  [WARN] Import check failed")

    # Check voice deps
    try:
        result = subprocess.run(
            [str(venv_python), "-c",
             "from forge.audio.stt import check_voice_deps; "
             "d = check_voice_deps(); "
             "print('ready' if d['ready'] else 'missing: ' + ', '.join(d['missing']))"],
            capture_output=True, text=True, check=True,
        )
        voice_status = result.stdout.strip()
        if voice_status == "ready":
            print("  [OK] Voice input: all deps ready")
        else:
            print(f"  [--] Voice input: {voice_status}")
    except subprocess.CalledProcessError:
        print("  [--] Voice input: not available")

    # 4. Create desktop shortcut
    print("\n  [4/4] Creating desktop shortcut...")
    desktop = Path.home() / "Desktop"

    if os.name == "nt":
        shortcut_path = desktop / "Forge NC.lnk"
        vbs_path = project_dir / "Forge.vbs"
        ico_path = project_dir / "forge" / "ui" / "assets" / "forge.ico"

        try:
            ico_line = ""
            if ico_path.exists():
                ico_line = f'\n$sc.IconLocation = "{ico_path}"'

            ps_script = f'''
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("{shortcut_path}")
$sc.TargetPath = "wscript.exe"
$sc.Arguments = '"{vbs_path}"'
$sc.WorkingDirectory = "{project_dir}"
$sc.Description = "Forge Neural Cortex - Local AI Coding Assistant"{ico_line}
$sc.Save()
'''
            subprocess.run(
                ["powershell", "-Command", ps_script],
                check=True, capture_output=True,
            )
            print(f"  [OK] Desktop shortcut: {shortcut_path}")
        except Exception as e:
            print(f"  [WARN] Could not create shortcut: {e}")
            print(f"  You can manually create a shortcut to: {vbs_path}")
    else:
        desktop_file = desktop / "Forge NC.desktop"
        content = f"""[Desktop Entry]
Type=Application
Name=Forge NC
Comment=Local AI Coding Assistant
Exec=bash "{project_dir / 'forge.sh'}"
Terminal=true
Categories=Development;
StartupNotify=true
"""
        try:
            desktop_file.write_text(content)
            desktop_file.chmod(0o755)
            print(f"  [OK] Desktop shortcut: {desktop_file}")
        except Exception as e:
            print(f"  [WARN] Could not create shortcut: {e}")
            print(f"  You can run Forge with: {project_dir / 'forge.sh'}")

    print("\n  " + "=" * 40)
    print("  Installation complete!")
    print(f"  Project:  {project_dir}")
    print(f"  Venv:     {venv_dir}")
    print("  Launch:   Double-click 'Forge NC' on your desktop")
    print()


if __name__ == "__main__":
    main()
