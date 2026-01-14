# SLAP Setup Guide

This guide covers hardware setup, software installation, and CasparCG configuration.

## Software Installation

### Prerequisites

- Python 3.8 or higher
- Linux, macOS, or Windows with bash support

### Install Steps

```bash
# Clone or download SLAP
cd /path/to/SLAP

# Run the install script
./deploy.sh install
```

That's it! The deploy script handles:
- Python version verification
- Virtual environment creation
- Dependency installation

### Verify Installation

```bash
# Start in simulation mode
./deploy.sh start

# Check status
./deploy.sh status
```

Open http://localhost:9876 - you should see the SLAP dashboard.

## Hardware Setup

### Required Equipment

1. **Trans-Lux FairPlay MP-70 Controller**
   - Also compatible with MP-71, MP-72, MP-73 variants
   - Must have firmware version 2.25 or later

2. **RS-232 to USB Adapter**
   - Any standard USB-serial adapter should work
   - Recommended: FTDI-based adapters for reliability

3. **Serial Cable**
   - DB-9 or appropriate connector for your MP-70 variant
   - May need null-modem adapter depending on wiring

### MP-70 Configuration

1. Access the MP-70 setup menu
2. Navigate to sport-specific setup
3. When prompted "VIDEO CHAR?", answer **NO**
   - This sets RS-232 to ProLine data format
4. Verify RS-232 output is enabled

### Connection

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

### Serial Port Configuration

| Setting | Description |
|---------|-------------|
| `port` | Serial port path (e.g., `/dev/ttyUSB0`, `COM4`) |
| `baudrate` | Always 9600 for MP-70 |
| `timeout` | Read timeout in seconds (default: 0.1) |

### CasparCG Configuration

| Setting | Description |
|---------|-------------|
| `host` | CasparCG server IP address |
| `port` | AMCP port (default: 5250) |
| `channel` | Video channel number |
| `layer` | Graphics layer number |
| `enabled` | Set to `false` to disable CasparCG |

## CasparCG Setup

### Installing CasparCG via Deploy Script

The easiest way to install CasparCG is using the built-in installer:

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
- Works on immutable Linux systems (Fedora Silverblue, Ubuntu Core, etc.)
- Doesn't require root/sudo access
- Automatically copies SLAP templates
- Creates a default config for 1080p output

**Supported distributions:**
- Ubuntu 22.04 (Jammy) and derivatives
- Ubuntu 24.04 (Noble) and derivatives
- Other Debian-based systems (uses Noble packages)

### Web-Based Control

You can also control CasparCG from the SLAP web dashboard:
1. Open http://localhost:9876
2. Find the "CasparCG Server" card
3. Use Start/Stop buttons to control the server
4. Click "Connect" to link SLAP to CasparCG

### Manual Installation

If you prefer to install CasparCG manually or need a different version:

1. Download from https://github.com/CasparCG/server/releases
2. Extract to your preferred location
3. Copy SLAP templates:
   ```bash
   cp -r src/templates/* /path/to/casparcg/templates/
   ```

### Testing Templates

1. Start CasparCG Server
2. Open CasparCG Client
3. Load template: `CG 1-10 ADD 1 "scorebug" 1`
4. Update with test data: `CG 1-10 UPDATE 1 "{\"home\":3,\"away\":2}"`

### AMCP Commands

SLAP sends these commands to CasparCG:

| Command | Description |
|---------|-------------|
| `CG 1-10 UPDATE 1 "{json}"` | Update scorebug data |
| `CG 1-10 INVOKE 1 "goal:HOME"` | Trigger goal animation |
| `CG 1-10 INVOKE 1 "show"` | Show scorebug |
| `CG 1-10 INVOKE 1 "hide"` | Hide scorebug |

## Running SLAP

### Using deploy.sh (Recommended)

```bash
# Start with defaults (simulation mode, port 9876)
./deploy.sh start

# Start on custom port
./deploy.sh start --port 9876

# Start with debug logging
./deploy.sh start --debug

# Stop server
./deploy.sh stop

# Check status
./deploy.sh status
```

### Running as Service (Linux)

Create systemd service file `/etc/systemd/system/slap.service`:

```ini
[Unit]
Description=SLAP Scoreboard Service
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/SLAP/src
ExecStart=/path/to/SLAP/src/venv/bin/python run.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable slap
sudo systemctl start slap
```

## Troubleshooting

### Serial Port Issues

**Permission denied:**
```bash
# Linux: Add user to dialout group
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
- Verify SLAP is running: `./deploy.sh status`
- Try different port: `./deploy.sh start --port 8888`
- Check firewall settings

## Getting Help

- Check the [API documentation](API.md)
- Review [protocol specification](PROTOCOL.md)
