<p align="center">
  <img src="src/slap/web/static/img/SLAP_icon.webp" alt="SLAP Logo" width="200" height="200">
</p>

<h3 align="center">Scoreboard Live Automation Platform</h3>

<p align="center">
  <em>Professional broadcast graphics for hockey powered by real-time scoreboard data</em>
</p>

<p align="center">
  <a href="#-quick-start">🚀 Quick Start</a> •
  <a href="#-features">✨ Features</a> •
  <a href="#-broadcast-overlays">📺 Overlays</a> •
  <a href="#-api-reference">🔌 API</a> •
  <a href="#-license">📄 License</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Version-2.3.0-brightgreen?style=for-the-badge" alt="Version 2.3.0">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/License-GPL%20v3-blue?style=for-the-badge" alt="GPL-3.0">
  <img src="https://img.shields.io/badge/CasparCG-Ready-orange?style=for-the-badge" alt="CasparCG">
  <img src="https://img.shields.io/badge/OBS-Compatible-purple?style=for-the-badge&logo=obsstudio&logoColor=white" alt="OBS">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Status-Active%20Development-brightgreen?style=flat-square" alt="Status">
  <img src="https://img.shields.io/badge/PRs-Welcome-ff69b4?style=flat-square" alt="PRs Welcome">
</p>

---

## 📑 Table of Contents

<details>
<summary>Click to expand</summary>

