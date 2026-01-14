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

## References

- [Trans-Lux Fair-Play MP-70 Manual](https://www.fair-play.com/wp-content/uploads/2023/03/98-0002-29MP-50_MP-70.pdf)
- [BoxCast Integration Guide](https://support.boxcast.com/en/articles/4235162-capture-scoreboard-data-from-a-translux-fair-play-scoreboard)
- [CasparCG Forum Discussion](https://casparcgforum.org/t/trans-lux-fair-play-mp-70-scoreboard-data-output-into-casparcg/3712)
