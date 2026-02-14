# FairPlay MP-70 Serial Protocol Research Notes

## Overview

The FairPlay/Trans-Lux MP-70/50 Series scoreboard controller uses a **proprietary protocol**
that is not publicly documented by the manufacturer. These notes compile findings from
reverse engineering, community projects, and integration guides.

## Two Data Interfaces

The MP-70 has two completely different data output interfaces:

### 1. Proprietary Scoreboard Wire (1/4" phone jacks)
- **Signal**: Differential signaling (not RS-232), received via AM26LS33 chip
- **Encoding**: Self-clocking, pulse-width modulated (~30 microseconds/symbol)
- **Data**: 4-bit BCD nibbles, 105 bits (SCOREBOARD) + 56 bits (TIMERS) per frame
- **Use**: Driving the physical scoreboard display

### 2. RS-232 Serial Port (DB-9 connector)
- **This is the interface SLAP connects to**
- Configurable between two output formats:
  - **ProLine data** (default, VIDEO CHAR? = NO)
  - **VCG/VideoStamp+** (VIDEO CHAR? = YES, sends ASCII text for character generators)
- Used by ProScoreboard, BoxCast, CasparCG, and SLAP

## RS-232 Serial Settings

| Parameter | Value |
|-----------|-------|
| **Baud rate** | **9600** (standard) or **19200** (some firmware/models) |
| Data bits | 8 |
| Parity | None |
| Stop bits | 1 |
| Flow control | None |

**Important**: If 9600 doesn't work, try 19200. The baud rate may vary by firmware version.

## MP-70 vs MP-69 Format

The controller can output in either format (configurable per connector):

| Feature | MP-69 (1984) | MP-70 (1998+) |
|---------|-------------|---------------|
| Target | Incandescent scoreboards | LED + incandescent |
| Encoding | 4-bit BCD nibbles | STX/ETX framed ASCII |
| Connector prompts | CONN.1,MP69? / CONN.2,MP69? / CONN3&4,MP69? | Same (answer NO for MP-70) |

## Packet Structure (MP-70 RS-232 ProLine Format)

### Framing
- **STX** (0x02) = Start of packet
- **ETX** (0x03) = End of packet
- Packets are everything between STX and ETX (inclusive)

### Packet Types
| Byte at position 1 | Type | Description |
|---------------------|------|-------------|
| `'C'` (0x43) | Clock | Updates game clock only |
| `'H'` (0x48) | Hockey/Score | Full game state (scores, period, penalties) |

Other type bytes may exist for different sports or firmware versions.

### Clock Packet (Type 'C')
```
[0]    STX (0x02)
[1]    'C' (0x43)
[2:6]  Clock as "MMSS" ASCII (e.g., "1530" = 15:30)
[6:79] Unused/padding
[79]   ETX (0x03)
```

### Score Packet (Type 'H') - Standard 80-byte Layout
```
[0]      STX (0x02)
[1]      'H' (0x48)
[2:12]   Unknown
[13:15]  Home score (2 ASCII digits, space-padded)
[15:29]  Unknown
[29:31]  Away score (2 ASCII digits, space-padded)
[31:45]  Unknown
[45:46]  Period (1 ASCII digit: "1","2","3" or "O" for OT)
[46:52]  Unknown
[52:56]  Home penalty 1 time (MMSS)
[56]     Separator
[57:61]  Home penalty 2 time (MMSS)
[61]     Separator
[62:66]  Away penalty 1 time (MMSS)
[66]     Separator
[67:71]  Away penalty 2 time (MMSS)
[71:79]  Unknown
[79]     ETX (0x03)
```

**Note**: The "unknown" regions may contain additional data like shots on goal,
timeouts remaining, or sport-specific fields. The exact contents depend on
the board type and sport selected.

## MP-69D Wire Protocol Field Positions (BCD Nibbles)

From the MP-69D-Scoreboard-Decoder project (Arduino-based hardware decoder):

