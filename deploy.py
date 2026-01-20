#!/usr/bin/env python3
"""
SLAP - Scoreboard Live Automation Platform
Installation and Deployment Script

This script handles complete installation including all prerequisites.
After installation, use the 'slap' command to control the application.

Usage:
    ./deploy.py              - Full installation with all prerequisites
    ./deploy.py --uninstall  - Remove SLAP completely
    ./deploy.py --help       - Show this help

After installation, control SLAP with:
    slap start               - Start the server
    slap stop                - Stop the server
    slap status              - Check server status
    slap -update             - Update from GitHub
    slap -simulation:enable  - Enable simulation mode
    slap -simulation:disable - Disable simulation mode
    slap --help              - Show all available commands
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime

# ============================================================================
# Configuration
# ============================================================================

APP_NAME = "slap"
APP_DISPLAY_NAME = "SLAP - Scoreboard Live Automation Platform"
VERSION = "2.1.0"
GITHUB_REPO = "https://github.com/sworrl/SLAP.git"
GITHUB_RAW = "https://raw.githubusercontent.com/sworrl/SLAP/main"

# Paths
SCRIPT_DIR = Path(__file__).parent.resolve()
SRC_DIR = SCRIPT_DIR / "src"

# Installation directories (non-web-hosted, secure)
if os.name == 'nt':  # Windows
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "slap"
    CONFIG_DIR = DATA_DIR / "config"
    LOG_DIR = DATA_DIR / "logs"
    BIN_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Programs" / "slap"
else:  # Linux/macOS
    DATA_DIR = Path.home() / ".local" / "share" / "slap"
    CONFIG_DIR = Path.home() / ".config" / "slap"
    LOG_DIR = DATA_DIR / "logs"
    BIN_DIR = Path.home() / ".local" / "bin"

VENV_DIR = DATA_DIR / "venv"
DB_DIR = DATA_DIR / "db"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
PID_FILE = DATA_DIR / "slap.pid"

# SSL/HTTPS paths (system-level, require sudo)
SSL_DIR = Path("/opt/slap/ssl")
NGINX_AVAILABLE = Path("/etc/nginx/sites-available")
NGINX_ENABLED = Path("/etc/nginx/sites-enabled")
HOSTS_FILE = Path("/etc/hosts")

# Default settings
DEFAULT_SETTINGS = {
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
    "caspar_host": "127.0.0.1",
    "caspar_port": 5250,
    "caspar_enabled": False,
    "obs_host": "127.0.0.1",
    "obs_port": 4455,
    "obs_enabled": False,
    "tray_enabled": True,
    "auto_start": True,
    "last_update": None,
    "db_version": 1,
}

# ============================================================================
# Colors and Output
# ============================================================================

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


def print_banner():
    """Print the SLAP installation banner."""
    print(f"""
{Colors.CYAN}{Colors.BOLD}
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   ███████╗██╗      █████╗ ██████╗                            ║
║   ██╔════╝██║     ██╔══██╗██╔══██╗                           ║
║   ███████╗██║     ███████║██████╔╝                           ║
║   ╚════██║██║     ██╔══██║██╔═══╝                            ║
║   ███████║███████╗██║  ██║██║                                ║
║   ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝                                ║
║                                                               ║
║        Scoreboard Live Automation Platform                    ║
║                    Version {VERSION}                             ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
{Colors.NC}
""")


def print_status(message, status="info"):
    """Print a status message with icon."""
    icons = {
        "success": f"{Colors.GREEN}[OK]{Colors.NC}",
        "error": f"{Colors.RED}[X]{Colors.NC}",
        "warning": f"{Colors.YELLOW}[!]{Colors.NC}",
        "info": f"{Colors.CYAN}->{Colors.NC}",
        "skip": f"{Colors.BLUE}[~]{Colors.NC}",
    }
    icon = icons.get(status, icons["info"])
    print(f"{icon} {message}")


def print_header(title):
    """Print a section header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}=== {title} ==={Colors.NC}\n")


