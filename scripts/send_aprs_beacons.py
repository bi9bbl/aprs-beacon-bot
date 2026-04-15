#!/usr/bin/env python3
"""
APRS-IS Beacon Sender - GitHub Actions.

Coordinates in configuration must use WGS-84 degree-minute strings:
- Latitude: DDMM.MMMMN / DDMM.MMMMS
- Longitude: DDDMM.MMMME / DDDMM.MMMMW

They are converted internally to APRS fixed-width position fields:
- Latitude: DDMM.HHN / DDMM.HHS
- Longitude: DDDMM.HHE / DDDMM.HHW
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
            course = self.course if self.course is not None else 0
            speed = self.speed if self.speed is not None else 0
            extension = f"{course:03d}/{speed:03d}"

        altitude_str = ""
        if self.altitude is not None:
            feet = round(self.altitude * 3.28084)
            altitude_str = f"/A={feet:06d}"

        info_field = f"{dti}{self.latitude}{self.symbol_table}{self.longitude}{self.symbol_code}{extension}{altitude_str}{self.comment}"
        return f"{source}>{self.destination},{self.path}:{info_field}"


def load_json_env(name: str, required: bool = True) -> Any:
    raw = os.getenv(name, "").strip()
    if not raw:
        if required:
            raise ConfigError(f"Missing environment variable: {name}")
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{name} must be valid JSON: {exc}") from exc


def load_stations() -> list[Station]:
    stations_data = load_json_env("APRS_CALLSIGNS_JSON")
    if not isinstance(stations_data, list):
        raise ConfigError("APRS_CALLSIGNS_JSON must be a JSON array")

    default_destination = os.getenv("APRS_DEFAULT_DESTINATION", DEFAULT_DESTINATION).strip() or DEFAULT_DESTINATION
    default_path = os.getenv("APRS_DEFAULT_PATH", DEFAULT_PATH).strip() or DEFAULT_PATH

    stations: list[Station] = []
    for index, item in enumerate(stations_data):
        if not isinstance(item, dict):
            raise ConfigError(f"Station {index} must be a JSON object")

        name = str(item.get("name", f"station-{index}")).strip() or f"station-{index}"
        callsign = item.get("callsign")
        ssid = item.get("ssid", "")
        passcode = item.get("passcode")
        enabled = item.get("enabled", True)
        latitude = item.get("latitude")
        longitude = item.get("longitude")

        if not isinstance(callsign, str) or not callsign.strip():
            raise ConfigError(f"Station {index} has an invalid callsign")
        if not isinstance(ssid, str):
            raise ConfigError(f"Station {index} has an invalid SSID")
        if not isinstance(passcode, str) or not passcode.strip():
            raise ConfigError(f"Station {index} has an invalid passcode")
        if not isinstance(enabled, bool):
            raise ConfigError(f"Station {index} enabled must be true or false")

        comment = str(item.get("comment", "")).strip()
        if any(c in comment for c in ("|", "~")):
            raise ConfigError(f"Station {index} comment must not contain '|' or '~' (reserved by APRS)")
        if comment and not all(0x20 <= ord(c) <= 0x7E for c in comment):
            raise ConfigError(f"Station {index} comment must contain only printable ASCII characters")
        destination = str(item.get("destination", default_destination)).strip() or default_destination
        path = str(item.get("path", default_path)).strip() or default_path
        symbol_table = str(item.get("symbol_table", DEFAULT_SYMBOL_TABLE))
        symbol_code = str(item.get("symbol_code", DEFAULT_SYMBOL_CODE))

        if len(symbol_table) != 1 or len(symbol_code) != 1:
            raise ConfigError(f"Station {index} symbol_table and symbol_code must be single characters")

        messaging_capable = item.get("messaging_capable", False)
        if not isinstance(messaging_capable, bool):
            raise ConfigError(f"Station {index} messaging_capable must be true or false")

        course_raw = item.get("course")
        if course_raw is not None:
            if not isinstance(course_raw, int) or not 0 <= course_raw <= 360:
                raise ConfigError(f"Station {index} course must be an integer 0-360")
        course = course_raw

        speed_raw = item.get("speed")
        if speed_raw is not None:
            if not isinstance(speed_raw, int) or not 0 <= speed_raw <= 999:
                raise ConfigError(f"Station {index} speed must be an integer 0-999")
        speed = speed_raw

        altitude_raw = item.get("altitude")
        if altitude_raw is not None and not isinstance(altitude_raw, (int, float)):
            raise ConfigError(f"Station {index} altitude must be a number (meters)")
        altitude = float(altitude_raw) if altitude_raw is not None else None

        phg = str(item.get("phg", "")).strip()
        if phg and not re.fullmatch(r"\d{4}", phg):
            raise ConfigError(f"Station {index} phg must be 4 digits (e.g. '5132')")

        rng = str(item.get("rng", "")).strip()
        if rng and not re.fullmatch(r"\d{4}", rng):
            raise ConfigError(f"Station {index} rng must be 4 digits (e.g. '0050')")

        if phg and rng:
            raise ConfigError(f"Station {index} phg and rng cannot both be set")
        if (phg or rng) and (course is not None or speed is not None):
            raise ConfigError(f"Station {index} phg/rng and course/speed cannot both be set")

        station_server = str(item.get("server", "")).strip()
        station_port_raw = item.get("port")
        station_port: int | None = None
        if station_port_raw is not None:
            if not isinstance(station_port_raw, int) or not 1 <= station_port_raw <= 65535:
                raise ConfigError(f"Station {index} port must be an integer 1-65535")
            station_port = station_port_raw

        try:
            latitude_value = normalize_latitude(latitude)
            longitude_value = normalize_longitude(longitude)
        except ConfigError as exc:
            raise ConfigError(f"Station {index} {exc}") from exc

        stations.append(
            Station(
                name=name,
                callsign=callsign,
                ssid=ssid,
                passcode=passcode,
                enabled=enabled,
                latitude=latitude_value,
                longitude=longitude_value,
                comment=comment,
                destination=destination,
                path=path,
                symbol_table=symbol_table,
                symbol_code=symbol_code,
                messaging_capable=messaging_capable,
                course=course,
                speed=speed,
                altitude=altitude,
                phg=phg,
                rng=rng,
                server=station_server,
                port=station_port,
            )
        )

    if not stations:
        raise ConfigError("At least one station must be configured in APRS_CALLSIGNS_JSON")

    return stations


def validate_coordinates(latitude: float, longitude: float, station_index: int) -> None:
    if not -90 <= latitude <= 90:
        raise ConfigError(f"Station {station_index} latitude out of range: {latitude}")
    if not -180 <= longitude <= 180:
        raise ConfigError(f"Station {station_index} longitude out of range: {longitude}")


def normalize_latitude(value: Any) -> str:
    if isinstance(value, str):
        return validate_coordinate_string(value, is_latitude=True)
    raise ConfigError("latitude must match DDMM.MMMMN/S (e.g. 3412.9800N)")


def normalize_longitude(value: Any) -> str:
    if isinstance(value, str):
        return validate_coordinate_string(value, is_latitude=False)
    raise ConfigError("longitude must match DDDMM.MMMME/W (e.g. 10853.6100E)")


def validate_coordinate_string(value: str, is_latitude: bool) -> str:
    normalized = value.strip().upper()
    # Input must be DDMM.MMMM[D] / DDDMM.MMMM[D]; output is normalized to APRS fixed-width format.
    pattern = r"^\d{4}\.\d{4}[NS]$" if is_latitude else r"^\d{5}\.\d{4}[EW]$"
    coordinate_name = "latitude" if is_latitude else "longitude"
    expected = "DDMM.MMMMN/S (e.g. 3412.9800N)" if is_latitude else "DDDMM.MMMME/W (e.g. 10853.6100E)"

    if not re.fullmatch(pattern, normalized):
        raise ConfigError(f"{coordinate_name} must match {expected}")

    degree_digits = 2 if is_latitude else 3
    degrees = int(normalized[:degree_digits])
    minutes = float(normalized[degree_digits:-1])
    hemisphere = normalized[-1]

    if minutes >= 60:
        raise ConfigError(f"{coordinate_name} minutes must be less than 60")
    if is_latitude and degrees > 90:
        raise ConfigError(f"latitude degrees out of range: {degrees}")
    if not is_latitude and degrees > 180:
        raise ConfigError(f"longitude degrees out of range: {degrees}")
    if is_latitude and degrees == 90 and minutes != 0:
        raise ConfigError("latitude 90 degrees must have 00.0000 minutes")
    if not is_latitude and degrees == 180 and minutes != 0:
        raise ConfigError("longitude 180 degrees must have 00.0000 minutes")

    # Normalize to APRS-spec fixed-width format: DDMM.HHN (8 chars) / DDDMM.HHE (9 chars).
    if is_latitude:
        return f"{degrees:02d}{minutes:05.2f}{hemisphere}"
    return f"{degrees:03d}{minutes:05.2f}{hemisphere}"


def format_latitude(latitude: float) -> str:
    hemisphere = "N" if latitude >= 0 else "S"
    absolute = abs(latitude)
    degrees = int(absolute)
    minutes = (absolute - degrees) * 60
    return f"{degrees:02d}{minutes:05.2f}{hemisphere}"


def format_longitude(longitude: float) -> str:
    hemisphere = "E" if longitude >= 0 else "W"
    absolute = abs(longitude)
    degrees = int(absolute)
    minutes = (absolute - degrees) * 60
    return f"{degrees:03d}{minutes:05.2f}{hemisphere}"


def send_station(station: Station, global_server: str, global_port: int, version: str) -> None:
    server = station.server or global_server
    port = station.port if station.port is not None else global_port
    login_line = f"user {station.source} pass {station.passcode} vers {version}\n"

    with socket.create_connection((server, port), timeout=SOCKET_TIMEOUT_SECONDS) as connection:
        connection.settimeout(SOCKET_TIMEOUT_SECONDS)
        connection.sendall(login_line.encode("utf-8"))
        packet = station.packet(station.source)
        connection.sendall(f"{packet}\n".encode("utf-8"))
        print(f"Sent station '{station.name}' as {station.source}: {packet}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send APRS-IS beacons from GitHub Actions")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate environment variables and render packets without sending them",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        stations = load_stations()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    active_stations = [station for station in stations if station.enabled]

    server = os.getenv("APRS_SERVER", DEFAULT_SERVER).strip() or DEFAULT_SERVER
    version = os.getenv("APRS_LOGIN_VERSION", "aprs-beacon-bot/1.0").strip() or "aprs-beacon-bot/1.0"

    try:
        port = int(os.getenv("APRS_PORT", str(DEFAULT_PORT)).strip() or str(DEFAULT_PORT))
    except ValueError:
        print("Configuration error: APRS_PORT must be an integer", file=sys.stderr)
        return 1

    if args.validate_only:
        print(f"Validated {len(stations)} station(s), {len(active_stations)} enabled.")
        for station in active_stations:
            print(f"{station.source}: {station.packet(station.source)}")
        return 0

    if not active_stations:
        print("No enabled stations configured. Nothing to send.")
        return 0

    for station in active_stations:
        effective_server = station.server or server
        effective_port = station.port if station.port is not None else port
        print(f"Connecting to {effective_server}:{effective_port} for {station.source}")
        try:
            send_station(station, server, port, version)
        except OSError as exc:
            print(f"Network error while sending as {station.source}: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
