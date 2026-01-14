"""
Fake Serial Port for Testing

Simulates MP-70 scoreboard controller output for testing without hardware.
"""

import random
import threading
import time
import logging
from typing import Optional, Callable
from ..parser.mp70 import STX, ETX

logger = logging.getLogger(__name__)


class GameSimulator:
    """
    Simulates a hockey game for testing.

    Generates realistic game data including:
    - Countdown clock (20:00 -> 0:00)
    - Random goals
    - Random penalties
    - Period transitions
    """

    def __init__(
        self,
        period_seconds: int = 1200,  # 20 minutes
        goal_interval_min: int = 30,
        goal_interval_max: int = 90,
        penalty_chance: float = 0.1,
        speed_multiplier: float = 10.0
    ):
        self.period_seconds = period_seconds
        self.goal_interval_min = goal_interval_min
        self.goal_interval_max = goal_interval_max
        self.penalty_chance = penalty_chance
        self.speed_multiplier = speed_multiplier

        # Game state
        self.home_score = 0
        self.away_score = 0
        self.period = 1
        self.clock_seconds = period_seconds
        self.home_penalties: list[int] = []  # Seconds remaining
        self.away_penalties: list[int] = []

        # Simulation control
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._next_goal_time = self._random_goal_time()
        self._on_update: Optional[Callable[[dict], None]] = None

    def _random_goal_time(self) -> int:
        """Get random time until next goal."""
        return random.randint(self.goal_interval_min, self.goal_interval_max)

    def format_clock(self) -> str:
        """Format clock as MM:SS."""
        minutes = self.clock_seconds // 60
        seconds = self.clock_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def get_state(self) -> dict:
        """Get current game state as dictionary."""
        return {
            "home": self.home_score,
            "away": self.away_score,
            "period": str(self.period) if self.period <= 3 else "OT",
            "clock": self.format_clock(),
            "home_penalties": self.home_penalties.copy(),
            "away_penalties": self.away_penalties.copy()
        }

    def tick(self) -> dict:
        """
        Advance simulation by one second (game time).

        Returns:
            Current game state
        """
        # Countdown clock
        if self.clock_seconds > 0:
            self.clock_seconds -= 1

        # Countdown penalties
        self.home_penalties = [max(0, p - 1) for p in self.home_penalties if p > 1]
        self.away_penalties = [max(0, p - 1) for p in self.away_penalties if p > 1]

        # Random goal check
        self._next_goal_time -= 1
        if self._next_goal_time <= 0:
            if random.random() < 0.5:
                self.home_score += 1
                logger.info(f"SIM: Home goal! {self.home_score}-{self.away_score}")
            else:
                self.away_score += 1
                logger.info(f"SIM: Away goal! {self.home_score}-{self.away_score}")
            self._next_goal_time = self._random_goal_time()

        # Random penalty check
        if random.random() < self.penalty_chance / 60:  # Per-second probability
            penalty_time = random.choice([120, 120, 120, 300])  # 2min or 5min
            if random.random() < 0.5:
                if len(self.home_penalties) < 2:
                    self.home_penalties.append(penalty_time)
                    logger.info(f"SIM: Home penalty ({penalty_time}s)")
            else:
                if len(self.away_penalties) < 2:
                    self.away_penalties.append(penalty_time)
                    logger.info(f"SIM: Away penalty ({penalty_time}s)")

        # Period transition
        if self.clock_seconds <= 0 and self.period < 3:
            self.period += 1
            self.clock_seconds = self.period_seconds
            logger.info(f"SIM: Period {self.period}")

        return self.get_state()

    def set_on_update(self, callback: Callable[[dict], None]) -> None:
        """Set callback for state updates."""
        self._on_update = callback

    def start(self) -> None:
        """Start simulation in background thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Game simulation started")

    def stop(self) -> None:
        """Stop simulation."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("Game simulation stopped")

    def reset(self) -> None:
        """Reset game to initial state."""
        self.home_score = 0
        self.away_score = 0
        self.period = 1
        self.clock_seconds = self.period_seconds
        self.home_penalties = []
        self.away_penalties = []
        self._next_goal_time = self._random_goal_time()
        logger.info("Game simulation reset")

    def _run_loop(self) -> None:
        """Main simulation loop."""
        tick_interval = 1.0 / self.speed_multiplier

        while self._running:
            state = self.tick()
            if self._on_update:
                try:
                    self._on_update(state)
                except Exception as e:
                    logger.error(f"Update callback error: {e}")

            time.sleep(tick_interval)