- [🆕 What's New in v2.3.0](#-whats-new-in-v230)
- [🎯 Overview](#-overview)
  - [System Architecture](#system-architecture)
  - [Multi-Machine Setup](#multi-machine-setup-recommended)
- [🚀 Quick Start](#-quick-start)
- [✨ Features](#-features)
- [📺 Broadcast Overlays](#-broadcast-overlays)
  - [Overlay URLs](#overlay-urls)
  - [Using with CasparCG](#using-with-casparcg)
  - [Using with OBS](#using-with-obs)
- [📦 Installation](#-installation)
  - [Prerequisites](#prerequisites)
  - [Install Steps](#install-steps)
  - [Commands](#commands)
- [🔧 Hardware Setup](#-hardware-setup)
  - [Required Equipment](#required-equipment)
  - [MP-70 Configuration](#mp-70-configuration)
  - [Finding Your Serial Port](#finding-your-serial-port)
- [⚙️ Configuration](#️-configuration)
  - [Config File](#config-file)
  - [Serial Settings](#serial-settings)
  - [CasparCG Settings](#casparcg-settings)
  - [Database Location](#database-location)
- [🖥️ Web Dashboard](#️-web-dashboard)
  - [Game Control](#game-control)
  - [Broadcast Overlays Control](#broadcast-overlays-control)
  - [Team Management](#team-management)
  - [System Control](#system-control)
- [🔌 API Reference](#-api-reference)
  - [REST API](#rest-api)
  - [WebSocket Events](#websocket-events)
  - [Code Examples](#code-examples)
- [🎬 CasparCG Integration](#-casparcg-integration)
  - [Installing CasparCG](#installing-casparcg)
  - [AMCP Commands](#amcp-commands)
- [📡 MP-70 Protocol](#-mp-70-protocol)
  - [Serial Configuration](#serial-configuration)
  - [Packet Structure](#packet-structure)
  - [Packet Types](#packet-types)
  - [Protocol Capture](#protocol-capture)
- [📁 Project Structure](#-project-structure)
- [🔍 Troubleshooting](#-troubleshooting)
- [📋 Development TODO](#-development-todo)
- [📄 License](#-license)

</details>

---

## 🆕 What's New in v2.3.0

> **Release Date:** February 2026

### Highlights

| Change | Description |
|--------|-------------|
| 🧠 **Adaptive Protocol Parser** | Complete parser rewrite with 5 parsing strategies - auto-detects unknown packet formats from real hardware |
| 🔒 **Strategy Locking** | Parser locks onto the working strategy after 3 consecutive successes for fast, reliable parsing |
| 📐 **Multiple Field Layouts** | Supports standard 80-byte, short 55-byte (confirmed from real hardware), compact, and wide (3-digit score) layouts |
| 📝 **ASCII Text Mode** | Parses VCG/VideoStamp+ character generator output (CR/LF delimited ASCII lines) |
| 📚 **Documentation Viewer** | Browse protocol docs, reference PDFs, and research notes from the web dashboard |
| 🔬 **Protocol Research** | Compiled reverse-engineering notes from MP-69D decoder, PoC\|\|GTFO, and community sources |
| 📊 **Packet Diagnostics** | Unrecognized packets get detailed hex/ASCII/byte analysis logged for reverse engineering |
| 🔌 **Serial Reader Fix** | Serial connect now properly starts the reader thread (previously opened port but never read data) |
| 📼 **Serial Recording** | Record raw serial data to binary files for offline analysis |
| 🏟️ **Real Hardware Validation** | 55-byte field map confirmed from 3,130 live packets at Tony's rink (167 unique score patterns) |

### Upgrade Notes

If upgrading from v2.2.0:
```bash
cd /path/to/SLAP
git pull
./deploy.py
slap restart
```

---

## 🎯 Overview

> **SLAP** captures real-time game data from Trans-Lux FairPlay MP-70 scoreboard controllers and generates professional NHL-style broadcast graphics via CasparCG or OBS Studio.

<p align="center">
  <img src="https://img.shields.io/badge/📊_Real--Time-Data%20Capture-blue?style=flat-square" alt="Real-Time">
  <img src="https://img.shields.io/badge/🎨_NHL--Style-Graphics-red?style=flat-square" alt="NHL-Style">
  <img src="https://img.shields.io/badge/🔄_Live-Updates-green?style=flat-square" alt="Live Updates">
</p>

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

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

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

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

---

## 🚀 Quick Start

> [!TIP]
> After installation, SLAP is controlled via the `slap` command and available in your start menu!

```bash
# Clone the repository
git clone https://github.com/sworrl/SLAP.git
cd SLAP

# Run the installer (handles everything automatically)
chmod +x deploy.py
./deploy.py

# After installation, use the 'slap' command:
slap start                    # Start the server
slap status                   # Check if running
slap stop                     # Stop the server

# Open in browser
# https://slap.localhost
```

> **Note:** The installer automatically:
> - Installs all prerequisites (Python, nginx, openssl, etc.)
> - Creates a global `slap` command
> - Sets up HTTPS with self-signed SSL certificate
> - Adds SLAP to your start menu
> - Configures auto-start on boot

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

---

## ✨ Features

<table>
<tr>
<td>

### 🟢 Implemented Features
| Feature | Description | Status |
|---------|-------------|--------|
| 📡 **MP-70 Adaptive Parser** | Multi-strategy protocol decoder with auto-detection and locking | ✅ Complete |
| 🎬 **CasparCG AMCP Client** | Full AMCP protocol over TCP sockets | ✅ Complete |
| 📺 **OBS WebSocket Client** | Scene/source control via obs-websocket | ✅ Complete |
| 🖥️ **Web Dashboard** | Modern control panel with glass morphism UI and live preview | ✅ Complete |
| 🎮 **Game Simulator** | Fake serial with realistic game simulation | ✅ Complete |
| 🏒 **11 Broadcast Overlays** | Goal, shots, penalty, player, period, intro, goalie, powerplay, stars, replay, ticker | ✅ Complete |
| 👥 **Team Roster Manager** | CRUD API for player names/numbers/stats | ✅ Complete |
| 🎨 **Team Customization** | Logos, colors, names via web UI | ✅ Complete |
| ⚡ **Serial Port Config** | Hot-swap serial settings via web UI | ✅ Complete |
| 🔄 **Preview/Live Modes** | Test without hardware, switch when ready | ✅ Complete |
| 🌐 **Web-Only Mode** | Run dashboard without serial or simulation | ✅ Complete |
| 📦 **Local Dependencies** | All JS libraries hosted locally (no CDN) | ✅ Complete |
| 📚 **Documentation Viewer** | Browse protocol docs and reference PDFs from the web UI | ✅ Complete |
| 📼 **Serial Recording** | Record raw serial data to binary files for offline analysis | ✅ Complete |
| 🔬 **Packet Diagnostics** | Detailed hex/ASCII/byte analysis of unrecognized packets | ✅ Complete |
| 🔌 **REST API** | 75+ endpoints for full control | ✅ Complete |
| 💾 **SQLite Database** | Game history, events, player stats persistence | ✅ Complete |
| 📊 **Statistics Tracking** | Goals, assists, PIM, season leaders | ✅ Complete |

</td>
</tr>
<tr>
<td>

### 🟡 Needs Field Testing
> All features above are code-complete but need real-world testing with actual hardware:
> - MP-70 controller integration
> - CasparCG server connection
> - OBS Studio connection
> - Production broadcast environment

</td>
</tr>
</table>

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

---

## 📺 Broadcast Overlays

> SLAP includes a full suite of **NHL-style broadcast overlays**, all controllable via the web dashboard or API.

### 🎨 Overlay URLs

| Overlay | URL | Description |
|:--------|:----|:------------|
| 🏒 **Scorebug** | `/overlay` | Main game scorebug with scores, clock, period |
| 🚨 **Goal Splash** | `/overlay/goal` | Full-screen goal celebration with confetti |
| 🎯 **Shot Counter** | `/overlay/shots` | Shots on goal tracker |
| ⏱️ **Penalty Box** | `/overlay/penalty` | Detailed penalty info display |
| 👤 **Player Card** | `/overlay/player` | Lower third player spotlight |
| 📊 **Period Summary** | `/overlay/period` | End-of-period stats summary |
| 🎬 **Game Intro** | `/overlay/intro` | Pre-game matchup graphic |
| 🥅 **Goalie Stats** | `/overlay/goalie` | Goalie performance display |
| ⚡ **Power Play** | `/overlay/powerplay` | Power play countdown graphic |
| ⭐ **Three Stars** | `/overlay/stars` | Post-game three stars of the game |
| 🔁 **Replay Bug** | `/overlay/replay` | Flashing replay indicator |
| 📰 **Ticker** | `/overlay/ticker` | Scrolling scores crawl |

### Using with CasparCG

Add overlays as HTML templates:

```
PLAY 1-10 [HTML] "https://slap.localhost/overlay"
PLAY 1-11 [HTML] "https://slap.localhost/overlay/goal"
```

### Using with OBS

Add as Browser Source:
- **URL:** `https://slap.localhost/overlay` (or `http://localhost:9876/overlay`)
- **Width:** 1920
- **Height:** 1080
- **Custom CSS:** (leave empty)

All overlays respond to Socket.IO events for real-time triggering.

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

---

## 📦 Installation

### Prerequisites

- Python 3.8 or higher
- Linux, macOS, or Windows

### Install Steps

```bash
# Clone or download SLAP
git clone https://github.com/sworrl/SLAP.git
cd SLAP

# Run the installer
chmod +x deploy.py
./deploy.py
```

The installer handles:
- System package installation (Python, nginx, openssl, git)
- Python virtual environment creation
- Dependency installation
- HTTPS/SSL certificate generation
- nginx reverse proxy configuration
- Start menu entry creation
- Systemd service for auto-start

### Commands (after installation)

| Command | Description |
|---------|-------------|
| `slap start` | Start SLAP server |
| `slap stop` | Stop SLAP server |
| `slap restart` | Restart SLAP server |
| `slap status` | Check if running |
| `slap logs` | Show logs (`-f` to follow) |
| `slap config` | View/edit configuration |
| `slap -update` | Update from GitHub |
| `slap --help` | Show all commands |

#### Simulation Mode

Simulation mode is **hidden by default** in the WebUI. To enable it:

```bash
slap -simulation:enable     # Show simulation controls in WebUI
slap -simulation:disable    # Hide simulation controls (default)
```

#### HTTPS Commands

```bash
slap -https:setup          # Configure HTTPS with nginx and SSL
slap -https:remove         # Remove HTTPS configuration
```

#### Other Options

```bash
slap start --port 9876            # Custom port
slap start --debug                # Debug logging
slap -serial:/dev/ttyUSB0         # Set serial port
```

### Uninstall

```bash
./deploy.py --uninstall
```

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

---

## 🔧 Hardware Setup

> [!NOTE]
> SLAP works in simulation mode without any hardware. Only need this for live games!

### Required Equipment

| Item | Description |
|------|-------------|
| **MP-70 Controller** | Trans-Lux FairPlay MP-70, MP-71, MP-72, or MP-73 |
| **USB-Serial Adapter** | Any RS-232 to USB adapter (FTDI recommended) |
| **Serial Cable** | DB-9 or appropriate connector for your MP-70 |

### MP-70 Configuration

1. Access the MP-70 setup menu
2. Navigate to sport-specific setup
3. When prompted "VIDEO CHAR?", answer **NO** for ProLine data (recommended)
   - **NO** = ProLine binary format (STX/ETX framed, default)
   - **YES** = VCG/VideoStamp+ ASCII text format (also supported by SLAP)
4. Verify RS-232 output is enabled
5. Note which connector (CONN.1, CONN.2, CONN3&4) the cable is on

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

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

---

## ⚙️ Configuration

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
| `baudrate` | 9600 (standard) or 19200 (some firmware) |

### CasparCG Settings

| Setting | Description |
|---------|-------------|
| `host` | CasparCG server IP address |
| `port` | AMCP port (default: 5250) |
| `enabled` | Set to `false` to disable CasparCG |

### Database Location

SLAP stores game history, events, and player statistics in a SQLite database. The database is stored outside the source directory for security:

| Platform | Location |
|----------|----------|
| **Linux** | `~/.local/share/slap/slap.db` |
| **macOS** | `~/Library/Application Support/slap/slap.db` |
| **Windows** | `%LOCALAPPDATA%\slap\slap.db` |

> [!NOTE]
> The database is automatically created during `./deploy.py install` and includes **self-healing** - if the database becomes corrupted, SLAP will back it up and create a fresh one automatically.

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

---

## 🖥️ Web Dashboard

> The dashboard at `https://slap.localhost` (or `http://localhost:9876` without HTTPS) provides **full control** over SLAP.

### 🎮 Game Control

- **Live scorebug preview** - See exactly what appears on broadcast
- **Preview/Live toggle** - Switch between simulation and real hardware
- **Score controls** - Manually adjust scores with +/- buttons
- **Goal buttons** - Trigger goal animations
- **Clock controls** - Set period and game time
- **Penalty controls** - Add 2-minute or 5-minute penalties

### 📺 Broadcast Overlays Control

- 🚨 **Goal Splash** - Trigger home/away goal celebrations
- 🔁 **Replay Bug** - Show/hide replay indicator
- 👤 **Player Card** - Display player lower thirds with roster lookup
- 🥅 **Goalie Stats** - Show goalie save percentages
- 📊 **Period Summary** - End of period stats
- 🎬 **Game Intro** - Pre-game matchup graphic
- ⭐ **Three Stars** - Post-game honors
- ⚡ **Power Play** - Enhanced PP graphic
- 🎯 **Shot Counter** - Update SOG display
- 📰 **Ticker** - League scores crawl

### 👥 Team Management

- 🎨 **Team Customization** - Set team names, colors, and logos
- 📋 **Roster Manager** - Add/edit player names and numbers
- 🖼️ **Logo Upload** - Upload custom team logos (PNG, SVG, etc.)

### 🔌 System Control

- 📡 **Serial Port** - Configure MP-70 connection
- 🎬 **CasparCG control** - Start/stop server, connect AMCP
- 📺 **OBS control** - Start/stop OBS, connect WebSocket
- 🔗 **Connection status** - Monitor all integrations

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

---

## 🔌 API Reference

<p align="center">
  <img src="https://img.shields.io/badge/Base%20URL-slap.localhost/api-blue?style=for-the-badge" alt="Base URL">
</p>

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
| `POST` | `/api/serial/connect` | Connect to serial port and start reader |
| `POST` | `/api/serial/disconnect` | Disconnect from serial port |
| `POST` | `/api/serial/recording/start` | Start recording raw serial data |
| `POST` | `/api/serial/recording/stop` | Stop recording |
| `GET` | `/api/serial/recording/status` | Get recording status |

#### Documentation Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/docs` | List available documentation files |
| `GET` | `/docs/file/<filename>` | Serve a documentation file |

#### Simulator Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/simulator/start` | Start simulator |
| `POST` | `/api/simulator/stop` | Stop simulator |
| `POST` | `/api/simulator/reset` | Reset simulator |

#### Game History Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/games` | Get recent games (add `?limit=N`) |
| `POST` | `/api/games` | Create new game |
| `GET` | `/api/games/current` | Get current in-progress game |
| `GET` | `/api/games/{id}` | Get specific game |
| `PUT` | `/api/games/{id}` | Update game details |
| `DELETE` | `/api/games/{id}` | Delete game |
| `POST` | `/api/games/{id}/end` | End game (status: final/cancelled) |
| `GET` | `/api/games/{id}/summary` | Get full game summary with events |
| `GET` | `/api/games/{id}/events` | Get game events (add `?type=goal`) |
| `POST` | `/api/games/{id}/goal` | Log a goal |
| `POST` | `/api/games/{id}/penalty` | Log a penalty |
| `POST` | `/api/games/{id}/shot` | Log a shot |

#### Statistics Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/stats` | Get player stats (add `?season=YYYY&team=X`) |
| `GET` | `/api/stats/leaders` | Get stat leaders (add `?stat=points&limit=N`) |
| `GET` | `/api/stats/team/{team}` | Get team win/loss record |
| `GET` | `/api/stats/h2h` | Head-to-head record (add `?team1=X&team2=Y`) |

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
const socket = io('https://slap.localhost');

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
curl https://slap.localhost/api/state

# Trigger home goal
curl -X POST https://slap.localhost/api/goal \
  -H "Content-Type: application/json" \
  -d '{"side": "HOME"}'

# Set score manually
curl -X POST https://slap.localhost/api/state \
  -H "Content-Type: application/json" \
  -d '{"home": 3, "away": 1}'

# Add 2-minute penalty to away team
curl -X POST https://slap.localhost/api/penalty \
  -H "Content-Type: application/json" \
  -d '{"side": "AWAY", "duration": 120}'

# Show player card
curl -X POST https://slap.localhost/api/overlay/player \
  -H "Content-Type: application/json" \
  -d '{"team": "home", "number": "87", "name": "CROSBY", "duration": 5000}'
```

#### Python

```python
import requests

BASE_URL = "https://slap.localhost/api"

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

### 🎛️ Stream Deck Integration

> [!TIP]
> SLAP's API works great with Stream Deck and similar control surfaces!

| Button | HTTP Request |
|--------|--------------|
| Home Goal | `POST /api/goal` with `{"side":"HOME"}` |
| Away Goal | `POST /api/goal` with `{"side":"AWAY"}` |
| Show Bug | `POST /api/bug/show` |
| Hide Bug | `POST /api/bug/hide` |
| Replay | `POST /api/overlay/replay` |
| Player Card | `POST /api/overlay/player` with player data |

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

---

## 🎬 CasparCG Integration

### Installing CasparCG

> [!NOTE]
> The easiest way is using the built-in installer:

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

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

---

## 📡 MP-70 Protocol

> The MP-70 controller outputs game data via RS-232 serial connection using a **proprietary protocol** that varies by firmware, board type, and configuration. SLAP's adaptive parser handles multiple formats automatically.
>
> For comprehensive protocol research, see [`docs/PROTOCOL_NOTES.md`](src/docs/PROTOCOL_NOTES.md) and the Documentation page in the web dashboard.

### Serial Configuration

| Parameter | Value |
|-----------|-------|
| Baud Rate | **9600** (standard) or **19200** (some firmware) |
| Data Bits | 8 |
| Parity | None |
| Stop Bits | 1 |
| Flow Control | None |

> **Tip:** If 9600 doesn't work, try 19200. The baud rate varies by firmware version.

### Data Formats

The MP-70 has two RS-232 output modes (set via "VIDEO CHAR?" menu):

| Mode | Setting | Format |
|------|---------|--------|
| **ProLine** (default) | VIDEO CHAR? = NO | STX/ETX framed binary, 80-byte packets |
| **VCG/VideoStamp+** | VIDEO CHAR? = YES | CR/LF delimited ASCII text lines |

### Adaptive Parser

SLAP's parser auto-detects the format using 5 strategies, tried in order:

| # | Strategy | Description |
|---|----------|-------------|
| 1 | **Type-byte dispatch** | Standard MP-70 type bytes: `'C'` (clock), `'H'` (score) |
| 2 | **Alternative type bytes** | Other sport-specific indicators (`S`, `G`, `D`, `F`, `B`, etc.) |
| 3 | **Layout-only** | Ignores type byte, tries all field layouts against the packet |
| 4 | **ASCII text scan** | Regex search for score/clock patterns in readable text |
| 5 | **Clock extraction** | Finds embedded MM:SS times anywhere in the data |

After **3 consecutive successes** with the same strategy, the parser **locks** onto it for fast processing. If the locked strategy fails (e.g., sport change on controller), it falls back to trying all strategies.

### Supported Field Layouts

| Layout | Length | Score Fields | Use Case |
|--------|--------|-------------|----------|
| **Standard** | 80 bytes | 2-digit scores at [13:15], [29:31] | Default MP-70 hockey |
| **Short** | 55 bytes | 1-digit scores at [13], [39] + penalty player #s | **Confirmed from real hardware** |
| **Wide** | 80 bytes | 3-digit scores at [13:16], [29:32] | Basketball/football |
| **Compact** | 40 bytes | Tighter field packing | Some firmware variants |

### Packet Structure (Standard Layout)

#### Type 'C' - Clock Update

```
Position  Length  Field          Format
--------  ------  -----          ------
[0]       1       STX            0x02
[1]       1       Type           'C' (0x43)
[2:6]     4       Clock          ASCII "MMSS" (BCD-like)
[7:10]    3       Period+Flags   Hundreds digit = period (e.g. "160"=P1, "260"=P2, "360"=P3)
...       ...     Padding        (unused)
[last]    1       ETX            0x03
```

**Clock Format:** BCD-like packed digits - `"1000"` = 10:00, `"959"` = 9:59, `"900"` = 9:00, `"859"` = 8:59 (rolls over at century boundaries)

**Period:** Encoded in C packets (not H packets) at bytes [7:10]. The hundreds digit is the period number.

#### Type 'H' - Score/Game State Update

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

> **Note:** The "unknown" regions between fields may contain shots on goal, timeouts, or sport-specific data depending on the board type (40+ types supported by the MP-70).

#### Type 'H' - Short Format (55-byte, confirmed from real hardware)

```
Position  Length  Field              Format
--------  ------  -----              ------
[0]       1       STX                0x02
[1]       1       Type               'H' (0x48)
[2:6]     4       Clock              ASCII BCD digits
[13]      1       Home Score         ASCII digit (single)
[16:18]   2       Home Pen1 Player   Jersey number (ASCII)
[19:22]   3       Home Pen1 Time     BCD seconds ("100"=1:00, "059"=0:59)
[22:24]   2       Home Pen2 Player   Jersey number (ASCII)
[25:28]   3       Home Pen2 Time     BCD seconds
[39]      1       Away Score         ASCII digit (single)
[42:44]   2       Away Pen1 Player   Jersey number (ASCII)
[45:48]   3       Away Pen1 Time     BCD seconds
[48:50]   2       Away Pen2 Player   Jersey number (ASCII)
[51:54]   3       Away Pen2 Time     BCD seconds
[54]      1       ETX                0x03
```

> **Note:** Period is NOT in the H packet in this format, it comes from C packets (bytes [7:10]). This layout was confirmed by analyzing 3,130 packets (167 unique H patterns) from a live game. See [`docs/DEBUG_LOG_ANALYSIS_2026-02-16.md`](src/docs/DEBUG_LOG_ANALYSIS_2026-02-16.md) for the full analysis.

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

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

---

## 📁 Project Structure

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
    │       ├── templates/  # Dashboard HTML (index, docs)
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
    └── docs/               # Reference docs (viewable at /docs)
        ├── MP-70_Manual.pdf
        ├── MP-70_Quick_Reference.pdf
        ├── SP-70_Statistics_Controller.pdf
        ├── pocgtfo-fairplay-reversing.pdf
        ├── PROTOCOL_NOTES.md
        ├── DEBUG_LOG_ANALYSIS_2026-02-16.md  # Real hardware packet analysis
        └── slap_debug_2026-02-16.log         # Raw debug log from live game
```

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

---

## 🔍 Troubleshooting

<details>
<summary><strong>🔌 Serial Port Issues</strong></summary>

**Permission denied (Linux):**
```bash
sudo usermod -a -G dialout $USER
# Log out and back in
```

**All packets "invalid":**
- Try both baud rates (9600 and 19200)
- Enable debug logging: `slap start --debug`
- Start a serial recording from the web UI to capture raw data
- Toggle the VIDEO CHAR? setting on the MP-70 (try both YES and NO)
- Check which connector (CONN.1, CONN.2, CONN3&4) the cable is on

**No data received:**
- Verify the RS-232 cable is connected (not the 1/4" scoreboard jacks)
- Check cable: straight-through DB-9, pins 2 (RX), 3 (TX), 5 (GND)
- Try different USB port or USB-to-serial adapter
- Try both baud rates (9600 and 19200)

</details>

<details>
<summary><strong>🎬 CasparCG Issues</strong></summary>

**Connection refused:**
- Verify CasparCG server is running
- Check firewall settings
- Verify host and port in config

**Template not updating:**
- Verify template is loaded: `CG 1-10 INFO`
- Check channel/layer numbers match config

</details>

<details>
<summary><strong>🖥️ Web Interface Issues</strong></summary>

**Page not loading:**
- Verify SLAP is running: `./deploy.py status`
- Try different port: `./deploy.py start --port 8888`
- Check firewall settings

</details>

<details>
<summary><strong>🐍 Virtual Environment Issues</strong></summary>

**pip missing or broken:**
```bash
./deploy.py update  # Recreates venv if broken
```

</details>

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

---

## 📋 Development TODO

### ✅ Code Complete (Needs Field Testing)

<img src="https://img.shields.io/badge/25_Features-Code%20Complete-success?style=flat-square" alt="25 Complete">

<table>
<tr><td>

**Core Systems**
- [x] MP-70 adaptive protocol parser (5 strategies, auto-locking)
- [x] CasparCG AMCP client (205 lines)
- [x] OBS WebSocket client (363 lines)
- [x] Thread-safe game state management
- [x] Hockey logic engine (goal/period detection)
- [x] Game simulator with realistic data
- [x] Configuration management (JSON + env vars)
- [x] SQLite database (game history, stats)

</td><td>

**Web & API**
- [x] Flask/SocketIO web application
- [x] 75+ REST API endpoints
- [x] Real-time WebSocket updates
- [x] Team roster CRUD API
- [x] Serial port configuration API
- [x] CasparCG/OBS control API
- [x] Game history & events API
- [x] Player statistics API

</td><td>

**Overlays (11 templates)**
- [x] Scorebug (main)
- [x] Goal splash with particles
- [x] Shot counter
- [x] Penalty box
- [x] Player card
- [x] Period summary
- [x] Game intro
- [x] Goalie stats
- [x] Power play
- [x] Three stars
- [x] Replay bug
- [x] Ticker/crawl

</td></tr>
</table>

### 🗺️ Roadmap

<details>
<summary><strong>🔊 Audio & Media (Not Implemented)</strong></summary>

- [ ] Goal horn audio playback
- [ ] Siren/buzzer sound effects
- [ ] PA announcement integration
- [ ] Video replay control (NDI/RTMP switching)

</details>

<details>
<summary><strong>💾 Data & Storage (Partially Implemented)</strong></summary>

- [x] SQLite database backend ✅
- [x] Game history & archive ✅
- [x] Season player statistics ✅
- [ ] Roster import from CSV/Excel
- [ ] Historical game data CSV export
- [ ] Career statistics (multi-season)

</details>

<details>
<summary><strong>🔐 Security & Multi-user (Not Implemented)</strong></summary>

- [ ] User authentication system
- [ ] Role-based permissions
- [ ] API key management

</details>

<details>
<summary><strong>📱 Extended Interfaces (Not Implemented)</strong></summary>

- [ ] Mobile companion app
- [ ] Stream Deck native plugin
- [ ] Discord/Slack notifications
- [ ] Multi-game tournament mode

</details>

<details>
<summary><strong>🔌 Future Hardware Support</strong></summary>

- [ ] Daktronics All Sport 5000
- [ ] OES scoreboard protocol
- [ ] Generic protocol adapters

</details>

<p align="right"><a href="#-table-of-contents">⬆ Back to top</a></p>

---

## 📄 License

This project is licensed under the **GNU General Public License v3.0**.

See the [LICENSE](LICENSE) file for details.

---

<p align="center">
  <img src="https://img.shields.io/badge/Made%20with-❤️-red?style=for-the-badge" alt="Made with Love">
</p>

<p align="center">
  <em>Scoreboard Live Automation Platform</em><br>
  Built for hockey broadcast professionals 🏒
</p>

<p align="center">
  <a href="#scoreboard-live-automation-platform">⬆️ Back to Top</a>
</p>
