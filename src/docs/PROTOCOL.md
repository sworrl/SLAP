# MP-70 Binary Protocol Specification

This document describes the serial data protocol used by Trans-Lux FairPlay MP-70 series scoreboard controllers.

## Overview

The MP-70 controller outputs game data via RS-232 serial connection. The data stream contains binary packets with score, clock, and penalty information.

## Serial Configuration

| Parameter | Value |
|-----------|-------|
| Baud Rate | 9600 |
| Data Bits | 8 |
| Parity | None |
| Stop Bits | 1 |
| Flow Control | None |

## Packet Structure

### Packet Delimiters

All packets are wrapped with ASCII control characters:

| Byte | Value | Name | Description |
|------|-------|------|-------------|
| Start | `0x02` | STX | Start of Text |
| End | `0x03` | ETX | End of Text |

### Minimum Packet Length

Packets must be at least **80 bytes** to be considered valid.

## Packet Types

The packet type is identified by the character at byte position 1 (after STX).

### Type 'C' - Clock Update

Clock packets contain only the game clock time. These are sent frequently to update the countdown timer.

```
Position  Length  Field          Format
--------  ------  -----          ------
[0]       1       STX            0x02
[1]       1       Type           'C' (0x43)
[2:6]     4       Clock          ASCII "MMSS"
[7:79]    73      Padding        (unused)
[79]      1       ETX            0x03
```

**Clock Format:**
- 4 ASCII digits representing minutes and seconds
- Example: `"1500"` = 15:00 (15 minutes, 0 seconds)
- Example: `"0130"` = 01:30 (1 minute, 30 seconds)

### Type 'H' - Score/Game State Update

Score packets contain the full game state including scores, period, and penalties.

```
Position  Length  Field              Format
--------  ------  -----              ------
[0]       1       STX                0x02
[1]       1       Type               'H' (0x48)
[2:12]    11      Reserved           (unused)
[13:15]   2-3     Home Score         ASCII digits + space
[16:28]   13      Reserved           (unused)
[29:31]   2-3     Away Score         ASCII digits + space
[32:44]   13      Reserved           (unused)
[45:46]   1       Period             ASCII digit
[47:51]   5       Reserved           (unused)
[52:56]   4       Home Penalty 1     ASCII "MMSS" or spaces
[57:61]   4       Home Penalty 2     ASCII "MMSS" or spaces
[62:66]   4       Away Penalty 1     ASCII "MMSS" or spaces
[67:71]   4       Away Penalty 2     ASCII "MMSS" or spaces
[72:78]   7       Reserved           (unused)
[79]      1       ETX                0x03
```

## Field Formats

### Score Fields (bytes 13-15, 29-31)

- 2-3 ASCII characters
- Right-padded with space
- Examples:
  - `" 0 "` = 0
  - `" 3 "` = 3
  - `"12 "` = 12

### Period Field (byte 45)

- Single ASCII digit
- Values:
  - `'1'` = 1st Period
  - `'2'` = 2nd Period
  - `'3'` = 3rd Period
  - `'4'` or `'O'` = Overtime

### Penalty Time Fields (bytes 52-71)

- 4 ASCII characters in MMSS format
- Empty/spaces = no penalty
- Examples:
  - `"0200"` = 2:00 (2 minutes)
  - `"0130"` = 1:30 (1 minute 30 seconds)
  - `"    "` = No penalty active

## Data Flow

1. Controller sends packets continuously during game
2. Clock packets ('C') sent frequently for countdown updates
3. Score packets ('H') sent when game state changes
4. Parser must maintain last known clock since 'H' packets don't include clock

## Parsing Algorithm

```python
# Pseudocode for packet parsing

# Global state
last_clock = "20:00"

def parse_packet(packet):
    if len(packet) < 80:
        return None

    packet_type = chr(packet[1])

    if packet_type == 'C':
        # Clock update only
        raw = packet[2:6].decode('ascii')
        last_clock = f"{raw[:2]}:{raw[2:]}"
        return None  # No data to return

    if packet_type == 'H':
        # Full game state
        return {
            "home": int(packet[13:15].decode().strip()),
            "away": int(packet[29:31].decode().strip()),
            "period": packet[45:46].decode(),
            "clock": last_clock,
            "home_penalties": parse_penalties(packet[52:61]),
            "away_penalties": parse_penalties(packet[62:71])
        }

    return None

def parse_penalties(data):
    penalties = []
    for i in range(0, 8, 4):
        raw = data[i:i+4].decode('ascii')
        if raw.strip():
            minutes = int(raw[:2])
            seconds = int(raw[2:])
            penalties.append(minutes * 60 + seconds)
    return penalties
```

## Example Packets

### Clock Packet

```
Hex: 02 43 31 35 30 30 ... 03
     |  |  |________|
     |  |     Clock: "1500" = 15:00
     |  Type: 'C'
     STX
```

### Score Packet

```
Hex: 02 48 ... 20 33 20 ... 20 32 20 ... 32 ... 30 32 30 30 ... 03
     |  |      |_____|      |_____|      |      |________|
     |  |      Home: " 3"   Away: " 2"   Period Home Pen: "0200"
     |  Type: 'H'
     STX
```

## Notes

- The protocol appears to be proprietary and was reverse-engineered
- Field positions may vary slightly between firmware versions
- Some fields marked as "Reserved" may contain data in newer firmware
- RS-232 should be set to "ProLine data format" (not "VIDEO CHAR" mode)

