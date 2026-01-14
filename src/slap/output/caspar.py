"""
CasparCG AMCP Client

Communicates with CasparCG server using the AMCP protocol over TCP.
"""

import socket
import logging
import json
from typing import Optional
from ..config import get_config

logger = logging.getLogger(__name__)


class CasparClient:
    """
    CasparCG AMCP protocol client.

    Handles connection management and command sending to CasparCG server.
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None,
                 channel: int = 1, layer: int = 10):
        """
        Initialize CasparCG client.

        Args:
            host: CasparCG server hostname (default from config)
            port: CasparCG server port (default from config)
            channel: Video channel number (default 1)
            layer: Graphics layer number (default 10)
        """
        config = get_config()
        self.host = host or config.caspar.host
        self.port = port or config.caspar.port
        self.channel = channel or config.caspar.channel
        self.layer = layer or config.caspar.layer
        self._socket: Optional[socket.socket] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        """Check if connected to CasparCG."""
        return self._connected

    def connect(self) -> bool:
        """
        Connect to CasparCG server.

        Returns:
            True if connection successful, False otherwise
        """
        if self._connected:
            return True

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(5.0)
            self._socket.connect((self.host, self.port))
            # Read welcome message
            self._socket.recv(4096)
            self._connected = True
            logger.info(f"Connected to CasparCG at {self.host}:{self.port}")
            return True
        except (socket.error, socket.timeout) as e:
            logger.warning(f"Failed to connect to CasparCG: {e}")
            self._connected = False
            self._socket = None
            return False

    def disconnect(self) -> None:
        """Disconnect from CasparCG server."""
        if self._socket:
            try:
                self._socket.close()
            except socket.error:
                pass
        self._socket = None
        self._connected = False
        logger.info("Disconnected from CasparCG")

    def send(self, command: str) -> bool:
        """
        Send raw AMCP command to CasparCG.

        Args:
            command: AMCP command string

        Returns:
            True if sent successfully, False otherwise
        """
        if not self._connected:
            if not self.connect():
                return False

        try:
            full_command = f"{command}\r\n"
            self._socket.sendall(full_command.encode("utf-8"))
            logger.debug(f"Sent: {command}")
            return True
        except (socket.error, socket.timeout) as e:
            logger.warning(f"Failed to send command: {e}")
            self._connected = False
            return False

    def update_scorebug(self, data: dict) -> bool:
        """
        Update scorebug template with new data.

        Args:
            data: Dictionary of scorebug data

        Returns:
            True if update sent successfully
        """
        payload = json.dumps(data).replace('"', '\\"')
        cmd = f'CG {self.channel}-{self.layer} UPDATE 1 "{payload}"'
        return self.send(cmd)

    def trigger_goal(self, side: str) -> bool:
        """
        Trigger goal animation.

        Args:
            side: "HOME" or "AWAY"

        Returns:
            True if command sent successfully
        """
        cmd = f'CG {self.channel}-{self.layer} INVOKE 1 "goal:{side}"'
        return self.send(cmd)

    def show_scorebug(self) -> bool:
        """Show the scorebug overlay."""
        cmd = f'CG {self.channel}-{self.layer} INVOKE 1 "show"'
        return self.send(cmd)

    def hide_scorebug(self) -> bool:
        """Hide the scorebug overlay."""
        cmd = f'CG {self.channel}-{self.layer} INVOKE 1 "hide"'
        return self.send(cmd)

    def play_template(self, template_name: str) -> bool:
        """
        Play a CasparCG HTML template.

        Args:
            template_name: Name of the template file (without extension)
        """
        cmd = f'CG {self.channel}-{self.layer} ADD 1 "{template_name}" 1'
        return self.send(cmd)

    def stop_template(self) -> bool:
        """Stop the current template."""
        cmd = f'CG {self.channel}-{self.layer} STOP 1'
        return self.send(cmd)

    def play_video(self, filename: str, layer: Optional[int] = None) -> bool:
        """
        Play a video file.

        Args:
            filename: Video filename (without extension)
            layer: Layer to play on (default: self.layer + 20)
        """
        video_layer = layer or (self.layer + 20)
        cmd = f'PLAY {self.channel}-{video_layer} {filename}'
        return self.send(cmd)


# Mock client for testing without CasparCG
class MockCasparClient(CasparClient):
    """
    Mock CasparCG client for testing.

    Logs all commands instead of sending to server.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._commands: list = []

    def connect(self) -> bool:
        self._connected = True
        logger.info("MockCasparClient: Simulated connection")
        return True

    def disconnect(self) -> None:
        self._connected = False
        logger.info("MockCasparClient: Simulated disconnect")

    def send(self, command: str) -> bool:
        self._commands.append(command)
        logger.debug(f"MockCasparClient: {command}")
        return True

    def get_commands(self) -> list:
        """Get list of all commands sent."""
        return self._commands.copy()

    def clear_commands(self) -> None:
        """Clear command history."""
        self._commands.clear()
