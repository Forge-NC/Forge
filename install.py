"""Install Forge -- creates venv, installs deps, sets up Ollama, configures telemetry.

Usage:
    python install.py
    python install.py --token TOKEN --label "name-gpu"
    python install.py --no-interactive
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import venv
import webbrowser
from pathlib import Path


# ---------------------------------------------------------------------------
# Phase 1 -- Prerequisites
# ---------------------------------------------------------------------------

def _check_prerequisites():
    """Phase 1: Check Python (3.10+), git, Ollama.  Returns status dict."""
    status = {
        "python": False,
        "git": False,
        "ollama_installed": False,
        "ollama_running": False,
    }

    # Python version
    v = sys.version_info
    status["python"] = v >= (3, 10)
    print(f"  [{'OK' if status['python'] else '!!'}] Python {v.major}.{v.minor}.{v.micro}"
          + ("" if status["python"] else " (3.10+ required)"))

    # Git
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
        status["git"] = r.returncode == 0
        if status["git"]:
            print(f"  [OK] {r.stdout.strip()}")
        else:
            print("  [!!] git not working")
    except FileNotFoundError:
        print("  [!!] git not found -- install from https://git-scm.com")

    # Ollama installed?
    try:
        subprocess.run(["ollama", "--version"], capture_output=True, text=True, timeout=5)
        status["ollama_installed"] = True
    except FileNotFoundError:
        pass

    # Ollama running?
    if status["ollama_installed"]:
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:11434/", timeout=3)
            status["ollama_running"] = True
            print("  [OK] Ollama installed and running")
        except Exception:
            print("  [OK] Ollama installed (not running)")
    else:
        print("  [!!] Ollama not found -- install from https://ollama.com")

    return status


# ---------------------------------------------------------------------------
# Phase 2 -- Virtual environment
# ---------------------------------------------------------------------------

def _create_venv(project_dir, venv_dir):
    """Phase 2: Create .venv if needed, upgrade pip."""
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
        sys.exit(1)

    # Upgrade pip
    print("  [..] Upgrading pip...")
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--upgrade",
         "pip", "setuptools", "wheel", "--quiet"],
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Phase 3 -- Dependencies
# ---------------------------------------------------------------------------

def _install_deps(project_dir, venv_pip):
    """Phase 3: Install Forge + dependencies (try voice extras, fall back to core)."""
    # Resolve venv python from the pip path
    if os.name == "nt":
        venv_python = venv_pip.parent / "python.exe"
    else:
        venv_python = venv_pip.parent / "python"

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
        print("  [WARN] pip install failed -- try running manually:")
        print(f"    {venv_python} -m pip install -e \"{project_dir}[voice]\"")

    # Verify import
    try:
        result = subprocess.run(
            [str(venv_python), "-c",
             "import forge; print(forge.__version__)"],
            capture_output=True, text=True, check=True,
        )
        print(f"  [OK] Forge v{result.stdout.strip()}")
    except subprocess.CalledProcessError:
        print("  [WARN] Import check failed")


# ---------------------------------------------------------------------------
# Phase 4 -- Ollama setup
# ---------------------------------------------------------------------------

def _setup_ollama(status, interactive):
    """Phase 4: Offer to install/start Ollama and pull default model."""
    if not status["ollama_installed"] and interactive:
        print("\n  Ollama is required to run AI models locally.")
        try:
            choice = input("  Open Ollama download page? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = "n"
        if choice != "n":
            if os.name == "nt":
                webbrowser.open("https://ollama.com/download/windows")
            elif sys.platform == "darwin":
                webbrowser.open("https://ollama.com/download/mac")
            else:
                print("\n  Run: curl -fsSL https://ollama.com/install.sh | sh")
            print("  Install Ollama, then re-run install.py")
            return
    elif not status["ollama_installed"]:
        print("  [!!] Ollama not installed -- install from https://ollama.com")
        return

    if status["ollama_installed"] and not status["ollama_running"]:
        print("  Starting Ollama...")
        try:
            extra = {}
            if os.name == "nt":
                extra["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **extra,
            )
            for _ in range(10):
                time.sleep(1)
                try:
                    import urllib.request
                    urllib.request.urlopen("http://localhost:11434/", timeout=2)
                    status["ollama_running"] = True
                    print("  [OK] Ollama started")
                    break
                except Exception:
                    pass
        except Exception as e:
            print(f"  [!!] Could not start Ollama: {e}")

    if status["ollama_running"] and interactive:
        _offer_model_pull()
    elif status["ollama_running"]:
        # Non-interactive: just report model status
        try:
            import urllib.request
            resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            if models:
                print(f"  [OK] Models available: {', '.join(models[:5])}")
            else:
                print("  [--] No models pulled yet")
        except Exception:
            pass


def _offer_model_pull():
    """Check if models exist, offer to pull recommended one."""
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        data = json.loads(resp.read())
        models = [m["name"] for m in data.get("models", [])]
        if models:
            print(f"  [OK] Models available: {', '.join(models[:5])}")
            return
    except Exception:
        models = []

    # VRAM-aware recommendation
    model = "qwen2.5-coder:14b"
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            vram_mb = int(float(r.stdout.strip().split("\n")[0]))
            if vram_mb < 6000:
                model = "qwen2.5-coder:3b"
            elif vram_mb < 10000:
                model = "qwen2.5-coder:7b"
            print(f"  GPU detected ({vram_mb}MB VRAM)")
    except Exception:
        model = "qwen2.5-coder:7b"

    print(f"\n  No AI models found. Recommended: {model}")
    try:
        choice = input(f"  Pull {model} now? This downloads several GB. [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = "n"
    if choice != "n":
        print(f"  Pulling {model} (this may take several minutes)...")
        try:
            subprocess.run(["ollama", "pull", model], timeout=600)
            print(f"  [OK] {model} ready")
        except Exception as e:
            print(f"  [!!] Pull failed: {e}")


# ---------------------------------------------------------------------------
# Phase 5 -- Configuration / telemetry
# ---------------------------------------------------------------------------

def _setup_config(args, interactive):
    """Phase 5: Configure telemetry from args or interactive prompt."""
    config_dir = Path.home() / ".forge"
    config_path = config_dir / "config.yaml"

    if args.token:
        # Token provided via CLI -- auto-configure
        config_dir.mkdir(parents=True, exist_ok=True)
        label = args.label or _generate_label()
        _set_config_values(config_path, {
            "telemetry_enabled": True,
            "telemetry_redact": True,
            "telemetry_token": args.token,
            "telemetry_label": label,
        })
        print(f"  [OK] Telemetry configured (label: {label})")
        return True

    if not interactive:
        print("  [--] Telemetry: skipped (non-interactive)")
        return False

    # Interactive prompt
    print("\n  Forge can send anonymous session metadata to help improve")
    print("  reliability across different hardware. No prompts, responses,")
    print("  or file contents are sent -- only token counts, durations,")
    print("  and threat detection statistics.")
    try:
        choice = input("\n  Enable anonymous telemetry? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = "n"

    if choice in ("y", "yes"):
        config_dir.mkdir(parents=True, exist_ok=True)
        _set_config_values(config_path, {
            "telemetry_enabled": True,
            "telemetry_redact": True,
        })
        print("  [OK] Telemetry enabled (redacted mode)")
        return True
    else:
        print("  [OK] Telemetry disabled")
        return False


def _generate_label():
    """Generate machine label from hostname + GPU name."""
    hostname = socket.gethostname().lower().replace(" ", "-")[:16]
    gpu_name = ""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            raw = r.stdout.strip().split("\n")[0]
            gpu_name = raw.replace("NVIDIA ", "").replace("GeForce ", "").replace(" ", "")[:12]
    except Exception:
        pass
    return f"{hostname}-{gpu_name}" if gpu_name else hostname


def _set_config_values(config_path, values):
    """Set values in config.yaml, creating file if needed.

    Works standalone -- does NOT import from forge.config.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""

    for key, val in values.items():
        if isinstance(val, bool):
            val_str = "true" if val else "false"
        elif isinstance(val, str):
            val_str = f'"{val}"'
        else:
            val_str = str(val)

        line = f"{key}: {val_str}"
        if re.search(rf'^#?\s*{re.escape(key)}:', text, re.MULTILINE):
            text = re.sub(rf'^#?\s*{re.escape(key)}:.*$', line, text, flags=re.MULTILINE)
        else:
            text = text.rstrip() + f"\n{line}\n"

    config_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Phase 6 -- Desktop shortcut
