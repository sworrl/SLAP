#!/usr/bin/env python3
"""
SLAP - Scoreboard Live Automation Platform

Main entry point for running the full application.
Connects to serial port (or simulator) and serves web interface.
"""

import argparse
import logging
import threading
import time
import sys
from pathlib import Path

# Add slap package to path
sys.path.insert(0, str(Path(__file__).parent))

from slap.config import load_config, set_config
from slap.core.state import state
from slap.core.hockey import HockeyLogic
from slap.parser.mp70 import MP70Parser
from slap.output.caspar import CasparClient, MockCasparClient
from slap.simulator.fake_serial import FakeSerial
from slap.web.app import create_app, socketio, set_simulator, set_caspar_client


def setup_logging(debug: bool = False):
    """Configure logging."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )


def run_serial_reader(serial_port, parser, hockey_logic, caspar_client, stop_event):
    """
    Main serial reading loop.

    Reads from serial port, parses packets, updates state, and triggers CasparCG.
    """
    logger = logging.getLogger("serial_reader")
    buffer = bytearray()

    logger.info("Serial reader started")
    state.serial_connected = True

    try:
        while not stop_event.is_set():
            # Read available data
            if serial_port.in_waiting > 0:
                data = serial_port.read(min(512, serial_port.in_waiting))
                buffer.extend(data)

            # Extract complete packets
            packets, buffer = parser.extract_packets(buffer)

            for packet in packets:
                game_data = parser.parse(packet)
                if game_data:
                    # Update state
                    state.update_game(
                        home_score=game_data.home_score,
                        away_score=game_data.away_score,
                        period=game_data.period,
                        clock=game_data.clock,
                        home_penalties=game_data.home_penalties,
                        away_penalties=game_data.away_penalties
                    )

                    # Check for goals
                    event = hockey_logic.process_update(game_data.to_dict())
                    if event and event.startswith("GOAL_"):
                        side = event.replace("GOAL_", "")
                        state.update_game(last_goal=side)
                        if caspar_client:
                            caspar_client.trigger_goal(side)

                    # Update CasparCG
                    if caspar_client and caspar_client.connected:
                        caspar_client.update_scorebug(game_data.to_dict())

            time.sleep(0.01)

    except Exception as e:
        logger.error(f"Serial reader error: {e}")
    finally:
        state.serial_connected = False
        logger.info("Serial reader stopped")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="SLAP - Scoreboard Live Automation Platform"
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config file",
        default=None
    )
    parser.add_argument(
        "--simulate", "-s",
        action="store_true",
        help="Run in simulation mode (no hardware required)"
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        help="Web server port (default: 8080)",
        default=None
    )
    parser.add_argument(
        "--no-caspar",
        action="store_true",
        help="Disable CasparCG connection"
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Apply command line overrides
    if args.simulate:
        config.simulator.enabled = True
    if args.debug:
        config.debug = True
    if args.port:
        config.web.port = args.port
    if args.no_caspar:
        config.caspar.enabled = False

    set_config(config)

    # Setup logging
    setup_logging(config.debug)
    logger = logging.getLogger("slap")

    logger.info("=" * 50)
    logger.info("SLAP - Scoreboard Live Automation Platform")
    logger.info("=" * 50)

    # Initialize components
    mp70_parser = MP70Parser()
    hockey_logic = HockeyLogic()

    # Setup CasparCG client
    if config.caspar.enabled:
        caspar_client = CasparClient()
        if caspar_client.connect():
            state.caspar_connected = True
            logger.info("Connected to CasparCG")
        else:
            logger.warning("Could not connect to CasparCG")
    else:
        caspar_client = MockCasparClient()
        logger.info("CasparCG disabled, using mock client")

    set_caspar_client(caspar_client)

    # Setup serial port
    stop_event = threading.Event()

    if config.simulator.enabled:
        logger.info("Starting in SIMULATION mode")
        serial_port = FakeSerial()
        serial_port.open()
        simulator = serial_port.get_simulator()
        set_simulator(simulator)
        state.simulator_running = True

        # Connect simulator updates to state
        def on_sim_update(sim_data):
            state.update_game(
                home_score=sim_data.get("home", 0),
                away_score=sim_data.get("away", 0),
                period=sim_data.get("period", "1"),
                clock=sim_data.get("clock", "20:00"),
                home_penalties=sim_data.get("home_penalties", []),
                away_penalties=sim_data.get("away_penalties", [])
            )

        simulator.set_on_update(on_sim_update)
    else:
        try:
            import serial
            serial_port = serial.Serial(
                port=config.serial.port,
                baudrate=config.serial.baudrate,
                timeout=config.serial.timeout
            )
            logger.info(f"Opened serial port: {config.serial.port}")
        except Exception as e:
            logger.error(f"Failed to open serial port: {e}")
            logger.info("Falling back to simulation mode")
            serial_port = FakeSerial()
            serial_port.open()
            simulator = serial_port.get_simulator()
            set_simulator(simulator)
            config.simulator.enabled = True

    # Start serial reader thread
    serial_thread = threading.Thread(
        target=run_serial_reader,
        args=(serial_port, mp70_parser, hockey_logic, caspar_client, stop_event),
        daemon=True
    )
    serial_thread.start()

    # Create and run web app
    app = create_app()

    logger.info(f"Starting web server on http://0.0.0.0:{config.web.port}")
    logger.info("Press Ctrl+C to stop")

    try:
        socketio.run(
            app,
            host=config.web.host,
            port=config.web.port,
            debug=False,  # Disable Flask debug to prevent double-start
            use_reloader=False,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        stop_event.set()
        if hasattr(serial_port, 'close'):
            serial_port.close()
        if caspar_client:
            caspar_client.disconnect()

    logger.info("SLAP stopped")


if __name__ == "__main__":
    main()
