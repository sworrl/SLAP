"""
SLAP Web Application

Flask-based web interface with WebSocket support for real-time updates.
"""

import json
import logging
import threading
import time
from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit
from pathlib import Path

from ..core.state import state, GameState
from ..config import get_config
from ..db import get_db

logger = logging.getLogger(__name__)

socketio = SocketIO(cors_allowed_origins="*")

# References to simulator and serial (set by main app)
_simulator = None
_caspar_client = None
_obs_client = None
_serial_port = None
_serial_reader_active = False
_serial_reader_thread = None
_serial_reader_stop_event = None

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


def _web_serial_reader(serial_port, stop_event):
    """Serial reader thread for web-initiated connections."""
    global _serial_reader_active
    from ..parser.mp70 import MP70Parser, update_raw_data
    from ..core.hockey import HockeyLogic

    reader_logger = logging.getLogger("web_serial_reader")
    parser = MP70Parser()
    hockey_logic = HockeyLogic()
    buffer = bytearray()

    reader_logger.info("Web serial reader started")
    _serial_reader_active = True

    try:
        while not stop_event.is_set():
            if serial_port and serial_port.is_open and serial_port.in_waiting > 0:
                try:
                    data = serial_port.read(min(512, serial_port.in_waiting))
                    buffer.extend(data)
                    update_raw_data(data)
                    reader_logger.debug(f"RX ({len(data)} bytes): {data.hex(' ')}")

                    packets, buffer = parser.extract_packets(buffer)
                    for packet in packets:
                        game_data = parser.parse(packet)
                        if game_data:
                            state.update_game(
                                home_score=game_data.home_score,
                                away_score=game_data.away_score,
                                period=game_data.period,
                                clock=game_data.clock,
                                home_penalties=game_data.home_penalties,
                                away_penalties=game_data.away_penalties
                            )
                            event = hockey_logic.process_update(game_data.to_dict())
                            if event and event.startswith("GOAL_"):
                                side = event.replace("GOAL_", "")
                                reader_logger.info(f"GOAL detected: {side}")
                                state.update_game(last_goal=side)
                                if _caspar_client:
                                    _caspar_client.trigger_goal(side)
                            if _caspar_client and _caspar_client.connected:
                                _caspar_client.update_scorebug(game_data.to_dict())
                except Exception as e:
                    reader_logger.error(f"Serial read error: {e}")
                    time.sleep(1)
            time.sleep(0.01)
    except Exception as e:
        reader_logger.error(f"Web serial reader critical error: {e}")
    finally:
        _serial_reader_active = False
        reader_logger.info("Web serial reader stopped")


def _start_serial_reader():
    """Start the background serial reader thread."""
    global _serial_reader_thread, _serial_reader_stop_event
    _stop_serial_reader()

    if _serial_port is None:
        return

    _serial_reader_stop_event = threading.Event()
    _serial_reader_thread = threading.Thread(
        target=_web_serial_reader,
        args=(_serial_port, _serial_reader_stop_event),
        daemon=True
    )
    _serial_reader_thread.start()
    logger.info("Serial reader thread started")


