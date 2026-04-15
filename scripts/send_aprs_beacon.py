#!/usr/bin/env python3
"""
APRS-IS Beacon Sender - GitHub Actions.
支持 主表 / 次级表 0-9 A-Z + 中文评论正常显示
"""

import argparse
import json
import os
import re
import socket
import sys
from dataclasses import dataclass
from typing import Any

DEFAULT_SERVER = "rotate.aprs2.net"
DEFAULT_PORT = 14580
DEFAULT_DESTINATION = "APRS"
DEFAULT_PATH = "TCPIP*"
DEFAULT_SYMBOL_TABLE = "/"
DEFAULT_SYMBOL_CODE = ">"
SOCKET_TIMEOUT_SECONDS = 15

class ConfigError(Exception):
    pass

@dataclass(frozen=True)
class Station:
    name: str
    callsign: str
    ssid: str
    passcode: str
    enabled: bool
    latitude: str
    longitude: str
    comment: str
    destination: str
    path: str
    symbol_table: str
    symbol_code: str
    messaging_capable: bool = False
    course: int | None = None
    speed: int | None = None
    altitude: float | None = None
    phg: str = ""
    rng: str = ""
    server: str = ""
    port: int | None = None

    @property
    def source(self) -> str:
        ssid = self.ssid.strip()
        if not ssid or ssid == "0":
            return self.callsign.strip().upper()
        return f"{self.callsign.strip().upper()}-{ssid}"

    def packet(self, source: str) -> str:
        dti = "=" if self.messaging_capable else "!"

        extension = ""
        if self.phg:
            extension = f"PHG{self.phg}"
        elif self.rng:
            extension = f"RNG{self.rng}"
        elif self.course is not None or self.speed is not None:
            course = self.course or 0
            speed = self.speed or 0
            extension = f"{course:03d}/{speed:03d}"

        altitude_str = ""
        if self.altitude is not None:
            feet = round(self.altitude * 3.28084)
            altitude_str = f"/A={feet:06d}"

        # ✅ 这里完全支持 主表 / 次表 0-9 A-Z
        info_field = f"{dti}{self.latitude}{self.symbol_table}{self.longitude}{self.symbol_code}{extension}{altitude_str}{self.comment}"
        return f"{source}>{self.destination},{self.path}:{info_field}"

def utf8_to_latin1(s: str) -> str:
    return s.encode("utf-8").decode("latin-1")

def load_json_env(name: str, required: bool = True) -> Any:
    raw = os.getenv(name, "").strip()
    if not raw:
        if required:
            raise ConfigError(f"Missing environment variable: {name}")
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{name} invalid JSON: {exc}") from exc

def load_stations() -> list[Station]:
    stations_data = load_json_env("APRS_CALLSIGNS_JSON")
    if not isinstance(stations_data, list):
        raise ConfigError("APRS_CALLSIGNS_JSON must be array")

    default_dest = os.getenv("APRS_DEFAULT_DESTINATION", DEFAULT_DESTINATION).strip() or DEFAULT_DESTINATION
    default_path = os.getenv("APRS_DEFAULT_PATH", DEFAULT_PATH).strip() or DEFAULT_PATH
    stations = []

    for idx, item in enumerate(stations_data):
        name = str(item.get("name", f"st{idx}"))
        callsign = item.get("callsign")
        ssid = item.get("ssid", "")
        passcode = item.get("passcode")
        enabled = item.get("enabled", True)
        lat = item.get("latitude")
        lon = item.get("longitude")
        comment = str(item.get("comment", "")).strip()

        comment = utf8_to_latin1(comment)

        if any(c in comment for c in ("|", "~")):
            raise ConfigError(f"Station {idx} comment cannot contain | ~")

        # ✅ 放开限制：现在支持 主表 / 次表 0-9 A-Z
        symbol_table = str(item.get("symbol_table", DEFAULT_SYMBOL_TABLE))
        symbol_code = str(item.get("symbol_code", DEFAULT_SYMBOL_CODE))

        destination = item.get("destination", default_dest)
        path = item.get("path", default_path)

        def validate_coordinate_string(value: str, is_latitude: bool) -> str:
            normalized = value.strip().upper()
            pattern = r"^\d{4}\.\d{4}[NS]$" if is_latitude else r"^\d{5}\.\d{4}[EW]$"
            if not re.fullmatch(pattern, normalized):
                raise ConfigError(f"Invalid coordinate: {value}")
            degree_digits = 2 if is_latitude else 3
            degrees = int(normalized[:degree_digits])
            minutes = float(normalized[degree_digits:-1])
            hemisphere = normalized[-1]
            if minutes >= 60:
                raise ConfigError("Minutes >= 60")
            if is_latitude and degrees > 90:
                raise ConfigError("Latitude > 90")
            if not is_latitude and degrees > 180:
                raise ConfigError("Longitude > 180")
            if is_latitude:
                return f"{degrees:02d}{minutes:05.2f}{hemisphere}"
            return f"{degrees:03d}{minutes:05.2f}{hemisphere}"

        try:
            lat_val = validate_coordinate_string(lat, is_latitude=True)
            lon_val = validate_coordinate_string(lon, is_latitude=False)
        except Exception as e:
            raise ConfigError(f"Station {idx} coordinate error: {e}")

        station = Station(
            name=name,
            callsign=callsign,
            ssid=ssid,
            passcode=passcode,
            enabled=enabled,
            latitude=lat_val,
            longitude=lon_val,
            comment=comment,
            destination=destination,
            path=path,
            symbol_table=symbol_table,
            symbol_code=symbol_code
        )
        stations.append(station)
    return stations

def send_station(station: Station, server: str, port: int, version: str) -> None:
    srv = station.server or server
    prt = station.port or port
    login = f"user {station.source} pass {station.passcode} vers {version}\n"

    with socket.create_connection((srv, prt), timeout=15) as conn:
        conn.sendall(login.encode("latin-1"))
        packet = station.packet(station.source)
        conn.sendall(f"{packet}\n".encode("latin-1"))
        print(f"✅ Sent: {station.source} | {packet}")

def main():
    try:
        stations = load_stations()
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 1

    port_str = os.getenv("APRS_PORT", "").strip()
    port = int(port_str) if port_str else DEFAULT_PORT

    server = os.getenv("APRS_SERVER", DEFAULT_SERVER).strip() or DEFAULT_SERVER
    version = os.getenv("APRS_LOGIN_VERSION", "aprs-bot/1.0").strip() or "aprs-bot/1.0"

    for st in [s for s in stations if s.enabled]:
        try:
            send_station(st, server, port, version)
        except Exception as e:
            print(f"Failed {st.source}: {e}", file=sys.stderr)
            return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