### Hockey
| Field | Nibble Position | Description |
|-------|----------------|-------------|
| PRD | 17 | Period |
| VS1 | 18 | Visitor score tens |
| VS2 | 19 | Visitor score ones |
| HS1 | 20 | Home score tens |
| HS2 | 21 | Home score ones |
| CLKSEC1 | 22 | Clock seconds tens |
| CLKSEC2 | 23 | Clock seconds ones |
| CLKMIN1 | 24 | Clock minutes tens |
| CLKMIN2 | 25 | Clock minutes ones |

### Basketball
| Field | Nibble Position |
|-------|----------------|
| VF1/VF2 | 8-9 (visitor fouls) |
| HF1/HF2 | 10-11 (home fouls) |
| POSS | 15 |
| PRD | 17 |
| VS1/VS2 | 18-19 |
| HS1/HS2 | 20-21 |
| CLKSEC1/2 | 22-23 |
| CLKMIN1/2 | 24-25 |
| SHOT1/2 | 32-33 (shot clock) |

### Football
| Field | Nibble Position |
|-------|----------------|
| HTO/VTO | 4-5 (timeouts) |
| BALLON | 6-7 |
| POSS | 10 |
| DOWN | 14 |
| QTR | 15 |
| VS1/VS2 | 16-17 |
| HS1/HS2 | 18-19 |
| CLKSEC/MIN | 20-23 |

## Board Types

The MP-70 supports 40+ board types (00-40, 83, PS). Each type maps to
specific scoreboard models. The board type affects which data fields
are transmitted and their positions. See the Boards Supported table
in the MP-70 manual (pages 145-148).

Key hockey-related board types:
- **13**: HK-1650/1655/1670/1750/1755 (Default groups 25/26)
- **14**: HK-1660/1760/1770/1780/1790/1870/1880/1885 (Default groups 25/26)

## SLAP Parser Auto-Detection

The SLAP parser tries multiple strategies to decode incoming data:

1. **STX/ETX framing** with known type bytes ('C', 'H')
2. **Multiple field layouts** (standard 80-byte, compact, wide)
3. **Alternative type bytes** (sport-specific indicators)
4. **CR/LF line framing** (VCG/VideoStamp+ ASCII text mode)
5. **ASCII pattern scanning** (regex search for scores/clock in text)
6. **Fixed-length chunking** (80-byte blocks when no delimiters found)

When no strategy succeeds, detailed diagnostics are logged including
hex dumps, ASCII representation, and byte analysis to aid reverse engineering.

## Troubleshooting

### All packets "invalid"
1. Check baud rate (try both 9600 and 19200)
2. Enable debug logging: `slap --debug`
3. Start a serial recording from the web UI
4. Check the VIDEO CHAR? setting on the MP-70 (try both YES and NO)
5. Check which connector (CONN.1, CONN.2, CONN3&4) the cable is on
6. Verify the MP-69/MP-70 format setting matches your connector

### No data received
1. Verify the RS-232 cable is connected (not the 1/4" scoreboard jacks)
2. Check cable: straight-through DB-9, pins 2 (RX), 3 (TX), 5 (GND)
3. Try a USB-to-serial adapter if using a laptop

## References

- MP-70/50 Series User Guide (PN 98-0002-29)
- SP-70 Statistics Controller Guide (PN 98-0002-33)
- [MP-69D Scoreboard Decoder](https://github.com/will62794/MP-69D-Scoreboard-Decoder)
- [PoC||GTFO 21:06 - Reversing FairPlay 710](https://mcfp.felk.cvut.cz/publicDatasets/pocorgtfo/contents/articles/21-06.pdf)
- [BoxCast - Fair-Play Integration](https://support.boxcast.com/en/articles/4235162)
- [ProScoreboard - MP-70 Connection](https://support.renewedvision.com/hc/en-us/articles/360011596914)
- FairPlay Technical Support: (800) 462-2716
