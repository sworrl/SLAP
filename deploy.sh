#!/bin/bash
#
# SLAP - Scoreboard Live Automation Platform
# Deploy/Update/Uninstall Script
#
# Usage:
#   ./deploy.sh install         - Install SLAP and dependencies
#   ./deploy.sh update          - Update SLAP (pull latest, reinstall deps)
#   ./deploy.sh uninstall       - Remove SLAP installation
#   ./deploy.sh start           - Start SLAP server
#   ./deploy.sh stop            - Stop SLAP server
#   ./deploy.sh status          - Check if SLAP is running
#   ./deploy.sh caspar-install  - Install CasparCG server
#   ./deploy.sh caspar-start    - Start CasparCG server
#   ./deploy.sh caspar-stop     - Stop CasparCG server
#   ./deploy.sh caspar-status   - Check CasparCG status
#
# This script is idempotent - safe to run multiple times.
# Works on immutable Linux systems (installs to ~/.local/)
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/src"
VENV_DIR="$SRC_DIR/venv"
PID_FILE="/tmp/slap.pid"
LOG_FILE="/tmp/slap.log"
DEFAULT_PORT=9876

# CasparCG Configuration
CASPAR_LOCAL_DIR="$HOME/.local/share/casparcg"
CASPAR_BIN_DIR="$HOME/.local/bin"
CASPAR_PID_FILE="/tmp/casparcg.pid"
CASPAR_LOG_FILE="/tmp/casparcg.log"
CASPAR_VERSION="2.5.0-stable"

# OBS Configuration
OBS_WEBSOCKET_PORT=4455

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[SLAP]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SLAP]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[SLAP]${NC} $1"
}

print_error() {
    echo -e "${RED}[SLAP]${NC} $1"
}

# Check for Python 3
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        print_error "Python 3 is required but not found."
        print_error "Please install Python 3.8 or higher."
        exit 1
    fi

    # Check version
    PY_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.major)')
    PY_MINOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.minor)')

    if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 8 ]); then
        print_error "Python 3.8+ required, found $PY_VERSION"
        exit 1
    fi

    print_status "Found Python $PY_VERSION"
}

# Create virtual environment
create_venv() {
    if [ -d "$VENV_DIR" ]; then
        print_status "Virtual environment already exists"
    else
        print_status "Creating virtual environment..."
        $PYTHON_CMD -m venv "$VENV_DIR"
        print_success "Virtual environment created"
    fi
}

# Activate virtual environment
activate_venv() {
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
    elif [ -f "$VENV_DIR/Scripts/activate" ]; then
        source "$VENV_DIR/Scripts/activate"
    else
        print_error "Virtual environment not found. Run: $0 install"
        exit 1
    fi
}

# Install dependencies
install_deps() {
    print_status "Installing dependencies..."
    activate_venv
    pip install --quiet --upgrade pip
    pip install --quiet -r "$SRC_DIR/requirements.txt"
    print_success "Dependencies installed"
}

# Install SLAP
do_install() {
    print_status "Installing SLAP..."
    echo ""

    check_python
    create_venv
    install_deps

    echo ""
    print_success "========================================="
    print_success "SLAP installed successfully!"
    print_success "========================================="
    echo ""
    print_status "To start SLAP:"
    print_status "  $0 start"
    echo ""
    print_status "Or run manually:"
    print_status "  cd $SCRIPT_DIR"
    print_status "  source venv/bin/activate"
    print_status "  python run.py --simulate"
    echo ""
}

# Update SLAP
do_update() {
    print_status "Updating SLAP..."
    echo ""

    # If git repo, pull latest
    if [ -d "$SCRIPT_DIR/.git" ]; then
        print_status "Pulling latest changes..."
        cd "$SRC_DIR"
        git pull
    fi

    # Reinstall dependencies
    check_python
    create_venv
    install_deps

    echo ""
    print_success "SLAP updated successfully!"
    echo ""
}

