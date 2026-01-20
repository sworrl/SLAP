#!/usr/bin/env python3
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
