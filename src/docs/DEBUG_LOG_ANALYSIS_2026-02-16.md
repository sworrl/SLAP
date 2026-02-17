# Debug Log Analysis — February 16, 2026

## Session Overview

| Parameter | Value |
|-----------|-------|
| **Date** | February 16, 2026 |
| **Time** | 22:44:14 – 22:51:25 (approx. 7 minutes) |
| **Tester** | Tony |
| **Location** | Rink (real MP-70 hardware) |
| **SLAP Version** | 2.2.0 (pre-adaptive parser) |
| **Serial Port** | `/dev/ttyUSB0` |
| **Baud Rate** | 9600 |
| **Server** | `http://0.0.0.0:9876` |
| **Log File** | `/home/slap/SLAP/src/slap_debug.log` |
| **Database** | `/root/.local/share/slap/slap.db` |
| **CasparCG** | Disabled (mock client) |
| **Log Lines** | 30,892 |
| **Log Size** | ~2.8 MB |

### Session Timeline

| Time | Event |
|------|-------|
| 22:44:14 | SLAP started (1st attempt), serial port opened |
| 22:47:48 | SLAP restarted (2nd instance), serial port re-opened |
| 22:48:01 | Web dashboard loaded, WebSocket connected |
| 22:48:16 | **Recording start attempted → HTTP 400 (BUG)** |
| 22:48:56 | First serial packets received (game idle at 0-0, 10:00) |
| ~22:49:xx | Game started, clock counting down |
| ~22:49:xx | Scores progressed: 1-0, 2-0, 3-0, 3-1, 3-2, 3-3, 3-4, 3-5 |
| ~22:49:xx | Penalties: Home #11, Home #33, Guest #77, Guest #99 |
| ~22:50:xx | Period transitions: P1 → P2 → P3 |
| 22:51:25 | WebSocket disconnected, log ends |

---

## Recording Error

Tony attempted to start serial recording at 22:48:16. The request failed:

```
"POST /api/system/serial/record/start HTTP/1.1" 400 293
```

**Root Cause:** The JavaScript `api()` function sent `Content-Type: application/json` with an
empty body. Flask attempted to parse the empty string as JSON and returned 400 Bad Request
before the route handler was reached.

**Fix Applied (v2.3.0):**
- Frontend: `api()` now sends `{}` as body for all POST requests
- Backend: All `request.get_json()` calls now use `silent=True`

---

## Packet Statistics

| Metric | Value |
|--------|-------|
| **Total Packets** | 3,130 |
| **Clock Packets (type 'C')** | 2,236 (71.4%) |
| **Score Packets (type 'H')** | 894 (28.6%) |
| **Unique Clock Patterns** | 185 |
| **Unique Score Patterns** | 167 |
| **Other Packet Types** | 0 |
| **Packet Sizes** | 11 bytes (C) and 55 bytes (H) only |
| **Packets per second** | ~22 (3,130 packets / ~140 seconds) |
| **C:H ratio** | 2.5:1 (approx 2-3 clock packets per score packet) |

### Packet Size Discovery

The MP-70 at Tony's rink sends **11-byte** clock packets and **55-byte** score packets.
This is significantly smaller than the 80-byte packets described in most documentation.
The firmware/board type likely determines the packet size.

---

## Clock Packet Analysis (Type 'C' — 11 bytes)

### Packet Structure

```
Byte  Hex   Field              Description
----  ----  -----              -----------
[0]   02    STX                Start of Text
[1]   43    Type               'C' = Clock
[2]   20/3x Clock digit 1     Space or leading digit (minutes tens)
[3]   3x    Clock digit 2     Minutes ones / seconds tens
[4]   3x    Clock digit 3     Seconds tens
[5]   3x    Clock digit 4     Seconds ones
[6]   20    Separator          Space
[7]   3x    Period indicator   Period number (hundreds digit)
[8]   36    Fixed              '6' (always)
[9]   30    Fixed              '0' (always)
[10]  03    ETX                End of Text
```

### Clock Format

The clock field [2:6] encodes game time as a **packed decimal integer** where:
- Digit 1-2 = minutes (0-99)
- Digit 3-4 = seconds (00-59)

Observed countdown sequence confirms BCD-like encoding:

```
"1000" = 10:00 (initial)
" 959" =  9:59
" 958" =  9:58
  ...
" 900" =  9:00
" 859" =  8:59   ← NOT 8:60, rolls from 900 to 859
  ...
" 800" =  8:00
" 759" =  7:59   ← Same rollover pattern
  ...
" 658" =  6:58   (last observed)
```

**Key Finding:** The clock is NOT plain seconds (which would count 900→899→898).
Instead it uses the same encoding as MMSS where minutes and seconds are concatenated
as a single number. SLAP's `_format_clock()` already handles this correctly.

### Period Indicator

The trailing 3 bytes [7:10] encode the **current period**:

| Value | ASCII | Meaning |
|-------|-------|---------|
| `31 36 30` | `160` | **Period 1** |
| `32 36 30` | `260` | **Period 2** |
| `33 36 30` | `360` | **Period 3** |

The hundreds digit is the period number. The `60` suffix is constant (possibly
representing period length or a configuration code).

**Critical Discovery:** The **period is transmitted in clock packets**, NOT in score
packets. The H packet does not appear to carry period information at all. SLAP must
extract period from C packets.

Period transitions observed:
- `160` → `260` at Packet #2188 (clock value 756)
- `260` → `360` at Packet #2304 (clock value 748)

---

## Score Packet Analysis (Type 'H' — 55 bytes)

### Complete Field Map

Derived from observing 167 unique packets with scores 0-0 through 3-5 and
four simultaneous penalty countdowns:

```
Byte   Hex    Field                     Notes
-----  -----  -----                     -----
[0]    02     STX                       Start of Text
[1]    48     Type                      'H' = Score/Game State
[2-12] 20..   (unused)                  Always spaces
[13]   3x     HOME SCORE                Single ASCII digit (0-9)
[14-15] 20    (unused)                  Spaces
[16-17] 3x3x  Home Penalty 1 PLAYER #  2-digit jersey number (e.g. "11")
[18]   20     Separator                 Space
[19-21] 3x3x3x Home Penalty 1 TIME     3-digit seconds (e.g. "100"=1:00, "059"=0:59)
[22-23] 3x3x  Home Penalty 2 PLAYER #  2-digit jersey number (e.g. "33")
[24]   20     Separator                 Space
[25-27] 3x3x3x Home Penalty 2 TIME     3-digit seconds
[28-38] 20..   (unused)                 Always spaces
[39]   3x     AWAY SCORE                Single ASCII digit (0-9)
[40-41] 20    (unused)                  Spaces
[42-43] 3x3x  Away Penalty 1 PLAYER #  2-digit jersey number (e.g. "77")
[44]   20     Separator                 Space
[45-47] 3x3x3x Away Penalty 1 TIME     3-digit seconds
[48-49] 3x3x  Away Penalty 2 PLAYER #  2-digit jersey number (e.g. "99")
[50]   20     Separator                 Space
[51-53] 3x3x3x Away Penalty 2 TIME     3-digit seconds
[54]   03     ETX                       End of Text
```

### Visual Layout

```
Position: 0  1  2        12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28       38 39 40 41 42 43 44 45 46 47 48 49 50 51 52 53 54
          |  |  |         | |     |  |     |  |        |  |     |  |        |        | |     |  |     |  |        |  |     |  |        |
          S  H  [unused ] S [pad] P1#   P1time  P2#   P2time   [unused  ] S [pad] P1#   P1time  P2#   P2time   E
          T  |            c       l           l                            c       l           l                  T
          X  type         o       a           a                            o       a           a                  X
                          r       y           y                            r       y           y
                          e       e           e                            e       e           e
                                  r           r                                    r           r
                          H       #           #                            A       #           #
                                  1           2                                    1           2

S = Home Score (1 byte)    P1# = Penalty 1 Player Number (2 bytes)    P1time = Penalty 1 Time (3 bytes)
                           P2# = Penalty 2 Player Number (2 bytes)    P2time = Penalty 2 Time (3 bytes)
```

### Score Progression

| First Packet # | Home | Away | Context |
|----------------|------|------|---------|
| #3 | 0 | 0 | Game idle (10:00 on clock) |
| #846 | **1** | 0 | Home scores |
| #963 | **2** | 0 | Home scores |
| #1081 | **3** | 0 | Home scores |
| #1162 | 3 | **1** | Away scores |
| #1218 | 3 | **2** | Away scores |
| #1274 | 3 | **3** | Away ties it |
| #1313 | 3 | **4** | Away takes lead |
| #1344 | 3 | **5** | Away extends lead |

