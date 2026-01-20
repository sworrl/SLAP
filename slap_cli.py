#!/usr/bin/env python3
"""
SLAP - Scoreboard Live Automation Platform
Command Line Interface

Usage:
    slap start [--port PORT] [--debug]
    slap stop
    slap restart
    slap status
    slap logs [-f] [-n LINES]
    slap -update
    slap -simulation:enable
    slap -simulation:disable
    slap -serial:PORT
    slap -https:setup
    slap -https:remove
    slap config [KEY] [VALUE]
    slap --version
    slap --help
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import threading
from pathlib import Path
from datetime import datetime

# Configuration paths
SCRIPT_DIR = Path(__file__).parent.resolve()
SRC_DIR = SCRIPT_DIR / "src"

if os.name == 'nt':
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "slap"
    CONFIG_DIR = DATA_DIR / "config"
else:
    DATA_DIR = Path.home() / ".local" / "share" / "slap"
    CONFIG_DIR = Path.home() / ".config" / "slap"

VENV_DIR = DATA_DIR / "venv"
LOG_DIR = DATA_DIR / "logs"
DB_DIR = DATA_DIR / "db"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
PID_FILE = DATA_DIR / "slap.pid"
ERROR_LOG = LOG_DIR / "error.log"
APP_LOG = LOG_DIR / "slap.log"

# SSL paths
SSL_DIR = Path("/opt/slap/ssl")
NGINX_AVAILABLE = Path("/etc/nginx/sites-available")
NGINX_ENABLED = Path("/etc/nginx/sites-enabled")
HOSTS_FILE = Path("/etc/hosts")

VERSION = "2.1.0"
GITHUB_REPO = "https://github.com/sworrl/SLAP.git"


class Colors:
    if sys.stdout.isatty():
        BOLD = "\033[1m"
        RED = "\033[0;31m"
        GREEN = "\033[0;32m"
        YELLOW = "\033[1;33m"
        BLUE = "\033[0;34m"
        CYAN = "\033[0;96m"
        NC = "\033[0m"
    else:
        BOLD = RED = GREEN = YELLOW = BLUE = CYAN = NC = ""


def print_status(message, status="info"):
    icons = {
        "success": f"{Colors.GREEN}[OK]{Colors.NC}",
        "error": f"{Colors.RED}[X]{Colors.NC}",
        "warning": f"{Colors.YELLOW}[!]{Colors.NC}",
        "info": f"{Colors.CYAN}->{Colors.NC}",
    }
    icon = icons.get(status, icons["info"])
    print(f"{icon} {message}")


def load_settings():
    """Load settings from file."""
    defaults = {
        "version": VERSION,
        "port": 9876,
        "hostname": "slap.localhost",
        "https_enabled": False,
        "simulation_enabled": False,
        "simulation_visible": False,
        "serial_port": None,
        "serial_baudrate": 9600,
        "debug_mode": False,
        "log_level": "INFO",
        "tray_enabled": True,
        "auto_start": True,
        "last_update": None,
        "db_version": 1,
    }

    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE) as f:
                settings = json.load(f)
            for key, value in defaults.items():
                if key not in settings:
                    settings[key] = value
            return settings
        except Exception:
            pass
    return defaults


def save_settings(settings):
    """Save settings to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print_status(f"Error saving settings: {e}", "error")
        return False


def get_pid():
    """Get PID from PID file."""
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        return None


def is_root():
    return os.geteuid() == 0 if hasattr(os, 'geteuid') else False


def run_privileged(cmd, password=None, check=True):
    """Run a command with elevated privileges."""
    import getpass as gp

    if is_root():
        result = subprocess.run(cmd, capture_output=True, text=True)
    else:
        # Check cached credentials
        cached = subprocess.run(["sudo", "-n", "true"], capture_output=True)
        if cached.returncode == 0:
            result = subprocess.run(["sudo"] + cmd, capture_output=True, text=True)
        else:
            if password is None:
                password = gp.getpass("Enter sudo password: ")
            result = subprocess.run(
                ["sudo", "-S"] + cmd,
                input=password + "\n",
                capture_output=True,
                text=True,
            )

    if check and result.returncode != 0:
        return None
    return result


