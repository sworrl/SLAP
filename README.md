# SLAP - Scoreboard Live Automation Platform

A hockey scoreboard integration system for broadcast graphics. SLAP captures real-time game data from Trans-Lux FairPlay MP-70 scoreboard controllers and displays live score overlays via CasparCG.

## Features

- **Real-time scoreboard capture** - Reads data from MP-70 controllers via RS-232 serial
- **CasparCG integration** - Sends live updates to broadcast graphics
- **Web dashboard** - Control panel with live scorebug preview
- **Preview/Live modes** - Test without hardware, switch to live when ready
- **Simulation mode** - Full game simulation for testing
- **Smooth animations** - 60fps clock updates and score animations
- **Goal detection** - Automatic goal animations with visual feedback
- **Power play indicators** - Animated dropdown overlays for penalties

## Quick Start

```bash
# Install
./deploy.sh install

# Start in simulation mode
./deploy.sh start

# Open in browser
# http://localhost:8080
```

## Commands

```bash
./deploy.sh install     # Install SLAP and dependencies
./deploy.sh update      # Update/reinstall dependencies
./deploy.sh uninstall   # Remove installation
./deploy.sh start       # Start SLAP server
./deploy.sh stop        # Stop SLAP server
./deploy.sh status      # Check if running
```

### Start Options

```bash
./deploy.sh start --port 9876      # Custom port
./deploy.sh start --simulate       # Simulation mode (default)
./deploy.sh start --debug          # Debug logging
```

## Web Dashboard

The dashboard at http://localhost:8080 provides:

- **Live scorebug preview** - See exactly what appears on broadcast
- **Preview/Live toggle** - Switch between simulation and real hardware
- **Score controls** - Manually adjust scores with +/- buttons
- **Goal buttons** - Trigger goal animations
- **Clock controls** - Set period and game time
- **Penalty controls** - Add 2-minute or 5-minute penalties
- **Connection status** - Monitor serial port and CasparCG

## Project Structure

```
SLAP/
├── deploy.sh           # Install/start/stop script
├── LICENSE             # GPL-3.0 License
├── README.md           # This file
└── src/
    ├── run.py          # Main entry point
    ├── simulate.py     # Quick simulation launcher
    ├── requirements.txt
    ├── slap/           # Python package
    │   ├── config.py
    │   ├── parser/     # Protocol parsers
    │   ├── core/       # Game state & logic
    │   ├── output/     # CasparCG client
    │   ├── simulator/  # Fake serial for testing
    │   └── web/        # Flask dashboard
    ├── templates/      # CasparCG HTML templates
    ├── config/         # Configuration files
    └── docs/           # Additional documentation
```

## Configuration

Edit `src/config/default.json`:

```json
{
  "serial": {
    "port": "/dev/ttyUSB0",
    "baudrate": 9600
  },
  "caspar": {
    "host": "127.0.0.1",
    "port": 5250,
    "enabled": true
  },
  "web": {
    "port": 8080
  }
}
```

## Documentation

- [Protocol Specification](src/docs/PROTOCOL.md) - MP-70 binary protocol details
- [Setup Guide](src/docs/SETUP.md) - Hardware and software setup
- [API Reference](src/docs/API.md) - REST API and WebSocket events

## Hardware Requirements

- Trans-Lux FairPlay MP-70 (or MP-71/72/73) controller
- RS-232 to USB adapter cable
- Computer running SLAP

## Software Requirements

- Python 3.8+
- CasparCG Server (optional, for broadcast output)

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