### Penalty Tracking

The log captured four separate penalty events with real-time countdown:

#### Home Penalty 1: Player #11

| First Pkt | Bytes [16:22] | Decoded |
|-----------|---------------|---------|
| #1551 | `31 31 20 31 30 30` | #11, 1:00 (starts) |
| #1565 | `31 31 20 30 35 39` | #11, 0:59 |
| ... | (counting down 1/sec) | ... |
| #2377 | `31 31 20 30 30 31` | #11, 0:01 |
| #2391 | `20 20 20 20 20 20` | (cleared — expired) |

#### Home Penalty 2: Player #33

| First Pkt | Bytes [22:28] | Decoded |
|-----------|---------------|---------|
| #1764 | `33 33 20 31 30 30` | #33, 1:00 (starts while #11 at 0:45) |
| #1778 | `33 33 20 30 35 39` | #33, 0:59 |
| ... | (counting down) | ... |
| #2601 | `33 33 20 30 30 31` | #33, 0:01 |
| #2604 | `20 20 20 20 20 20` | (cleared — expired) |

#### Away Penalty 1: Player #77

| First Pkt | Bytes [42:48] | Decoded |
|-----------|---------------|---------|
| #1929 | `37 37 20 31 30 30` | #77, 1:00 (starts) |
| #1943 | `37 37 20 30 35 39` | #77, 0:59 |
| ... | (counting down) | ... |
| #2755 | `37 37 20 30 30 31` | #77, 0:01 |
| #2769 | `20 20 20 20 20 20` | (cleared — expired) |

#### Away Penalty 2: Player #99

| First Pkt | Bytes [48:54] | Decoded |
|-----------|---------------|---------|
| #2069 | `39 39 20 31 30 30` | #99, 1:00 (starts while #77 at 0:50) |
| #2083 | `39 39 20 30 35 39` | #99, 0:59 |
| ... | (counting down) | ... |
| #2895 | `39 39 20 30 30 31` | #99, 0:01 |

### Penalty Time Format

Penalty times are encoded as **3-digit seconds** (NOT MMSS):

| Bytes | ASCII | Meaning |
|-------|-------|---------|
| `31 30 30` | `100` | 100 seconds = 1:40 ... wait, it counts down to 059. |
| `30 35 39` | `059` | 59 seconds |
| `30 30 31` | `001` | 1 second |

**Correction:** The "100" represents 1:00 (one minute zero seconds), NOT 100 seconds.
The encoding is the same BCD/MMSS as the clock: `1` = 1 minute, `00` = 0 seconds.
This is confirmed by the countdown: `100 → 059 → 058 → ... → 001` (skips from 100 to 059,
same rollover as clock). These are 2-minute penalties displayed as the time remaining.

---

## Differences From Previously Assumed Protocol