def run_cmd(cmd, check=True, capture=True, timeout=300):
    """Run a command and return the result."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=timeout,
            check=False
        )
        if check and result.returncode != 0:
            return None
        return result
    except subprocess.TimeoutExpired:
        print_status(f"Command timed out: {' '.join(cmd)}", "error")
        return None
    except Exception as e:
        print_status(f"Command failed: {e}", "error")
        return None


def is_root():
    """Check if running as root."""
    return os.geteuid() == 0 if hasattr(os, 'geteuid') else False


def get_sudo_password():
    """Get sudo password if needed."""
    if is_root():
        return None

    # Check if sudo credentials are cached
    result = subprocess.run(["sudo", "-n", "true"], capture_output=True)
    if result.returncode == 0:
        return ""  # Empty string means use cached credentials

    import getpass
    print(f"\n{Colors.YELLOW}Elevated privileges required for system-level installation.{Colors.NC}")

    for attempt in range(3):
        password = getpass.getpass("Enter sudo password: ")
        result = subprocess.run(
            ["sudo", "-S", "-v"],
            input=password + "\n",
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return password
        print_status("Invalid password, try again", "error")

    print_status("Too many failed attempts", "error")
    sys.exit(1)


def run_privileged(cmd, password=None, check=True):
    """Run a command with elevated privileges."""
    if is_root():
        result = subprocess.run(cmd, capture_output=True, text=True)
    elif password == "":
        # Use cached sudo credentials
        result = subprocess.run(["sudo"] + cmd, capture_output=True, text=True)
    elif password:
        result = subprocess.run(
            ["sudo", "-S"] + cmd,
            input=password + "\n",
            capture_output=True,
            text=True,
        )
    else:
        result = subprocess.run(["sudo"] + cmd, capture_output=True, text=True)

    if check and result.returncode != 0:
        if result.stderr:
            print_status(f"Error: {result.stderr.strip()}", "error")
        return None
    return result


# ============================================================================
# Package Manager Detection and Installation
# ============================================================================

def detect_package_manager():
    """Detect the system's package manager."""
    managers = [
        ("apt-get", "apt"),      # Debian/Ubuntu
        ("dnf", "dnf"),          # Fedora/RHEL 8+
        ("yum", "yum"),          # CentOS/RHEL 7
        ("pacman", "pacman"),    # Arch Linux
        ("zypper", "zypper"),    # openSUSE
        ("apk", "apk"),          # Alpine
        ("brew", "brew"),        # macOS Homebrew
    ]

    for cmd, name in managers:
        if shutil.which(cmd):
            return name

    return None


def get_package_install_cmd(pkg_manager, packages):
    """Get the install command for a package manager."""
    cmds = {
        "apt": ["apt-get", "install", "-y"] + packages,
        "dnf": ["dnf", "install", "-y"] + packages,
        "yum": ["yum", "install", "-y"] + packages,
        "pacman": ["pacman", "-S", "--noconfirm"] + packages,
        "zypper": ["zypper", "install", "-y"] + packages,
        "apk": ["apk", "add"] + packages,
        "brew": ["brew", "install"] + packages,
    }
    return cmds.get(pkg_manager, [])


def get_package_names(pkg_manager, package):
    """Get platform-specific package names."""
    # Map generic names to platform-specific names
    package_map = {
        "apt": {
            "python3": "python3",
            "python3-pip": "python3-pip",
            "python3-venv": "python3-venv",
            "nginx": "nginx",
            "openssl": "openssl",
            "git": "git",
            "python3-dev": "python3-dev",
            "build-essential": "build-essential",
            "libffi-dev": "libffi-dev",
            "libssl-dev": "libssl-dev",
            "python3-gi": "python3-gi",
            "gir1.2-ayatanaappindicator3-0.1": "gir1.2-ayatanaappindicator3-0.1",
        },
        "dnf": {
            "python3": "python3",
            "python3-pip": "python3-pip",
            "python3-venv": "python3",
            "nginx": "nginx",
            "openssl": "openssl",
            "git": "git",
            "python3-dev": "python3-devel",
            "build-essential": "gcc gcc-c++ make",
            "libffi-dev": "libffi-devel",
            "libssl-dev": "openssl-devel",
            "python3-gi": "python3-gobject",
            "gir1.2-ayatanaappindicator3-0.1": "libappindicator-gtk3",
        },
        "pacman": {
            "python3": "python",
            "python3-pip": "python-pip",
            "python3-venv": "python",
            "nginx": "nginx",
            "openssl": "openssl",
            "git": "git",
            "python3-dev": "python",
            "build-essential": "base-devel",
            "libffi-dev": "libffi",
            "libssl-dev": "openssl",
            "python3-gi": "python-gobject",
            "gir1.2-ayatanaappindicator3-0.1": "libappindicator-gtk3",
        },
        "brew": {
            "python3": "python@3",
            "python3-pip": "python@3",
            "python3-venv": "python@3",
            "nginx": "nginx",
            "openssl": "openssl",
            "git": "git",
            "python3-dev": "python@3",
            "build-essential": "",
            "libffi-dev": "libffi",
            "libssl-dev": "openssl",
        },
    }

    if pkg_manager in package_map:
        return package_map[pkg_manager].get(package, package)
    return package