# Uninstall SLAP
do_uninstall() {
    print_warning "Uninstalling SLAP..."
    echo ""

    # Stop if running
    do_stop 2>/dev/null || true

    # Remove virtual environment
    if [ -d "$VENV_DIR" ]; then
        print_status "Removing virtual environment..."
        rm -rf "$VENV_DIR"
    fi

    # Remove PID and log files
    rm -f "$PID_FILE" "$LOG_FILE"

    echo ""
    print_success "SLAP uninstalled."
    print_status "Source files remain in: $SCRIPT_DIR"
    print_status "To completely remove, delete the SLAP directory."
    echo ""
}

# Start SLAP
do_start() {
    # Check if already running
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            print_warning "SLAP is already running (PID: $OLD_PID)"
            print_status "URL: http://localhost:$DEFAULT_PORT"
            return 0
        else
            rm -f "$PID_FILE"
        fi
    fi

    # Check venv exists
    if [ ! -d "$VENV_DIR" ]; then
        print_error "SLAP not installed. Run: $0 install"
        exit 1
    fi

    print_status "Starting SLAP..."
    activate_venv

    # Parse additional arguments
    EXTRA_ARGS=""
    PORT=$DEFAULT_PORT
    shift 2>/dev/null || true
    while [[ $# -gt 0 ]]; do
        case $1 in
            --port|-p)
                PORT="$2"
                EXTRA_ARGS="$EXTRA_ARGS --port $2"
                shift 2
                ;;
            --live)
                EXTRA_ARGS="$EXTRA_ARGS"
                shift
                ;;
            --simulate|-s)
                EXTRA_ARGS="$EXTRA_ARGS --simulate"
                shift
                ;;
            --debug|-d)
                EXTRA_ARGS="$EXTRA_ARGS --debug"
                shift
                ;;
            *)
                EXTRA_ARGS="$EXTRA_ARGS $1"
                shift
                ;;
        esac
    done

    # Default to simulate mode if not specified
    if [[ ! "$EXTRA_ARGS" =~ "--simulate" ]] && [[ ! "$EXTRA_ARGS" =~ "--no-simulate" ]]; then
        EXTRA_ARGS="$EXTRA_ARGS --simulate"
    fi

    # Start in background
    cd "$SRC_DIR"
    nohup python run.py $EXTRA_ARGS > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"

    sleep 2

    if ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
        print_success "SLAP started (PID: $(cat $PID_FILE))"
        print_status "URL: http://localhost:$PORT"
        print_status "Log: $LOG_FILE"
    else
        print_error "Failed to start SLAP. Check log: $LOG_FILE"
        cat "$LOG_FILE"
        exit 1
    fi
}

# Stop SLAP
do_stop() {
    if [ ! -f "$PID_FILE" ]; then
        print_warning "SLAP is not running (no PID file)"
        return 0
    fi

    PID=$(cat "$PID_FILE")

    if ps -p "$PID" > /dev/null 2>&1; then
        print_status "Stopping SLAP (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
        sleep 2

        # Force kill if still running
        if ps -p "$PID" > /dev/null 2>&1; then
            kill -9 "$PID" 2>/dev/null || true
        fi

        print_success "SLAP stopped"
    else
        print_warning "SLAP process not found (stale PID file)"
    fi

    rm -f "$PID_FILE"
}

# Check status
do_status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            print_success "SLAP is running (PID: $PID)"

            # Try to get port from process
            PORT=$(ss -tlnp 2>/dev/null | grep "$PID" | awk '{print $4}' | grep -oE '[0-9]+$' | head -1)
            if [ -n "$PORT" ]; then
                print_status "URL: http://localhost:$PORT"
            fi
            return 0
        fi
    fi

    print_warning "SLAP is not running"
    return 1
}

# ============================================
# CasparCG Functions
# ============================================

