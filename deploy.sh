#!/bin/bash
#
# SLAP - Scoreboard Live Automation Platform
# Deploy/Update/Uninstall Script
#
# Usage:
#   ./deploy.sh install    - Install SLAP and dependencies
#   ./deploy.sh update     - Update SLAP (pull latest, reinstall deps)
#   ./deploy.sh uninstall  - Remove SLAP installation
#   ./deploy.sh start      - Start SLAP server
#   ./deploy.sh stop       - Stop SLAP server
#   ./deploy.sh status     - Check if SLAP is running
#
# This script is idempotent - safe to run multiple times.
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/src"
VENV_DIR="$SRC_DIR/venv"
PID_FILE="/tmp/slap.pid"
LOG_FILE="/tmp/slap.log"
DEFAULT_PORT=8080

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

# Show help
show_help() {
    echo "SLAP - Scoreboard Live Automation Platform"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  install     Install SLAP and dependencies"
    echo "  update      Update SLAP (reinstall dependencies)"
    echo "  uninstall   Remove SLAP installation"
    echo "  start       Start SLAP server"
    echo "  stop        Stop SLAP server"
    echo "  status      Check if SLAP is running"
    echo "  help        Show this help message"
    echo ""
    echo "Start options:"
    echo "  --port, -p <port>   Web server port (default: 8080)"
    echo "  --simulate, -s      Run in simulation mode (default)"
    echo "  --debug, -d         Enable debug logging"
    echo ""
    echo "Examples:"
    echo "  $0 install"
    echo "  $0 start --port 9876 --simulate"
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