def _stop_serial_reader():
    """Stop the background serial reader thread."""
    global _serial_reader_thread, _serial_reader_stop_event
    if _serial_reader_stop_event:
        _serial_reader_stop_event.set()
    if _serial_reader_thread and _serial_reader_thread.is_alive():
        _serial_reader_thread.join(timeout=2.0)
        logger.info("Serial reader thread stopped")
    _serial_reader_thread = None
    _serial_reader_stop_event = None


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

    @app.route("/overlay")
    def overlay():
        """
        Live scorebug overlay for broadcast/streaming.
        Use this URL in CasparCG or OBS Browser Source.
        """
        templates_dir = Path(__file__).parent.parent.parent / "templates"
        return send_from_directory(str(templates_dir), "scorebug.html")

    @app.route("/overlay/transparent")
    def overlay_transparent():
        """Scorebug overlay with transparent background for OBS."""
        templates_dir = Path(__file__).parent.parent.parent / "templates"
        return send_from_directory(str(templates_dir), "scorebug.html")

    @app.route("/templates/<path:filename>")
    def serve_template(filename):
        """Serve CasparCG template files."""
        templates_dir = Path(__file__).parent.parent.parent / "templates"
        return send_from_directory(str(templates_dir), filename)

    # ============ Overlay Routes ============

    @app.route("/overlay/<overlay_name>")
    def serve_overlay(overlay_name):
        """
        Serve individual broadcast overlays.
        Available overlays: goal, shots, penalty, player, period, intro, goalie, powerplay, stars, replay, ticker
        """
        overlays_dir = Path(__file__).parent.parent.parent / "templates" / "overlays"
        valid_overlays = ['goal', 'shots', 'penalty', 'player', 'period', 'intro', 'goalie', 'powerplay', 'stars', 'replay', 'ticker']

        if overlay_name not in valid_overlays:
            return jsonify({"error": f"Unknown overlay. Valid: {', '.join(valid_overlays)}"}), 404

        return send_from_directory(str(overlays_dir), f"{overlay_name}.html")

    @app.route("/api/overlays", methods=["GET"])
    def list_overlays():
        """List all available overlays with their URLs."""
        config = get_config()
        base_url = f"http://localhost:{config.web.port}"

        overlays = [
            {"name": "scorebug", "description": "Main scorebug", "url": f"{base_url}/overlay"},
            {"name": "goal", "description": "Goal celebration splash", "url": f"{base_url}/overlay/goal"},
            {"name": "shots", "description": "Shot on goal counter", "url": f"{base_url}/overlay/shots"},
            {"name": "penalty", "description": "Penalty box display", "url": f"{base_url}/overlay/penalty"},
            {"name": "player", "description": "Player card lower third", "url": f"{base_url}/overlay/player"},
            {"name": "period", "description": "Period summary", "url": f"{base_url}/overlay/period"},
            {"name": "intro", "description": "Game intro/matchup", "url": f"{base_url}/overlay/intro"},
            {"name": "goalie", "description": "Goalie statistics", "url": f"{base_url}/overlay/goalie"},
            {"name": "powerplay", "description": "Power play graphic", "url": f"{base_url}/overlay/powerplay"},
            {"name": "stars", "description": "Three stars of the game", "url": f"{base_url}/overlay/stars"},
            {"name": "replay", "description": "Replay bug indicator", "url": f"{base_url}/overlay/replay"},
            {"name": "ticker", "description": "Scores ticker/crawl", "url": f"{base_url}/overlay/ticker"},
        ]
        return jsonify({"overlays": overlays})

    # ============ Overlay Control API ============

    @app.route("/api/overlay/goal", methods=["POST"])
    def trigger_goal_splash():
        """Trigger goal splash overlay."""
        data = request.get_json() or {}

        goal_data = {
            "team": data.get("team", "home"),
            "number": data.get("number", "00"),
            "name": data.get("name", "GOAL SCORER"),
            "assists": data.get("assists", []),
            "period": data.get("period", state.game.period),
            "time": data.get("time", state.game.clock),
            "duration": data.get("duration", 5000)
        }

        socketio.emit("goal", goal_data)
        return jsonify({"status": "ok", "data": goal_data})

    @app.route("/api/overlay/goal/hide", methods=["POST"])
    def hide_goal_splash():
        """Hide goal splash overlay."""
        socketio.emit("hide_goal")
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/shots", methods=["POST"])
    def update_shots():
        """Update shot counter."""
        data = request.get_json() or {}
        socketio.emit("shots", data)
        return jsonify({"status": "ok", "data": data})

    @app.route("/api/overlay/penalty", methods=["POST"])
    def update_penalties():
        """Update penalty box display."""
        data = request.get_json() or {}
        socketio.emit("penalties", data)
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/penalty/add", methods=["POST"])
    def add_overlay_penalty():
        """Add a penalty to the penalty box."""
        data = request.get_json() or {}
        socketio.emit("add_penalty", data)
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/player", methods=["POST"])
    def show_player_card():
        """Show player card overlay."""
        data = request.get_json() or {}
        socketio.emit("show_player", data)
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/player/hide", methods=["POST"])
    def hide_player_card():
        """Hide player card overlay."""
        socketio.emit("hide_player")
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/period", methods=["POST"])
    def show_period_summary():
        """Show period summary overlay."""
        data = request.get_json() or {}

        # Fill in current game data if not provided
        if "homeScore" not in data:
            data["homeScore"] = state.game.home_score
        if "awayScore" not in data:
            data["awayScore"] = state.game.away_score
        if "period" not in data:
            data["period"] = state.game.period

        socketio.emit("period_summary", data)
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/period/hide", methods=["POST"])
    def hide_period_summary():
        """Hide period summary overlay."""
        socketio.emit("hide_period_summary")
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/intro", methods=["POST"])
    def show_game_intro():
        """Show game intro overlay."""
        data = request.get_json() or {}
        socketio.emit("game_intro", data)
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/intro/hide", methods=["POST"])
    def hide_game_intro():
        """Hide game intro overlay."""
        socketio.emit("hide_game_intro")
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/goalie", methods=["POST"])
    def show_goalie_stats():
        """Show goalie stats overlay."""
        data = request.get_json() or {}
        socketio.emit("show_goalie", data)
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/goalie/hide", methods=["POST"])
    def hide_goalie_stats():
        """Hide goalie stats overlay."""
        socketio.emit("hide_goalie")
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/powerplay", methods=["POST"])
    def show_powerplay():
        """Show power play overlay."""
        data = request.get_json() or {}
        socketio.emit("power_play", data)
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/powerplay/hide", methods=["POST"])
    def hide_powerplay():
        """Hide power play overlay."""
        socketio.emit("hide_power_play")
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/stars", methods=["POST"])
    def show_three_stars():
        """Show three stars overlay."""
        data = request.get_json() or {}
        socketio.emit("three_stars", data)
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/stars/hide", methods=["POST"])
    def hide_three_stars():
        """Hide three stars overlay."""
        socketio.emit("hide_three_stars")
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/replay", methods=["POST"])
    def show_replay():
        """Show replay bug."""
        data = request.get_json() or {}
        socketio.emit("replay", data)
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/replay/hide", methods=["POST"])
    def hide_replay():
        """Hide replay bug."""
        socketio.emit("hide_replay")
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/ticker", methods=["POST"])
    def show_ticker():
        """Show scores ticker."""
        data = request.get_json() or {}
        socketio.emit("ticker", data)
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/ticker/hide", methods=["POST"])
    def hide_ticker():
        """Hide scores ticker."""
        socketio.emit("hide_ticker")
        return jsonify({"status": "ok"})

    @app.route("/api/overlay/ticker/update", methods=["POST"])
    def update_ticker():
        """Update ticker scores."""
        data = request.get_json() or {}
        socketio.emit("update_ticker", data)
        return jsonify({"status": "ok"})

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

        # Check if simulation is enabled in settings
        settings_file = Path.home() / ".config" / "slap" / "settings.json"
        simulation_enabled = False
        if settings_file.exists():
            try:
                with open(settings_file) as f:
                    settings = json.load(f)
                simulation_enabled = settings.get("simulation_enabled", False)
            except Exception:
                pass

        if not simulation_enabled:
            return jsonify({"error": "Simulation mode is disabled. Enable via: slap -simulation:enable"}), 403

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

        # Load settings to check if simulation is enabled
        settings_file = Path.home() / ".config" / "slap" / "settings.json"
        simulation_enabled = False
        if settings_file.exists():
            try:
                with open(settings_file) as f:
                    settings = json.load(f)
                simulation_enabled = settings.get("simulation_enabled", False)
            except Exception:
                pass

        if new_mode == "preview":
            # Switch to preview: only start simulator if simulation is explicitly enabled
            if _simulator and simulation_enabled:
                _simulator.reset()
                _simulator.start()
                state.simulator_running = True
                state.serial_connected = True  # Simulated
                logger.info("Switched to PREVIEW mode with simulator")
            else:
                # Preview mode without simulator - just for viewing
                state.simulator_running = False
                logger.info("Switched to PREVIEW mode (no simulator)")

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

    # ============ Team Configuration API ============

    @app.route("/api/teams", methods=["GET"])
    def get_teams():
        """Get team configuration."""
        config = get_config()
        return jsonify({
            "home": {
                "name": getattr(config, 'home_team', {}).get('name', 'HOME') if isinstance(getattr(config, 'home_team', {}), dict) else config.home_team.name if hasattr(config, 'home_team') else 'HOME',
                "short_name": getattr(config, 'home_team', {}).get('short_name', 'HOM') if isinstance(getattr(config, 'home_team', {}), dict) else config.home_team.short_name if hasattr(config, 'home_team') else 'HOM',
                "logo": getattr(config, 'home_team', {}).get('logo', 'home.png') if isinstance(getattr(config, 'home_team', {}), dict) else config.home_team.logo if hasattr(config, 'home_team') else 'home.png',
                "primary_color": getattr(config, 'home_team', {}).get('color', '#1b6eb8') if isinstance(getattr(config, 'home_team', {}), dict) else config.home_team.color if hasattr(config, 'home_team') else '#1b6eb8',
                "secondary_color": getattr(config, 'home_team', {}).get('secondary_color', '#00529c') if isinstance(getattr(config, 'home_team', {}), dict) else getattr(config.home_team, 'secondary_color', '#00529c') if hasattr(config, 'home_team') else '#00529c',
            },
            "away": {
                "name": getattr(config, 'away_team', {}).get('name', 'AWAY') if isinstance(getattr(config, 'away_team', {}), dict) else config.away_team.name if hasattr(config, 'away_team') else 'AWAY',
                "short_name": getattr(config, 'away_team', {}).get('short_name', 'AWY') if isinstance(getattr(config, 'away_team', {}), dict) else config.away_team.short_name if hasattr(config, 'away_team') else 'AWY',
                "logo": getattr(config, 'away_team', {}).get('logo', 'away.png') if isinstance(getattr(config, 'away_team', {}), dict) else config.away_team.logo if hasattr(config, 'away_team') else 'away.png',
                "primary_color": getattr(config, 'away_team', {}).get('color', '#aa0000') if isinstance(getattr(config, 'away_team', {}), dict) else config.away_team.color if hasattr(config, 'away_team') else '#aa0000',
                "secondary_color": getattr(config, 'away_team', {}).get('secondary_color', '#780000') if isinstance(getattr(config, 'away_team', {}), dict) else getattr(config.away_team, 'secondary_color', '#780000') if hasattr(config, 'away_team') else '#780000',
            }
        })

    @app.route("/api/teams", methods=["POST"])
    def update_teams():
        """Update team configuration."""
        data = request.get_json() or {}
        config = get_config()

        # Update home team
        if "home" in data:
            home = data["home"]
            if hasattr(config, 'home_team'):
                if isinstance(config.home_team, dict):
                    config.home_team.update(home)
                else:
                    for key, value in home.items():
                        setattr(config.home_team, key, value)

        # Update away team
        if "away" in data:
            away = data["away"]
            if hasattr(config, 'away_team'):
                if isinstance(config.away_team, dict):
                    config.away_team.update(away)
                else:
                    for key, value in away.items():
                        setattr(config.away_team, key, value)

        # Broadcast update to all clients
        socketio.emit('teams_update', data)

        return jsonify({"status": "ok", "message": "Teams updated"})

    @app.route("/api/teams/logos", methods=["GET"])
    def list_logos():
        """List available logo files."""
        logos_dir = Path(__file__).parent.parent.parent / "templates" / "Logos"
        logos = []
        if logos_dir.exists():
            for f in logos_dir.iterdir():
                if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp']:
                    logos.append(f.name)
        return jsonify({"logos": sorted(logos)})

    @app.route("/api/teams/logo/upload", methods=["POST"])
    def upload_logo():
        """Upload a team logo."""
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400

        # Validate file type
        allowed_extensions = {'.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp'}
        ext = Path(file.filename).suffix.lower()
        if ext not in allowed_extensions:
            return jsonify({"error": f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"}), 400

        # Save file
        logos_dir = Path(__file__).parent.parent.parent / "templates" / "Logos"
        logos_dir.mkdir(parents=True, exist_ok=True)

        # Use provided name or original filename
        filename = request.form.get('name', file.filename)
        if not Path(filename).suffix:
            filename += ext

        filepath = logos_dir / filename
        file.save(str(filepath))

        return jsonify({"status": "ok", "filename": filename, "path": f"Logos/{filename}"})

    # ============ Serial Port API ============

    @app.route("/api/serial/ports", methods=["GET"])
    def serial_list_ports():
        """List available serial ports."""
        import serial.tools.list_ports
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append({
                "device": port.device,
                "description": port.description,
                "hwid": port.hwid
            })
        return jsonify({"ports": ports})

    @app.route("/api/serial/status", methods=["GET"])
    def serial_status():
        """Get current serial port status."""
        config = get_config()
        return jsonify({
            "configured_port": config.serial.port,
            "baudrate": config.serial.baudrate,
            "connected": state.serial_connected,
            "reader_active": _serial_reader_active,
            "simulator_mode": config.simulator.enabled
        })

    @app.route("/api/serial/config", methods=["POST"])
    def serial_config():
        """Configure serial port settings."""
        data = request.get_json() or {}
        config = get_config()

        if "port" in data:
            config.serial.port = data["port"]
        if "baudrate" in data:
            config.serial.baudrate = int(data["baudrate"])

        return jsonify({
            "status": "ok",
            "port": config.serial.port,
            "baudrate": config.serial.baudrate,
            "message": "Config updated. Restart SLAP to apply changes."
        })

    @app.route("/api/serial/disconnect", methods=["POST"])
    def serial_disconnect():
        """Disconnect/release the serial port and stop reader thread."""
        global _serial_port

        if _serial_port is None:
            return jsonify({"status": "ok", "message": "Serial port already disconnected"})

        try:
            # Stop reader thread first
            _stop_serial_reader()

            if hasattr(_serial_port, 'close'):
                _serial_port.close()
            _serial_port = None
            state.serial_connected = False
            logger.info("Serial port disconnected/released")
            return jsonify({"status": "ok", "message": "Serial port released"})
        except Exception as e:
            logger.error(f"Failed to disconnect serial: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/serial/connect", methods=["POST"])
    def serial_connect():
        """Connect/open the configured serial port and start reader thread."""
        global _serial_port

        config = get_config()
        if not config.serial.port:
            return jsonify({"error": "No serial port configured"}), 400

        # Stop existing reader and close port if any
        _stop_serial_reader()
        if _serial_port is not None:
            try:
                if hasattr(_serial_port, 'close'):
                    _serial_port.close()
            except:
                pass

        try:
            import serial
            _serial_port = serial.Serial(
                port=config.serial.port,
                baudrate=config.serial.baudrate,
                timeout=config.serial.timeout if hasattr(config.serial, 'timeout') else 0.1
            )
            state.serial_connected = True

            # Start reader thread to process incoming data
            _start_serial_reader()

            logger.info(f"Serial port connected with reader: {config.serial.port}")
            return jsonify({
                "status": "ok",
                "message": f"Connected to {config.serial.port} (reader started)",
                "port": config.serial.port,
                "baudrate": config.serial.baudrate
            })
        except Exception as e:
            _serial_port = None
            state.serial_connected = False
            logger.error(f"Failed to connect serial: {e}")
            return jsonify({"error": str(e)}), 500

    # ============ Roster Management API ============

    def get_roster_path():
        """Get the roster file path."""
        return Path(__file__).parent.parent.parent / "config" / "roster.json"

    def load_roster():
        """Load roster from JSON file."""
        roster_path = get_roster_path()
        if roster_path.exists():
            try:
                with open(roster_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load roster: {e}")
        return {"home": {"players": []}, "away": {"players": []}}

    def save_roster(roster):
        """Save roster to JSON file."""
        roster_path = get_roster_path()
        roster_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(roster_path, 'w') as f:
                json.dump(roster, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save roster: {e}")
            return False

    @app.route("/api/roster", methods=["GET"])
    def get_all_rosters():
        """Get all team rosters."""
        return jsonify(load_roster())

    @app.route("/api/roster/<team>", methods=["GET"])
    def get_team_roster(team):
        """Get roster for a specific team (home/away)."""
        if team not in ("home", "away"):
            return jsonify({"error": "Invalid team. Use 'home' or 'away'"}), 400

        roster = load_roster()
        return jsonify(roster.get(team, {"players": []}))

    @app.route("/api/roster/<team>", methods=["POST"])
    def update_team_roster(team):
        """Replace entire roster for a team."""
        if team not in ("home", "away"):
            return jsonify({"error": "Invalid team. Use 'home' or 'away'"}), 400

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        roster = load_roster()
        roster[team] = data

        if save_roster(roster):
            socketio.emit("roster_update", {team: data})
            return jsonify({"status": "ok", "message": f"{team.title()} roster updated"})
        else:
            return jsonify({"error": "Failed to save roster"}), 500

    @app.route("/api/roster/<team>/player", methods=["POST"])
    def add_player(team):
        """Add or update a player in the roster."""
        if team not in ("home", "away"):
            return jsonify({"error": "Invalid team. Use 'home' or 'away'"}), 400

        data = request.get_json()
        if not data or "number" not in data:
            return jsonify({"error": "Player number is required"}), 400

        roster = load_roster()
        players = roster.get(team, {}).get("players", [])

        # Create player object
        player = {
            "number": str(data.get("number", "0")),
            "name": data.get("name", "PLAYER").upper(),
            "position": data.get("position", "F").upper(),
            "goals": data.get("goals", 0),
            "assists": data.get("assists", 0)
        }

        # Check if player with this number exists
        found = False
        for i, p in enumerate(players):
            if p["number"] == player["number"]:
                players[i] = player
                found = True
                break

        if not found:
            players.append(player)

        # Sort by number
        players.sort(key=lambda x: int(x["number"]) if x["number"].isdigit() else 999)

        roster[team]["players"] = players

        if save_roster(roster):
            socketio.emit("roster_update", {team: roster[team]})
            return jsonify({"status": "ok", "player": player})
        else:
            return jsonify({"error": "Failed to save roster"}), 500

    @app.route("/api/roster/<team>/player/<number>", methods=["DELETE"])
    def remove_player(team, number):
        """Remove a player from the roster."""
        if team not in ("home", "away"):
            return jsonify({"error": "Invalid team. Use 'home' or 'away'"}), 400

        roster = load_roster()
        players = roster.get(team, {}).get("players", [])

        # Find and remove player
        original_len = len(players)
        players = [p for p in players if p["number"] != str(number)]

        if len(players) == original_len:
            return jsonify({"error": f"Player #{number} not found"}), 404

        roster[team]["players"] = players

        if save_roster(roster):
            socketio.emit("roster_update", {team: roster[team]})
            return jsonify({"status": "ok", "message": f"Player #{number} removed"})
        else:
            return jsonify({"error": "Failed to save roster"}), 500

    @app.route("/api/roster/<team>/player/<number>", methods=["GET"])
    def get_player(team, number):
        """Get a specific player by number."""
        if team not in ("home", "away"):
            return jsonify({"error": "Invalid team. Use 'home' or 'away'"}), 400

        roster = load_roster()
        players = roster.get(team, {}).get("players", [])

        for player in players:
            if player["number"] == str(number):
                return jsonify(player)

        return jsonify({"error": f"Player #{number} not found"}), 404

    @app.route("/api/roster/<team>/player/<number>/stats", methods=["POST"])
    def update_player_stats(team, number):
        """Update a player's game stats."""
        if team not in ("home", "away"):
            return jsonify({"error": "Invalid team. Use 'home' or 'away'"}), 400

        data = request.get_json() or {}
        roster = load_roster()
        players = roster.get(team, {}).get("players", [])

        for i, player in enumerate(players):
            if player["number"] == str(number):
                if "goals" in data:
                    players[i]["goals"] = data["goals"]
                if "assists" in data:
                    players[i]["assists"] = data["assists"]
                if "add_goal" in data:
                    players[i]["goals"] = players[i].get("goals", 0) + 1
                if "add_assist" in data:
                    players[i]["assists"] = players[i].get("assists", 0) + 1

                roster[team]["players"] = players
                if save_roster(roster):
                    socketio.emit("roster_update", {team: roster[team]})
                    return jsonify({"status": "ok", "player": players[i]})
                else:
                    return jsonify({"error": "Failed to save roster"}), 500

        return jsonify({"error": f"Player #{number} not found"}), 404

    @app.route("/api/roster/reset", methods=["POST"])
    def reset_roster_stats():
        """Reset all player stats to zero (new game)."""
        roster = load_roster()

        for team in ["home", "away"]:
            for player in roster.get(team, {}).get("players", []):
                player["goals"] = 0
                player["assists"] = 0

        if save_roster(roster):
            socketio.emit("roster_update", roster)
            return jsonify({"status": "ok", "message": "All stats reset to zero"})
        else:
            return jsonify({"error": "Failed to save roster"}), 500

    # ============ Database & History API ============

    @app.route("/api/games", methods=["GET"])
    def get_games():
        """Get recent games history."""
        db = get_db()
        limit = request.args.get("limit", 20, type=int)
        games = db.get_recent_games(limit=limit)
        return jsonify({"status": "ok", "games": [g.to_dict() for g in games]})

    @app.route("/api/games", methods=["POST"])
    def create_game():
        """Create a new game."""
        db = get_db()
        data = request.get_json() or {}
        game_id = db.create_game(
            home_team=data.get("home_team", state.game.home_name or "HOME"),
            away_team=data.get("away_team", state.game.away_name or "AWAY"),
            venue=data.get("venue", "")
        )
        return jsonify({"status": "ok", "game_id": game_id})

    @app.route("/api/games/current", methods=["GET"])
    def get_current_game():
        """Get the current in-progress game."""
        db = get_db()
        game = db.get_current_game()
        if game:
            return jsonify({"status": "ok", "game": game.to_dict()})
        return jsonify({"status": "ok", "game": None, "message": "No game in progress"})

    @app.route("/api/games/<int:game_id>", methods=["GET"])
    def get_game(game_id):
        """Get a specific game by ID."""
        db = get_db()
        game = db.get_game(game_id)
        if game:
            return jsonify({"status": "ok", "game": game.to_dict()})
        return jsonify({"error": "Game not found"}), 404

    @app.route("/api/games/<int:game_id>", methods=["PUT"])
    def update_game(game_id):
        """Update game details."""
        db = get_db()
        data = request.get_json() or {}
        success = db.update_game(game_id, **data)
        if success:
            return jsonify({"status": "ok"})
        return jsonify({"error": "Game not found or no updates made"}), 404

    @app.route("/api/games/<int:game_id>/end", methods=["POST"])
    def end_game(game_id):
        """Mark a game as ended."""
        db = get_db()
        data = request.get_json() or {}
        status = data.get("status", "final")
        success = db.end_game(game_id, status=status)
        if success:
            db.increment_games_played(game_id)
            return jsonify({"status": "ok"})
        return jsonify({"error": "Game not found"}), 404

    @app.route("/api/games/<int:game_id>", methods=["DELETE"])
    def delete_game(game_id):
        """Delete a game."""
        db = get_db()
        success = db.delete_game(game_id)
        if success:
            return jsonify({"status": "ok"})
        return jsonify({"error": "Game not found"}), 404

    @app.route("/api/games/<int:game_id>/summary", methods=["GET"])
    def get_game_summary(game_id):
        """Get complete game summary with events."""
        db = get_db()
        summary = db.export_game_summary(game_id)
        if summary:
            return jsonify({"status": "ok", **summary})
        return jsonify({"error": "Game not found"}), 404

    @app.route("/api/games/<int:game_id>/events", methods=["GET"])
    def get_game_events(game_id):
        """Get all events for a game."""
        db = get_db()
        event_type = request.args.get("type")
        events = db.get_game_events(game_id, event_type=event_type)
        return jsonify({"status": "ok", "events": [e.to_dict() for e in events]})

    @app.route("/api/games/<int:game_id>/goal", methods=["POST"])
    def log_game_goal(game_id):
        """Log a goal for a game."""
        db = get_db()
        data = request.get_json() or {}
        event_id = db.log_goal(
            game_id=game_id,
            team=data.get("team", "home"),
            period=data.get("period", int(state.game.period) if state.game.period.isdigit() else 1),
            game_time=data.get("game_time", state.game.clock),
            player_number=data.get("player_number", ""),
            player_name=data.get("player_name", ""),
            assist1_number=data.get("assist1_number", ""),
            assist1_name=data.get("assist1_name", ""),
            assist2_number=data.get("assist2_number", ""),
            assist2_name=data.get("assist2_name", "")
        )
        return jsonify({"status": "ok", "event_id": event_id})

    @app.route("/api/games/<int:game_id>/penalty", methods=["POST"])
    def log_game_penalty(game_id):
        """Log a penalty for a game."""
        db = get_db()
        data = request.get_json() or {}
        event_id = db.log_penalty(
            game_id=game_id,
            team=data.get("team", "home"),
            period=data.get("period", int(state.game.period) if state.game.period.isdigit() else 1),
            game_time=data.get("game_time", state.game.clock),
            player_number=data.get("player_number", ""),
            player_name=data.get("player_name", ""),
            penalty_minutes=data.get("penalty_minutes", 2),
            penalty_type=data.get("penalty_type", "")
        )
        return jsonify({"status": "ok", "event_id": event_id})

    @app.route("/api/games/<int:game_id>/shot", methods=["POST"])
    def log_game_shot(game_id):
        """Log a shot for a game."""
        db = get_db()
        data = request.get_json() or {}
        db.log_shot(game_id, team=data.get("team", "home"))
        return jsonify({"status": "ok"})

    @app.route("/api/stats", methods=["GET"])
    def get_player_stats():
        """Get player statistics."""
        db = get_db()
        season = request.args.get("season")
        team = request.args.get("team")
        stats = db.get_player_stats(season=season, team=team)
        return jsonify({"status": "ok", "stats": [s.to_dict() for s in stats]})

    @app.route("/api/stats/leaders", methods=["GET"])
    def get_stat_leaders():
        """Get statistical leaders."""
        db = get_db()
        season = request.args.get("season")
        stat = request.args.get("stat", "points")
        limit = request.args.get("limit", 10, type=int)
        leaders = db.get_season_leaders(season=season, stat=stat, limit=limit)
        return jsonify({"status": "ok", "leaders": [l.to_dict() for l in leaders]})

    @app.route("/api/stats/team/<team>", methods=["GET"])
    def get_team_record(team):
        """Get team win/loss record."""
        db = get_db()
        season = request.args.get("season")
        record = db.get_team_record(team, season=season)
        return jsonify({"status": "ok", "team": team, "record": record})

    @app.route("/api/stats/h2h", methods=["GET"])
    def get_head_to_head():
        """Get head-to-head record between two teams."""
        db = get_db()
        team1 = request.args.get("team1")
        team2 = request.args.get("team2")
        if not team1 or not team2:
            return jsonify({"error": "Both team1 and team2 are required"}), 400
        h2h = db.get_head_to_head(team1, team2)
        return jsonify({"status": "ok", **h2h})

    # ============ System API ============

    @app.route("/api/system/update", methods=["POST"])
    def system_update():
        """Update SLAP from GitHub."""
        import subprocess
        import os
        from datetime import datetime

        try:
            script_dir = Path(__file__).parent.parent.parent.parent
            git_dir = script_dir / ".git"

            if not git_dir.exists():
                return jsonify({"error": "Not a git repository"}), 400

            # Pull from git
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=str(script_dir),
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                return jsonify({
                    "error": "Git pull failed",
                    "details": result.stderr
                }), 500

            # Update Python dependencies
            venv_pip = script_dir.parent / "venv" / "bin" / "pip"
            if not venv_pip.exists():
                venv_pip = Path.home() / ".local" / "share" / "slap" / "venv" / "bin" / "pip"

            requirements = script_dir / "src" / "requirements.txt"
            if venv_pip.exists() and requirements.exists():
                subprocess.run(
                    [str(venv_pip), "install", "--quiet", "-r", str(requirements)],
                    timeout=120
                )

            # Update settings
            settings_file = Path.home() / ".config" / "slap" / "settings.json"
            if settings_file.exists():
                with open(settings_file) as f:
                    settings = json.load(f)
                settings["last_update"] = datetime.now().isoformat()
                with open(settings_file, "w") as f:
                    json.dump(settings, f, indent=2)

            return jsonify({
                "status": "ok",
                "message": "Update successful. Restart SLAP to apply changes.",
                "output": result.stdout
            })

        except subprocess.TimeoutExpired:
            return jsonify({"error": "Update timed out"}), 500
        except Exception as e:
            logger.error(f"Update failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/system/errors", methods=["GET"])
    def get_error_log():
        """Get the error log."""
        error_log = Path.home() / ".local" / "share" / "slap" / "logs" / "error.log"

        lines = request.args.get("lines", 100, type=int)

        if not error_log.exists():
            return jsonify({"status": "ok", "errors": [], "message": "No errors logged"})

        try:
            content = error_log.read_text()
            log_lines = content.strip().split("\n")[-lines:]
            return jsonify({"status": "ok", "errors": log_lines})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/system/errors/clear", methods=["POST"])
    def clear_error_log():
        """Clear the error log."""
        error_log = Path.home() / ".local" / "share" / "slap" / "logs" / "error.log"

        try:
            if error_log.exists():
                error_log.write_text("")
            return jsonify({"status": "ok", "message": "Error log cleared"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/system/settings", methods=["GET"])
    def get_settings():
        """Get system settings."""
        settings_file = Path.home() / ".config" / "slap" / "settings.json"

        defaults = {
            "port": 9876,
            "hostname": "slap.localhost",
            "https_enabled": False,
            "simulation_enabled": False,
            "simulation_visible": False,
            "serial_port": None,
            "debug_mode": False,
            "tray_enabled": True,
        }

        if settings_file.exists():
            try:
                with open(settings_file) as f:
                    settings = json.load(f)
                # Merge with defaults
                for key, value in defaults.items():
                    if key not in settings:
                        settings[key] = value
                return jsonify({"status": "ok", "settings": settings})
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        return jsonify({"status": "ok", "settings": defaults})

    @app.route("/api/system/settings", methods=["POST"])
    def update_settings():
        """Update system settings."""
        settings_file = Path.home() / ".config" / "slap" / "settings.json"
        settings_file.parent.mkdir(parents=True, exist_ok=True)

        data = request.get_json() or {}

        # Load existing settings
        settings = {}
        if settings_file.exists():
            try:
                with open(settings_file) as f:
                    settings = json.load(f)
            except Exception:
                pass

        # Update with new values
        for key, value in data.items():
            settings[key] = value

        try:
            with open(settings_file, "w") as f:
                json.dump(settings, f, indent=2)
            return jsonify({"status": "ok", "settings": settings})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/system/status", methods=["GET"])
    def get_system_status():
        """Get system status information."""
        import os
        import platform

        settings_file = Path.home() / ".config" / "slap" / "settings.json"
        settings = {}
        if settings_file.exists():
            try:
                with open(settings_file) as f:
                    settings = json.load(f)
            except Exception:
                pass

        # Get process info
        pid = os.getpid()
        try:
            import resource
            mem_usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # MB
        except Exception:
            mem_usage = None

        return jsonify({
            "status": "ok",
            "system": {
                "platform": platform.system(),
                "python_version": platform.python_version(),
                "pid": pid,
                "memory_mb": mem_usage,
            },
            "slap": {
                "version": settings.get("version", "unknown"),
                "simulation_enabled": settings.get("simulation_enabled", False),
                "simulation_visible": settings.get("simulation_visible", False),
                "https_enabled": settings.get("https_enabled", False),
                "last_update": settings.get("last_update"),
            }
        })

    @app.route("/api/system/serial/data", methods=["GET"])
    def get_serial_data():
        """Get detailed serial port data for verbose display."""
        from ..parser.mp70 import get_last_raw_data, get_packet_stats, get_recording_status

        try:
            raw_data = get_last_raw_data()
            stats = get_packet_stats()
            recording = get_recording_status()

            return jsonify({
                "status": "ok",
                "serial": {
                    "connected": _serial_port is not None,
                    "reader_active": _serial_reader_active,
                    "last_raw_data": raw_data.hex() if raw_data else None,
                    "last_raw_ascii": raw_data.decode('ascii', errors='replace') if raw_data else None,
                    "packet_stats": stats,
                    "recording": recording,
                }
            })
        except Exception as e:
            return jsonify({
                "status": "ok",
                "serial": {
                    "connected": _serial_port is not None,
                    "reader_active": _serial_reader_active,
                    "error": str(e)
                }
            })

    @app.route("/api/system/serial/record/start", methods=["POST"])
    def start_serial_recording():
        """Start recording serial data to a file."""
        from ..parser.mp70 import start_recording

        data = request.get_json() or {}
        filepath = data.get("filepath")

        try:
            path = start_recording(filepath)
            return jsonify({"status": "ok", "path": path, "message": "Recording started"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/system/serial/record/stop", methods=["POST"])
    def stop_serial_recording():
        """Stop recording serial data."""
        from ..parser.mp70 import stop_recording

        try:
            result = stop_recording()
            return jsonify({"status": "ok", **result})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/system/serial/record/status", methods=["GET"])
    def get_serial_recording_status():
        """Get serial recording status."""
        from ..parser.mp70 import get_recording_status

        return jsonify({"status": "ok", **get_recording_status()})

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
