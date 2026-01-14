"""
SLAP Configuration Management

Loads settings from config/default.json with environment variable overrides.
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SerialConfig:
    port: str = "/dev/ttyUSB0"
    baudrate: int = 9600
    timeout: float = 0.1


@dataclass
class CasparConfig:
    host: str = "127.0.0.1"
    port: int = 5250
    channel: int = 1
    layer: int = 10
    enabled: bool = True


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False


@dataclass
class SimulatorConfig:
    enabled: bool = False
    period_seconds: int = 1200  # 20 minutes
    goal_interval_min: int = 30
    goal_interval_max: int = 90
    penalty_chance: float = 0.1
    speed_multiplier: float = 10.0  # 10x speed for testing


@dataclass
class TeamConfig:
    name: str = "TEAM"
    short_name: str = "TM"
    logo: str = ""
    color: str = "#0033AA"


@dataclass
class Config:
    serial: SerialConfig = field(default_factory=SerialConfig)
    caspar: CasparConfig = field(default_factory=CasparConfig)
    web: WebConfig = field(default_factory=WebConfig)
    simulator: SimulatorConfig = field(default_factory=SimulatorConfig)
    home_team: TeamConfig = field(default_factory=lambda: TeamConfig(name="HOME", short_name="HOM", color="#0033AA"))
    away_team: TeamConfig = field(default_factory=lambda: TeamConfig(name="AWAY", short_name="AWY", color="#AA0000"))
    debug: bool = False


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from JSON file with environment variable overrides.

    Priority (highest to lowest):
    1. Environment variables (SLAP_*)
    2. Config file values
    3. Default values
    """
    config = Config()

    # Determine config file path
    if config_path is None:
        base_dir = Path(__file__).parent.parent
        config_path = base_dir / "config" / "default.json"
    else:
        config_path = Path(config_path)

    # Load from JSON if exists
    if config_path.exists():
        with open(config_path, "r") as f:
            data = json.load(f)

        # Serial config
        if "serial" in data:
            config.serial.port = data["serial"].get("port", config.serial.port)
            config.serial.baudrate = data["serial"].get("baudrate", config.serial.baudrate)
            config.serial.timeout = data["serial"].get("timeout", config.serial.timeout)

        # CasparCG config
        if "caspar" in data:
            config.caspar.host = data["caspar"].get("host", config.caspar.host)
            config.caspar.port = data["caspar"].get("port", config.caspar.port)
            config.caspar.channel = data["caspar"].get("channel", config.caspar.channel)
            config.caspar.layer = data["caspar"].get("layer", config.caspar.layer)
            config.caspar.enabled = data["caspar"].get("enabled", config.caspar.enabled)

        # Web config
        if "web" in data:
            config.web.host = data["web"].get("host", config.web.host)
            config.web.port = data["web"].get("port", config.web.port)
            config.web.debug = data["web"].get("debug", config.web.debug)

        # Simulator config
        if "simulator" in data:
            config.simulator.enabled = data["simulator"].get("enabled", config.simulator.enabled)
            config.simulator.period_seconds = data["simulator"].get("period_seconds", config.simulator.period_seconds)
            config.simulator.goal_interval_min = data["simulator"].get("goal_interval_min", config.simulator.goal_interval_min)
            config.simulator.goal_interval_max = data["simulator"].get("goal_interval_max", config.simulator.goal_interval_max)
            config.simulator.speed_multiplier = data["simulator"].get("speed_multiplier", config.simulator.speed_multiplier)

        # Team configs
        if "home_team" in data:
            config.home_team.name = data["home_team"].get("name", config.home_team.name)
            config.home_team.short_name = data["home_team"].get("short_name", config.home_team.short_name)
            config.home_team.logo = data["home_team"].get("logo", config.home_team.logo)
            config.home_team.color = data["home_team"].get("color", config.home_team.color)

        if "away_team" in data:
            config.away_team.name = data["away_team"].get("name", config.away_team.name)
            config.away_team.short_name = data["away_team"].get("short_name", config.away_team.short_name)
            config.away_team.logo = data["away_team"].get("logo", config.away_team.logo)
            config.away_team.color = data["away_team"].get("color", config.away_team.color)

        config.debug = data.get("debug", config.debug)

    # Environment variable overrides
    if os.environ.get("SLAP_SERIAL_PORT"):
        config.serial.port = os.environ["SLAP_SERIAL_PORT"]
    if os.environ.get("SLAP_SERIAL_BAUDRATE"):
        config.serial.baudrate = int(os.environ["SLAP_SERIAL_BAUDRATE"])
    if os.environ.get("SLAP_CASPAR_HOST"):
        config.caspar.host = os.environ["SLAP_CASPAR_HOST"]
    if os.environ.get("SLAP_CASPAR_PORT"):
        config.caspar.port = int(os.environ["SLAP_CASPAR_PORT"])
    if os.environ.get("SLAP_CASPAR_ENABLED"):
        config.caspar.enabled = os.environ["SLAP_CASPAR_ENABLED"].lower() in ("true", "1", "yes")
    if os.environ.get("SLAP_WEB_PORT"):
        config.web.port = int(os.environ["SLAP_WEB_PORT"])
    if os.environ.get("SLAP_SIMULATOR"):
        config.simulator.enabled = os.environ["SLAP_SIMULATOR"].lower() in ("true", "1", "yes")
    if os.environ.get("SLAP_DEBUG"):
        config.debug = os.environ["SLAP_DEBUG"].lower() in ("true", "1", "yes")

    return config


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global config instance, loading it if necessary."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: Config) -> None:
    """Set the global config instance."""
    global _config
    _config = config