def install_system_packages(password=None):
    """Install required system packages."""
    print_header("Installing System Prerequisites")

    pkg_manager = detect_package_manager()
    if not pkg_manager:
        print_status("Could not detect package manager", "error")
        print("Please install manually: python3, python3-pip, python3-venv, nginx, openssl, git")
        return False

    print_status(f"Detected package manager: {pkg_manager}", "info")

    # Required packages
    required = [
        "python3",
        "python3-pip",
        "python3-venv",
        "nginx",
        "openssl",
        "git",
    ]

    # Optional packages for full functionality (tray icon support)
    optional = [
        "python3-gi",
        "gir1.2-ayatanaappindicator3-0.1",
    ]

    # Build dependencies
    build_deps = [
        "python3-dev",
        "build-essential",
        "libffi-dev",
        "libssl-dev",
    ]

    # Check what's already installed
    to_install = []

    for pkg in required:
        pkg_name = get_package_names(pkg_manager, pkg)
        if pkg_name:
            to_install.append(pkg_name)

    for pkg in build_deps:
        pkg_name = get_package_names(pkg_manager, pkg)
        if pkg_name:
            to_install.append(pkg_name)

    # Remove duplicates and empty strings
    to_install = list(set(p for p in to_install if p))

    if not to_install:
        print_status("All required packages appear to be available", "success")
        return True

    # Update package cache first
    print_status("Updating package cache...")
    if pkg_manager == "apt":
        run_privileged(["apt-get", "update"], password, check=False)
    elif pkg_manager == "dnf":
        run_privileged(["dnf", "check-update"], password, check=False)
    elif pkg_manager == "pacman":
        run_privileged(["pacman", "-Sy"], password, check=False)

    # Install packages
    print_status(f"Installing: {', '.join(to_install)}")
    cmd = get_package_install_cmd(pkg_manager, to_install)
    if cmd:
        result = run_privileged(cmd, password, check=False)
        if result and result.returncode == 0:
            print_status("System packages installed", "success")
        else:
            print_status("Some packages may have failed to install", "warning")
            print_status("Continuing anyway - installation may still succeed", "info")

    # Try to install optional packages (don't fail if they don't install)
    optional_to_install = []
    for pkg in optional:
        pkg_name = get_package_names(pkg_manager, pkg)
        if pkg_name:
            optional_to_install.append(pkg_name)

    if optional_to_install:
        print_status(f"Installing optional packages for tray icon support...")
        cmd = get_package_install_cmd(pkg_manager, optional_to_install)
        if cmd:
            run_privileged(cmd, password, check=False)

    return True


# ============================================================================
# Python Virtual Environment
# ============================================================================