def log_error(message, exception=None):
    """Log an error to the error log file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat()
    entry = f"[{timestamp}] {message}"
    if exception:
        entry += f"\n  Exception: {type(exception).__name__}: {exception}"

    try:
        with open(ERROR_LOG, "a") as f:
            f.write(entry + "\n")
    except Exception:
        pass


# ============================================================================
# Commands
# ============================================================================

def cmd_start(args):
    """Start SLAP server."""
    settings = load_settings()

    # Check if already running
    pid = get_pid()
    if pid:
        print_status(f"SLAP is already running (PID: {pid})", "warning")
        return

    # Try systemd first
    if subprocess.run(["systemctl", "--user", "is-enabled", "slap"],
                      capture_output=True).returncode == 0:
        result = subprocess.run(["systemctl", "--user", "start", "slap"],
                               capture_output=True)
        if result.returncode == 0:
            print_status("SLAP started via systemd", "success")
            hostname = settings.get("hostname", "slap.localhost")
            if settings.get("https_enabled"):
                print(f"\n  Access at: {Colors.GREEN}https://{hostname}{Colors.NC}\n")
            else:
                port = args.port or settings.get("port", 9876)
                print(f"\n  Access at: {Colors.GREEN}http://localhost:{port}{Colors.NC}\n")
            return

    # Direct start
    print_status("Starting SLAP...")

    python_path = VENV_DIR / "bin" / "python"
    run_script = SRC_DIR / "run.py"

    if not python_path.exists():
        print_status("Python environment not found. Please reinstall.", "error")
        return

    cmd = [str(python_path), str(run_script)]

    port = args.port or settings.get("port", 9876)
    cmd.extend(["--port", str(port)])

    if args.debug or settings.get("debug_mode"):
        cmd.append("--debug")

    if settings.get("simulation_enabled") and settings.get("simulation_visible"):
        cmd.append("--simulate")

    serial_port = settings.get("serial_port")
    if serial_port:
        cmd.extend(["--serial", serial_port])

    # Start in background
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    with open(APP_LOG, "w") as log:
        process = subprocess.Popen(
            cmd,
            cwd=str(SRC_DIR),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )

    PID_FILE.write_text(str(process.pid))

    time.sleep(2)

    if get_pid():
        print_status(f"SLAP started (PID: {process.pid})", "success")
        hostname = settings.get("hostname", "slap.localhost")
        if settings.get("https_enabled"):
            print(f"\n  Access at: {Colors.GREEN}https://{hostname}{Colors.NC}\n")
        else:
            print(f"\n  Access at: {Colors.GREEN}http://localhost:{port}{Colors.NC}\n")

        # Start tray icon if enabled
        if settings.get("tray_enabled", True):
            start_tray_icon()
    else:
        print_status("Failed to start SLAP", "error")
        print_status(f"Check log: {APP_LOG}", "info")
        try:
            print(APP_LOG.read_text()[-2000:])
        except Exception:
            pass


def cmd_stop(args=None):
    """Stop SLAP server."""
    # Stop tray icon first
    stop_tray_icon()

    # Try systemd first
    subprocess.run(["systemctl", "--user", "stop", "slap"],
                  capture_output=True)

    pid = get_pid()
    if not pid:
        print_status("SLAP is not running", "warning")
        PID_FILE.unlink(missing_ok=True)
        return

    print_status(f"Stopping SLAP (PID: {pid})...")

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    time.sleep(2)

    try:
        os.kill(pid, 0)
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    PID_FILE.unlink(missing_ok=True)
    print_status("SLAP stopped", "success")


def cmd_restart(args):
    """Restart SLAP server."""
    cmd_stop()
    time.sleep(1)
    cmd_start(args)


def cmd_status(args=None):
    """Check SLAP status."""
    settings = load_settings()

    # Check systemd
    result = subprocess.run(
        ["systemctl", "--user", "is-active", "slap"],
        capture_output=True, text=True
    )
    if result.stdout.strip() == "active":
        print_status("SLAP is running (systemd service)", "success")
        hostname = settings.get("hostname", "slap.localhost")
        port = settings.get("port", 9876)
        if settings.get("https_enabled"):
            print(f"  URL: https://{hostname}")
        else:
            print(f"  URL: http://localhost:{port}")
        return 0

    # Check PID
    pid = get_pid()
    if pid:
        print_status(f"SLAP is running (PID: {pid})", "success")
        return 0

    print_status("SLAP is not running", "warning")
    return 1


def cmd_logs(args):
    """Show SLAP logs."""
    # Try journalctl first
    if subprocess.run(["which", "journalctl"], capture_output=True).returncode == 0:
        cmd = ["journalctl", "--user", "-u", "slap", "-n", str(args.lines)]
        if args.follow:
            cmd.append("-f")
        try:
            subprocess.run(cmd)
            return
        except KeyboardInterrupt:
            return
        except Exception:
            pass

    # Fallback to log file
    if not APP_LOG.exists():
        print_status("No log file found", "warning")
        return

    if args.follow:
        try:
            subprocess.run(["tail", "-f", str(APP_LOG)])
        except KeyboardInterrupt:
            pass
    else:
        subprocess.run(["tail", "-n", str(args.lines), str(APP_LOG)])


def cmd_errors(args):
    """Show error log."""
    if not ERROR_LOG.exists():
        print_status("No error log found", "info")
        return

    lines = args.lines if hasattr(args, 'lines') else 50
    subprocess.run(["tail", "-n", str(lines), str(ERROR_LOG)])


def cmd_update(args=None):
    """Update SLAP from GitHub."""
    print_status("Checking for updates...")

    settings = load_settings()

    # Stop the server if running
    was_running = get_pid() is not None
    if was_running:
        print_status("Stopping server for update...")
        cmd_stop()

    # Backup current settings
    settings_backup = settings.copy()

    # Pull from git
    if (SCRIPT_DIR / ".git").exists():
        print_status("Pulling latest changes from GitHub...")
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=str(SCRIPT_DIR),
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print_status("Git pull failed", "error")
            print(result.stderr)
            log_error("Git pull failed", Exception(result.stderr))
            return False
        print_status("Code updated", "success")
    else:
        print_status("Not a git repository - please update manually", "warning")
        return False

    # Reinstall Python dependencies
    print_status("Updating Python dependencies...")
    pip_path = VENV_DIR / "bin" / "pip"
    requirements = SRC_DIR / "requirements.txt"

    if requirements.exists():
        subprocess.run([str(pip_path), "install", "--quiet", "-r", str(requirements)])

    # Handle database migrations
    handle_db_migration(settings_backup)

    # Update settings version
    settings["version"] = VERSION
    settings["last_update"] = datetime.now().isoformat()
    save_settings(settings)

    print_status("Update complete!", "success")

    # Restart if it was running
    if was_running:
        print_status("Restarting server...")
        cmd_start(argparse.Namespace(port=None, debug=False))

    return True


def handle_db_migration(old_settings):
    """Handle database migrations during updates."""
    old_version = old_settings.get("db_version", 1)
    new_version = DEFAULT_SETTINGS.get("db_version", 1) if 'DEFAULT_SETTINGS' in dir() else 1

    if old_version >= new_version:
        return

    print_status(f"Migrating database from v{old_version} to v{new_version}...")

    # Add migration logic here as needed
    # Example:
    # if old_version < 2:
    #     migrate_v1_to_v2()

    print_status("Database migration complete", "success")


def cmd_simulation_enable(args=None):
    """Enable simulation mode."""
    settings = load_settings()
    settings["simulation_enabled"] = True
    settings["simulation_visible"] = True
    save_settings(settings)
    print_status("Simulation mode ENABLED", "success")
    print_status("Restart SLAP to apply changes: slap restart", "info")


def cmd_simulation_disable(args=None):
    """Disable simulation mode."""
    settings = load_settings()
    settings["simulation_enabled"] = False
    settings["simulation_visible"] = False
    save_settings(settings)
    print_status("Simulation mode DISABLED", "success")
    print_status("Restart SLAP to apply changes: slap restart", "info")


def cmd_serial(port):
    """Set serial port."""
    settings = load_settings()
    settings["serial_port"] = port
    save_settings(settings)
    print_status(f"Serial port set to: {port}", "success")
    print_status("Restart SLAP to apply changes: slap restart", "info")


def cmd_https_setup(args=None):
    """Setup HTTPS with nginx."""
    settings = load_settings()
    hostname = settings.get("hostname", "slap.localhost")
    port = settings.get("port", 9876)

    print_status("Setting up HTTPS...")

    # Check prerequisites
    if not subprocess.run(["which", "nginx"], capture_output=True).returncode == 0:
        print_status("nginx not installed", "error")
        return False

    if not subprocess.run(["which", "openssl"], capture_output=True).returncode == 0:
        print_status("openssl not installed", "error")
        return False

    # Create SSL directory
    run_privileged(["mkdir", "-p", str(SSL_DIR)])

    # Generate certificate
    print_status("Generating SSL certificate...")
    run_privileged([
        "openssl", "req", "-x509", "-nodes", "-days", "365",
        "-newkey", "rsa:2048",
        "-keyout", str(SSL_DIR / "key.pem"),
        "-out", str(SSL_DIR / "cert.pem"),
        "-subj", f"/CN={hostname}",
        "-addext", f"subjectAltName=DNS:{hostname}"
    ])

    # Add to hosts file
    hosts_content = HOSTS_FILE.read_text()
    if hostname not in hosts_content:
        print_status(f"Adding {hostname} to /etc/hosts...")
        run_privileged(["bash", "-c", f'echo "127.0.0.1 {hostname}" >> /etc/hosts'])

    # Create nginx config
    nginx_config = f"""# SLAP - Auto-generated
