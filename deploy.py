#!/usr/bin/env python3
"""
SLAP - Scoreboard Live Automation Platform
Deploy/Update/Uninstall Script

Usage:
    ./deploy.py install    - Install SLAP and dependencies (includes HTTPS setup)
    ./deploy.py update     - Update SLAP (reinstall dependencies)
    ./deploy.py uninstall  - Remove SLAP installation
    ./deploy.py start      - Start SLAP server
    ./deploy.py stop       - Stop SLAP server
    ./deploy.py restart    - Restart SLAP server
    ./deploy.py status     - Check if SLAP is running
    ./deploy.py logs       - Show logs

Options:
    --no-service      Don't create systemd service
    --no-https        Don't set up HTTPS (nginx, SSL)
    --port PORT       Server port (default: 9876)
    --simulate, -s    Run in simulation mode

This script is idempotent - safe to run multiple times.
Can be run as root, with sudo, or as a standard user (will prompt for sudo when needed).
"""

import argparse
import getpass
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

# Configuration
SCRIPT_DIR = Path(__file__).parent.resolve()
SRC_DIR = SCRIPT_DIR / "src"
VENV_DIR = SRC_DIR / "venv"
PID_FILE = Path("/tmp/slap.pid")
LOG_FILE = Path("/tmp/slap.log")
DEFAULT_PORT = 9876
HOSTNAME = "slap.localhost"

# Installation paths
INSTALL_DIR = Path.home() / ".local" / "share" / "slap"
CONFIG_DIR = Path.home() / ".config" / "slap"
BIN_DIR = Path.home() / ".local" / "bin"

# System paths (require root/sudo)
SSL_DIR = Path("/opt/slap/ssl")
NGINX_AVAILABLE = Path("/etc/nginx/sites-available")
NGINX_ENABLED = Path("/etc/nginx/sites-enabled")
HOSTS_FILE = Path("/etc/hosts")


class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;96m'
    BOLD = '\033[1m'
    NC = '\033[0m'  # No Color


def print_status(msg, status="info"):
    """Print a status message with color."""
    colors = {
        "info": Colors.CYAN,
        "success": Colors.GREEN,
        "warning": Colors.YELLOW,
        "error": Colors.RED,
    }
    prefix = {"info": "->", "success": "[OK]", "warning": "[!]", "error": "[X]"}.get(status, "->")
    color = colors.get(status, Colors.CYAN)
    print(f"{color}{prefix}{Colors.NC} {msg}")


def print_header(msg):
    """Print a header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}=== {msg} ==={Colors.NC}\n")


def is_root():
    """Check if running as root."""
    return os.geteuid() == 0


def run_cmd(cmd, check=True, capture=False, **kwargs):
    """Run a command."""
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    result = subprocess.run(cmd, **kwargs)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result


def run_privileged(cmd, password=None, check=True):
    """Run a command with elevated privileges.

    - If running as root, run directly
    - If password provided, use sudo -S
    - Otherwise, use sudo (will prompt if needed)
    """
    if is_root():
        # Running as root, execute directly
        result = subprocess.run(cmd, capture_output=True, text=True)
    elif password:
        # Use sudo with password
        full_cmd = ["sudo", "-S"] + cmd
        result = subprocess.run(
            full_cmd,
            input=password + "\n",
            capture_output=True,
            text=True,
        )
    else:
        # Use sudo, let it prompt if needed
        full_cmd = ["sudo"] + cmd
        result = subprocess.run(full_cmd, capture_output=True, text=True)

    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result


def get_sudo_password():
    """Prompt for sudo password and verify it works. Returns None if running as root."""
    if is_root():
        print_status("Running as root, no sudo needed", "success")
        return None

    print_header("Administrator Access Required")
    print("HTTPS setup requires elevated privileges to:")
    print(f"  - Create SSL certificates in {SSL_DIR}")
    print("  - Add nginx configuration")
    print(f"  - Add {HOSTNAME} to /etc/hosts")
    print()

    # First check if we already have sudo access (passwordless or cached)
    result = subprocess.run(["sudo", "-n", "true"], capture_output=True)
    if result.returncode == 0:
        print_status("Sudo access available (cached/passwordless)", "success")
        return ""  # Empty string means use sudo without -S

    for attempt in range(3):
        password = getpass.getpass("Enter sudo password: ")

        # Test the password
        result = subprocess.run(
            ["sudo", "-S", "-v"],
            input=password + "\n",
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print_status("Sudo access verified", "success")
            return password
        else:
            print_status("Invalid password, try again", "error")

    print_status("Too many failed attempts", "error")
    sys.exit(1)


def check_python():
    """Verify Python version is 3.8+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print_status(f"Python 3.8+ required, found {version.major}.{version.minor}", "error")
        sys.exit(1)
    print_status(f"Python {version.major}.{version.minor}.{version.micro}", "success")


