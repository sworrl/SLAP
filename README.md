<p align="center">
  <img src="src/templates/Logos/league.svg" alt="SLAP Logo" width="120" height="120">
</p>

<h1 align="center">SLAP</h1>
<h3 align="center">Scoreboard Live Automation Platform</h3>

<p align="center">
  <strong>Professional broadcast graphics for hockey powered by real-time scoreboard data</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#features">Features</a> •
  <a href="#broadcast-overlays">Overlays</a> •
  <a href="#api-reference">API</a> •
  <a href="#license">License</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.8+-blue.svg" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/license-GPL--3.0-green.svg" alt="GPL-3.0">
  <img src="https://img.shields.io/badge/platform-linux%20%7C%20macos%20%7C%20windows-lightgrey.svg" alt="Platform">
</p>

---

## Table of Contents

- [Overview](#overview)
  - [System Architecture](#system-architecture)
  - [Multi-Machine Setup](#multi-machine-setup)
- [Quick Start](#quick-start)
- [Features](#features)
- [Broadcast Overlays](#broadcast-overlays)
  - [Overlay URLs](#overlay-urls)
  - [Using with CasparCG](#using-with-casparcg)
  - [Using with OBS](#using-with-obs)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Install Steps](#install-steps)
  - [Commands](#commands)
- [Hardware Setup](#hardware-setup)
  - [Required Equipment](#required-equipment)
  - [MP-70 Configuration](#mp-70-configuration)
  - [Finding Your Serial Port](#finding-your-serial-port)
- [Configuration](#configuration)
  - [Config File](#config-file)
  - [Serial Settings](#serial-settings)
  - [CasparCG Settings](#casparcg-settings)
- [Web Dashboard](#web-dashboard)
  - [Game Control](#game-control)
  - [Broadcast Overlays Control](#broadcast-overlays-control)
  - [Team Management](#team-management)
  - [System Control](#system-control)
- [API Reference](#api-reference)
  - [REST API](#rest-api)
  - [WebSocket Events](#websocket-events)
  - [Code Examples](#code-examples)
- [CasparCG Integration](#casparcg-integration)
  - [Installing CasparCG](#installing-casparcg)
  - [AMCP Commands](#amcp-commands)
- [MP-70 Protocol](#mp-70-protocol)
  - [Serial Configuration](#serial-configuration)
  - [Packet Structure](#packet-structure)
  - [Packet Types](#packet-types)
  - [Protocol Capture](#protocol-capture)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Development TODO](#development-todo)
- [License](#license)

---

## Overview

SLAP captures real-time game data from Trans-Lux FairPlay MP-70 scoreboard controllers and generates professional NHL-style broadcast graphics via CasparCG or OBS Studio.

### System Architecture

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
│                          │   Web Dashboard  │    │   CasparCG    │  │
│                          │   (Socket.IO)    │    │    Server     │  │
│                          └────────┬─────────┘    └───────┬───────┘  │
└───────────────────────────────────┼──────────────────────┼──────────┘
                                    │                      │
                                    ▼                      ▼
                           ┌──────────────┐    ┌─────────────────────┐
                           │  OBS Studio  │◀───│  HTML/CSS/JS        │
                           │  (streaming) │ NDI│  Templates          │
                           └──────────────┘    └─────────────────────┘
```

**Dataflow:**
1. **Scorekeeper** operates the MP-70 console during the game
2. **MP-70** sends game data via RS-232 to the physical scoreboard
3. **SLAP** passively sniffs the RS-232 line (no interference with scoreboard)
4. **Parser** decodes the MP-70 binary protocol (scores, period, clock, penalties)
5. **AMCP Client** sends data updates to CasparCG via AMCP protocol
6. **CasparCG** renders HTML/CSS/JS templates with live data
7. **Web Dashboard** provides real-time monitoring and manual override control

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

### Multi-Machine Setup (Recommended)

For best performance, run SLAP and CasparCG on the same machine:

```
CasparCG Machine (runs SLAP):
├── RS-232 USB adapter → MP-70 serial sniff
├── SLAP server (localhost:5000)
├── CasparCG server (localhost:5250)
└── HTML templates served locally (zero latency)
         │
         │ NDI (network)
         ▼
OBS Machine (powerful workstation):
├── Receives NDI stream from CasparCG
├── Composites overlays onto camera feeds
└── Outputs final broadcast stream
```

**Why this works best:**
- **Localhost AMCP** = zero network latency for graphics
- **Single machine** handles capture → parse → render
- **OBS stays separate** for compositing only
- **Serial port** directly connected to graphics machine

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

---

## Quick Start

```bash
# Install
python deploy.py install

# Start in demo mode (fake game data for testing)
python deploy.py start --simulate

# Or start in live mode (reads from serial port)
python deploy.py start

# Open in browser
# http://localhost:9876
```

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

---

## Features

| Feature | Description |
|---------|-------------|
| **Real-time Capture** | Reads data from MP-70 controllers via RS-232 serial |
| **CasparCG Integration** | Sends live updates to broadcast graphics server |
| **OBS Studio Integration** | WebSocket control for streaming/recording |
| **NHL-style Overlays** | Full suite of 12+ professional broadcast graphics |
| **Web Dashboard** | Control panel with live scorebug preview |
| **Team Roster Manager** | Store player names/numbers for quick overlay insertion |
| **Team Customization** | Logos, colors, and names configurable via web UI |
| **Serial Configuration** | Hot-swap serial settings via web UI |
| **Preview/Live Modes** | Test without hardware, switch to live when ready |
| **Simulation Mode** | Full game simulation for testing |
| **Local Dependencies** | All JavaScript libraries hosted locally (no CDN) |
| **Stream Deck Support** | REST API designed for hardware control surfaces |

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

---

## Broadcast Overlays

SLAP includes a full suite of NHL-style broadcast overlays, all controllable via the web dashboard or API.

### Overlay URLs

| Overlay | URL | Description |
|---------|-----|-------------|
| **Scorebug** | `/overlay` | Main game scorebug with scores, clock, period |
| **Goal Splash** | `/overlay/goal` | Full-screen goal celebration with confetti |
| **Shot Counter** | `/overlay/shots` | Shots on goal tracker |
| **Penalty Box** | `/overlay/penalty` | Detailed penalty info display |
| **Player Card** | `/overlay/player` | Lower third player spotlight |
| **Period Summary** | `/overlay/period` | End-of-period stats summary |
| **Game Intro** | `/overlay/intro` | Pre-game matchup graphic |
| **Goalie Stats** | `/overlay/goalie` | Goalie performance display |
| **Power Play** | `/overlay/powerplay` | Power play countdown graphic |
| **Three Stars** | `/overlay/stars` | Post-game three stars of the game |
| **Replay Bug** | `/overlay/replay` | Flashing replay indicator |
| **Ticker** | `/overlay/ticker` | Scrolling scores crawl |

### Using with CasparCG

Add overlays as HTML templates:

```
PLAY 1-10 [HTML] "http://localhost:5000/overlay"
PLAY 1-11 [HTML] "http://localhost:5000/overlay/goal"
```

### Using with OBS

Add as Browser Source:
- **URL:** `http://localhost:5000/overlay`
- **Width:** 1920
- **Height:** 1080
- **Custom CSS:** (leave empty)

All overlays respond to Socket.IO events for real-time triggering.

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

---

## Installation

### Prerequisites

- Python 3.8 or higher
- Linux, macOS, or Windows

### Install Steps

```bash
# Clone or download SLAP
git clone https://github.com/sworrl/SLAP.git
cd SLAP

# Run the install script
python deploy.py install
```

The deploy script handles:
- Python version verification
- Virtual environment creation
- Dependency installation

### Commands

| Command | Description |
|---------|-------------|
| `python deploy.py install` | Install SLAP and dependencies |
| `python deploy.py start` | Start SLAP server |
| `python deploy.py stop` | Stop SLAP server |
| `python deploy.py restart` | Restart SLAP server |
| `python deploy.py status` | Check if running |
| `python deploy.py logs` | Show logs (`-f` to follow) |
| `python deploy.py update` | Update/reinstall dependencies |
| `python deploy.py uninstall` | Remove installation |

#### Start Options

```bash
python deploy.py start                        # Live mode (default)
python deploy.py start --simulate             # Demo mode (fake data)
python deploy.py start --port 9876            # Custom port
python deploy.py start --debug                # Debug logging
python deploy.py start --serial /dev/ttyUSB0  # Specify serial port
```

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

---

## Hardware Setup

### Required Equipment

| Item | Description |
|------|-------------|
| **MP-70 Controller** | Trans-Lux FairPlay MP-70, MP-71, MP-72, or MP-73 |
| **USB-Serial Adapter** | Any RS-232 to USB adapter (FTDI recommended) |
| **Serial Cable** | DB-9 or appropriate connector for your MP-70 |

### MP-70 Configuration

1. Access the MP-70 setup menu
2. Navigate to sport-specific setup
3. When prompted "VIDEO CHAR?", answer **NO**
   - This sets RS-232 to ProLine data format
4. Verify RS-232 output is enabled

```
MP-70 RS-232 Port → Serial Cable → USB Adapter → Computer
```

### Finding Your Serial Port

**Linux:**
```bash
ls /dev/ttyUSB*
# Usually /dev/ttyUSB0
```

**macOS:**
```bash
ls /dev/tty.usb*
# Usually /dev/tty.usbserial-XXXX
```

**Windows:**
- Open Device Manager
- Look under "Ports (COM & LPT)"
- Usually COM3 or COM4

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

---

## Configuration

### Config File

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
  },
  "simulator": {
    "enabled": false
  }
}
```

### Serial Settings

| Setting | Description |
|---------|-------------|
| `port` | Serial port path (e.g., `/dev/ttyUSB0`, `COM4`) |
| `baudrate` | Always 9600 for MP-70 |

### CasparCG Settings

| Setting | Description |
|---------|-------------|
| `host` | CasparCG server IP address |
| `port` | AMCP port (default: 5250) |
| `enabled` | Set to `false` to disable CasparCG |

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

---

## Web Dashboard

The dashboard at `http://localhost:9876` provides full control over SLAP.

### Game Control

- **Live scorebug preview** - See exactly what appears on broadcast
- **Preview/Live toggle** - Switch between simulation and real hardware
- **Score controls** - Manually adjust scores with +/- buttons
- **Goal buttons** - Trigger goal animations
- **Clock controls** - Set period and game time
- **Penalty controls** - Add 2-minute or 5-minute penalties

### Broadcast Overlays Control

- **Goal Splash** - Trigger home/away goal celebrations
- **Replay Bug** - Show/hide replay indicator
- **Player Card** - Display player lower thirds with roster lookup
- **Goalie Stats** - Show goalie save percentages
- **Period Summary** - End of period stats
- **Game Intro** - Pre-game matchup graphic
- **Three Stars** - Post-game honors
- **Power Play** - Enhanced PP graphic
- **Shot Counter** - Update SOG display
- **Ticker** - League scores crawl

### Team Management

- **Team Customization** - Set team names, colors, and logos
- **Roster Manager** - Add/edit player names and numbers
- **Logo Upload** - Upload custom team logos (PNG, SVG, etc.)

### System Control

- **Serial Port** - Configure MP-70 connection
- **CasparCG control** - Start/stop server, connect AMCP
- **OBS control** - Start/stop OBS, connect WebSocket
- **Connection status** - Monitor all integrations

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

---

## API Reference

**Base URL:** `http://localhost:9876/api`

### REST API

#### State Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/state` | Get current game state |
| `POST` | `/api/state` | Update game state |
| `POST` | `/api/goal` | Trigger goal event |
| `POST` | `/api/penalty` | Add penalty |

#### Overlay Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/overlays` | List all available overlays |
| `POST` | `/api/overlay/goal` | Trigger goal splash |
| `POST` | `/api/overlay/player` | Show player card |
| `POST` | `/api/overlay/goalie` | Show goalie stats |
| `POST` | `/api/overlay/period` | Show period summary |
| `POST` | `/api/overlay/intro` | Show game intro |
| `POST` | `/api/overlay/stars` | Show three stars |
| `POST` | `/api/overlay/powerplay` | Show power play graphic |
| `POST` | `/api/overlay/shots` | Update shot counter |
| `POST` | `/api/overlay/replay` | Show replay bug |
| `POST` | `/api/overlay/ticker` | Show scores ticker |
| `POST` | `/api/overlay/{name}/hide` | Hide any overlay |

#### Roster Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/roster` | Get all rosters |
| `GET` | `/api/roster/{team}` | Get team roster (home/away) |
| `POST` | `/api/roster/{team}` | Update team roster |
| `POST` | `/api/roster/{team}/player` | Add player to roster |
| `DELETE` | `/api/roster/{team}/player/{number}` | Remove player |
| `POST` | `/api/roster/{team}/player/{number}/stats` | Update player stats |
| `POST` | `/api/roster/reset` | Reset all game stats |

#### Team Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/teams` | Get team configuration |
| `POST` | `/api/teams` | Update team configuration |
| `GET` | `/api/teams/logos` | List available logos |
| `POST` | `/api/teams/logo/upload` | Upload new logo |

#### Serial Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/serial/ports` | List available serial ports |
| `GET` | `/api/serial/status` | Get serial connection status |
| `POST` | `/api/serial/config` | Configure serial port |

#### Simulator Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/simulator/start` | Start simulator |
| `POST` | `/api/simulator/stop` | Stop simulator |
| `POST` | `/api/simulator/reset` | Reset simulator |

#### Response Format

**Success:**
```json
{
  "status": "ok",
  "data": { ... }
}
```

**Error:**
```json
{
  "error": "Error message description"
}
```

| Status Code | Description |
|-------------|-------------|
| 200 | Success |
| 400 | Bad request (invalid parameters) |
| 404 | Not found |
| 503 | Service unavailable |

### WebSocket Events

SLAP uses Socket.IO for real-time updates.

```javascript
const socket = io('http://localhost:9876');

// Listen for state updates
socket.on('state_update', (state) => {
  console.log('Score:', state.game.home, '-', state.game.away);
});

// Request current state
socket.emit('request_state');

// Update score
socket.emit('update_score', { home: 5, away: 3 });

// Update clock
socket.emit('update_clock', { clock: "12:30" });

// Update period
socket.emit('update_period', { period: "3" });
```

### Code Examples

#### cURL

```bash
# Get current state
curl http://localhost:9876/api/state

# Trigger home goal
curl -X POST http://localhost:9876/api/goal \
  -H "Content-Type: application/json" \
  -d '{"side": "HOME"}'

# Set score manually
curl -X POST http://localhost:9876/api/state \
  -H "Content-Type: application/json" \
  -d '{"home": 3, "away": 1}'

# Add 2-minute penalty to away team
curl -X POST http://localhost:9876/api/penalty \
  -H "Content-Type: application/json" \
  -d '{"side": "AWAY", "duration": 120}'

# Show player card
curl -X POST http://localhost:9876/api/overlay/player \
  -H "Content-Type: application/json" \
  -d '{"team": "home", "number": "87", "name": "CROSBY", "duration": 5000}'
```

#### Python

```python
import requests

BASE_URL = "http://localhost:9876/api"

# Get state
state = requests.get(f"{BASE_URL}/state").json()
print(f"Score: {state['game']['home']} - {state['game']['away']}")

# Trigger goal
requests.post(f"{BASE_URL}/goal", json={"side": "HOME"})

# Update score
requests.post(f"{BASE_URL}/state", json={"home": 5, "away": 2})

# Show player card
requests.post(f"{BASE_URL}/overlay/player", json={
    "team": "home",
    "number": "87",
    "name": "CROSBY",
    "duration": 5000
})
```

#### JavaScript

```javascript
// Using fetch API
async function triggerGoal(side) {
  const response = await fetch('/api/goal', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ side })
  });
  return response.json();
}

// Using Socket.IO for real-time updates
const socket = io();

socket.on('state_update', (state) => {
  document.getElementById('homeScore').textContent = state.game.home;
  document.getElementById('awayScore').textContent = state.game.away;
});
```

### Stream Deck Integration

SLAP's API works great with Stream Deck and similar control surfaces.

| Button | HTTP Request |
|--------|--------------|
| Home Goal | `POST /api/goal` with `{"side":"HOME"}` |
| Away Goal | `POST /api/goal` with `{"side":"AWAY"}` |
| Show Bug | `POST /api/bug/show` |
| Hide Bug | `POST /api/bug/hide` |
| Replay | `POST /api/overlay/replay` |
| Player Card | `POST /api/overlay/player` with player data |

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

---

## CasparCG Integration

### Installing CasparCG

The easiest way is using the built-in installer:

```bash
# Install CasparCG (downloads ~105MB)
./deploy.sh caspar-install

# Start CasparCG
./deploy.sh caspar-start

# Check status
./deploy.sh caspar-status

# Stop CasparCG
./deploy.sh caspar-stop
```

This installs CasparCG to `~/.local/share/casparcg/` which:
- Works on immutable Linux systems
- Doesn't require root/sudo access
- Automatically copies SLAP templates
- Creates a default config for 1080p output

You can also control CasparCG from the web dashboard.

### AMCP Commands

SLAP sends these commands to CasparCG:

| Command | Description |
|---------|-------------|
| `CG 1-10 UPDATE 1 "{json}"` | Update scorebug data |
| `CG 1-10 INVOKE 1 "goal:HOME"` | Trigger goal animation |
| `CG 1-10 INVOKE 1 "show"` | Show scorebug |
| `CG 1-10 INVOKE 1 "hide"` | Hide scorebug |

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

---

## MP-70 Protocol

The MP-70 controller outputs game data via RS-232 serial connection using a binary protocol.

### Serial Configuration

| Parameter | Value |
|-----------|-------|
| Baud Rate | 9600 |
| Data Bits | 8 |
| Parity | None |
| Stop Bits | 1 |
| Flow Control | None |

### Packet Structure

All packets are wrapped with ASCII control characters:

| Byte | Value | Name | Description |
|------|-------|------|-------------|
| Start | `0x02` | STX | Start of Text |
| End | `0x03` | ETX | End of Text |

Packets must be at least **80 bytes** to be considered valid.

### Packet Types

#### Type 'C' - Clock Update

Clock packets contain only the game clock time.

```
Position  Length  Field          Format
--------  ------  -----          ------
[0]       1       STX            0x02
[1]       1       Type           'C' (0x43)
[2:6]     4       Clock          ASCII "MMSS"
[7:79]    73      Padding        (unused)
[79]      1       ETX            0x03
```

**Clock Format:** 4 ASCII digits (MMSS)
- `"1500"` = 15:00
- `"0130"` = 01:30

#### Type 'H' - Score/Game State Update

Score packets contain the full game state.

```
Position  Length  Field              Format
--------  ------  -----              ------
[0]       1       STX                0x02
[1]       1       Type               'H' (0x48)
[13:15]   2-3     Home Score         ASCII digits
[29:31]   2-3     Away Score         ASCII digits
[45:46]   1       Period             ASCII digit
[52:56]   4       Home Penalty 1     ASCII "MMSS"
[57:61]   4       Home Penalty 2     ASCII "MMSS"
[62:66]   4       Away Penalty 1     ASCII "MMSS"
[67:71]   4       Away Penalty 2     ASCII "MMSS"
[79]      1       ETX                0x03
```

### Protocol Capture

For debugging or reverse-engineering the MP-70 protocol:

#### Hardware Snooping

```
MP-70 Controller                         Scoreboard Display
     |                                        |
     | TX (Pin 3) ----------+---------------> RX
     |                      |
     |                      v
     |              [Snooper RX]
     |              USB-Serial Adapter
     |              (capture only)
```

**Key Points:**
- Only connect TX from MP-70 to your snooper's RX
- Do NOT connect your snooper's TX (passive listening)
- Connect GND between all devices

#### Software Capture

**Linux:**
```bash
stty -F /dev/ttyUSB0 9600 cs8 -cstopb -parenb raw
cat /dev/ttyUSB0 | tee capture.bin | hexdump -C
```

**Windows:**
- TeraTerm: File > Log > Start logging (binary mode)
- PuTTY: Session > Logging > All session output

#### Analyzing Captured Data

```bash
# View hex dump
hexdump -C capture.bin | less

# Find packet boundaries
hexdump -C capture.bin | grep "02.*03"
```

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

---

## Project Structure

```
SLAP/
├── deploy.py               # Python deploy script
├── LICENSE                 # GPL-3.0 License
├── README.md               # This file
└── src/
    ├── run.py              # Main entry point
    ├── requirements.txt    # Python dependencies
    ├── config/             # Configuration files
    │   ├── default.json    # Default config
    │   └── roster.json     # Team rosters
    ├── slap/               # Python package
    │   ├── config.py       # Config loader
    │   ├── parser/         # MP-70 protocol decoder
    │   ├── core/           # Game state & logic
    │   ├── output/         # CasparCG & OBS clients
    │   ├── simulator/      # Fake serial for testing
    │   └── web/            # Flask dashboard
    │       ├── app.py      # API routes & Socket.IO
    │       ├── templates/  # Dashboard HTML
    │       └── static/js/  # Local JS libraries
    ├── templates/          # Broadcast overlay templates
    │   ├── scorebug.html   # Main scorebug
    │   ├── css/
    │   │   ├── scorebug.css
    │   │   └── overlays.css
    │   ├── js/
    │   │   ├── scorebug.js
    │   │   └── socket.io.min.js
    │   ├── overlays/       # Individual overlay templates
    │   │   ├── goal.html
    │   │   ├── player.html
    │   │   ├── goalie.html
    │   │   ├── period.html
    │   │   ├── intro.html
    │   │   ├── stars.html
    │   │   ├── powerplay.html
    │   │   ├── shots.html
    │   │   ├── penalty.html
    │   │   ├── replay.html
    │   │   └── ticker.html
    │   └── Logos/          # Team logo files
    └── docs/               # Reference docs
        └── MP-70_Manual.pdf
```

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

---

## Troubleshooting

### Serial Port Issues

**Permission denied (Linux):**
```bash
sudo usermod -a -G dialout $USER
# Log out and back in
```

**No data received:**
- Verify MP-70 is set to ProLine data format (not VIDEO CHAR)
- Check cable connections
- Try different USB port
- Verify baud rate is 9600

### CasparCG Issues

**Connection refused:**
- Verify CasparCG server is running
- Check firewall settings
- Verify host and port in config

**Template not updating:**
- Verify template is loaded: `CG 1-10 INFO`
- Check channel/layer numbers match config

### Web Interface Issues

**Page not loading:**
- Verify SLAP is running: `python deploy.py status`
- Try different port: `python deploy.py start --port 8888`
- Check firewall settings

### Virtual Environment Issues

**pip missing or broken:**
```bash
python deploy.py update  # Recreates venv if broken
```

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

---

## Development TODO

### Completed ✅

- [x] Core scorebug template with animations
- [x] RS-232 serial parser for MP-70
- [x] CasparCG AMCP client integration
- [x] OBS WebSocket integration
- [x] Web dashboard with live preview
- [x] Team customization (logos, colors, names)
- [x] Serial port configuration via web UI
- [x] Local JavaScript hosting (no CDN dependencies)
- [x] Goal Splash overlay
- [x] Shot Counter overlay
- [x] Penalty Box overlay
- [x] Player Card (lower third)
- [x] Period Summary overlay
- [x] Game Intro overlay
- [x] Goalie Stats overlay
- [x] Power Play enhanced graphic
- [x] Three Stars overlay
- [x] Replay Bug
- [x] Ticker/Crawl
- [x] Broadcast overlay controls in Web UI
- [x] Team roster manager

### In Progress 🔄

- [ ] Player headshot image support
- [ ] Roster import from CSV/Excel

### Planned 📋

- [ ] Multi-game ticker with live scores API
- [ ] Intermission countdown clock
- [ ] Video replay integration
- [ ] Custom animation editor
- [ ] Mobile companion app for operators
- [ ] Multi-language support
- [ ] Audio cue triggers
- [ ] Stat tracking (saves, hits, shots by player)
- [ ] Historical game data export
- [ ] CasparCG template hot-reload
- [ ] OBS scene auto-switching

### Hardware Support (Future) 🔌

- [ ] Daktronics All Sport 5000 support
- [ ] OES scoreboard support
- [ ] Generic scoreboard protocol adapters

<p align="right"><a href="#table-of-contents">⬆ Back to top</a></p>

---

## License

This project is licensed under the **GNU General Public License v3.0**.

See the [LICENSE](LICENSE) file for details.

---

<p align="center">
  <strong>SLAP</strong> - Scoreboard Live Automation Platform<br>
  Built for hockey broadcast professionals
</p>
