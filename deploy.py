#!/usr/bin/env python3
"""
SLAP - Scoreboard Live Automation Platform
Deploy/Update/Uninstall Script

Usage:
    ./deploy.py install    - Install SLAP and dependencies
    ./deploy.py update     - Update SLAP (reinstall dependencies)
    ./deploy.py uninstall  - Remove SLAP installation
    ./deploy.py start      - Start SLAP server
    ./deploy.py stop       - Stop SLAP server
    ./deploy.py status     - Check if SLAP is running

This script is idempotent - safe to run multiple times.
"""

import os
import sys
import subprocess
import signal
import shutil
import time
import argparse
from pathlib import Path

# Configuration
SCRIPT_DIR = Path(__file__).parent.resolve()
SRC_DIR = SCRIPT_DIR / "src"
VENV_DIR = SRC_DIR / "venv"
PID_FILE = Path("/tmp/slap.pid")
LOG_FILE = Path("/tmp/slap.log")
DEFAULT_PORT = 9876

# Colors for terminal output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

def print_status(msg):
    print(f"{Colors.BLUE}[SLAP]{Colors.NC} {msg}")

def print_success(msg):
    print(f"{Colors.GREEN}[SLAP]{Colors.NC} {msg}")

def print_warning(msg):
    print(f"{Colors.YELLOW}[SLAP]{Colors.NC} {msg}")

def print_error(msg):
    print(f"{Colors.RED}[SLAP]{Colors.NC} {msg}")