def is_venv_valid():
    """Check if virtual environment exists and is functional"""
    if not VENV_DIR.exists():
        return False, "not found"

    python = get_venv_python()
    pip = get_venv_pip()

    if not python.exists():
        return False, "python missing"
    if not pip.exists():
        return False, "pip missing"

    try:
        result = subprocess.run(
            [str(python), "-c", "import sys; print(sys.version_info.major)"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return False, "python broken"
    except Exception:
        return False, "python broken"

    try:
        result = subprocess.run(
            [str(pip), "--version"],
            capture_output=True, text=True, timeout=10
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
        print_status("Virtual environment OK", "success")
        return

    if VENV_DIR.exists():
        print_status(f"Virtual environment broken ({reason}), recreating...", "warning")
        shutil.rmtree(VENV_DIR)
    else:
        print_status("Creating virtual environment...")

    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    print_status("Virtual environment created", "success")


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

    subprocess.run([str(pip), "install", "--quiet", "--upgrade", "pip"], check=True)
    subprocess.run([str(pip), "install", "--quiet", "-r", str(requirements)], check=True)

    print_status("Dependencies installed", "success")


def get_data_dir():
    """Get platform-appropriate data directory for SLAP."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "slap"


def init_data_dir():
    """Initialize SLAP data directory and database."""
    data_dir = get_data_dir()

    print_status(f"Initializing data directory: {data_dir}")

    data_dir.mkdir(parents=True, exist_ok=True)

    try:
        sys.path.insert(0, str(SRC_DIR))
        from slap.db import get_db
        db = get_db()
        print_status(f"Database initialized: {db.db_path}", "success")
    except Exception as e:
        print_status(f"Database will be created on first run: {e}", "warning")
    finally:
        if str(SRC_DIR) in sys.path:
            sys.path.remove(str(SRC_DIR))


def check_https_prerequisites():
    """Check prerequisites for HTTPS setup."""
    all_ok = True

    if shutil.which("nginx"):
        print_status("nginx available", "success")
    else:
        print_status("nginx not found - install with: sudo apt install nginx", "warning")
        all_ok = False

    if shutil.which("openssl"):
        print_status("openssl available", "success")
    else:
        print_status("openssl not found", "warning")
        all_ok = False

    return all_ok


def setup_https(password=None, port=DEFAULT_PORT):
    """Set up HTTPS with nginx and self-signed certificates."""
    print_header("Setting Up HTTPS")

    # Create SSL directory
    print_status("Creating SSL directory...")
    run_privileged(["mkdir", "-p", str(SSL_DIR)], password)

    # Generate self-signed certificate
    print_status("Generating SSL certificate...")
    run_privileged([
        "openssl", "req", "-x509", "-nodes", "-days", "365",
        "-newkey", "rsa:2048",
        "-keyout", str(SSL_DIR / "key.pem"),
        "-out", str(SSL_DIR / "cert.pem"),
        "-subj", f"/CN={HOSTNAME}",
        "-addext", f"subjectAltName=DNS:{HOSTNAME}"
    ], password)
    print_status("SSL certificate generated", "success")

    # Check if hosts entry exists
    hosts_content = HOSTS_FILE.read_text()
    if HOSTNAME not in hosts_content:
        print_status(f"Adding {HOSTNAME} to /etc/hosts...")
        run_privileged(["bash", "-c", f'echo "127.0.0.1 {HOSTNAME}" >> /etc/hosts'], password)
        print_status(f"Added {HOSTNAME} to /etc/hosts", "success")
    else:
        print_status(f"{HOSTNAME} already in /etc/hosts", "success")

    # Create nginx config
    nginx_config = f'''# SLAP - Scoreboard Live Automation Platform
# Auto-generated by deploy.py

# HTTP server - redirect to HTTPS
server {{
    listen 80;
    listen [::]:80;
    server_name {HOSTNAME};

    return 301 https://$host$request_uri;
}}

# HTTPS server
server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;

    server_name {HOSTNAME};

    ssl_certificate {SSL_DIR}/cert.pem;
    ssl_certificate_key {SSL_DIR}/key.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    client_max_body_size 100M;

    # Proxy all requests to SLAP server
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support for Socket.IO
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }}
}}
'''

    # Write nginx config via privileged command
    config_path = NGINX_AVAILABLE / "slap.conf"
    print_status("Creating nginx configuration...")

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        f.write(nginx_config)
        temp_path = f.name

    run_privileged(["cp", temp_path, str(config_path)], password)
    os.unlink(temp_path)
    print_status(f"Created {config_path}", "success")

    # Enable the site
    enabled_path = NGINX_ENABLED / "slap.conf"
    run_privileged(["ln", "-sf", str(config_path), str(enabled_path)], password, check=False)
    print_status("Enabled nginx site", "success")

    # Test nginx config
    print_status("Testing nginx configuration...")
    result = run_privileged(["nginx", "-t"], password, check=False)
    if result.returncode != 0:
        print_status("nginx config test failed", "error")
        print(result.stderr)
        return False
    print_status("nginx config test passed", "success")

    # Reload nginx
    print_status("Reloading nginx...")
    run_privileged(["systemctl", "reload", "nginx"], password)
    print_status("nginx reloaded", "success")

    return True


def setup_systemd_service(port=DEFAULT_PORT, simulate=False):
    """Create systemd user service for SLAP."""
    print_header("Setting Up Systemd Service")

    if not shutil.which("systemctl"):
        print_status("systemctl not found, skipping service setup", "warning")
        return True

    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)

    service_file = service_dir / "slap.service"
    venv_python = get_venv_python()

    sim_flag = " --simulate" if simulate else ""

    service_content = f'''[Unit]
Description=SLAP - Scoreboard Live Automation Platform
After=network.target

[Service]
Type=simple
Environment=HOME={Path.home()}
WorkingDirectory={SRC_DIR}
ExecStart={venv_python} run.py --port {port}{sim_flag}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
'''

    service_file.write_text(service_content)
    print_status(f"Service file created: {service_file}", "success")

    try:
        run_cmd(["systemctl", "--user", "daemon-reload"], check=False)
        print_status("Systemd daemon reloaded", "success")
    except Exception:
        print_status("Could not reload systemd", "warning")
        return True

    try:
        run_cmd(["systemctl", "--user", "enable", "slap"], check=False)
        print_status("Service enabled for autostart", "success")
    except Exception:
        print_status("Could not enable service", "warning")

    return True


def create_wrapper_script():
    """Create a wrapper script in ~/.local/bin."""
    print_header("Creating CLI Wrapper")

    BIN_DIR.mkdir(parents=True, exist_ok=True)

    wrapper_path = BIN_DIR / "slap"
    deploy_script = SCRIPT_DIR / "deploy.py"

    content = f'''#!/bin/bash
# SLAP CLI wrapper - auto-generated
exec python3 "{deploy_script}" "$@"
'''

    wrapper_path.write_text(content)
    wrapper_path.chmod(0o755)

    print_status(f"Created {wrapper_path}", "success")

    # Check if ~/.local/bin is in PATH
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    if str(BIN_DIR) not in path_dirs:
        print_status(f"Add {BIN_DIR} to your PATH:", "warning")
        print(f"    export PATH=\"{BIN_DIR}:$PATH\"")

    return True


def do_install(args):
    """Install SLAP"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}")
    print("=" * 50)
    print("   SLAP - Scoreboard Live Automation Platform")
    print("              Installation")
    print("=" * 50)
    print(f"{Colors.NC}")

    print_header("Checking Prerequisites")
    check_python()

    # Check HTTPS prerequisites
    https_available = check_https_prerequisites() and not args.no_https

    # Get sudo password if HTTPS is enabled and not running as root
    sudo_password = None
    if https_available:
        sudo_password = get_sudo_password()

    print_header("Setting Up Virtual Environment")
    create_venv()
    install_deps()
    init_data_dir()

    # Create wrapper script
    create_wrapper_script()

    # Setup systemd service
    if not args.no_service:
        setup_systemd_service(port=args.port, simulate=args.simulate)

    # Setup HTTPS
    https_enabled = False
    if https_available:
        if setup_https(sudo_password, port=args.port):
            https_enabled = True
        else:
            print_status("HTTPS setup failed, continuing without it", "warning")

    # Start service
    if not args.no_service:
        start_service()

    # Print success message
    print_success_message(args.port, https_enabled, args.simulate)


def print_success_message(port, https_enabled, simulate):
    """Print success message with access info."""
    print_header("Installation Complete!")

    print(f"{Colors.GREEN}SLAP has been installed successfully!{Colors.NC}\n")

    print(f"{Colors.BOLD}Access URLs:{Colors.NC}")
    if https_enabled:
        print(f"  {Colors.GREEN}https://{HOSTNAME}{Colors.NC}  (recommended)")
    print(f"  http://localhost:{port}")
    print()

    if simulate:
        print(f"{Colors.YELLOW}Running in SIMULATION mode (fake game data){Colors.NC}\n")

    print(f"{Colors.BOLD}Commands:{Colors.NC}")
    print("  ./deploy.py start      # Start server")
    print("  ./deploy.py stop       # Stop server")
    print("  ./deploy.py restart    # Restart server")
    print("  ./deploy.py status     # Check status")
    print("  ./deploy.py logs -f    # Follow logs")
    print()

    print(f"{Colors.BOLD}Data directory:{Colors.NC} {get_data_dir()}")
    print()


def do_update(args):
    """Update SLAP"""
    print_header("Updating SLAP")

    # If git repo, pull latest
    git_dir = SCRIPT_DIR / ".git"
    if git_dir.exists():
        print_status("Pulling latest changes...")
        subprocess.run(["git", "pull"], cwd=str(SCRIPT_DIR))

    check_python()
    create_venv()
    install_deps()

    print_status("SLAP updated successfully!", "success")


def do_uninstall(args):
    """Uninstall SLAP"""
    print_header("Uninstalling SLAP")

    # Stop service
    try:
        do_stop()
    except:
        pass

    # Stop systemd service
    if shutil.which("systemctl"):
        print_status("Stopping service...")
        run_cmd(["systemctl", "--user", "stop", "slap"], check=False)
        run_cmd(["systemctl", "--user", "disable", "slap"], check=False)

        service_file = Path.home() / ".config" / "systemd" / "user" / "slap.service"
        if service_file.exists():
            service_file.unlink()
            print_status("Removed service file", "success")

    # Check if HTTPS was set up
    has_https = (NGINX_AVAILABLE / "slap.conf").exists()

    if has_https:
        print("\nHTTPS configuration detected. Removing requires elevated privileges.")
        sudo_password = get_sudo_password()

        print_status("Removing HTTPS configuration...")
        run_privileged(["rm", "-f", str(NGINX_ENABLED / "slap.conf")], sudo_password, check=False)
        run_privileged(["rm", "-f", str(NGINX_AVAILABLE / "slap.conf")], sudo_password, check=False)
        run_privileged(["rm", "-rf", str(SSL_DIR.parent)], sudo_password, check=False)
        run_privileged(["systemctl", "reload", "nginx"], sudo_password, check=False)
        print_status("Removed nginx configuration", "success")

    # Remove wrapper
    wrapper = BIN_DIR / "slap"
    if wrapper.exists():
        wrapper.unlink()
        print_status("Removed CLI wrapper", "success")

    # Remove virtual environment
    if VENV_DIR.exists():
        print_status("Removing virtual environment...")
        shutil.rmtree(VENV_DIR)

    # Remove PID and log files
    PID_FILE.unlink(missing_ok=True)
    LOG_FILE.unlink(missing_ok=True)

    print_status("SLAP uninstalled.", "success")
    print_status(f"Source files remain in: {SCRIPT_DIR}")
    print_status(f"Data directory: {get_data_dir()}")
    print("Remove manually for complete uninstall:")
    print(f"    rm -rf {get_data_dir()}")


def get_pid():
    """Get PID from PID file, return None if not found or stale"""
    if not PID_FILE.exists():
        return None

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        return None


def start_service():
    """Start SLAP via systemd if available."""
    if not shutil.which("systemctl"):
        print_status("systemctl not found", "warning")
        return False

    try:
        run_cmd(["systemctl", "--user", "start", "slap"])
        print_status("Service started", "success")
        print(f"\n  Access SLAP at: {Colors.GREEN}https://{HOSTNAME}{Colors.NC}\n")
        return True
    except Exception as e:
        print_status(f"Could not start service: {e}", "error")
        return False


def do_start(args):
    """Start SLAP server"""
    # Try systemd first
    if shutil.which("systemctl"):
        # Update service file with current args
        setup_systemd_service(port=args.port, simulate=args.simulate)
        if start_service():
            return

    # Fallback to direct start
    pid = get_pid()
    if pid:
        print_status(f"SLAP is already running (PID: {pid})", "warning")
        print_status(f"URL: http://localhost:{args.port}")
        return

    if not VENV_DIR.exists():
        print_status(f"SLAP not installed. Run: {sys.argv[0]} install", "error")
        sys.exit(1)

    print_status("Starting SLAP...")

    python = get_venv_python()
    cmd = [str(python), "run.py"]

    if args.port:
        cmd.extend(["--port", str(args.port)])

    if args.simulate:
        cmd.append("--simulate")

    if args.debug:
        cmd.append("--debug")

    if args.serial:
        cmd.extend(["--serial", args.serial])

    with open(LOG_FILE, "w") as log:
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
        print_status(f"URL: https://{HOSTNAME}")
        print_status(f"Log: {LOG_FILE}")
    else:
        print_status(f"Failed to start SLAP. Check log: {LOG_FILE}", "error")
        print(LOG_FILE.read_text())
        sys.exit(1)


def do_stop():
    """Stop SLAP server"""
    # Try systemd first
    if shutil.which("systemctl"):
        try:
            run_cmd(["systemctl", "--user", "stop", "slap"], check=False)
            print_status("Service stopped", "success")
        except Exception:
            pass

    pid = get_pid()

    if not pid:
        if PID_FILE.exists():
            print_status("SLAP process not found (stale PID file)", "warning")
            PID_FILE.unlink()
        else:
            print_status("SLAP is not running", "warning")
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

    print_status("SLAP stopped", "success")
    PID_FILE.unlink(missing_ok=True)


def do_status(args):
    """Check if SLAP is running"""
    # Check systemd service
    if shutil.which("systemctl"):
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "slap"],
            capture_output=True, text=True
        )
        if result.stdout.strip() == "active":
            print_status("SLAP is running (systemd service)", "success")
            print_status(f"URL: https://{HOSTNAME}")
            return 0

    pid = get_pid()

    if pid:
        print_status(f"SLAP is running (PID: {pid})", "success")

        try:
            result = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if str(pid) in line:
                    parts = line.split()
                    for part in parts:
                        if ":" in part:
                            port = part.split(":")[-1]
                            if port.isdigit():
                                print_status(f"URL: https://{HOSTNAME}")
                                break
                    break
        except:
            pass
        return 0

    print_status("SLAP is not running", "warning")
    return 1


