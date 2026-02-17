"""
MP-70 / MP-69 Protocol Parser

Decodes serial data from Trans-Lux FairPlay MP-70/50 Series scoreboard controllers.

Supports multiple data formats that the MP-70 can output:
  - MP-70 format (1998+): STX/ETX framed ASCII packets, 80+ bytes
  - Shorter MP-70 packets: Some firmware/board types send shorter frames
  - ASCII text lines: CR/LF delimited readable text (VCG/VideoStamp+ mode)
  - Raw BCD nibble data: MP-69 legacy format (4-bit encoded)

The parser auto-detects the format from incoming data and adapts accordingly.
When a format is unknown, extensive diagnostics are logged to help reverse-engineer it.

See docs/PROTOCOL_NOTES.md for detailed protocol research.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional, List

logger = logging.getLogger(__name__)

# Packet delimiters
STX = 0x02  # Start of Text
ETX = 0x03  # End of Text
CR = 0x0D   # Carriage Return
LF = 0x0A   # Line Feed
SOH = 0x01  # Start of Header

# Minimum valid packet lengths for different strategies
MIN_PACKET_LENGTH_STRICT = 80   # Original MP-70 full packet
MIN_PACKET_LENGTH_RELAXED = 10  # Allow shorter packets from different firmware

# Global tracking for verbose serial data display
_last_raw_data: Optional[bytes] = None
_packet_stats = {
    "total_received": 0,
    "valid_packets": 0,
    "clock_packets": 0,
    "score_packets": 0,
    "invalid_packets": 0,
    "bytes_received": 0,
    "last_packet_type": None,
    "last_packet_time": None,
    "detected_format": None,
    "auto_detect_attempts": 0,
}

# Serial recording
_recording_active = False
_recording_file = None
_recording_path: Optional[str] = None
_recording_bytes = 0


def get_last_raw_data() -> Optional[bytes]:
    """Get the last raw packet data for verbose display."""
    return _last_raw_data


def get_packet_stats() -> dict:
    """Get packet statistics for verbose display."""
    return _packet_stats.copy()


def update_raw_data(data: bytes) -> None:
    """Update the last raw data received."""
    global _last_raw_data
    _last_raw_data = data
    _packet_stats["bytes_received"] += len(data)
    # Write to recording if active
    write_to_recording(data)


def record_packet(packet_type: str, valid: bool = True) -> None:
    """Record packet statistics."""
    from datetime import datetime

    _packet_stats["total_received"] += 1
    _packet_stats["last_packet_time"] = datetime.now().isoformat()

    if valid:
        _packet_stats["valid_packets"] += 1
        _packet_stats["last_packet_type"] = packet_type
        if packet_type == "C":
            _packet_stats["clock_packets"] += 1
        elif packet_type in ("H", "score", "text_score"):
            _packet_stats["score_packets"] += 1
    else:
        _packet_stats["invalid_packets"] += 1


def start_recording(filepath: Optional[str] = None) -> str:
    """Start recording serial data to a file.

    Args:
        filepath: Optional path for the recording file.
                  If not provided, creates a timestamped file in the logs directory.

    Returns:
        The path to the recording file.
    """
    global _recording_active, _recording_file, _recording_path, _recording_bytes
    from datetime import datetime
    from pathlib import Path
    import os

    if _recording_active:
        return _recording_path

    # Determine file path
    if filepath:
        _recording_path = filepath
    else:
        # Default to logs directory
        if os.name == 'nt':
            log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "slap" / "logs"
        else:
            log_dir = Path.home() / ".local" / "share" / "slap" / "logs"

        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            raise PermissionError(f"Cannot create logs directory: {log_dir}. Check permissions.")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _recording_path = str(log_dir / f"serial_recording_{timestamp}.bin")

    try:
        _recording_file = open(_recording_path, "wb")
        _recording_active = True
        _recording_bytes = 0
        logger.info(f"Started serial recording to: {_recording_path}")
        return _recording_path
    except PermissionError:
        failed_path = _recording_path
        _recording_path = None
        raise PermissionError(f"Cannot write to: {failed_path}. Check permissions.")
    except Exception as e:
        logger.error(f"Failed to start recording: {e}")
        _recording_path = None
        raise


def stop_recording() -> dict:
    """Stop recording serial data.

    Returns:
        Dictionary with recording info (path, bytes recorded).
    """
    global _recording_active, _recording_file, _recording_path, _recording_bytes

    if not _recording_active:
        return {"status": "not_recording"}

    result = {
        "status": "stopped",
        "path": _recording_path,
        "bytes_recorded": _recording_bytes,
    }

    try:
        if _recording_file:
            _recording_file.close()
            _recording_file = None
    except Exception as e:
        logger.error(f"Error closing recording file: {e}")

    _recording_active = False
    logger.info(f"Stopped serial recording. Total bytes: {_recording_bytes}")

    return result


def get_recording_status() -> dict:
    """Get the current recording status.

    Returns:
        Dictionary with recording status info.
    """
    return {
        "recording": _recording_active,
        "path": _recording_path,
        "bytes_recorded": _recording_bytes,
    }


def write_to_recording(data: bytes) -> None:
    """Write data to the recording file if recording is active."""
    global _recording_bytes

    if not _recording_active or not _recording_file:
        return

    try:
        _recording_file.write(data)
        _recording_file.flush()
        _recording_bytes += len(data)
    except Exception as e:
        logger.error(f"Error writing to recording: {e}")


@dataclass
class GameData:
    """Parsed game state from MP-70 packet."""
    home_score: int
    away_score: int
    period: str
    clock: str
    home_penalties: List[int]  # List of penalty times in seconds
    away_penalties: List[int]
    parse_method: str = ""  # Which parsing strategy succeeded

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "home": self.home_score,
            "away": self.away_score,
            "period": self.period,
            "clock": self.clock,
            "home_penalties": self.home_penalties,
            "away_penalties": self.away_penalties
        }


# ============ Field Layout Definitions ============
# Different board types / firmware versions may use different byte positions.
# Each layout maps field names to (start, end) byte offsets within the packet.

LAYOUT_MP70_STANDARD = {
    "name": "MP-70 Standard (80-byte)",
    "min_length": 80,
    "type_byte": 1,
    "clock": (2, 6),          # 'C' packets: MMSS at bytes 2-5
    "home_score": (13, 15),   # 2 ASCII digits
    "away_score": (29, 31),   # 2 ASCII digits
    "period": (45, 46),       # 1 ASCII digit
    "home_pen1": (52, 56),    # MMSS
    "home_pen2": (57, 61),    # MMSS
    "away_pen1": (62, 66),    # MMSS
    "away_pen2": (67, 71),    # MMSS
}

LAYOUT_MP70_COMPACT = {
    "name": "MP-70 Compact (shorter packets)",
    "min_length": 40,
    "type_byte": 1,
    "clock": (2, 6),
    "home_score": (7, 10),    # Try tighter packing
    "away_score": (11, 14),
    "period": (15, 16),
    "home_pen1": (17, 21),
    "home_pen2": (22, 26),
    "away_pen1": (27, 31),
    "away_pen2": (32, 36),
}

LAYOUT_MP70_WIDE = {
    "name": "MP-70 Wide (3-digit scores)",
    "min_length": 80,
    "type_byte": 1,
    "clock": (2, 6),
    "home_score": (13, 16),   # 3 ASCII digits
    "away_score": (29, 32),   # 3 ASCII digits
    "period": (45, 46),
    "home_pen1": (52, 56),
    "home_pen2": (57, 61),
    "away_pen1": (62, 66),
    "away_pen2": (67, 71),
}

# Confirmed from real MP-70 hardware (Tony's rink, Feb 2026)
# 55-byte STX/ETX packets. Field map verified with 167 unique score patterns,
# penalty countdowns for 4 simultaneous players, and score changes 0-0 through 3-5.
# Period is NOT in H packets — it's in C packets at byte [7].
# See docs/DEBUG_LOG_ANALYSIS_2026-02-16.md for full analysis.
LAYOUT_MP70_SHORT = {
    "name": "MP-70 Short (55-byte)",
    "min_length": 55,
    "max_length": 70,       # Prevent matching 80-byte standard packets
    "type_byte": 1,
    "clock": (2, 6),
    "home_score": (13, 14),     # Single ASCII digit
    "away_score": (39, 40),     # Single ASCII digit
    # Period comes from C packets, not H — field intentionally omitted
    # Penalties include player jersey numbers (new format):
    #   player# (2 bytes) + space + time (3 bytes BCD)
    "home_pen1_player": (16, 18),
    "home_pen1": (19, 22),      # 3-digit BCD seconds (e.g. "100"=1:00)
    "home_pen2_player": (22, 24),
    "home_pen2": (25, 28),
    "away_pen1_player": (42, 44),
    "away_pen1": (45, 48),
    "away_pen2_player": (48, 50),
    "away_pen2": (51, 54),
}

ALL_LAYOUTS = [LAYOUT_MP70_STANDARD, LAYOUT_MP70_WIDE, LAYOUT_MP70_SHORT, LAYOUT_MP70_COMPACT]


class MP70Parser:
    """
    Adaptive parser for FairPlay MP-70/50 Series serial data.

    Supports multiple data formats and auto-detects the protocol:
    - STX/ETX framed binary (MP-70 standard)
    - CR/LF delimited ASCII text (VCG/VideoStamp+ mode)
    - Various packet lengths and field positions

    Maintains the last known clock value since clock updates
    come in separate packets from score updates.
    """

    # Number of consecutive successes with the same method before locking
    LOCK_THRESHOLD = 3

    def __init__(self):
        self._last_clock = "20:00"
        self._last_period = "1"        # Period from C packets (bytes [7:10])
        self._detected_format = None   # "stx_etx", "ascii_lines", etc.
        self._detected_layout = None   # Which field layout works
        self._locked_strategy = None   # Full strategy string that's been locked
        self._format_locked = False    # Once locked, skip other strategies
        self._strategy_hits = {}       # {strategy_name: consecutive_success_count}
        self._last_winning_strategy = None

    @property
    def last_clock(self) -> str:
        """Get the last known clock value."""
        return self._last_clock

    @last_clock.setter
    def last_clock(self, value: str) -> None:
        """Set the clock value (useful for simulation)."""
        self._last_clock = value

    @property
    def detected_format(self) -> Optional[str]:
        """Get the detected protocol format."""
        return self._detected_format

    @property
    def locked_strategy(self) -> Optional[str]:
        """Get the locked parsing strategy, or None if still auto-detecting."""
        return self._locked_strategy

    def get_detection_status(self) -> dict:
        """Get full auto-detection status for the web UI."""
        return {
            "locked": self._format_locked,
            "locked_strategy": self._locked_strategy,
            "detected_format": self._detected_format,
            "last_winning_strategy": self._last_winning_strategy,
            "strategy_hits": dict(self._strategy_hits),
            "lock_threshold": self.LOCK_THRESHOLD,
        }

    def _record_strategy_success(self, strategy_name: str, layout: dict = None) -> None:
        """Record a successful parse with a given strategy. Lock if threshold reached."""
        self._last_winning_strategy = strategy_name
        _packet_stats["detected_format"] = strategy_name

        # Count consecutive hits — reset all other strategies' counts
        prev_count = self._strategy_hits.get(strategy_name, 0)
        self._strategy_hits = {strategy_name: prev_count + 1}

        if not self._format_locked and self._strategy_hits[strategy_name] >= self.LOCK_THRESHOLD:
            self._format_locked = True
            self._locked_strategy = strategy_name
            self._detected_format = strategy_name
            if layout:
                self._detected_layout = layout
            logger.info(f"PROTOCOL LOCKED: '{strategy_name}' "
                       f"(after {self._strategy_hits[strategy_name]} consecutive successes)")
        elif not self._format_locked:
            logger.info(f"Strategy '{strategy_name}' success "
                       f"({self._strategy_hits[strategy_name]}/{self.LOCK_THRESHOLD} to lock)")

    def _parse_mmss(self, raw: bytes) -> Optional[int]:
        """Parse a 4-byte MMSS time field to seconds."""
        try:
            text = raw.decode("ascii").strip()
            if not text or text == "0000":
                return None
            # Try MMSS format
            if len(text) >= 3:
                minutes = int(text[:-2] or "0")
                seconds = int(text[-2:])
                if 0 <= minutes <= 99 and 0 <= seconds <= 59:
                    total = minutes * 60 + seconds
                    return total if total > 0 else None
            # Try just seconds
            val = int(text)
            return val if val > 0 else None
        except (ValueError, UnicodeDecodeError):
            return None

    def _format_clock(self, raw: bytes) -> Optional[str]:
        """Parse and format a clock field as MM:SS string."""
        try:
            text = raw.decode("ascii").strip()
            if not text:
                return None
            # Already has colon? Validate it looks like a time
            if ":" in text:
                parts = text.split(":")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    m, s = int(parts[0]), int(parts[1])
                    if m < 100 and s < 60:
                        return text
                return None
            # Must be all digits for MMSS format
            if not text.isdigit():
                return None
            # MMSS format
            if len(text) >= 3:
                mins = text[:-2]
                secs = text[-2:]
                if int(secs) < 60:
                    return f"{mins}:{secs}"
                return None
            # Just seconds
            if len(text) <= 2:
                secs = int(text)
                if secs < 60:
                    return f"0:{secs:02d}"
            return None
        except (ValueError, UnicodeDecodeError):
            return None

    def _try_parse_score_field(self, raw: bytes) -> Optional[int]:
        """Try to parse a score from raw bytes, tolerating various formats."""
        try:
            text = raw.decode("ascii").strip()
            if not text:
                return 0
            # Remove any non-digit characters
            digits = ''.join(c for c in text if c.isdigit())
            if digits:
                return int(digits)
            return 0
        except (ValueError, UnicodeDecodeError):
            return None

    def _try_parse_period(self, raw: bytes) -> Optional[str]:
        """Try to parse a period indicator from raw bytes."""
        try:
            text = raw.decode("ascii").strip()
            if not text:
                return None
            # Common period values: 1, 2, 3, OT, O, 4, S (shootout)
            if text in ("1", "2", "3", "4", "5"):
                return text
            if text.upper() in ("O", "OT"):
                return "OT"
            if text.upper() in ("S", "SO"):
                return "SO"
            # If it's a digit, use it
            if text[0].isdigit():
                return text[0]
            return text[0].upper()
        except (ValueError, UnicodeDecodeError):
            return None

    def _try_layout(self, packet: bytes, layout: dict) -> Optional[GameData]:
        """Try to parse a packet using a specific field layout."""
        if len(packet) < layout["min_length"]:
            return None
        if "max_length" in layout and len(packet) > layout["max_length"]:
            return None

        try:
            hs = layout["home_score"]
            home_score = self._try_parse_score_field(packet[hs[0]:hs[1]])
            if home_score is None:
                return None

            aws = layout["away_score"]
            away_score = self._try_parse_score_field(packet[aws[0]:aws[1]])
            if away_score is None:
                return None

            # Period may come from H packet or from C packet (stored in _last_period).
            # The 55-byte format has no period in H packets — it's in C packets only.
            period = self._last_period  # Default from most recent C packet
            if "period" in layout:
                ps = layout["period"]
                if ps[1] <= len(packet):
                    parsed_period = self._try_parse_period(packet[ps[0]:ps[1]])
                    if parsed_period is not None:
                        period = parsed_period

            # Parse penalties (optional - don't fail if missing)
            home_penalties = []
            away_penalties = []
            for key in ("home_pen1", "home_pen2"):
                if key in layout:
                    r = layout[key]
                    if r[1] <= len(packet):
                        p = self._parse_mmss(packet[r[0]:r[1]])
                        if p is not None:
                            home_penalties.append(p)
            for key in ("away_pen1", "away_pen2"):
                if key in layout:
                    r = layout[key]
                    if r[1] <= len(packet):
                        p = self._parse_mmss(packet[r[0]:r[1]])
                        if p is not None:
                            away_penalties.append(p)

            # Sanity check: scores should be reasonable
            if home_score > 99 or away_score > 99:
                return None
            if period not in ("1", "2", "3", "4", "5", "OT", "SO"):
                return None

            return GameData(
                home_score=home_score,
                away_score=away_score,
                period=period,
                clock=self._last_clock,
                home_penalties=home_penalties,
                away_penalties=away_penalties,
                parse_method=layout["name"]
            )
        except (IndexError, ValueError, UnicodeDecodeError):
            return None

    def _scan_for_ascii_scores(self, packet: bytes) -> Optional[GameData]:
        """
        Scan a packet for score-like patterns anywhere in the data.
        This is a last-resort heuristic for unknown packet formats.
        """
        try:
            text = packet.decode("ascii", errors="replace")
        except Exception:
            return None

        # Look for common scoreboard text patterns
        # Pattern: "HH:MM" or "MM:SS" (clock)
        clock_match = re.search(r'(\d{1,2}:\d{2})', text)
        if clock_match:
            clock = clock_match.group(1)
            self._last_clock = clock

        # Pattern: score like "3 - 1" or "03-01" or "H 3  A 1"
        score_patterns = [
            # "HOME 3 AWAY 1" style (most specific, try first)
            r'[Hh](?:ome|OME)?\s*(\d{1,3})\s+[AaVv](?:way|WAY|is|IS)?\s*(\d{1,3})',
            # "3 - 1" (dash-separated only, NOT colon to avoid matching clock times)
            r'(\d{1,3})\s*-\s*(\d{1,3})',
        ]

        for pattern in score_patterns:
            match = re.search(pattern, text)
            if match:
                home = int(match.group(1))
                away = int(match.group(2))
                if home <= 99 and away <= 99:
                    # Try to find period
                    period = "1"
                    period_match = re.search(r'[Pp](?:eriod|RD|ER)?\s*(\d)', text)
                    if period_match:
                        period = period_match.group(1)

                    return GameData(
                        home_score=home,
                        away_score=away,
                        period=period,
                        clock=self._last_clock,
                        home_penalties=[],
                        away_penalties=[],
                        parse_method="ascii_scan"
                    )

        return None

    def parse(self, packet: bytes) -> Optional[GameData]:
        """
        Parse an MP-70 binary packet using adaptive strategy.

        Tries multiple parsing approaches:
        1. Known MP-70 packet types ('C' clock, 'H' score)
        2. Multiple field layouts for score packets
        3. ASCII text scanning for VCG/unknown formats
        4. Detailed diagnostic logging for unrecognized data
        """
        if len(packet) < 3:
            record_packet("?", valid=False)
            return None

        # Log every packet in debug mode for diagnostics
        logger.debug(f"PARSE: len={len(packet)} hex={packet[:60].hex(' ')}{'...' if len(packet) > 60 else ''}")
        try:
            ascii_repr = packet.decode('ascii', errors='replace')
            logger.debug(f"  ASCII: {ascii_repr[:80]}{'...' if len(ascii_repr) > 80 else ''}")
        except Exception:
            pass

        # === Strategy 1: Standard MP-70 type-byte dispatch ===
        try:
            packet_type = chr(packet[1])
        except (IndexError, ValueError):
            packet_type = None

        # Clock packet (type 'C')
        if packet_type == "C":
            clock = self._format_clock(packet[2:6])
            if clock:
                self._last_clock = clock
                logger.debug(f"Clock updated: {clock}")
            # Extract period from trailing bytes (e.g. "160"=P1, "260"=P2, "360"=P3)
            # The hundreds digit is the period number
            if len(packet) >= 10:
                try:
                    period_field = packet[7:10].decode("ascii", errors="replace").strip()
                    if period_field and period_field[0].isdigit() and period_field[0] != "0":
                        new_period = period_field[0]
                        if new_period != self._last_period:
                            logger.info(f"Period changed: {self._last_period} → {new_period} (from C packet '{period_field}')")
                        self._last_period = new_period
                except Exception:
                    pass
            record_packet("C", valid=True)
            return None

        # === If format is locked, use the locked strategy directly ===
        if self._format_locked and self._locked_strategy:
            result = self._run_locked_strategy(packet, packet_type)
            if result:
                return result
            # Locked strategy failed - fall through to try everything
            # (data format may have changed, e.g. sport change on controller)
            logger.warning(f"Locked strategy '{self._locked_strategy}' failed, trying all strategies")

        # Score packet (type 'H') - try all layouts
        if packet_type == "H":
            for layout in ALL_LAYOUTS:
                result = self._try_layout(packet, layout)
                if result:
                    strategy = f"STX/ETX type_H + {layout['name']}"
                    self._record_strategy_success(strategy, layout)
                    record_packet("H", valid=True)
                    logger.info(f"PARSED [{strategy}]: H={result.home_score} A={result.away_score} "
                               f"P={result.period} Clock={result.clock}")
                    return result

            # 'H' type but no layout worked
            logger.warning(f"Type 'H' packet but no layout matched. len={len(packet)}")
            self._log_packet_diagnostic(packet)

        # === Strategy 2: Try other known type bytes ===
        # Only use this for STX/ETX framed packets (first byte is STX)
        if len(packet) >= 10 and packet[0] == STX:
            known_score_types = set("HSGDFBWVTL")
            known_clock_types = set("CT")

            if packet_type and packet_type.upper() in known_clock_types and packet_type != "C":
                clock = self._format_clock(packet[2:6])
                if clock:
                    self._last_clock = clock
                    logger.info(f"Clock updated (type '{packet_type}'): {clock}")
                    record_packet("C", valid=True)
                    return None

            if packet_type and packet_type.upper() in known_score_types and packet_type != "H":
                for layout in ALL_LAYOUTS:
                    result = self._try_layout(packet, layout)
                    if result:
                        strategy = f"STX/ETX type_{packet_type} + {layout['name']}"
                        result.parse_method = strategy
                        self._record_strategy_success(strategy, layout)
                        record_packet("score", valid=True)
                        logger.info(f"PARSED [{strategy}]: "
                                   f"H={result.home_score} A={result.away_score} P={result.period}")
                        return result

        # === Strategy 3: Ignore type byte, try all layouts anyway ===
        if len(packet) >= MIN_PACKET_LENGTH_RELAXED:
            for layout in ALL_LAYOUTS:
                if len(packet) >= layout["min_length"]:
                    result = self._try_layout(packet, layout)
                    if result:
                        strategy = f"no_type + {layout['name']}"
                        result.parse_method = strategy
                        self._record_strategy_success(strategy, layout)
                        record_packet("score", valid=True)
                        logger.info(f"PARSED [{strategy}]: "
                                   f"H={result.home_score} A={result.away_score} P={result.period}")
                        return result

        # === Strategy 4: ASCII text scanning ===
        if len(packet) >= 5:
            result = self._scan_for_ascii_scores(packet)
            if result:
                strategy = f"ASCII scan ({result.parse_method})"
                self._record_strategy_success(strategy)
                record_packet("text_score", valid=True)
                logger.info(f"PARSED [{strategy}]: H={result.home_score} A={result.away_score} "
                           f"P={result.period} Clock={result.clock}")
                return result

        # === Strategy 5: Check if this contains a clock update embedded somewhere ===
        if len(packet) >= 4:
            self._try_extract_clock(packet)

        # Nothing worked - log detailed diagnostics
        _packet_stats["auto_detect_attempts"] += 1
        record_packet("?", valid=False)
        self._log_packet_diagnostic(packet)
        return None

    def _run_locked_strategy(self, packet: bytes, packet_type: Optional[str]) -> Optional[GameData]:
        """
        Fast-path: replay only the locked strategy instead of trying all.

        Returns the parsed result, or None if the locked strategy can't handle this packet.
        """
        strategy = self._locked_strategy
        if not strategy:
            return None

        # STX/ETX type + layout (Strategies 1 & 2)
        if strategy.startswith("STX/ETX type_") and self._detected_layout:
            # Extract the expected type byte from the strategy name
            # e.g. "STX/ETX type_H + MP-70 Standard (80-byte)" → "H"
            expected_type = strategy[len("STX/ETX type_"):]
            expected_type = expected_type.split(" + ")[0] if " + " in expected_type else expected_type
            if packet_type == expected_type:
                result = self._try_layout(packet, self._detected_layout)
                if result:
                    result.parse_method = strategy
                    record_packet("H" if expected_type == "H" else "score", valid=True)
                    return result
            return None

        # No type byte + layout (Strategy 3)
        if strategy.startswith("no_type + ") and self._detected_layout:
            result = self._try_layout(packet, self._detected_layout)
            if result:
                result.parse_method = strategy
                record_packet("score", valid=True)
                return result
            return None

        # ASCII scan (Strategy 4)
        if strategy.startswith("ASCII scan"):
            result = self._scan_for_ascii_scores(packet)
            if result:
                result.parse_method = strategy
                record_packet("text_score", valid=True)
                return result
            return None

        return None

    def _try_extract_clock(self, packet: bytes) -> None:
        """Try to find a clock value anywhere in the packet."""
        try:
            text = packet.decode("ascii", errors="replace")
            # Look for MM:SS pattern
            match = re.search(r'(\d{1,2}:\d{2})', text)
            if match:
                clock = match.group(1)
                # Sanity check: minutes < 100, seconds < 60
                parts = clock.split(":")
                if int(parts[0]) < 100 and int(parts[1]) < 60:
                    self._last_clock = clock
                    logger.debug(f"Extracted clock from data: {clock}")
        except Exception:
            pass

    def _log_packet_diagnostic(self, packet: bytes) -> None:
        """Log detailed diagnostic information about an unrecognized packet."""
        logger.warning(f"UNRECOGNIZED PACKET: len={len(packet)}")
        logger.warning(f"  Full hex: {packet.hex(' ')}")
        try:
            logger.warning(f"  ASCII:    {packet.decode('ascii', errors='replace')}")
        except Exception:
            pass

        # Analyze content
        printable = sum(1 for b in packet if 32 <= b <= 126)
        pct = (printable / len(packet)) * 100 if packet else 0
        logger.warning(f"  Printable ASCII: {printable}/{len(packet)} bytes ({pct:.0f}%)")

        # Show byte frequency
        if len(packet) > 10:
            unique_bytes = len(set(packet))
            logger.warning(f"  Unique byte values: {unique_bytes}")
            # Show positions of digit characters
            digit_positions = [i for i, b in enumerate(packet) if 48 <= b <= 57]
            if digit_positions:
                logger.warning(f"  Digit positions: {digit_positions}")
            # Show positions of colon (common in time)
            colon_positions = [i for i, b in enumerate(packet) if b == 58]
            if colon_positions:
                logger.warning(f"  Colon positions: {colon_positions}")

    def extract_packets(self, buffer: bytearray) -> tuple[list[bytes], bytearray]:
        """
        Extract complete packets from a buffer using multiple framing strategies.

        Tries:
        1. STX/ETX framing (standard MP-70)
        2. CR/LF line framing (VCG/ASCII mode)
        3. SOH-based framing (some older protocols)
        """
        packets = []

        # === Strategy 1: STX/ETX framing ===
        if STX in buffer and ETX in buffer:
            temp_buf = buffer
            while STX in temp_buf and ETX in temp_buf:
                start = temp_buf.index(STX)

                # Discard any garbage before STX
                if start > 0:
                    garbage = temp_buf[:start]
                    logger.debug(f"Discarding {start} bytes before STX: {bytes(garbage).hex(' ')}")

                try:
                    end = temp_buf.index(ETX, start)
                except ValueError:
                    break

                packet = bytes(temp_buf[start:end + 1])
                packets.append(packet)
                temp_buf = temp_buf[end + 1:]

            if packets:
                return packets, temp_buf

        # === Strategy 2: CR/LF line framing ===
        # VCG/VideoStamp+ mode sends ASCII lines
        if CR in buffer or LF in buffer:
            temp_buf = buffer
            while True:
                # Find line ending (CR, LF, or CRLF)
                cr_pos = temp_buf.find(CR) if CR in temp_buf else len(temp_buf)
                lf_pos = temp_buf.find(LF) if LF in temp_buf else len(temp_buf)
                end_pos = min(cr_pos, lf_pos)

                if end_pos >= len(temp_buf):
                    break

                line = bytes(temp_buf[:end_pos])
                if len(line) >= 3:  # Minimum meaningful line
                    packets.append(line)

                # Skip past line ending (handle CRLF)
                skip = end_pos + 1
                if skip < len(temp_buf) and end_pos == cr_pos and temp_buf[skip] == LF:
                    skip += 1
                temp_buf = temp_buf[skip:]

            if packets:
                return packets, temp_buf

        # === Strategy 3: SOH-based framing ===
        if SOH in buffer:
            temp_buf = buffer
            while SOH in temp_buf:
                start = temp_buf.index(SOH)
                # Look for next SOH or ETX as end marker
                next_soh = -1
                for i in range(start + 1, len(temp_buf)):
                    if temp_buf[i] in (SOH, ETX):
                        next_soh = i
                        break

                if next_soh == -1:
                    break

                end = next_soh + 1 if temp_buf[next_soh] == ETX else next_soh
                packet = bytes(temp_buf[start:end])
                if len(packet) >= 3:
                    packets.append(packet)
                temp_buf = temp_buf[end:]

            if packets:
                return packets, temp_buf

        # === Strategy 4: Fixed-length chunking ===
        # If buffer is growing but no delimiters found, try treating
        # fixed-size chunks as packets (common for some protocols)
        if len(buffer) >= 80:
            # Try 80-byte chunks
            while len(buffer) >= 80:
                packet = bytes(buffer[:80])
                packets.append(packet)
                buffer = buffer[80:]
                logger.debug("Using 80-byte fixed-length chunking (no delimiters found)")

            if packets:
                return packets, buffer

        # If buffer is getting large with no recognized framing, log and trim
        if len(buffer) > 512:
            logger.warning(f"Buffer overflow ({len(buffer)} bytes) with no recognized framing. "
                          f"First 100 bytes hex: {bytes(buffer[:100]).hex(' ')}")
            try:
                logger.warning(f"  ASCII: {bytes(buffer[:100]).decode('ascii', errors='replace')}")
            except Exception:
                pass
            # Keep last 256 bytes in case we're in the middle of a packet
            buffer = buffer[-256:]

        return packets, buffer