---

## RS-232 Protocol Capture / Snooping

To reverse-engineer or debug the MP-70 protocol, you can capture the serial data stream using hardware or software methods.

### Hardware Snooping (Recommended)

For capturing live data between the MP-70 and an existing device without interruption:

#### Equipment Needed

| Item | Description | Example |
|------|-------------|---------|
| **Y-Cable / Splitter** | DB-9 RS-232 Y-cable or breakout board | DB-9 serial tap |
| **USB-Serial Adapter** | USB to RS-232 adapter (FTDI recommended) | FTDI FT232RL |
| **Terminal Software** | Serial capture software | TeraTerm, PuTTY, minicom |

#### Wiring Diagram

```
MP-70 Controller                         Scoreboard Display
     |                                        |
     | TX (Pin 3) ----------+---------------> RX
     |                      |
     |                      v
     |              [Snooper RX]
     |              USB-Serial Adapter
     |              (capture only)
     |
     +---------------------------------------- GND
```

**Key Points:**
- Only connect TX from MP-70 to your snooper's RX
- Do NOT connect your snooper's TX (this is passive listening)
- Connect GND between all devices
- The original connection remains intact

#### Pre-made Snooping Solutions

1. **RS-232 Protocol Analyzer** - Hardware devices like the Saleae Logic Analyzer with serial decoder
2. **Serial Port Splitter** - DB-9 Y-cable that duplicates TX to two destinations
3. **DIY Breakout Board** - Simple breadboard with screw terminals

### Software Capture

If you have direct access to the serial port (MP-70 connected only to your computer):

#### Linux

```bash
# Raw binary capture using cat
cat /dev/ttyUSB0 > capture.bin

# Using stty for proper settings first
stty -F /dev/ttyUSB0 9600 cs8 -cstopb -parenb raw
cat /dev/ttyUSB0 | tee capture.bin | hexdump -C

# Using screen with logging
screen -L -Logfile capture.log /dev/ttyUSB0 9600

# Using minicom
minicom -D /dev/ttyUSB0 -b 9600 -C capture.log
```

#### Windows

- **TeraTerm**: File > Log > Start logging (binary mode)
- **PuTTY**: Session > Logging > All session output
- **RealTerm**: Capture > Start, select binary format

#### macOS

```bash
# Using screen
screen -L /dev/tty.usbserial-XXXXX 9600

# Using minicom (via Homebrew)
brew install minicom
minicom -D /dev/tty.usbserial-XXXXX -b 9600 -C capture.log
```

### Analyzing Captured Data

Once you have a binary capture file:

```bash
# View hex dump
hexdump -C capture.bin | less

# Find packet boundaries (STX = 0x02, ETX = 0x03)
hexdump -C capture.bin | grep "02.*03"

# Using Python for analysis
python3 -c "
data = open('capture.bin', 'rb').read()
# Find all packets (STX to ETX)
packets = []
start = 0
while True:
    stx = data.find(b'\x02', start)
    if stx == -1:
        break
    etx = data.find(b'\x03', stx)
    if etx == -1:
        break
    packets.append(data[stx:etx+1])
    start = etx + 1
print(f'Found {len(packets)} packets')
for i, p in enumerate(packets[:5]):
    print(f'Packet {i}: {len(p)} bytes, type={chr(p[1]) if len(p)>1 else \"?\"}')
"
```

### Logic Analyzer Setup

For detailed timing and protocol analysis:

1. **Saleae Logic Analyzer** (recommended)
   - Connect CH0 to TX line
   - Set async serial analyzer: 9600 baud, 8N1
   - Export decoded data as CSV or binary

2. **sigrok / PulseView** (open source)
   ```bash
   # Install on Linux
   sudo apt install sigrok pulseview

   # Capture with compatible hardware
   pulseview  # GUI for visual analysis
   ```

3. **Bus Pirate** (budget option)
   - Connect MISO to TX line
   - Use UART sniffer mode at 9600 baud

### Tips for Reverse Engineering

1. **Trigger Score Changes** - Manually adjust scores during capture to identify which bytes change
2. **Record Clock Changes** - Watch the countdown timer to identify clock position
3. **Note Penalties** - Add penalties and observe which fields populate
4. **Compare Periods** - Advance through periods (1st, 2nd, 3rd, OT) to find period byte
5. **Document Everything** - Keep notes on byte positions and observed values

### Sample Capture Session

```bash
# 1. Configure port
stty -F /dev/ttyUSB0 9600 cs8 -cstopb -parenb raw

# 2. Start capture in one terminal
cat /dev/ttyUSB0 > session_$(date +%Y%m%d_%H%M%S).bin &

# 3. Monitor in another terminal
tail -f session_*.bin | hexdump -C

# 4. On the MP-70:
#    - Set home score to 1, watch for change
#    - Set away score to 2, watch for change
#    - Start clock, observe continuous updates
#    - Add penalty, note new data

# 5. Stop capture
kill %1
```

## References

- [Trans-Lux Fair-Play MP-70 Manual](https://www.fair-play.com/wp-content/uploads/2023/03/98-0002-29MP-50_MP-70.pdf)
- [BoxCast Integration Guide](https://support.boxcast.com/en/articles/4235162-capture-scoreboard-data-from-a-translux-fair-play-scoreboard)
- [CasparCG Forum Discussion](https://casparcgforum.org/t/trans-lux-fair-play-mp-70-scoreboard-data-output-into-casparcg/3712)