def check_python():
    """Verify Python version is 3.8+."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print_status(f"Python 3.8+ required, found {version.major}.{version.minor}", "error")
        return False
    print_status(f"Python {version.major}.{version.minor}.{version.micro}", "success")
    return True


def create_venv():
    """Create virtual environment."""
    print_header("Setting Up Python Environment")

    VENV_DIR.parent.mkdir(parents=True, exist_ok=True)

    if VENV_DIR.exists():
        # Check if venv is valid
        python_path = VENV_DIR / "bin" / "python"
        if python_path.exists():
            result = run_cmd([str(python_path), "--version"])
            if result and result.returncode == 0:
                print_status("Virtual environment exists and is valid", "success")
                return True

        print_status("Virtual environment is broken, recreating...", "warning")
        shutil.rmtree(VENV_DIR)

    print_status("Creating virtual environment...")
    result = run_cmd([sys.executable, "-m", "venv", str(VENV_DIR)])
    if not result or result.returncode != 0:
        print_status("Failed to create virtual environment", "error")
        return False

    print_status("Virtual environment created", "success")
    return True


def install_python_deps():
    """Install Python dependencies."""
    print_status("Installing Python dependencies...")

    pip_path = VENV_DIR / "bin" / "pip"
    requirements = SRC_DIR / "requirements.txt"

    if not requirements.exists():
        print_status(f"Requirements file not found: {requirements}", "error")
        return False

    # Upgrade pip first
    run_cmd([str(pip_path), "install", "--quiet", "--upgrade", "pip"])

    # Install requirements
    result = run_cmd([str(pip_path), "install", "--quiet", "-r", str(requirements)])
    if not result or result.returncode != 0:
        print_status("Failed to install Python dependencies", "error")
        return False

    # Install additional packages for tray icon
    tray_packages = ["pystray", "Pillow"]
    run_cmd([str(pip_path), "install", "--quiet"] + tray_packages)

    print_status("Python dependencies installed", "success")
    return True


# ============================================================================
# Settings Management
# ============================================================================

def load_settings():
    """Load settings from file."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE) as f:
                settings = json.load(f)
            # Merge with defaults for any missing keys
            for key, value in DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = value
            return settings
        except Exception as e:
            print_status(f"Error loading settings: {e}", "warning")
    return DEFAULT_SETTINGS.copy()


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


# ============================================================================
# Directory Setup
# ============================================================================