class FakeSerial:
    """
    Fake serial port that mimics pyserial interface.

    Generates MP-70 binary packets from simulated game data.
    """

    def __init__(
        self,
        port: str = "SIM",
        baudrate: int = 9600,
        timeout: float = 0.1,
        **kwargs
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout

        self._simulator = GameSimulator()
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._running = False

        # Start packet generation
        self._simulator.set_on_update(self._generate_packet)

    def _generate_packet(self, state: dict) -> None:
        """Generate MP-70 binary packet from game state."""
        # Create a packet buffer (minimum 80 bytes)
        packet = bytearray(80)
        packet[0] = STX

        # Alternating packet types for realism
        if random.random() < 0.3:
            # Clock packet
            packet[1] = ord('C')
            clock = state["clock"].replace(":", "")
            packet[2:6] = clock.encode("ascii").ljust(4)
        else:
            # Score packet
            packet[1] = ord('H')

            # Home score at bytes 13-15
            home_str = f"{state['home']:2d} "
            packet[13:16] = home_str.encode("ascii")

            # Away score at bytes 29-31
            away_str = f"{state['away']:2d} "
            packet[29:32] = away_str.encode("ascii")

            # Period at byte 45
            period_str = state["period"]
            packet[45:46] = period_str[0].encode("ascii")

            # Penalties
            def format_penalty(seconds: int) -> bytes:
                if seconds <= 0:
                    return b"    "
                mins = seconds // 60
                secs = seconds % 60
                return f"{mins:02d}{secs:02d}".encode("ascii")

            # Home penalties at 52-56 and 57-61
            home_pens = state.get("home_penalties", [])
            if len(home_pens) > 0:
                packet[52:56] = format_penalty(home_pens[0])
            if len(home_pens) > 1:
                packet[57:61] = format_penalty(home_pens[1])

            # Away penalties at 62-66 and 67-71
            away_pens = state.get("away_penalties", [])
            if len(away_pens) > 0:
                packet[62:66] = format_penalty(away_pens[0])
            if len(away_pens) > 1:
                packet[67:71] = format_penalty(away_pens[1])

        packet[79] = ETX

        # Add to buffer
        with self._lock:
            self._buffer.extend(packet)

    def open(self) -> None:
        """Open the fake serial port (start simulation)."""
        self._running = True
        self._simulator.start()
        logger.info(f"FakeSerial opened on {self.port}")

    def close(self) -> None:
        """Close the fake serial port (stop simulation)."""
        self._running = False
        self._simulator.stop()
        logger.info("FakeSerial closed")

    def read(self, size: int = 1) -> bytes:
        """Read bytes from the fake serial buffer."""
        with self._lock:
            if len(self._buffer) == 0:
                return b""
            data = bytes(self._buffer[:size])
            self._buffer = self._buffer[size:]
            return data

    def write(self, data: bytes) -> int:
        """Write to fake serial (no-op, just return length)."""
        return len(data)

    @property
    def in_waiting(self) -> int:
        """Number of bytes in receive buffer."""
        with self._lock:
            return len(self._buffer)

    def reset_input_buffer(self) -> None:
        """Clear input buffer."""
        with self._lock:
            self._buffer.clear()

    def reset_output_buffer(self) -> None:
        """Clear output buffer (no-op for fake)."""
        pass

    # Context manager support
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()

    # Simulator access
    def get_simulator(self) -> GameSimulator:
        """Get the underlying game simulator."""
        return self._simulator
