#!/usr/bin/env python3
"""
APRS-IS Beacon Sender - GitHub Actions.
支持 UTF-8 中文评论，aprs.fi 正常显示
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

        info_field = f"{dti}{self.latitude}{self.symbol_table}{self.longitude}{self.symbol_code}{extension}{altitude_str}{self.comment}"
        return f"{source}>{self.destination},{self.path}:{info_field}"

def utf8_to_latin1(s: str) -> str:
    """
    【核心】UTF-8 中文 → Latin-1 透明传输，让 aprs.fi 正确显示
    这是 APRS 中文唯一标准方案
    """
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

    default_dest = os.getenv("APRS_DEFAULT_DESTINATION", DEFAULT_DESTINATION)
    default_path = os.getenv("APRS_DEFAULT_PATH", DEFAULT_PATH)
    stations = []

    for idx, item in enumerate(stations_data):
        name = str(item.get("name", f"st{idx}"))
        callsign = item.get("callsign")
        ssid = item.get("ssid", "")
        passcode = item.get("passcode")
        enabled = item.get("enabled", True)
        lat = item.get("latitude")
        lon = item.get("longitude")
        comment = str(item.get("comment", ""))

        # ✅ 关键：中文编码转换
        comment = utf8_to_latin1(comment)

        # 保留禁止字符检查
        if any(c in comment for c in ("|", "~")):
            raise ConfigError(f"Station {idx} comment 不能包含 | ~")

        # 移除原来的 ASCII 检查，允许中文
        destination = item.get("destination", default_dest)
        path = item.get("path", default_path)
        sym_table = item.get("symbol_table", "/")
        sym_code = item.get("symbol_code", ">")

        station = Station(
            name=name,
            callsign=callsign,
            ssid=ssid,
            passcode=passcode,
            enabled=enabled,
            latitude=lat,
            longitude=lon,
            comment=comment,
            destination=destination,
            path=path,
            symbol_table=sym_table,
            symbol_code=sym_code
        )
        stations.append(station)
    return stations

def normalize_latitude(v: Any) -> str: return str(v)
def normalize_longitude(v: Any) -> str: return str(v)

def send_station(station: Station, server: str, port: int, version: str) -> None:
    srv = station.server or server
    prt = station.port or port
    login = f"user {station.source} pass {station.passcode} vers {version}\n"

    with socket.create_connection((srv, prt), timeout=15) as conn:
        conn.sendall(login.encode("latin-1"))
        packet = station.packet(station.source)
        # ✅ 发送必须用 latin-1
        conn.sendall(f"{packet}\n".encode("latin-1"))
        print(f"✅ 发送成功: {station.source} | {packet}")

def main():
    stations = load_stations()
    server = os.getenv("APRS_SERVER", DEFAULT_SERVER)
    port = int(os.getenv("APRS_PORT", DEFAULT_PORT))
    version = os.getenv("APRS_LOGIN_VERSION", "aprs-bot/1.0")

    for st in [s for s in stations if s.enabled]:
        send_station(st, server, port, version)
    return 0

if __name__ == "__main__":
    sys.exit(main())