# Detect Ubuntu version for package selection
get_ubuntu_codename() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "$VERSION_CODENAME" in
            jammy|kinetic|lunar)
                echo "jammy"
                ;;
            noble|mantic|oracular|questing|*)
                echo "noble"
                ;;
        esac
    else
        echo "noble"  # Default to noble
    fi
}

# Find CasparCG binary
find_casparcg() {
    # Check common locations
    if [ -x "$CASPAR_BIN_DIR/casparcg" ]; then
        echo "$CASPAR_BIN_DIR/casparcg"
    elif [ -x "$CASPAR_LOCAL_DIR/bin/casparcg" ]; then
        echo "$CASPAR_LOCAL_DIR/bin/casparcg"
    elif command -v casparcg &> /dev/null; then
        command -v casparcg
    elif [ -x "/usr/bin/casparcg" ]; then
        echo "/usr/bin/casparcg"
    elif [ -x "/opt/casparcg/bin/casparcg" ]; then
        echo "/opt/casparcg/bin/casparcg"
    else
        echo ""
    fi
}

# Check if CasparCG is installed
caspar_detect() {
    CASPAR_BIN=$(find_casparcg)
    if [ -n "$CASPAR_BIN" ]; then
        print_success "CasparCG found: $CASPAR_BIN"
        if [ -x "$CASPAR_BIN" ]; then
            VERSION=$("$CASPAR_BIN" --version 2>/dev/null | head -1 || echo "unknown")
            print_status "Version: $VERSION"
        fi
        return 0
    else
        print_warning "CasparCG not found"
        print_status "Install with: $0 caspar-install"
        return 1
    fi
}