def setup_directories():
    """Create necessary directories."""
    print_header("Setting Up Directories")

    directories = [
        DATA_DIR,
        CONFIG_DIR,
        LOG_DIR,
        DB_DIR,
        BIN_DIR,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        print_status(f"Created: {directory}", "success")

    return True


# ============================================================================
# SLAP Command Installation
# ============================================================================

def create_slap_command():
    """Create the global 'slap' command."""
    print_header("Creating SLAP Command")

    slap_script = BIN_DIR / "slap"
    python_path = VENV_DIR / "bin" / "python"

    script_content = f'''#!/usr/bin/env bash
# SLAP - Scoreboard Live Automation Platform
# Main command wrapper

PYTHON_PATH="{python_path}"
SLAP_DIR="{SCRIPT_DIR}"
SLAP_CLI="{SCRIPT_DIR}/slap_cli.py"
SETTINGS_FILE="{SETTINGS_FILE}"
DATA_DIR="{DATA_DIR}"
LOG_DIR="{LOG_DIR}"

# Ensure the CLI exists
if [[ ! -f "$SLAP_CLI" ]]; then
    echo "Error: SLAP CLI not found at $SLAP_CLI"
    echo "Please reinstall SLAP: cd $SLAP_DIR && ./deploy.py"
    exit 1
fi

# Run the CLI
exec "$PYTHON_PATH" "$SLAP_CLI" "$@"
'''

    try:
        slap_script.write_text(script_content)
        slap_script.chmod(0o755)
        print_status(f"Created command: {slap_script}", "success")
    except Exception as e:
        print_status(f"Failed to create slap command: {e}", "error")
        return False

    # Check if BIN_DIR is in PATH
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    if str(BIN_DIR) not in path_dirs:
        print_status(f"Add to your PATH: export PATH=\"{BIN_DIR}:$PATH\"", "warning")

        # Try to add to shell profile
        shell_profiles = [
            Path.home() / ".bashrc",
            Path.home() / ".zshrc",
            Path.home() / ".profile",
        ]

        path_line = f'\n# SLAP - Added by installer\nexport PATH="{BIN_DIR}:$PATH"\n'

        for profile in shell_profiles:
            if profile.exists():
                content = profile.read_text()
                if str(BIN_DIR) not in content:
                    try:
                        with open(profile, "a") as f:
                            f.write(path_line)
                        print_status(f"Added PATH to {profile}", "success")
                        break
                    except Exception:
                        pass

    return True


def create_desktop_entry():
    """Create a desktop entry for the start menu."""
    print_header("Creating Start Menu Entry")

    applications_dir = Path.home() / ".local" / "share" / "applications"
    applications_dir.mkdir(parents=True, exist_ok=True)

    desktop_file = applications_dir / "slap.desktop"
    icon_path = SCRIPT_DIR / "src" / "slap" / "web" / "static" / "img" / "SLAP_icon.webp"

    desktop_content = f'''[Desktop Entry]
Version=1.0
Type=Application
Name=SLAP
GenericName=Scoreboard Live Automation Platform
Comment=Hockey scoreboard automation for broadcast
Exec={BIN_DIR}/slap start
Icon={icon_path}
Terminal=false
Categories=Utility;AudioVideo;
Keywords=scoreboard;hockey;broadcast;overlay;
StartupNotify=true
Actions=start;stop;status;

[Desktop Action start]
Name=Start SLAP
Exec={BIN_DIR}/slap start

[Desktop Action stop]
Name=Stop SLAP
Exec={BIN_DIR}/slap stop

[Desktop Action status]
Name=Check Status
Exec=bash -c "{BIN_DIR}/slap status; read -p 'Press Enter...'"
'''

    try:
        desktop_file.write_text(desktop_content)
        desktop_file.chmod(0o755)
        print_status(f"Created: {desktop_file}", "success")

        # Update desktop database
        run_cmd(["update-desktop-database", str(applications_dir)], check=False)

        return True
    except Exception as e:
        print_status(f"Failed to create desktop entry: {e}", "error")
        return False


def create_slap_cli():
    """Create the SLAP CLI script."""
    cli_path = SCRIPT_DIR / "slap_cli.py"

    cli_content = '''#!/usr/bin/env python3
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
        BOLD = "\\033[1m"
        RED = "\\033[0;31m"
        GREEN = "\\033[0;32m"
        YELLOW = "\\033[1;33m"
        BLUE = "\\033[0;34m"
        CYAN = "\\033[0;96m"
        NC = "\\033[0m"
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
                input=password + "\\n",
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
        entry += f"\\n  Exception: {type(exception).__name__}: {exception}"

    try:
        with open(ERROR_LOG, "a") as f:
            f.write(entry + "\\n")
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
                print(f"\\n  Access at: {Colors.GREEN}https://{hostname}{Colors.NC}\\n")
            else:
                port = args.port or settings.get("port", 9876)
                print(f"\\n  Access at: {Colors.GREEN}http://localhost:{port}{Colors.NC}\\n")
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
            print(f"\\n  Access at: {Colors.GREEN}https://{hostname}{Colors.NC}\\n")
        else:
            print(f"\\n  Access at: {Colors.GREEN}http://localhost:{port}{Colors.NC}\\n")

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
    print(f"\\n  Access at: {Colors.GREEN}https://{hostname}{Colors.NC}\\n")
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
        print(f"\\n{Colors.BOLD}SLAP Configuration:{Colors.NC}")
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
'''

    try:
        cli_path.write_text(cli_content)
        cli_path.chmod(0o755)
        print_status(f"Created CLI: {cli_path}", "success")
        return True
    except Exception as e:
        print_status(f"Failed to create CLI: {e}", "error")
        return False


def create_tray_icon_script():
    """Create the system tray icon script."""
    tray_path = SCRIPT_DIR / "slap_tray.py"

    tray_content = '''#!/usr/bin/env python3
"""
SLAP System Tray Icon
Provides quick access to SLAP controls and status.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    sys.exit(0)

# Paths
if os.name == 'nt':
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "slap"
    CONFIG_DIR = DATA_DIR / "config"
else:
    DATA_DIR = Path.home() / ".local" / "share" / "slap"
    CONFIG_DIR = Path.home() / ".config" / "slap"

SETTINGS_FILE = CONFIG_DIR / "settings.json"
PID_FILE = DATA_DIR / "slap.pid"
SCRIPT_DIR = Path(__file__).parent.resolve()


def load_settings():
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def is_running():
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        return False


def get_resource_usage():
    """Get CPU and memory usage of SLAP process."""
    if not PID_FILE.exists():
        return None, None

    try:
        pid = int(PID_FILE.read_text().strip())

        # Read from /proc on Linux
        if os.path.exists(f"/proc/{pid}/stat"):
            with open(f"/proc/{pid}/stat") as f:
                stat = f.read().split()

            # Get memory from statm
            with open(f"/proc/{pid}/statm") as f:
                statm = f.read().split()

            page_size = os.sysconf("SC_PAGE_SIZE")
            mem_mb = int(statm[1]) * page_size / (1024 * 1024)

            # CPU is harder to calculate accurately, use ps
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "%cpu", "--no-headers"],
                capture_output=True, text=True
            )
            cpu = result.stdout.strip() if result.returncode == 0 else "?"

            return f"{cpu}%", f"{mem_mb:.1f} MB"
    except Exception:
        pass

    return None, None


def create_icon_image():
    """Create the tray icon image."""
    # Try to load SLAP icon
    icon_path = SCRIPT_DIR / "src" / "slap" / "web" / "static" / "img" / "SLAP_icon.webp"

    try:
        if icon_path.exists():
            img = Image.open(icon_path)
            img = img.resize((64, 64), Image.Resampling.LANCZOS)
            return img
    except Exception:
        pass

    # Fallback: create a simple icon
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw a hockey puck shape
    draw.ellipse([8, 24, 56, 56], fill=(40, 40, 40), outline=(100, 100, 100))
    draw.ellipse([8, 16, 56, 48], fill=(60, 60, 60), outline=(120, 120, 120))

    # Add "S" for SLAP
    try:
        draw.text((24, 20), "S", fill=(0, 212, 255))
    except Exception:
        pass

    return img


def on_start(icon, item):
    subprocess.run(["slap", "start"])
    update_menu(icon)


def on_stop(icon, item):
    subprocess.run(["slap", "stop"])
    update_menu(icon)


def on_restart(icon, item):
    subprocess.run(["slap", "restart"])
    update_menu(icon)


def on_open_browser(icon, item):
    settings = load_settings()
    hostname = settings.get("hostname", "slap.localhost")
    port = settings.get("port", 9876)

    if settings.get("https_enabled"):
        url = f"https://{hostname}"
    else:
        url = f"http://localhost:{port}"

    subprocess.run(["xdg-open", url])


def on_quit(icon, item):
    icon.stop()


def update_menu(icon):
    """Update the menu with current status."""
    running = is_running()
    cpu, mem = get_resource_usage()
    settings = load_settings()

    status_text = "Running" if running else "Stopped"

    menu_items = [
        pystray.MenuItem(f"Status: {status_text}", None, enabled=False),
    ]

    if running and cpu and mem:
        menu_items.append(pystray.MenuItem(f"CPU: {cpu}  Memory: {mem}", None, enabled=False))

    menu_items.append(pystray.Menu.SEPARATOR)

    if running:
        menu_items.extend([
            pystray.MenuItem("Open in Browser", on_open_browser),
            pystray.MenuItem("Restart", on_restart),
            pystray.MenuItem("Stop", on_stop),
        ])
    else:
        menu_items.append(pystray.MenuItem("Start", on_start))

    menu_items.extend([
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Tray Icon", on_quit),
    ])

    icon.menu = pystray.Menu(*menu_items)


def status_updater(icon):
    """Background thread to update status periodically."""
    while icon.visible:
        try:
            update_menu(icon)
            time.sleep(5)
        except Exception:
            break


def main():
    if not TRAY_AVAILABLE:
        print("Tray icon not available - pystray not installed")
        sys.exit(0)

    icon = pystray.Icon(
        "SLAP",
        create_icon_image(),
        "SLAP - Scoreboard Live Automation Platform"
    )

    update_menu(icon)

    # Start status updater thread
    updater = threading.Thread(target=status_updater, args=(icon,), daemon=True)
    updater.start()

    icon.run()


if __name__ == "__main__":
    main()
'''

    try:
        tray_path.write_text(tray_content)
        tray_path.chmod(0o755)
        print_status(f"Created tray icon: {tray_path}", "success")
        return True
    except Exception as e:
        print_status(f"Failed to create tray icon: {e}", "error")
        return False


# ============================================================================
# HTTPS Setup
# ============================================================================

def setup_https(password=None):
    """Set up HTTPS with nginx."""
    print_header("Setting Up HTTPS")

    settings = load_settings()
    hostname = settings.get("hostname", "slap.localhost")
    port = settings.get("port", 9876)

    # Create SSL directory
    print_status("Creating SSL directory...")
    run_privileged(["mkdir", "-p", str(SSL_DIR)], password)

    # Generate certificate
    print_status("Generating SSL certificate...")
    result = run_privileged([
        "openssl", "req", "-x509", "-nodes", "-days", "365",
        "-newkey", "rsa:2048",
        "-keyout", str(SSL_DIR / "key.pem"),
        "-out", str(SSL_DIR / "cert.pem"),
        "-subj", f"/CN={hostname}",
        "-addext", f"subjectAltName=DNS:{hostname}"
    ], password)

    if not result:
        print_status("Failed to generate SSL certificate", "error")
        return False

    print_status("SSL certificate generated", "success")

    # Add to hosts
    hosts_content = HOSTS_FILE.read_text()
    if hostname not in hosts_content:
        print_status(f"Adding {hostname} to /etc/hosts...")
        run_privileged(["bash", "-c", f'echo "127.0.0.1 {hostname}" >> /etc/hosts'], password)
        print_status(f"Added {hostname} to /etc/hosts", "success")

    # Create nginx config
    nginx_config = f'''# SLAP - Scoreboard Live Automation Platform
# Auto-generated by deploy.py

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
    ssl_prefer_server_ciphers on;

    client_max_body_size 100M;

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
'''

    # Write config
    print_status("Creating nginx configuration...")
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        f.write(nginx_config)
        temp_path = f.name

    run_privileged(["cp", temp_path, str(NGINX_AVAILABLE / "slap.conf")], password)
    os.unlink(temp_path)
    print_status(f"Created {NGINX_AVAILABLE / 'slap.conf'}", "success")

    # Enable site
    run_privileged(["ln", "-sf", str(NGINX_AVAILABLE / "slap.conf"),
                   str(NGINX_ENABLED / "slap.conf")], password)
    print_status("Enabled nginx site", "success")

    # Test and reload
    print_status("Testing nginx configuration...")
    result = run_privileged(["nginx", "-t"], password, check=False)
    if not result or result.returncode != 0:
        print_status("nginx config test failed", "error")
        if result and result.stderr:
            print(result.stderr)
        return False

    print_status("nginx config test passed", "success")

    run_privileged(["systemctl", "reload", "nginx"], password)
    print_status("nginx reloaded", "success")

    # Update settings
    settings["https_enabled"] = True
    save_settings(settings)

    return True


# ============================================================================
# Systemd Service
# ============================================================================

def create_systemd_service():
    """Create systemd user service."""
    print_header("Creating Systemd Service")

    if not shutil.which("systemctl"):
        print_status("systemctl not found, skipping service setup", "warning")
        return True

    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)

    service_file = service_dir / "slap.service"
    python_path = VENV_DIR / "bin" / "python"

    settings = load_settings()
    port = settings.get("port", 9876)

    service_content = f'''[Unit]
Description=SLAP - Scoreboard Live Automation Platform
After=network.target

[Service]
Type=simple
Environment=HOME={Path.home()}
WorkingDirectory={SRC_DIR}
ExecStart={python_path} run.py --port {port}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
'''

    service_file.write_text(service_content)
    print_status(f"Service file created: {service_file}", "success")

    # Reload and enable
    run_cmd(["systemctl", "--user", "daemon-reload"])
    run_cmd(["systemctl", "--user", "enable", "slap"])
    print_status("Service enabled for autostart", "success")

    return True


