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