# ---------------------------------------------------------------------------

def _create_shortcut(project_dir):
    """Phase 6: Create desktop shortcut (Windows .lnk or Linux .desktop)."""
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
        # Ensure forge.sh is executable
        forge_sh = project_dir / "forge.sh"
        if forge_sh.exists():
            try:
                forge_sh.chmod(0o755)
            except Exception:
                pass

        desktop_file = desktop / "Forge NC.desktop"
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Forge NC\n"
            "Comment=Local AI Coding Assistant\n"
            f"Exec=bash \"{forge_sh}\"\n"
            "Terminal=true\n"
            "Categories=Development;\n"
            "StartupNotify=true\n"
        )
        try:
            desktop_file.write_text(content)
            desktop_file.chmod(0o755)
            print(f"  [OK] Desktop shortcut: {desktop_file}")
        except Exception as e:
            print(f"  [WARN] Could not create shortcut: {e}")
            print(f"  You can run Forge with: {forge_sh}")


# ---------------------------------------------------------------------------
# Phase 7 -- Verification summary
# ---------------------------------------------------------------------------

def _verify(project_dir, venv_dir, status, telemetry_ok):
    """Phase 7: Print verification summary."""
    # Resolve venv python
    if os.name == "nt":
        venv_py = venv_dir / "Scripts" / "python.exe"
    else:
        venv_py = venv_dir / "bin" / "python"

    # Check voice deps
    voice_ok = False
    try:
        r = subprocess.run(
            [str(venv_py), "-c",
             "from forge.audio.stt import check_voice_deps; print(check_voice_deps())"],
            capture_output=True, text=True, timeout=10,
        )
        voice_ok = "ready" in r.stdout.lower()
    except Exception:
        pass

    # Check if at least one model is available
    model_ok = False
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        data = json.loads(resp.read())
        model_ok = len(data.get("models", [])) > 0
    except Exception:
        pass

    print("\n  " + "=" * 44)
    print("  Forge Installation Summary")
    print("  " + "-" * 44)
    checks = [
        ("Python 3.10+", status["python"]),
        ("Git", status["git"]),
        ("Ollama", status["ollama_running"]),
        ("AI Model", model_ok),
        ("Telemetry", telemetry_ok),
        ("Voice", voice_ok),
    ]
    for name, ok in checks:
        icon = "OK" if ok else "--"
        print(f"  [{icon}] {name}")
    print("  " + "=" * 44)
    print(f"  Project:  {project_dir}")
    print(f"  Venv:     {venv_dir}")
    print("  Launch:   Double-click 'Forge NC' on your desktop")
    if not status["ollama_running"]:
        print("  Note:     Install Ollama first: https://ollama.com")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Install Forge - Local AI Coding Assistant",
    )
    parser.add_argument("--token", help="Telemetry token (from admin)")
    parser.add_argument("--label", help="Machine label (e.g. alice-rtx4090)")
    parser.add_argument(
        "--no-interactive", action="store_true",
        help="Skip all interactive prompts",
    )
    args = parser.parse_args()

    interactive = not args.no_interactive and sys.stdin.isatty()
    project_dir = Path(__file__).parent.resolve()
    venv_dir = project_dir / ".venv"

    print("\n  Forge Installer")
    print("  " + "=" * 44)

    # Phase 1
    print("\n  [1/7] Checking prerequisites...")
    status = _check_prerequisites()
    if not status["python"]:
        print("\n  Python 3.10+ is required.")
        print("  Download: https://python.org/downloads")
        sys.exit(1)

    # Phase 2
    print("\n  [2/7] Setting up Python environment...")
    _create_venv(project_dir, venv_dir)

    # Phase 3
    print("\n  [3/7] Installing dependencies...")
    if os.name == "nt":
        venv_pip = venv_dir / "Scripts" / "pip.exe"
    else:
        venv_pip = venv_dir / "bin" / "pip"
    _install_deps(project_dir, venv_pip)

    # Phase 4
    print("\n  [4/7] Ollama setup...")
    _setup_ollama(status, interactive)

    # Phase 5
    print("\n  [5/7] Configuration...")
    telemetry_ok = _setup_config(args, interactive)

    # Phase 6
    print("\n  [6/7] Creating desktop shortcut...")
    _create_shortcut(project_dir)

    # Phase 7
    print("\n  [7/7] Verification...")
    _verify(project_dir, venv_dir, status, telemetry_ok)


if __name__ == "__main__":
    main()
