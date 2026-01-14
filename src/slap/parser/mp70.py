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
        if len(packet) < MIN_PACKET_LENGTH:
            logger.debug(f"Packet too short: {len(packet)} < {MIN_PACKET_LENGTH}")
            return None

        try:
            packet_type = chr(packet[1])
        except (IndexError, ValueError):
            logger.warning("Failed to read packet type byte")
            return None

        # Clock packet - update internal state only
        if packet_type == "C":
            clock = self._format_clock(packet[2:6])
            if clock:
                self._last_clock = clock
                logger.debug(f"Clock updated: {clock}")
            return None

        # Score packet - return full game data
        if packet_type == "H":
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