def check_python():
    """Verify Python version is 3.8+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print_error(f"Python 3.8+ required, found {version.major}.{version.minor}")
        sys.exit(1)
    print_status(f"Found Python {version.major}.{version.minor}")

def is_venv_valid():
    """Check if virtual environment exists and is functional"""
    if not VENV_DIR.exists():
        return False, "not found"

    python = get_venv_python()
    pip = get_venv_pip()

    # Check python exists
    if not python.exists():
        return False, "python missing"

    # Check pip exists
    if not pip.exists():
        return False, "pip missing"

    # Verify python actually works
    try:
        result = subprocess.run(
            [str(python), "-c", "import sys; print(sys.version_info.major)"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return False, "python broken"
    except Exception:
        return False, "python broken"

    # Verify pip works
    try:
        result = subprocess.run(
            [str(pip), "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return False, "pip broken"
    except Exception:
        return False, "pip broken"

    return True, "ok"


def create_venv():
    """Create virtual environment, recreating if broken"""
    valid, reason = is_venv_valid()

    if valid:
        print_status("Virtual environment OK")
        return

    # Remove broken venv if it exists
    if VENV_DIR.exists():
        print_warning(f"Virtual environment broken ({reason}), recreating...")
        shutil.rmtree(VENV_DIR)
    else:
        print_status("Creating virtual environment...")

    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    print_success("Virtual environment created")

def get_venv_python():
    """Get path to Python in virtual environment"""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"

def get_venv_pip():
    """Get path to pip in virtual environment"""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"

def install_deps():
    """Install Python dependencies"""
    print_status("Installing dependencies...")

    pip = get_venv_pip()
    requirements = SRC_DIR / "requirements.txt"

    # Upgrade pip first
    subprocess.run([str(pip), "install", "--quiet", "--upgrade", "pip"], check=True)

    # Install requirements
    subprocess.run([str(pip), "install", "--quiet", "-r", str(requirements)], check=True)

    print_success("Dependencies installed")

def do_install():
    """Install SLAP"""
    print_status("Installing SLAP...")
    print()

    check_python()
    create_venv()
    install_deps()

    print()
    print_success("=========================================")
    print_success("SLAP installed successfully!")
    print_success("=========================================")
    print()
    print_status("To start SLAP:")
    print_status(f"  {sys.argv[0]} start")
    print()
    print_status("Or run manually:")
    print_status(f"  cd {SRC_DIR}")
    print_status("  source venv/bin/activate")
    print_status("  python run.py")
    print()

def do_update():
    """Update SLAP"""
    print_status("Updating SLAP...")
    print()

    # If git repo, pull latest
    git_dir = SCRIPT_DIR / ".git"
    if git_dir.exists():
        print_status("Pulling latest changes...")
        subprocess.run(["git", "pull"], cwd=str(SCRIPT_DIR))

    # Reinstall dependencies
    check_python()
    create_venv()
    install_deps()

    print()
    print_success("SLAP updated successfully!")
    print()

def do_uninstall():
    """Uninstall SLAP"""
    print_warning("Uninstalling SLAP...")
    print()

    # Stop if running
    try:
        do_stop()
    except:
        pass

    # Remove virtual environment
    if VENV_DIR.exists():
        print_status("Removing virtual environment...")
        shutil.rmtree(VENV_DIR)

    # Remove PID and log files
    PID_FILE.unlink(missing_ok=True)
    LOG_FILE.unlink(missing_ok=True)

    print()
    print_success("SLAP uninstalled.")
    print_status(f"Source files remain in: {SCRIPT_DIR}")
    print_status("To completely remove, delete the SLAP directory.")
    print()

def get_pid():
    """Get PID from PID file, return None if not found or stale"""
    if not PID_FILE.exists():
        return None

    try:
        pid = int(PID_FILE.read_text().strip())
        # Check if process is running
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        return None

def do_start(args):
    """Start SLAP server"""
    # Check if already running
    pid = get_pid()
    if pid:
        print_warning(f"SLAP is already running (PID: {pid})")
        print_status(f"URL: http://localhost:{DEFAULT_PORT}")
        return

    # Check venv exists
    if not VENV_DIR.exists():
        print_error(f"SLAP not installed. Run: {sys.argv[0]} install")
        sys.exit(1)

    print_status("Starting SLAP...")

    # Build command
    python = get_venv_python()
    cmd = [str(python), "run.py"]

    port = DEFAULT_PORT
    if args.port:
        cmd.extend(["--port", str(args.port)])
        port = args.port

    if args.simulate:
        cmd.append("--simulate")

    if args.debug:
        cmd.append("--debug")

    if args.serial:
        cmd.extend(["--serial", args.serial])

    # Start in background
    with open(LOG_FILE, "w") as log:
        process = subprocess.Popen(
            cmd,
            cwd=str(SRC_DIR),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )

    PID_FILE.write_text(str(process.pid))

    # Wait for startup
    time.sleep(2)

    # Check if still running
    if get_pid():
        print_success(f"SLAP started (PID: {process.pid})")
        print_status(f"URL: http://localhost:{port}")
        print_status(f"Log: {LOG_FILE}")
    else:
        print_error(f"Failed to start SLAP. Check log: {LOG_FILE}")
        print(LOG_FILE.read_text())
        sys.exit(1)

def do_stop():
    """Stop SLAP server"""
    pid = get_pid()

    if not pid:
        if PID_FILE.exists():
            print_warning("SLAP process not found (stale PID file)")
            PID_FILE.unlink()
        else:
            print_warning("SLAP is not running (no PID file)")
        return

    print_status(f"Stopping SLAP (PID: {pid})...")

    # Send SIGTERM
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    # Wait for graceful shutdown
    time.sleep(2)

    # Force kill if still running
    try:
        os.kill(pid, 0)  # Check if still running
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    print_success("SLAP stopped")
    PID_FILE.unlink(missing_ok=True)

def do_status():
    """Check if SLAP is running"""
    pid = get_pid()

    if pid:
        print_success(f"SLAP is running (PID: {pid})")

        # Try to get port from netstat/ss
        try:
            result = subprocess.run(
                ["ss", "-tlnp"],
                capture_output=True,
                text=True
            )
            for line in result.stdout.splitlines():
                if str(pid) in line:
                    # Extract port
                    parts = line.split()
                    for part in parts:
                        if ":" in part:
                            port = part.split(":")[-1]
                            if port.isdigit():
                                print_status(f"URL: http://localhost:{port}")
                                break
                    break
        except:
            pass
        return 0

    print_warning("SLAP is not running")
    return 1


def do_restart(args):
    """Restart SLAP server"""
    do_stop()
    time.sleep(1)
    do_start(args)


def do_logs(args):
    """Show SLAP logs"""
    if not LOG_FILE.exists():
        print_warning("No log file found")
        return

    if args.follow:
        try:
            subprocess.run(["tail", "-f", str(LOG_FILE)])
        except KeyboardInterrupt:
            pass
    else:
        lines = args.lines or 50
        subprocess.run(["tail", "-n", str(lines), str(LOG_FILE)])

def show_help():
    """Show help message"""
    print("SLAP - Scoreboard Live Automation Platform")
    print()
    print(f"Usage: {sys.argv[0]} <command> [options]")
    print()
    print("Commands:")
    print("  install     Install SLAP and dependencies")
    print("  update      Update SLAP (reinstall dependencies)")
    print("  uninstall   Remove SLAP installation")
    print("  start       Start SLAP server")
    print("  stop        Stop SLAP server")
    print("  restart     Restart SLAP server")
    print("  status      Check if SLAP is running")
    print("  logs        Show SLAP logs")
    print("  help        Show this help message")
    print()
    print("Start options:")
    print(f"  --port, -p <port>   Web server port (default: {DEFAULT_PORT})")
    print("  --serial <device>   Serial port (e.g., /dev/ttyUSB0 or COM3)")
    print("  --simulate, -s      Run in simulation/demo mode (for testing)")
    print("  --debug, -d         Enable debug logging (shows raw serial data)")
    print()
    print("Logs options:")
    print("  --follow, -f        Follow log output in real-time")
    print("  --lines, -n <num>   Number of lines to show (default: 50)")
    print()
    print("Examples:")
    print(f"  {sys.argv[0]} install")
    print(f"  {sys.argv[0]} start              # Live mode (reads serial port)")
    print(f"  {sys.argv[0]} start --simulate   # Demo mode (fake game data)")
    print(f"  {sys.argv[0]} logs -f")
    print(f"  {sys.argv[0]} stop")
    print()

def main():
    parser = argparse.ArgumentParser(
        description="SLAP - Scoreboard Live Automation Platform",
        add_help=False
    )
    parser.add_argument("command", nargs="?", default="help",
                        choices=["install", "update", "uninstall", "start", "stop", "restart", "status", "logs", "help"])
    parser.add_argument("--port", "-p", type=int, default=None)
    parser.add_argument("--serial", default=None)
    parser.add_argument("--simulate", "-s", action="store_true")
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--follow", "-f", action="store_true")
    parser.add_argument("--lines", "-n", type=int, default=50)
    parser.add_argument("--help", "-h", action="store_true")

    args = parser.parse_args()

    if args.help or args.command == "help":
        show_help()
        return

    commands = {
        "install": do_install,
        "update": do_update,
        "uninstall": do_uninstall,
        "start": lambda: do_start(args),
        "stop": do_stop,
        "restart": lambda: do_restart(args),
        "status": do_status,
        "logs": lambda: do_logs(args),
    }

    if args.command in commands:
        commands[args.command]()
    else:
        print_error(f"Unknown command: {args.command}")
        print()
        show_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