# Install CasparCG
caspar_install() {
    print_status "Installing CasparCG..."
    echo ""

    # Check if already installed
    CASPAR_BIN=$(find_casparcg)
    if [ -n "$CASPAR_BIN" ]; then
        print_success "CasparCG already installed: $CASPAR_BIN"
        return 0
    fi

    # Detect Ubuntu version
    CODENAME=$(get_ubuntu_codename)
    print_status "Detected Ubuntu codename: $CODENAME"

    # Create directories
    mkdir -p "$CASPAR_LOCAL_DIR"
    mkdir -p "$CASPAR_BIN_DIR"
    mkdir -p "$CASPAR_LOCAL_DIR/templates"
    mkdir -p "$CASPAR_LOCAL_DIR/media"

    # Download URLs
    SERVER_DEB="casparcg-server-2.5_2.5.0.stable-${CODENAME}1_amd64.deb"
    if [ "$CODENAME" = "jammy" ]; then
        SERVER_DEB="casparcg-server-2.5_2.5.0.stable-${CODENAME}_amd64.deb"
    fi
    CEF_DEB="casparcg-cef-142_142.0.17.g60aac24+2-${CODENAME}1_amd64.deb"

    SERVER_URL="https://github.com/CasparCG/server/releases/download/v${CASPAR_VERSION}/${SERVER_DEB}"
    CEF_URL="https://github.com/CasparCG/server/releases/download/v${CASPAR_VERSION}/${CEF_DEB}"

    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"

    # Check if we can use dpkg (normal system) or need manual extraction (immutable)
    CAN_DPKG=false
    if command -v dpkg &> /dev/null; then
        # Test if we can write to /usr (not immutable)
        if touch /usr/.test_write 2>/dev/null; then
            rm -f /usr/.test_write
            CAN_DPKG=true
        fi
    fi

    if [ "$CAN_DPKG" = true ]; then
        print_status "Installing via dpkg (system-wide)..."

        # Download packages
        print_status "Downloading CasparCG server..."
        wget -q --show-progress -O server.deb "$SERVER_URL" || {
            print_error "Failed to download CasparCG server"
            rm -rf "$TEMP_DIR"
            exit 1
        }

        print_status "Downloading CasparCG CEF (HTML template support)..."
        wget -q --show-progress -O cef.deb "$CEF_URL" || {
            print_error "Failed to download CasparCG CEF"
            rm -rf "$TEMP_DIR"
            exit 1
        }

        # Install packages
        print_status "Installing packages (may require sudo)..."
        sudo dpkg -i cef.deb server.deb || {
            print_warning "Fixing dependencies..."
            sudo apt-get install -f -y
        }

    else
        print_status "Installing to user directory (immutable system compatible)..."

        # Download packages
        print_status "Downloading CasparCG server..."
        wget -q --show-progress -O server.deb "$SERVER_URL" || {
            print_error "Failed to download CasparCG server"
            rm -rf "$TEMP_DIR"
            exit 1
        }

        print_status "Downloading CasparCG CEF (HTML template support)..."
        wget -q --show-progress -O cef.deb "$CEF_URL" || {
            print_error "Failed to download CasparCG CEF"
            rm -rf "$TEMP_DIR"
            exit 1
        }

        # Extract .deb files (they're ar archives)
        print_status "Extracting packages..."

        # Extract CEF first
        mkdir -p cef_extract
        cd cef_extract
        ar x ../cef.deb
        tar -xf data.tar.* 2>/dev/null || tar -xzf data.tar.* 2>/dev/null || tar -xJf data.tar.* 2>/dev/null
        cp -r usr/lib/* "$CASPAR_LOCAL_DIR/lib/" 2>/dev/null || mkdir -p "$CASPAR_LOCAL_DIR/lib"
        if [ -d usr/lib ]; then
            cp -r usr/lib/* "$CASPAR_LOCAL_DIR/lib/"
        fi
        if [ -d usr/share ]; then
            cp -r usr/share/* "$CASPAR_LOCAL_DIR/share/" 2>/dev/null || true
        fi
        cd ..

        # Extract server
        mkdir -p server_extract
        cd server_extract
        ar x ../server.deb
        tar -xf data.tar.* 2>/dev/null || tar -xzf data.tar.* 2>/dev/null || tar -xJf data.tar.* 2>/dev/null
        if [ -d usr/bin ]; then
            cp -r usr/bin/* "$CASPAR_BIN_DIR/"
        fi
        if [ -d usr/lib ]; then
            cp -r usr/lib/* "$CASPAR_LOCAL_DIR/lib/" 2>/dev/null || true
        fi
        if [ -d usr/share/casparcg ]; then
            cp -r usr/share/casparcg/* "$CASPAR_LOCAL_DIR/"
        fi
        cd ..

        # Create wrapper script that sets library path
        cat > "$CASPAR_BIN_DIR/casparcg" << 'WRAPPER'
#!/bin/bash
CASPAR_DIR="$HOME/.local/share/casparcg"
export LD_LIBRARY_PATH="$CASPAR_DIR/lib:$LD_LIBRARY_PATH"
cd "$CASPAR_DIR"
exec "$CASPAR_DIR/bin/casparcg-bin" "$@"
WRAPPER
        chmod +x "$CASPAR_BIN_DIR/casparcg"

        # Move actual binary
        if [ -f "$CASPAR_BIN_DIR/casparcg-bin" ]; then
            mv "$CASPAR_BIN_DIR/casparcg-bin" "$CASPAR_LOCAL_DIR/bin/" 2>/dev/null || true
        fi
        mkdir -p "$CASPAR_LOCAL_DIR/bin"
        if [ -f "$CASPAR_BIN_DIR/casparcg" ] && [ ! -f "$CASPAR_LOCAL_DIR/bin/casparcg-bin" ]; then
            # The binary might have a different name
            for bin in "$CASPAR_BIN_DIR"/casparcg*; do
                if [ -x "$bin" ] && file "$bin" | grep -q "executable"; then
                    cp "$bin" "$CASPAR_LOCAL_DIR/bin/casparcg-bin"
                    break
                fi
            done
        fi
    fi

    # Cleanup
    cd /
    rm -rf "$TEMP_DIR"

    # Copy SLAP templates to CasparCG
    if [ -d "$SRC_DIR/templates" ]; then
        print_status "Installing SLAP templates..."
        cp -r "$SRC_DIR/templates/"* "$CASPAR_LOCAL_DIR/templates/" 2>/dev/null || true
    fi

    # Create default config if needed
    if [ ! -f "$CASPAR_LOCAL_DIR/casparcg.config" ]; then
        print_status "Creating default CasparCG config..."
        cat > "$CASPAR_LOCAL_DIR/casparcg.config" << 'CONFIG'
<?xml version="1.0" encoding="utf-8"?>
<configuration>
    <paths>
        <media-path>media/</media-path>
        <log-path>log/</log-path>
        <data-path>data/</data-path>
        <template-path>templates/</template-path>
    </paths>
    <channels>
        <channel>
            <video-mode>1080p5000</video-mode>
            <consumers>
                <screen>
                    <device>1</device>
                    <windowed>true</windowed>
                </screen>
            </consumers>
        </channel>
    </channels>
    <controllers>
        <tcp>
            <port>5250</port>
            <protocol>AMCP</protocol>
        </tcp>
    </controllers>
</configuration>
CONFIG
    fi

    # Verify installation
    echo ""
    CASPAR_BIN=$(find_casparcg)
    if [ -n "$CASPAR_BIN" ]; then
        print_success "========================================="
        print_success "CasparCG installed successfully!"
        print_success "========================================="
        echo ""
        print_status "Binary: $CASPAR_BIN"
        print_status "Config: $CASPAR_LOCAL_DIR/casparcg.config"
        print_status "Templates: $CASPAR_LOCAL_DIR/templates/"
        echo ""
        print_status "Start CasparCG with: $0 caspar-start"
    else
        print_error "CasparCG installation failed"
        exit 1
    fi
}

# Start CasparCG
caspar_start() {
    # Check if already running
    if [ -f "$CASPAR_PID_FILE" ]; then
        OLD_PID=$(cat "$CASPAR_PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            print_warning "CasparCG is already running (PID: $OLD_PID)"
            return 0
        else
            rm -f "$CASPAR_PID_FILE"
        fi
    fi

    CASPAR_BIN=$(find_casparcg)
    if [ -z "$CASPAR_BIN" ]; then
        print_error "CasparCG not found. Install with: $0 caspar-install"
        exit 1
    fi

    print_status "Starting CasparCG..."

    # Determine working directory
    if [ -d "$CASPAR_LOCAL_DIR" ]; then
        WORK_DIR="$CASPAR_LOCAL_DIR"
    else
        WORK_DIR=$(dirname "$CASPAR_BIN")
    fi

    # Start CasparCG
    cd "$WORK_DIR"
    export LD_LIBRARY_PATH="$CASPAR_LOCAL_DIR/lib:$LD_LIBRARY_PATH"
    nohup "$CASPAR_BIN" > "$CASPAR_LOG_FILE" 2>&1 &
    echo $! > "$CASPAR_PID_FILE"

    sleep 3

    if ps -p $(cat "$CASPAR_PID_FILE") > /dev/null 2>&1; then
        print_success "CasparCG started (PID: $(cat $CASPAR_PID_FILE))"
        print_status "AMCP port: 5250"
        print_status "Log: $CASPAR_LOG_FILE"
    else
        print_error "Failed to start CasparCG. Check log: $CASPAR_LOG_FILE"
        tail -20 "$CASPAR_LOG_FILE" 2>/dev/null || true
        exit 1
    fi
}

# Stop CasparCG
caspar_stop() {
    if [ ! -f "$CASPAR_PID_FILE" ]; then
        print_warning "CasparCG is not running (no PID file)"
        return 0
    fi

    PID=$(cat "$CASPAR_PID_FILE")

    if ps -p "$PID" > /dev/null 2>&1; then
        print_status "Stopping CasparCG (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
        sleep 2

        # Force kill if still running
        if ps -p "$PID" > /dev/null 2>&1; then
            kill -9 "$PID" 2>/dev/null || true
        fi

        print_success "CasparCG stopped"
    else
        print_warning "CasparCG process not found (stale PID file)"
    fi

    rm -f "$CASPAR_PID_FILE"
}

# CasparCG status
caspar_status() {
    # Check if binary exists
    CASPAR_BIN=$(find_casparcg)
    if [ -z "$CASPAR_BIN" ]; then
        print_warning "CasparCG not installed"
        print_status "Install with: $0 caspar-install"
        return 1
    fi

    print_status "CasparCG binary: $CASPAR_BIN"

    # Check if running
    if [ -f "$CASPAR_PID_FILE" ]; then
        PID=$(cat "$CASPAR_PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            print_success "CasparCG is running (PID: $PID)"

            # Check if AMCP port is listening
            if ss -tln | grep -q ":5250 "; then
                print_status "AMCP listening on port 5250"
            fi
            return 0
        fi
    fi

    # Also check by process name
    CASPAR_PIDS=$(pgrep -f "casparcg" 2>/dev/null || true)
    if [ -n "$CASPAR_PIDS" ]; then
        print_success "CasparCG is running (PID: $CASPAR_PIDS)"
        return 0
    fi

    print_warning "CasparCG is not running"
    return 1
}

# ============================================
# OBS Functions
# ============================================

# Find OBS binary
find_obs() {
    # Check common locations
    if command -v obs &> /dev/null; then
        command -v obs
    elif [ -x "/usr/bin/obs" ]; then
        echo "/usr/bin/obs"
    elif [ -x "/usr/bin/obs-studio" ]; then
        echo "/usr/bin/obs-studio"
    elif [ -x "/snap/bin/obs-studio" ]; then
        echo "/snap/bin/obs-studio"
    elif [ -x "/var/lib/flatpak/exports/bin/com.obsproject.Studio" ]; then
        echo "/var/lib/flatpak/exports/bin/com.obsproject.Studio"
    elif [ -x "$HOME/.local/share/flatpak/exports/bin/com.obsproject.Studio" ]; then
        echo "$HOME/.local/share/flatpak/exports/bin/com.obsproject.Studio"
    else
        echo ""
    fi
}

# Check if OBS is installed
obs_detect() {
    OBS_BIN=$(find_obs)
    if [ -n "$OBS_BIN" ]; then
        print_success "OBS found: $OBS_BIN"
        return 0
    else
        print_warning "OBS not found"
        print_status "Install OBS Studio from: https://obsproject.com/"
        return 1
    fi
}

# Start OBS
obs_start() {
    # Check if already running
    OBS_PIDS=$(pgrep -f "obs" 2>/dev/null || true)
    if [ -n "$OBS_PIDS" ]; then
        print_warning "OBS is already running (PID: $OBS_PIDS)"
        return 0
    fi

    OBS_BIN=$(find_obs)
    if [ -z "$OBS_BIN" ]; then
        print_error "OBS not found. Install from https://obsproject.com/"
        exit 1
    fi

    print_status "Starting OBS..."
    nohup "$OBS_BIN" > /tmp/obs.log 2>&1 &

    sleep 3

    OBS_PIDS=$(pgrep -f "obs" 2>/dev/null || true)
    if [ -n "$OBS_PIDS" ]; then
        print_success "OBS started (PID: $OBS_PIDS)"
        print_status "WebSocket port: $OBS_WEBSOCKET_PORT"
        echo ""
        print_warning "IMPORTANT: Enable WebSocket in OBS:"
        print_status "1. Go to Tools > WebSocket Server Settings"
        print_status "2. Check 'Enable WebSocket server'"
        print_status "3. Set port to $OBS_WEBSOCKET_PORT"
        print_status "4. (Optional) Set a password"
    else
        print_error "Failed to start OBS. Check log: /tmp/obs.log"
        exit 1
    fi
}

# Stop OBS
obs_stop() {
    OBS_PIDS=$(pgrep -f "obs" 2>/dev/null || true)
    if [ -z "$OBS_PIDS" ]; then
        print_warning "OBS is not running"
        return 0
    fi

    print_status "Stopping OBS (PID: $OBS_PIDS)..."
    kill $OBS_PIDS 2>/dev/null || true
    sleep 2

    # Force kill if still running
    OBS_PIDS=$(pgrep -f "obs" 2>/dev/null || true)
    if [ -n "$OBS_PIDS" ]; then
        kill -9 $OBS_PIDS 2>/dev/null || true
    fi

    print_success "OBS stopped"
}

# OBS status
obs_status() {
    # Check if binary exists
    OBS_BIN=$(find_obs)
    if [ -z "$OBS_BIN" ]; then
        print_warning "OBS not installed"
        print_status "Install from: https://obsproject.com/"
        return 1
    fi

    print_status "OBS binary: $OBS_BIN"

    # Check if running
    OBS_PIDS=$(pgrep -f "obs" 2>/dev/null || true)
    if [ -n "$OBS_PIDS" ]; then
        print_success "OBS is running (PID: $OBS_PIDS)"

        # Check if WebSocket port is listening
        if ss -tln | grep -q ":$OBS_WEBSOCKET_PORT "; then
            print_status "WebSocket listening on port $OBS_WEBSOCKET_PORT"
        else
            print_warning "WebSocket not listening on port $OBS_WEBSOCKET_PORT"
            print_status "Enable in OBS: Tools > WebSocket Server Settings"
        fi
        return 0
    fi

    print_warning "OBS is not running"
    return 1
}

# Show help
show_help() {
    echo "SLAP - Scoreboard Live Automation Platform"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "SLAP Commands:"
    echo "  install         Install SLAP and dependencies"
    echo "  update          Update SLAP (reinstall dependencies)"
    echo "  uninstall       Remove SLAP installation"
    echo "  start           Start SLAP server"
    echo "  stop            Stop SLAP server"
    echo "  status          Check if SLAP is running"
    echo ""
    echo "CasparCG Commands:"
    echo "  caspar-install  Install CasparCG server"
    echo "  caspar-start    Start CasparCG server"
    echo "  caspar-stop     Stop CasparCG server  "
    echo "  caspar-status   Check CasparCG status"
    echo ""
    echo "OBS Commands:"
    echo "  obs-start       Start OBS Studio"
    echo "  obs-stop        Stop OBS Studio"
    echo "  obs-status      Check OBS status"
    echo ""
    echo "Start options:"
    echo "  --port, -p <port>   Web server port (default: 9876)"
    echo "  --simulate, -s      Run in simulation mode (default)"
    echo "  --debug, -d         Enable debug logging"
    echo ""
    echo "Examples:"
    echo "  $0 install"
    echo "  $0 caspar-install"
    echo "  $0 caspar-start && $0 start"
    echo "  $0 stop"
    echo ""
}

# Main
case "${1:-help}" in
    install)
        do_install
        ;;
    update)
        do_update
        ;;
    uninstall)
        do_uninstall
        ;;
    start)
        do_start "$@"
        ;;
    stop)
        do_stop
        ;;
    status)
        do_status
        ;;
    caspar-install)
        caspar_install
        ;;
    caspar-start)
        caspar_start
        ;;
    caspar-stop)
        caspar_stop
        ;;
    caspar-status)
        caspar_status
        ;;
    caspar-detect)
        caspar_detect
        ;;
    obs-start)
        obs_start
        ;;
    obs-stop)
        obs_stop
        ;;
    obs-status)
        obs_status
        ;;
    obs-detect)
        obs_detect
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