server {{
    listen 80;
    listen [::]:80;
    server_name {hostname};
    return 301 https://$host$request_uri;
}}

server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name {hostname};

    ssl_certificate {SSL_DIR}/cert.pem;
    ssl_certificate_key {SSL_DIR}/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }}
}}
"""

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        f.write(nginx_config)
        temp_path = f.name

    run_privileged(["cp", temp_path, str(NGINX_AVAILABLE / "slap.conf")])
    os.unlink(temp_path)

    run_privileged(["ln", "-sf", str(NGINX_AVAILABLE / "slap.conf"),
                   str(NGINX_ENABLED / "slap.conf")])

    # Test and reload nginx
    result = run_privileged(["nginx", "-t"])
    if result and result.returncode == 0:
        run_privileged(["systemctl", "reload", "nginx"])
        print_status("nginx reloaded", "success")
    else:
        print_status("nginx config test failed", "error")
        return False

    # Update settings
    settings["https_enabled"] = True
    save_settings(settings)

    print_status("HTTPS setup complete!", "success")
    print(f"\n  Access at: {Colors.GREEN}https://{hostname}{Colors.NC}\n")
    return True


def cmd_https_remove(args=None):
    """Remove HTTPS configuration."""
    settings = load_settings()

    print_status("Removing HTTPS configuration...")

    run_privileged(["rm", "-f", str(NGINX_ENABLED / "slap.conf")])
    run_privileged(["rm", "-f", str(NGINX_AVAILABLE / "slap.conf")])
    run_privileged(["rm", "-rf", str(SSL_DIR)])
    run_privileged(["systemctl", "reload", "nginx"])

    settings["https_enabled"] = False
    save_settings(settings)

    print_status("HTTPS configuration removed", "success")


def cmd_config(args):
    """Get or set configuration values."""
    settings = load_settings()

    if not args.key:
        # Show all settings
        print(f"\n{Colors.BOLD}SLAP Configuration:{Colors.NC}")
        print(f"  Config file: {SETTINGS_FILE}")
        print()
        for key, value in sorted(settings.items()):
            print(f"  {key}: {value}")
        print()
        return

    key = args.key

    if args.value is None:
        # Get value
        if key in settings:
            print(f"{key}: {settings[key]}")
        else:
            print_status(f"Unknown setting: {key}", "error")
        return

    # Set value
    value = args.value

    # Type conversion
    if value.lower() == "true":
        value = True
    elif value.lower() == "false":
        value = False
    elif value.isdigit():
        value = int(value)

    settings[key] = value
    save_settings(settings)
    print_status(f"Set {key} = {value}", "success")


# ============================================================================
# Tray Icon
# ============================================================================

TRAY_PID_FILE = DATA_DIR / "tray.pid"


def start_tray_icon():
    """Start the system tray icon in background."""
    try:
        import pystray
    except ImportError:
        return  # Tray not available

    # Check if already running
    if TRAY_PID_FILE.exists():
        try:
            pid = int(TRAY_PID_FILE.read_text().strip())
            os.kill(pid, 0)
            return  # Already running
        except (ValueError, ProcessLookupError):
            pass

    # Start tray in background
    tray_script = SCRIPT_DIR / "slap_tray.py"
    if tray_script.exists():
        python_path = VENV_DIR / "bin" / "python"
        process = subprocess.Popen(
            [str(python_path), str(tray_script)],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        TRAY_PID_FILE.write_text(str(process.pid))


def stop_tray_icon():
    """Stop the system tray icon."""
    if not TRAY_PID_FILE.exists():
        return

    try:
        pid = int(TRAY_PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
    except (ValueError, ProcessLookupError):
        pass

    TRAY_PID_FILE.unlink(missing_ok=True)


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="SLAP - Scoreboard Live Automation Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  start                  Start the SLAP server
  stop                   Stop the SLAP server
  restart                Restart the SLAP server
  status                 Check server status
  logs                   View logs
  errors                 View error log
  config [KEY] [VALUE]   Get/set configuration

Flags:
  -update                Update from GitHub
  -simulation:enable     Enable simulation mode
  -simulation:disable    Disable simulation mode
  -serial:PORT           Set serial port
  -https:setup           Setup HTTPS with nginx
  -https:remove          Remove HTTPS configuration

Examples:
  slap start
  slap start --port 8080 --debug
  slap -update
  slap -simulation:enable
  slap config port 9876
"""
    )

    parser.add_argument("command", nargs="?", default="status",
                       help="Command to run")
    parser.add_argument("key", nargs="?", help="Config key")
    parser.add_argument("value", nargs="?", help="Config value")
    parser.add_argument("--port", "-p", type=int, help="Server port")
    parser.add_argument("--debug", "-d", action="store_true", help="Debug mode")
    parser.add_argument("--follow", "-f", action="store_true", help="Follow logs")
    parser.add_argument("--lines", "-n", type=int, default=50, help="Number of log lines")
    parser.add_argument("--version", "-v", action="store_true", help="Show version")

    # Handle special flag-style arguments
    args_list = sys.argv[1:]

    # Check for special flags before parsing
    for i, arg in enumerate(args_list):
        if arg == "-update":
            cmd_update()
            return
        elif arg == "-simulation:enable":
            cmd_simulation_enable()
            return
        elif arg == "-simulation:disable":
            cmd_simulation_disable()
            return
        elif arg.startswith("-serial:"):
            port = arg.split(":", 1)[1]
            cmd_serial(port)
            return
        elif arg == "-https:setup":
            cmd_https_setup()
            return
        elif arg == "-https:remove":
            cmd_https_remove()
            return

    args = parser.parse_args()

    if args.version:
        print(f"SLAP version {VERSION}")
        return

    commands = {
        "start": lambda: cmd_start(args),
        "stop": lambda: cmd_stop(args),
        "restart": lambda: cmd_restart(args),
        "status": lambda: cmd_status(args),
        "logs": lambda: cmd_logs(args),
        "errors": lambda: cmd_errors(args),
        "config": lambda: cmd_config(args),
        "update": cmd_update,
    }

    cmd = args.command.lower()
    if cmd in commands:
        commands[cmd]()
    else:
        print_status(f"Unknown command: {cmd}", "error")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
