"""
SLAP Web Application

Flask-based web interface with WebSocket support for real-time updates.
"""

import json
import logging
from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit
from pathlib import Path

from ..core.state import state, GameState
from ..config import get_config

logger = logging.getLogger(__name__)

socketio = SocketIO(cors_allowed_origins="*")

# References to simulator and serial (set by main app)
_simulator = None
_caspar_client = None
_obs_client = None
_serial_port = None
_serial_reader_active = False

# Mode: "preview" or "live"
_current_mode = "preview"


def set_simulator(sim):
    """Set the simulator instance for web control."""
    global _simulator
    _simulator = sim


def set_caspar_client(client):
    """Set the CasparCG client instance."""
    global _caspar_client
    _caspar_client = client


def set_obs_client(client):
    """Set the OBS client instance."""
    global _obs_client
    _obs_client = client


def set_serial_port(port):
    """Set the serial port instance."""
    global _serial_port
    _serial_port = port


def get_current_mode():
    """Get the current operating mode."""
    return _current_mode


def set_mode(mode):
    """Set the operating mode."""
    global _current_mode
    _current_mode = mode


def create_app(config_path=None) -> Flask:
    """
    Create and configure the Flask application.

    Args:
        config_path: Optional path to config file

    Returns:
        Configured Flask application
    """
    # Get paths
    base_dir = Path(__file__).parent
    template_dir = base_dir / "templates"
    static_dir = base_dir / "static"

    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir)
    )

    config = get_config()
    app.config["SECRET_KEY"] = "slap-secret-key"
    app.config["DEBUG"] = config.web.debug

    # Initialize SocketIO
    socketio.init_app(app)

    # Register state change listener
    def on_state_change():
        socketio.emit("state_update", state.to_dict())

    state.add_listener(on_state_change)

    # ============ Routes ============

    @app.route("/")
    def index():
        """Main dashboard page."""
        return render_template("index.html", config=get_config())

    @app.route("/scorebug")
    def scorebug():
        """Scorebug preview page (standalone)."""
        return render_template("scorebug_preview.html")

    @app.route("/templates/<path:filename>")
    def serve_template(filename):
        """Serve CasparCG template files."""
        templates_dir = Path(__file__).parent.parent.parent / "templates"
        return send_from_directory(str(templates_dir), filename)

    # ============ API Routes ============

    @app.route("/api/state", methods=["GET"])
    def get_state():
        """Get current system state."""
        return jsonify(state.to_dict())

    @app.route("/api/state", methods=["POST"])
    def update_state():
        """Update game state manually."""
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Update game state
        state.update_game(
            home_score=data.get("home", state.game.home_score),
            away_score=data.get("away", state.game.away_score),
            period=data.get("period", state.game.period),
            clock=data.get("clock", state.game.clock),
            home_penalties=data.get("home_penalties", state.game.home_penalties),
            away_penalties=data.get("away_penalties", state.game.away_penalties)
        )

        return jsonify({"status": "ok", "state": state.to_dict()})

    @app.route("/api/goal", methods=["POST"])
    def trigger_goal():
        """Trigger a goal event."""
        data = request.get_json() or {}
        side = data.get("side", "HOME").upper()

        if side not in ("HOME", "AWAY"):
            return jsonify({"error": "Invalid side, must be HOME or AWAY"}), 400

        # Update score
        if side == "HOME":
            state.update_game(
                home_score=state.game.home_score + 1,
                last_goal="HOME"
            )
        else:
            state.update_game(
                away_score=state.game.away_score + 1,
                last_goal="AWAY"
            )

        # Trigger CasparCG animation if connected
        if _caspar_client and _caspar_client.connected:
            _caspar_client.trigger_goal(side)

        return jsonify({"status": "ok", "side": side})

    @app.route("/api/penalty", methods=["POST"])
    def add_penalty():
        """Add a penalty."""
        data = request.get_json() or {}
        side = data.get("side", "HOME").upper()
        duration = data.get("duration", 120)  # Default 2 minutes

        if side not in ("HOME", "AWAY"):
            return jsonify({"error": "Invalid side"}), 400

        if side == "HOME":
            penalties = state.game.home_penalties.copy()
            if len(penalties) < 2:
                penalties.append(duration)
                state.update_game(home_penalties=penalties)
        else:
            penalties = state.game.away_penalties.copy()
            if len(penalties) < 2:
                penalties.append(duration)
                state.update_game(away_penalties=penalties)

        return jsonify({"status": "ok"})

    @app.route("/api/simulator/start", methods=["POST"])
    def start_simulator():
        """Start the game simulator."""
        if _simulator is None:
            return jsonify({"error": "Simulator not available"}), 503

        _simulator.start()
        state.simulator_running = True
        return jsonify({"status": "ok"})

    @app.route("/api/simulator/stop", methods=["POST"])
    def stop_simulator():
        """Stop the game simulator."""
        if _simulator is None:
            return jsonify({"error": "Simulator not available"}), 503

        _simulator.stop()
        state.simulator_running = False
        return jsonify({"status": "ok"})

    @app.route("/api/simulator/reset", methods=["POST"])
    def reset_simulator():
        """Reset the game simulator."""
        if _simulator is None:
            return jsonify({"error": "Simulator not available"}), 503

        _simulator.reset()
        state.update_game(
            home_score=0,
            away_score=0,
            period="1",
            clock="20:00",
            home_penalties=[],
            away_penalties=[],
            last_goal=None
        )
        return jsonify({"status": "ok"})

    @app.route("/api/bug/show", methods=["POST"])
    def show_bug():
        """Show the scorebug."""
        state.bug_visible = True
        if _caspar_client and _caspar_client.connected:
            _caspar_client.show_scorebug()
        return jsonify({"status": "ok"})

    @app.route("/api/bug/hide", methods=["POST"])
    def hide_bug():
        """Hide the scorebug."""
        state.bug_visible = False
        if _caspar_client and _caspar_client.connected:
            _caspar_client.hide_scorebug()
        return jsonify({"status": "ok"})

    @app.route("/api/config", methods=["GET"])
    def get_config_api():
        """Get current configuration."""
        cfg = get_config()
        return jsonify({
            "serial": {"port": cfg.serial.port, "baudrate": cfg.serial.baudrate},
            "caspar": {"host": cfg.caspar.host, "port": cfg.caspar.port, "enabled": cfg.caspar.enabled},
            "web": {"port": cfg.web.port},
            "simulator": {"enabled": cfg.simulator.enabled},
            "home_team": {"name": cfg.home_team.name, "color": cfg.home_team.color},
            "away_team": {"name": cfg.away_team.name, "color": cfg.away_team.color}
        })

    @app.route("/api/mode", methods=["GET"])
    def get_mode():
        """Get current operating mode."""
        return jsonify({
            "mode": _current_mode,
            "available_modes": ["preview", "live"]
        })

    @app.route("/api/mode", methods=["POST"])
    def switch_mode():
        """Switch between preview and live mode."""
        global _current_mode

        data = request.get_json() or {}
        new_mode = data.get("mode", "").lower()

        if new_mode not in ("preview", "live"):
            return jsonify({"error": "Invalid mode. Use 'preview' or 'live'"}), 400

        old_mode = _current_mode
        _current_mode = new_mode

        if new_mode == "preview":
            # Switch to preview: start simulator, use mock CasparCG
            if _simulator:
                _simulator.reset()
                _simulator.start()
                state.simulator_running = True
            state.serial_connected = True  # Simulated
            logger.info("Switched to PREVIEW mode")

        elif new_mode == "live":
            # Switch to live: stop simulator, connect to real hardware
            if _simulator:
                _simulator.stop()
                state.simulator_running = False

            # Try to connect to CasparCG
            if _caspar_client:
                if _caspar_client.connect():
                    state.caspar_connected = True
                    logger.info("Connected to CasparCG")
                else:
                    state.caspar_connected = False
                    logger.warning("Could not connect to CasparCG")

            logger.info("Switched to LIVE mode")

        # Notify all clients
        socketio.emit("mode_change", {"mode": _current_mode, "previous": old_mode})
        socketio.emit("state_update", state.to_dict())

        return jsonify({"status": "ok", "mode": _current_mode})

    # ============ CasparCG Server Control API ============

    @app.route("/api/caspar/status", methods=["GET"])
    def caspar_server_status():
        """Get CasparCG server status."""
        import subprocess
        import os

        result = {
            "installed": False,
            "running": False,
            "binary": None,
            "amcp_port": 5250,
            "amcp_listening": False,
            "connected": state.caspar_connected
        }

        # Check if installed
        caspar_paths = [
            os.path.expanduser("~/.local/bin/casparcg"),
            os.path.expanduser("~/.local/share/casparcg/bin/casparcg"),
            "/usr/bin/casparcg",
            "/opt/casparcg/bin/casparcg"
        ]

        for path in caspar_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                result["installed"] = True
                result["binary"] = path
                break

        # Check if binary exists via which
        if not result["installed"]:
            try:
                which_result = subprocess.run(["which", "casparcg"], capture_output=True, text=True)
                if which_result.returncode == 0:
                    result["installed"] = True
                    result["binary"] = which_result.stdout.strip()
            except:
                pass

        # Check if running
        pid_file = "/tmp/casparcg.pid"
        if os.path.exists(pid_file):
            try:
                with open(pid_file) as f:
                    pid = int(f.read().strip())
                # Check if process exists
                os.kill(pid, 0)
                result["running"] = True
                result["pid"] = pid
            except (ValueError, ProcessLookupError, PermissionError):
                pass

        # Also check by process name
        if not result["running"]:
            try:
                pgrep = subprocess.run(["pgrep", "-f", "casparcg"], capture_output=True, text=True)
                if pgrep.returncode == 0 and pgrep.stdout.strip():
                    result["running"] = True
                    result["pid"] = int(pgrep.stdout.strip().split()[0])
            except:
                pass

        # Check if AMCP port is listening
        try:
            ss = subprocess.run(["ss", "-tln"], capture_output=True, text=True)
            if ":5250 " in ss.stdout:
                result["amcp_listening"] = True
        except:
            pass

        return jsonify(result)

    @app.route("/api/caspar/start", methods=["POST"])
    def caspar_server_start():
        """Start CasparCG server."""
        import subprocess
        import os

        # Check if already running
        pid_file = "/tmp/casparcg.pid"
        if os.path.exists(pid_file):
            try:
                with open(pid_file) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                return jsonify({"status": "ok", "message": "CasparCG already running", "pid": pid})
            except:
                pass

        # Find binary
        caspar_bin = None
        caspar_paths = [
            os.path.expanduser("~/.local/bin/casparcg"),
            os.path.expanduser("~/.local/share/casparcg/bin/casparcg"),
            "/usr/bin/casparcg",
            "/opt/casparcg/bin/casparcg"
        ]

        for path in caspar_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                caspar_bin = path
                break

        if not caspar_bin:
            try:
                which_result = subprocess.run(["which", "casparcg"], capture_output=True, text=True)
                if which_result.returncode == 0:
                    caspar_bin = which_result.stdout.strip()
            except:
                pass

        if not caspar_bin:
            return jsonify({"error": "CasparCG not installed"}), 404

        # Determine working directory
        caspar_dir = os.path.expanduser("~/.local/share/casparcg")
        if not os.path.isdir(caspar_dir):
            caspar_dir = os.path.dirname(caspar_bin)

        # Set library path
        env = os.environ.copy()
        lib_path = os.path.join(os.path.expanduser("~/.local/share/casparcg"), "lib")
        if os.path.isdir(lib_path):
            env["LD_LIBRARY_PATH"] = lib_path + ":" + env.get("LD_LIBRARY_PATH", "")

        # Start CasparCG
        log_file = "/tmp/casparcg.log"
        try:
            with open(log_file, "w") as log:
                process = subprocess.Popen(
                    [caspar_bin],
                    cwd=caspar_dir,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True
                )

            with open(pid_file, "w") as f:
                f.write(str(process.pid))

            # Wait briefly and check if running
            import time
            time.sleep(2)

            try:
                os.kill(process.pid, 0)
                logger.info(f"CasparCG started with PID {process.pid}")
                return jsonify({"status": "ok", "pid": process.pid})
            except ProcessLookupError:
                return jsonify({"error": "CasparCG failed to start", "log": log_file}), 500

        except Exception as e:
            logger.error(f"Failed to start CasparCG: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/caspar/stop", methods=["POST"])
    def caspar_server_stop():
        """Stop CasparCG server."""
        import os
        import signal

        pid_file = "/tmp/casparcg.pid"
        pid = None

        # Get PID from file
        if os.path.exists(pid_file):
            try:
                with open(pid_file) as f:
                    pid = int(f.read().strip())
            except:
                pass

        # Also check by process name
        if not pid:
            import subprocess
            try:
                pgrep = subprocess.run(["pgrep", "-f", "casparcg"], capture_output=True, text=True)
                if pgrep.returncode == 0 and pgrep.stdout.strip():
                    pid = int(pgrep.stdout.strip().split()[0])
            except:
                pass

        if not pid:
            return jsonify({"status": "ok", "message": "CasparCG not running"})

        # Stop the process
        try:
            os.kill(pid, signal.SIGTERM)
            import time
            time.sleep(2)

            # Force kill if still running
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

            logger.info(f"CasparCG stopped (PID: {pid})")
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.error(f"Error stopping CasparCG: {e}")

        # Remove PID file
        try:
            os.remove(pid_file)
        except:
            pass

        # Update state
        state.caspar_connected = False

        return jsonify({"status": "ok"})

    @app.route("/api/caspar/connect", methods=["POST"])
    def caspar_connect():
        """Connect SLAP to CasparCG."""
        if _caspar_client:
            if _caspar_client.connect():
                state.caspar_connected = True
                return jsonify({"status": "ok", "connected": True})
            else:
                state.caspar_connected = False
                return jsonify({"status": "error", "connected": False, "error": "Connection failed"}), 503
        return jsonify({"error": "CasparCG client not configured"}), 503

    @app.route("/api/caspar/disconnect", methods=["POST"])
    def caspar_disconnect():
        """Disconnect SLAP from CasparCG."""
        if _caspar_client:
            _caspar_client.disconnect()
            state.caspar_connected = False
        return jsonify({"status": "ok", "connected": False})

    # ============ OBS Control API ============

    @app.route("/api/obs/status", methods=["GET"])
    def obs_status():
        """Get OBS status."""
        import subprocess
        import os

        result = {
            "installed": False,
            "running": False,
            "binary": None,
            "websocket_port": 4455,
            "websocket_listening": False,
            "connected": _obs_client.connected if _obs_client else False,
            "version": None,
            "current_scene": None
        }

        # Check if installed
        obs_paths = [
            "/usr/bin/obs",
            "/usr/bin/obs-studio",
            "/snap/bin/obs-studio",
            "/var/lib/flatpak/exports/bin/com.obsproject.Studio",
            os.path.expanduser("~/.local/share/flatpak/exports/bin/com.obsproject.Studio")
        ]

        for path in obs_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                result["installed"] = True
                result["binary"] = path
                break

        # Check if binary exists via which
        if not result["installed"]:
            try:
                which_result = subprocess.run(["which", "obs"], capture_output=True, text=True)
                if which_result.returncode == 0:
                    result["installed"] = True
                    result["binary"] = which_result.stdout.strip()
            except:
                pass

        # Check if running
        try:
            pgrep = subprocess.run(["pgrep", "-f", "obs"], capture_output=True, text=True)
            if pgrep.returncode == 0 and pgrep.stdout.strip():
                result["running"] = True
                result["pid"] = int(pgrep.stdout.strip().split()[0])
        except:
            pass

        # Check if WebSocket port is listening
        try:
            ss = subprocess.run(["ss", "-tln"], capture_output=True, text=True)
            if ":4455 " in ss.stdout:
                result["websocket_listening"] = True
        except:
            pass

        # Get OBS info if connected
        if _obs_client and _obs_client.connected:
            result["version"] = _obs_client.get_version()
            result["current_scene"] = _obs_client.get_current_scene()

        return jsonify(result)

    @app.route("/api/obs/start", methods=["POST"])
    def obs_start():
        """Start OBS Studio."""
        import subprocess
        import os

        # Check if already running
        try:
            pgrep = subprocess.run(["pgrep", "-f", "obs"], capture_output=True, text=True)
            if pgrep.returncode == 0 and pgrep.stdout.strip():
                pid = int(pgrep.stdout.strip().split()[0])
                return jsonify({"status": "ok", "message": "OBS already running", "pid": pid})
        except:
            pass

        # Find binary
        obs_bin = None
        obs_paths = [
            "/usr/bin/obs",
            "/usr/bin/obs-studio",
            "/snap/bin/obs-studio",
            "/var/lib/flatpak/exports/bin/com.obsproject.Studio",
            os.path.expanduser("~/.local/share/flatpak/exports/bin/com.obsproject.Studio")
        ]

        for path in obs_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                obs_bin = path
                break

        if not obs_bin:
            try:
                which_result = subprocess.run(["which", "obs"], capture_output=True, text=True)
                if which_result.returncode == 0:
                    obs_bin = which_result.stdout.strip()
            except:
                pass

        if not obs_bin:
            return jsonify({"error": "OBS not installed"}), 404

        # Start OBS
        try:
            with open("/tmp/obs.log", "w") as log:
                process = subprocess.Popen(
                    [obs_bin],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )

            # Wait briefly and check if running
            import time
            time.sleep(2)

            try:
                os.kill(process.pid, 0)
                logger.info(f"OBS started with PID {process.pid}")
                return jsonify({"status": "ok", "pid": process.pid})
            except ProcessLookupError:
                return jsonify({"error": "OBS failed to start", "log": "/tmp/obs.log"}), 500

        except Exception as e:
            logger.error(f"Failed to start OBS: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/obs/stop", methods=["POST"])
    def obs_stop():
        """Stop OBS Studio."""
        import subprocess
        import os
        import signal

        # Find OBS PIDs
        try:
            pgrep = subprocess.run(["pgrep", "-f", "obs"], capture_output=True, text=True)
            if pgrep.returncode != 0 or not pgrep.stdout.strip():
                return jsonify({"status": "ok", "message": "OBS not running"})

            pids = [int(p) for p in pgrep.stdout.strip().split()]
        except:
            return jsonify({"status": "ok", "message": "OBS not running"})

        # Stop the processes
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except:
                pass

        import time
        time.sleep(2)

        # Force kill if still running
        try:
            pgrep = subprocess.run(["pgrep", "-f", "obs"], capture_output=True, text=True)
            if pgrep.returncode == 0 and pgrep.stdout.strip():
                for pid in [int(p) for p in pgrep.stdout.strip().split()]:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except:
                        pass
        except:
            pass

        # Disconnect client
        if _obs_client:
            _obs_client.disconnect()

        logger.info("OBS stopped")
        return jsonify({"status": "ok"})

    @app.route("/api/obs/connect", methods=["POST"])
    def obs_connect():
        """Connect to OBS WebSocket."""
        global _obs_client

        data = request.get_json() or {}
        host = data.get("host", "localhost")
        port = data.get("port", 4455)
        password = data.get("password", "")

        # Create client if needed
        if _obs_client is None:
            from ..output.obs import OBSClient
            _obs_client = OBSClient(host=host, port=port, password=password)
        else:
            _obs_client.host = host
            _obs_client.port = port
            _obs_client.password = password

        if _obs_client.connect():
            return jsonify({
                "status": "ok",
                "connected": True,
                "version": _obs_client.get_version(),
                "current_scene": _obs_client.get_current_scene()
            })
        else:
            return jsonify({
                "status": "error",
                "connected": False,
                "error": "Connection failed. Check OBS WebSocket settings."
            }), 503

    @app.route("/api/obs/disconnect", methods=["POST"])
    def obs_disconnect():
        """Disconnect from OBS WebSocket."""
        if _obs_client:
            _obs_client.disconnect()
        return jsonify({"status": "ok", "connected": False})

    @app.route("/api/obs/scenes", methods=["GET"])
    def obs_scenes():
        """Get list of OBS scenes."""
        if not _obs_client or not _obs_client.connected:
            return jsonify({"error": "Not connected to OBS"}), 503

        scenes = _obs_client.get_scene_list()
        current = _obs_client.get_current_scene()
        return jsonify({
            "scenes": scenes,
            "current_scene": current
        })

    @app.route("/api/obs/sources", methods=["GET"])
    def obs_sources():
        """Get list of sources in current scene."""
        if not _obs_client or not _obs_client.connected:
            return jsonify({"error": "Not connected to OBS"}), 503

        scene = request.args.get("scene")
        sources = _obs_client.get_source_list(scene)
        return jsonify({"sources": sources, "scene": scene or _obs_client.get_current_scene()})

    @app.route("/api/obs/setup-scorebug", methods=["POST"])
    def obs_setup_scorebug():
        """Set up SLAP scorebug overlay in OBS."""
        if not _obs_client or not _obs_client.connected:
            return jsonify({"error": "Not connected to OBS"}), 503

        data = request.get_json() or {}
        slap_url = data.get("slap_url", f"http://localhost:{get_config().web.port}")

        if _obs_client.setup_scorebug(slap_url):
            return jsonify({
                "status": "ok",
                "message": "Scorebug overlay created in current scene",
                "source_name": "SLAP Scorebug"
            })
        else:
            return jsonify({"error": "Failed to create scorebug overlay"}), 500

    @app.route("/api/obs/scorebug/show", methods=["POST"])
    def obs_scorebug_show():
        """Show the scorebug overlay in OBS."""
        if not _obs_client or not _obs_client.connected:
            return jsonify({"error": "Not connected to OBS"}), 503

        if _obs_client.set_source_visible("SLAP Scorebug", True):
            return jsonify({"status": "ok", "visible": True})
        else:
            return jsonify({"error": "Failed to show scorebug"}), 500

    @app.route("/api/obs/scorebug/hide", methods=["POST"])
    def obs_scorebug_hide():
        """Hide the scorebug overlay in OBS."""
        if not _obs_client or not _obs_client.connected:
            return jsonify({"error": "Not connected to OBS"}), 503

        if _obs_client.set_source_visible("SLAP Scorebug", False):
            return jsonify({"status": "ok", "visible": False})
        else:
            return jsonify({"error": "Failed to hide scorebug"}), 500

    @app.route("/api/obs/scorebug/refresh", methods=["POST"])
    def obs_scorebug_refresh():
        """Refresh the scorebug browser source."""
        if not _obs_client or not _obs_client.connected:
            return jsonify({"error": "Not connected to OBS"}), 503

        if _obs_client.refresh_browser_source("SLAP Scorebug"):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"error": "Failed to refresh scorebug"}), 500

    # ============ WebSocket Events ============

    @socketio.on("connect")
    def handle_connect():
        """Handle client connection."""
        logger.info("WebSocket client connected")
        emit("state_update", state.to_dict())

    @socketio.on("disconnect")
    def handle_disconnect():
        """Handle client disconnection."""
        logger.info("WebSocket client disconnected")

    @socketio.on("request_state")
    def handle_request_state():
        """Handle state request from client."""
        emit("state_update", state.to_dict())

    @socketio.on("update_score")
    def handle_update_score(data):
        """Handle score update from client."""
        state.update_game(
            home_score=data.get("home", state.game.home_score),
            away_score=data.get("away", state.game.away_score)
        )

    @socketio.on("update_clock")
    def handle_update_clock(data):
        """Handle clock update from client."""
        state.update_game(clock=data.get("clock", state.game.clock))

    @socketio.on("update_period")
    def handle_update_period(data):
        """Handle period update from client."""
        state.update_game(period=data.get("period", state.game.period))

    return app