def do_restart(args):
    """Restart SLAP server"""
    do_stop()
    time.sleep(1)
    do_start(args)


def do_logs(args):
    """Show SLAP logs"""
    # Try journalctl first for systemd service
    if shutil.which("journalctl"):
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
    if not LOG_FILE.exists():
        print_status("No log file found", "warning")
        return

    if args.follow:
        try:
            subprocess.run(["tail", "-f", str(LOG_FILE)])
        except KeyboardInterrupt:
            pass
    else:
        subprocess.run(["tail", "-n", str(args.lines), str(LOG_FILE)])


def do_https(args):
    """Handle HTTPS subcommands"""
    subcommand = args.https_action

    if subcommand == "setup":
        print_header("HTTPS Setup")
        if not check_https_prerequisites():
            print_status("Prerequisites not met", "error")
            sys.exit(1)

        sudo_password = get_sudo_password()
        if setup_https(sudo_password, port=args.port):
            print_status(f"HTTPS configured successfully!", "success")
            print(f"\n  Access SLAP at: {Colors.GREEN}https://{HOSTNAME}{Colors.NC}\n")
        else:
            print_status("HTTPS setup failed", "error")
            sys.exit(1)

    elif subcommand == "remove":
        print_header("Remove HTTPS")

        if not (NGINX_AVAILABLE / "slap.conf").exists():
            print_status("HTTPS not configured", "warning")
            return

        sudo_password = get_sudo_password()

        print_status("Removing nginx configuration...")
        run_privileged(["rm", "-f", str(NGINX_ENABLED / "slap.conf")], sudo_password, check=False)
        run_privileged(["rm", "-f", str(NGINX_AVAILABLE / "slap.conf")], sudo_password, check=False)
        run_privileged(["systemctl", "reload", "nginx"], sudo_password, check=False)
        print_status("nginx configuration removed", "success")

        print_status("Removing SSL certificates...")
        run_privileged(["rm", "-rf", str(SSL_DIR)], sudo_password, check=False)
        print_status("SSL certificates removed", "success")

        print_status("HTTPS configuration removed", "success")
        print(f"\n  Access SLAP at: http://localhost:{args.port}\n")

    elif subcommand == "status":
        print_header("HTTPS Status")

        nginx_conf = NGINX_AVAILABLE / "slap.conf"
        nginx_enabled = NGINX_ENABLED / "slap.conf"
        ssl_cert = SSL_DIR / "cert.pem"
        ssl_key = SSL_DIR / "key.pem"

        # Check hosts entry
        hosts_content = HOSTS_FILE.read_text() if HOSTS_FILE.exists() else ""
        hosts_ok = HOSTNAME in hosts_content

        all_ok = True

        if nginx_conf.exists():
            print_status(f"nginx config: {nginx_conf}", "success")
        else:
            print_status("nginx config: not found", "error")
            all_ok = False

        if nginx_enabled.exists():
            print_status(f"nginx enabled: {nginx_enabled}", "success")
        else:
            print_status("nginx site not enabled", "error")
            all_ok = False

        if ssl_cert.exists() and ssl_key.exists():
            print_status(f"SSL certificates: {SSL_DIR}", "success")
        else:
            print_status("SSL certificates: not found", "error")
            all_ok = False

        if hosts_ok:
            print_status(f"/etc/hosts: {HOSTNAME} configured", "success")
        else:
            print_status(f"/etc/hosts: {HOSTNAME} not found", "error")
            all_ok = False

        print()
        if all_ok:
            print_status(f"HTTPS is fully configured: https://{HOSTNAME}", "success")
        else:
            print_status("HTTPS is NOT fully configured. Run: ./deploy.py https setup", "warning")

    else:
        print_status(f"Unknown https action: {subcommand}", "error")
        print("Usage: ./deploy.py https <setup|remove|status>")
        sys.exit(1)


