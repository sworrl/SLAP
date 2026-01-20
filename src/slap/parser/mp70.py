"""
MP-70 Binary Protocol Parser

Decodes serial data from Trans-Lux FairPlay MP-70 scoreboard controllers.

Protocol Overview:
- Packets are delimited by STX (0x02) and ETX (0x03) bytes
- Minimum packet length: 80 bytes
- Two packet types:
  - Type 'C': Clock update only
  - Type 'H': Full game state (scores, period, penalties)

See docs/PROTOCOL.md for detailed field specifications.
"""

import logging
from dataclasses import dataclass
from typing import Optional, List

logger = logging.getLogger(__name__)

# Packet delimiters
STX = 0x02  # Start of Text
ETX = 0x03  # End of Text

# Minimum valid packet length
MIN_PACKET_LENGTH = 80

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
        elif packet_type == "H":
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
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _recording_path = str(log_dir / f"serial_recording_{timestamp}.bin")

    try:
        _recording_file = open(_recording_path, "wb")
        _recording_active = True
        _recording_bytes = 0
        logger.info(f"Started serial recording to: {_recording_path}")
        return _recording_path
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


class MP70Parser:
    """
    Stateful parser for MP-70 binary packets.

    Maintains the last known clock value since clock updates
    come in separate packets from score updates.
    """

    def __init__(self):
        self._last_clock = "20:00"

    @property
    def last_clock(self) -> str:
        """Get the last known clock value."""
        return self._last_clock

    @last_clock.setter
    def last_clock(self, value: str) -> None:
        """Set the clock value (useful for simulation)."""
        self._last_clock = value

    def _parse_mmss(self, raw: bytes) -> Optional[int]:
        """
        Parse a 4-byte MMSS time field to seconds.

        Args:
            raw: 4 bytes representing MMSS (e.g., b"0130" = 1:30)

        Returns:
            Total seconds, or None if field is empty/invalid
        """
        try:
            text = raw.decode("ascii").strip()
            if not text:
                return None
            minutes = int(text[:2])
            seconds = int(text[2:])
            return minutes * 60 + seconds
        except (ValueError, UnicodeDecodeError) as e:
            logger.debug(f"Failed to parse time field '{raw}': {e}")
            return None

    def _format_clock(self, raw: bytes) -> Optional[str]:
        """
        Parse and format a clock field as MM:SS string.

        Args:
            raw: 4 bytes representing MMSS

        Returns:
            Formatted string like "15:30", or None if invalid
        """
        try:
            text = raw.decode("ascii").strip()
            if not text or len(text) < 4:
                return None
            return f"{text[:-2]}:{text[-2:]}"
        except (ValueError, UnicodeDecodeError) as e:
            logger.debug(f"Failed to format clock '{raw}': {e}")
            return None

    def parse(self, packet: bytes) -> Optional[GameData]:
        """
        Parse an MP-70 binary packet.

        Args:
            packet: Raw bytes including STX/ETX delimiters

        Returns:
            GameData object if valid score packet, None otherwise

        Packet Types:
            'C' - Clock update: Updates internal clock, returns None
            'H' - Score update: Returns full GameData
        """
        # Raw data is now captured in run.py before packet extraction
        # This allows seeing ALL serial data, not just valid MP-70 packets

        if len(packet) < MIN_PACKET_LENGTH:
            logger.debug(f"Packet too short: {len(packet)} < {MIN_PACKET_LENGTH}")
            record_packet("?", valid=False)
            return None

        try:
            packet_type = chr(packet[1])
        except (IndexError, ValueError):
            logger.warning("Failed to read packet type byte")
            record_packet("?", valid=False)
            return None

        # Clock packet - update internal state only
        if packet_type == "C":
            clock = self._format_clock(packet[2:6])
            if clock:
                self._last_clock = clock
                logger.debug(f"Clock updated: {clock}")
            record_packet("C", valid=True)
            return None

        # Score packet - return full game data
        if packet_type == "H":
            record_packet("H", valid=True)
            try:
                # Parse score fields (ASCII digits)
                home_score = int(packet[13:15].decode("ascii").strip() or "0")
                away_score = int(packet[29:31].decode("ascii").strip() or "0")
                period = packet[45:46].decode("ascii").strip() or "1"

                # Parse penalty times
                home_penalties = [
                    p for p in [
                        self._parse_mmss(packet[52:56]),
                        self._parse_mmss(packet[57:61])
                    ] if p is not None
                ]

                away_penalties = [
                    p for p in [
                        self._parse_mmss(packet[62:66]),
                        self._parse_mmss(packet[67:71])
                    ] if p is not None
                ]

                return GameData(
                    home_score=home_score,
                    away_score=away_score,
                    period=period,
                    clock=self._last_clock,
                    home_penalties=home_penalties,
                    away_penalties=away_penalties
                )

            except (ValueError, UnicodeDecodeError) as e:
                logger.warning(f"Failed to parse score packet: {e}")
                return None

        logger.debug(f"Unknown packet type: {packet_type}")
        return None

    def extract_packets(self, buffer: bytearray) -> tuple[list[bytes], bytearray]:
        """
        Extract complete packets from a buffer.

        Args:
            buffer: Accumulated serial data

        Returns:
            Tuple of (list of complete packets, remaining buffer)
        """
        packets = []

        while STX in buffer and ETX in buffer:
            start = buffer.index(STX)
            try:
                end = buffer.index(ETX, start)
            except ValueError:
                break

            # Extract packet including delimiters
            packet = bytes(buffer[start:end + 1])
            packets.append(packet)

            # Remove processed data from buffer
            buffer = buffer[end + 1:]

        return packets, buffer