# ============================================================================
# Uninstall
# ============================================================================

def uninstall(password=None):
    """Uninstall SLAP completely."""
    print_header("Uninstalling SLAP")

    # Stop service
    print_status("Stopping SLAP...")
    run_cmd(["systemctl", "--user", "stop", "slap"], check=False)
    run_cmd(["systemctl", "--user", "disable", "slap"], check=False)

    # Kill any running processes
    run_cmd(["pkill", "-f", "run.py"], check=False)
    run_cmd(["pkill", "-f", "slap_tray"], check=False)

    # Remove service file
    service_file = Path.home() / ".config" / "systemd" / "user" / "slap.service"
    if service_file.exists():
        service_file.unlink()
        print_status("Removed systemd service", "success")

    # Remove HTTPS config
    if (NGINX_AVAILABLE / "slap.conf").exists():
        run_privileged(["rm", "-f", str(NGINX_ENABLED / "slap.conf")], password)
        run_privileged(["rm", "-f", str(NGINX_AVAILABLE / "slap.conf")], password)
        run_privileged(["systemctl", "reload", "nginx"], password, check=False)
        print_status("Removed nginx configuration", "success")

    # Remove SSL certs
    if SSL_DIR.exists():
        run_privileged(["rm", "-rf", str(SSL_DIR)], password)
        print_status("Removed SSL certificates", "success")

    # Remove command
    slap_cmd = BIN_DIR / "slap"
    if slap_cmd.exists():
        slap_cmd.unlink()
        print_status("Removed slap command", "success")

    # Remove virtual environment
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)
        print_status("Removed virtual environment", "success")

    # Keep settings and data (user choice)
    print_status(f"Settings preserved in: {CONFIG_DIR}", "info")
    print_status(f"Data preserved in: {DATA_DIR}", "info")
    print_status("To remove completely: rm -rf ~/.config/slap ~/.local/share/slap", "info")

    print_status("SLAP uninstalled successfully", "success")