def show_help():
    """Show help message"""
    print("SLAP - Scoreboard Live Automation Platform")
    print()
    print(f"Usage: {sys.argv[0]} <command> [options]")
    print()
    print("Commands:")
    print("  install     Install SLAP and dependencies (includes HTTPS setup)")
    print("  update      Update SLAP (reinstall dependencies)")
    print("  uninstall   Remove SLAP installation")
    print("  start       Start SLAP server")
    print("  stop        Stop SLAP server")
    print("  restart     Restart SLAP server")
    print("  status      Check if SLAP is running")
    print("  logs        Show SLAP logs")
    print("  https       Manage HTTPS configuration")
    print("  help        Show this help message")
    print()
    print("Install options:")
    print("  --no-service        Don't create systemd service")
    print("  --no-https          Don't set up HTTPS (nginx, SSL)")
    print()
    print("Start options:")
    print(f"  --port, -p <port>   Web server port (default: {DEFAULT_PORT})")
    print("  --serial <device>   Serial port (e.g., /dev/ttyUSB0 or COM3)")
    print("  --simulate, -s      Run in simulation/demo mode (for testing)")
    print("  --debug, -d         Enable debug logging (shows raw serial data)")
    print()
    print("HTTPS commands:")
    print(f"  {sys.argv[0]} https setup     Set up HTTPS with nginx and SSL")
    print(f"  {sys.argv[0]} https remove    Remove HTTPS configuration")
    print(f"  {sys.argv[0]} https status    Check HTTPS configuration status")
    print()
    print("Logs options:")
    print("  --follow, -f        Follow log output in real-time")
    print("  --lines, -n <num>   Number of lines to show (default: 50)")
    print()
    print("Examples:")
    print(f"  {sys.argv[0]} install")
    print(f"  {sys.argv[0]} install --no-https    # Skip HTTPS setup")
    print(f"  {sys.argv[0]} https setup           # Set up HTTPS separately")
    print(f"  {sys.argv[0]} start                 # Live mode")
    print(f"  {sys.argv[0]} start --simulate      # Demo mode (fake data)")
    print(f"  {sys.argv[0]} logs -f")
    print(f"  {sys.argv[0]} stop")
    print()
    print(f"After install, access SLAP at: https://{HOSTNAME}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="SLAP - Scoreboard Live Automation Platform",
        add_help=False
    )
    parser.add_argument("command", nargs="?", default="help",
                        choices=["install", "update", "uninstall", "start", "stop", "restart", "status", "logs", "https", "help"])
    parser.add_argument("https_action", nargs="?", default=None,
                        help="HTTPS subcommand: setup, remove, status")
    parser.add_argument("--port", "-p", type=int, default=DEFAULT_PORT)
    parser.add_argument("--serial", default=None)
    parser.add_argument("--simulate", "-s", action="store_true")
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--follow", "-f", action="store_true")
    parser.add_argument("--lines", "-n", type=int, default=50)
    parser.add_argument("--help", "-h", action="store_true")
    parser.add_argument("--no-service", action="store_true")
    parser.add_argument("--no-https", action="store_true")

    args = parser.parse_args()

    if args.help or args.command == "help":
        show_help()
        return

    # Handle https command
    if args.command == "https":
        if not args.https_action:
            print_status("Usage: ./deploy.py https <setup|remove|status>", "error")
            sys.exit(1)
        do_https(args)
        return

    commands = {
        "install": lambda: do_install(args),
        "update": lambda: do_update(args),
        "uninstall": lambda: do_uninstall(args),
        "start": lambda: do_start(args),
        "stop": do_stop,
        "restart": lambda: do_restart(args),
        "status": lambda: do_status(args),
        "logs": lambda: do_logs(args),
    }

    if args.command in commands:
        commands[args.command]()
    else:
        print_status(f"Unknown command: {args.command}", "error")
        print()
        show_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