| Feature | Previous Assumption | Actual (Tony's MP-70) |
|---------|--------------------|-----------------------|
| Packet size | 80 bytes | **55 bytes** (H) / **11 bytes** (C) |
| Home score position | [13:15] (2 bytes) | **[13] (1 byte)** |
| Away score position | [29:31] (2 bytes) | **[39] (1 byte)** |
| Period location | H packet [45:46] | **C packet [7] (hundreds digit)** |
| Period format | ASCII digit "1","2","3" | **Encoded as "160","260","360"** |
| Penalty format | MMSS at fixed offsets | **Player# (2) + space + Time (3)** |
| Penalty player # | Not in protocol | **Included at [16:17],[22:23],[42:43],[48:49]** |
| Penalty time format | MMSS (4 bytes) | **BCD seconds (3 bytes)** |
| Clock trailing data | Padding/unused | **Period indicator (3 bytes)** |

---

## SLAP Parser Impact

### What Worked (v2.2.0)

- STX/ETX packet extraction: **Correct** — 100% of packets properly framed
- Clock parsing (`_format_clock`): **Correct** — BCD format happens to parse correctly
- Type byte detection: **Correct** — 'C' and 'H' properly identified

### What Failed (v2.2.0)

- All 894 H packets logged as "UNRECOGNIZED PACKET" (100% failure rate)
- No score, penalty, or period data was decoded
- Recording start failed with HTTP 400

### Fixes Applied (v2.3.0)

1. Added `LAYOUT_MP70_SHORT` for 55-byte packets
2. Made period parsing lenient (defaults to "1" when blank)
3. Fixed recording HTTP 400 bug
4. Fixed `start_recording()` error message bug

### Remaining Work (v2.3.1+)

Based on this analysis, the parser needs further updates:

1. **Extract period from clock packets** — Period is in C packet bytes [7:10],
   not the H packet. The parser should decode the hundreds digit as the period number.
2. **Update 55-byte layout** to use the exact discovered field positions:
   - Home score: [13] (1 byte, not 2)
   - Away score: [39] (1 byte, not 2)
   - Home penalty 1: player [16:18], time [19:22]
   - Home penalty 2: player [22:24], time [25:28]
   - Away penalty 1: player [42:44], time [45:48]
   - Away penalty 2: player [48:50], time [51:54]
3. **Parse penalty player numbers** — New feature, jersey numbers available
4. **Parse penalty times as 3-digit BCD** — Not MMSS 4-byte format
5. **Handle single-digit scores** — Scores are 1 byte, not 2

---

## Raw Data Examples

### Clock Packet — Period 1, 10:00

```
Hex:   02 43 31 30 30 30 20 31 36 30 03
ASCII: .  C  1  0  0  0     1  6  0  .
       STX   clock="1000"   per="160"  ETX
       → Clock 10:00, Period 1
```

### Clock Packet — Period 2, 7:56

```
Hex:   02 43 20 37 35 36 20 32 36 30 03
ASCII: .  C     7  5  6     2  6  0  .
       STX   clock=" 756"   per="260"  ETX
       → Clock 7:56, Period 2
```

### Score Packet — Score 0-0, No Penalties

```
Hex:   02 48 20 20 20 20 20 20 20 20 20 20 20 30 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 30 20 20 20 20 20 20 20 20 20 20 20 20 20 20 03
       STX H  [___________unused___________] 0  [_____________________________unused_____________________________] 0  [______________________________unused_____________________________] ETX
       → Home 0, Away 0, no penalties
```

### Score Packet — Score 3-5, Home #11 at 0:45, Home #33 at 1:00

```
Hex:   02 48 20 20 20 20 20 20 20 20 20 20 20 33 20 20 31 31 20 30 34 35 33 33 20 31 30 30 20 20 20 20 20 20 20 20 20 20 20 35 20 20 20 20 20 20 20 20 20 20 20 20 20 20 03
       STX H  [________unused________] 3     1  1     0  4  5  3  3     1  0  0  [________unused________] 5  [_________________unused_________________] ETX
       → Home 3, Away 5
       → Home Pen1: #11, 0:45
       → Home Pen2: #33, 1:00
```

### Score Packet — Score 3-5, All Four Penalty Slots Active

```
Hex:   02 48 20 20 20 20 20 20 20 20 20 20 20 33 20 20 31 31 20 30 32 33 33 33 20 30 33 39 20 20 20 20 20 20 20 20 20 20 20 35 20 20 37 37 20 30 35 30 39 39 20 31 30 30 03
       STX H  [________unused________] 3     1  1     0  2  3  3  3     0  3  9  [________unused________] 5     7  7     0  5  0  9  9     1  0  0  ETX
       → Home 3, Away 5
       → Home Pen1: #11, 0:23    Home Pen2: #33, 0:39
       → Away Pen1: #77, 0:50    Away Pen2: #99, 1:00
```

---

## Environment Notes

- SLAP runs as root on `/home/slap/SLAP/`
- Database stored at `/root/.local/share/slap/slap.db`
- Serial port: `/dev/ttyUSB0` (USB-to-serial adapter)
- Server port: 9876 (HTTP, no HTTPS configured)
- Client connects from localhost (127.0.0.1)
- Two SLAP starts in log (22:44:14 and 22:47:48) — Tony likely restarted to test
- WebSocket "Failed to write closing frame" at shutdown is normal (browser closed)

---

## Source File

The original debug log is available at:
- `src/docs/slap_debug_2026-02-16.log` (in this repository)
- Viewable from the SLAP web dashboard at `/docs`