# ============================================================================
# Main Installation
# ============================================================================

def install():
    """Main installation function."""
    print_banner()

    # Check if uninstall requested
    if "--uninstall" in sys.argv:
        password = get_sudo_password() if not is_root() else None
        uninstall(password)
        return

    print_header("Starting Installation")

    # Check Python version
    if not check_python():
        sys.exit(1)

    # Get sudo password for system-level operations
    password = get_sudo_password() if not is_root() else None

    # Install system packages
    if not install_system_packages(password):
        print_status("Failed to install system packages", "error")
        sys.exit(1)

    # Setup directories
    setup_directories()

    # Initialize settings
    settings = load_settings()
    save_settings(settings)
    print_status(f"Settings initialized: {SETTINGS_FILE}", "success")

    # Create virtual environment
    if not create_venv():
        sys.exit(1)

    # Install Python dependencies
    if not install_python_deps():
        sys.exit(1)

    # Create CLI script
    if not create_slap_cli():
        sys.exit(1)

    # Create tray icon script
    create_tray_icon_script()

    # Create slap command
    if not create_slap_command():
        sys.exit(1)

    # Create systemd service
    create_systemd_service()

    # Create start menu entry
    create_desktop_entry()

    # Setup HTTPS
    print_status("Setting up HTTPS...")
    if setup_https(password):
        settings["https_enabled"] = True
        save_settings(settings)
    else:
        print_status("HTTPS setup failed - continuing without it", "warning")

    # Print success message
    print_header("Installation Complete!")

    settings = load_settings()
    hostname = settings.get("hostname", "slap.localhost")
    port = settings.get("port", 9876)

    print(f"""
{Colors.GREEN}SLAP has been installed successfully!{Colors.NC}

{Colors.BOLD}Quick Start:{Colors.NC}
  slap start              Start the server
  slap status             Check server status
  slap stop               Stop the server

{Colors.BOLD}Access:{Colors.NC}
  https://{hostname}    (recommended)
  http://localhost:{port}

{Colors.BOLD}Control Commands:{Colors.NC}
  slap -update            Update from GitHub
  slap -simulation:enable Enable simulation mode
  slap config             View/edit settings
  slap --help             Show all commands

{Colors.BOLD}Files:{Colors.NC}
  Settings: {SETTINGS_FILE}
  Logs:     {LOG_DIR}
  Data:     {DATA_DIR}

{Colors.YELLOW}Note:{Colors.NC} If 'slap' command is not found, run:
  source ~/.bashrc   (or restart your terminal)
""")

    # Start the server
    print_status("Starting SLAP server...")
    run_cmd([str(BIN_DIR / "slap"), "start"])


if __name__ == "__main__":
    try:
        install()
    except KeyboardInterrupt:
        print("\n\nInstallation cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Installation failed: {e}{Colors.NC}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
