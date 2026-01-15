# SLAP - Scoreboard Live Automation Platform

A hockey scoreboard integration system for broadcast graphics. SLAP captures real-time game data from Trans-Lux FairPlay MP-70 scoreboard controllers and displays live score overlays via CasparCG or OBS Studio.

## System Overview

```
┌────────────┐      RS-232       ┌──────────────┐
│ Scorekeeper│───────────────────│  Scoreboard  │
│  Console   │                   │   Display    │
│  (MP-70)   │                   └──────────────┘
└─────┬──────┘
      │ RS-232 (sniff)
      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          SLAP Server                                │
│  ┌──────────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │   Serial Parser  │───▶│    Game State    │───▶│  AMCP Client  │  │
│  │  (MP-70 Protocol)│    │ scores, clock,   │    │               │  │
│  └──────────────────┘    │ period, penalties│    └───────┬───────┘  │
│                          └────────┬─────────┘            │          │
│                                   │                      │ AMCP     │
│                                   ▼                      ▼          │
│                          ┌──────────────────┐    ┌───────────────┐  │
│                          │   OBS Client     │    │   CasparCG    │  │
│                          │  (WebSocket)     │    │    Server     │  │
│                          └────────┬─────────┘    └───────┬───────┘  │
└───────────────────────────────────┼──────────────────────┼──────────┘
                                    │                      │
                                    ▼                      ▼
                           ┌──────────────┐    ┌─────────────────────┐
                           │  OBS Studio  │    │  HTML/CSS/JS        │
                           │  (streaming) │    │  Template           │
                           └──────────────┘    │  ┌───────────────┐  │
                                               │  │ <div id="...">│  │
                                               │  │ score, clock  │  │
                                               │  └───────────────┘  │
                                               └──────────┬──────────┘
                                                          │
                                                          ▼
                                               ┌─────────────────────┐
                                               │  Broadcast Output   │
                                               │  (SDI/NDI/Screen)   │
                                               └─────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    Web Dashboard (localhost:9876)                   │
│  • Live scorebug preview    • Manual score/clock override           │
│  • Goal trigger buttons     • CasparCG & OBS control                │
└─────────────────────────────────────────────────────────────────────┘
```

**Dataflow:**
1. **Scorekeeper** operates the MP-70 console during the game
2. **MP-70** sends game data via RS-232 to the physical scoreboard
3. **SLAP** passively sniffs the RS-232 line (no interference with scoreboard)
4. **Parser** decodes the MP-70 binary protocol (scores, period, clock, penalties)
5. **AMCP Client** sends data updates to CasparCG via AMCP protocol
6. **CasparCG** renders the HTML/CSS/JS template, updating divs with predefined IDs
7. **Web Dashboard** provides real-time monitoring and manual override control

## Features

- **Real-time scoreboard capture** - Reads data from MP-70 controllers via RS-232 serial
- **CasparCG integration** - Sends live updates to broadcast graphics
- **OBS Studio integration** - WebSocket control for streaming/recording
- **Web dashboard** - Control panel with live scorebug preview
- **Simultaneous control** - Web UI works alongside scorekeeper input
- **Preview/Live modes** - Test without hardware, switch to live when ready
- **Simulation mode** - Full game simulation for testing
- **Smooth animations** - 60fps clock updates and score animations
- **Goal detection** - Automatic goal animations with visual feedback
- **Power play indicators** - Animated dropdown overlays for penalties

## Quick Start

```bash
# Install
python deploy.py install

# Start in simulation mode
python deploy.py start

# Open in browser
# http://localhost:9876
```

## Commands

```bash
python deploy.py install     # Install SLAP and dependencies
python deploy.py start       # Start SLAP server
python deploy.py stop        # Stop SLAP server
python deploy.py restart     # Restart SLAP server
python deploy.py status      # Check if running
python deploy.py logs        # Show logs (-f to follow)
python deploy.py update      # Update/reinstall dependencies
python deploy.py uninstall   # Remove installation
```

### Start Options

```bash
python deploy.py start --port 9876   # Custom port
python deploy.py start --debug       # Debug logging
python deploy.py start --no-simulate # Use real hardware (default: simulation)
```

## Web Dashboard

The dashboard at http://localhost:9876 provides:

- **Live scorebug preview** - See exactly what appears on broadcast
- **Preview/Live toggle** - Switch between simulation and real hardware
- **Score controls** - Manually adjust scores with +/- buttons
- **Goal buttons** - Trigger goal animations
- **Clock controls** - Set period and game time
- **Penalty controls** - Add 2-minute or 5-minute penalties
- **CasparCG control** - Connect/disconnect from CasparCG server
- **OBS control** - Start/stop OBS, connect WebSocket, manage scorebug overlay
- **Connection status** - Monitor serial port, CasparCG, and OBS

## Project Structure

```
SLAP/
├── deploy.py           # Python deploy script (install/start/stop)
├── LICENSE             # GPL-3.0 License
├── README.md           # This file
└── src/
    ├── run.py          # Main entry point
    ├── requirements.txt
    ├── slap/           # Python package
    │   ├── config.py
    │   ├── parser/     # MP-70 protocol decoder
    │   ├── core/       # Game state & logic
    │   ├── output/     # CasparCG & OBS clients
    │   ├── simulator/  # Fake serial for testing
    │   └── web/        # Flask dashboard
    ├── templates/      # CasparCG HTML/CSS/JS templates
    ├── config/         # Configuration files
    └── docs/           # Protocol documentation
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
    "port": 9876
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
- CasparCG Server (for broadcast graphics output)
- OBS Studio 28+ (optional, for streaming/recording with WebSocket)

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
