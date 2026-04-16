# APRS Beacon Bot

This repository uses GitHub Actions to send scheduled APRS-IS position beacons.

## Features

- Scheduled beacon transmission with GitHub Actions
- Multiple callsigns, multiple SSIDs, and multiple positions
- Per-station enable/disable, APRS extensions, and server/port overrides
- Station configuration stored in a single GitHub Repository Variable
- WGS-84 coordinate input in `ddmm.mmmm` format
- Internal APRS-compatible coordinate conversion before send
- UTF-8 comments are preserved on the wire for non-ASCII beacon text
- No third-party Python dependencies

## Quick Start

1. Fork or clone this repository.
2. Go to **Settings -> Secrets and variables -> Actions -> Variables** and create `APRS_CALLSIGNS_JSON` with your station array.
3. The workflow runs automatically every hour. You can also trigger it manually from the **Actions** tab.

## Repository Variables

### Required

| Variable | Description |
|---|---|
| `APRS_CALLSIGNS_JSON` | Station configuration as a JSON array |

### Optional

| Variable | Default | Description |
|---|---|---|
| `APRS_SERVER` | `rotate.aprs2.net` | Global APRS-IS server address |
| `APRS_PORT` | `14580` | Global APRS-IS port |
| `APRS_LOGIN_VERSION` | `aprs-beacon-bot/1.0` | Client version string sent on login |
| `APRS_DEFAULT_DESTINATION` | `APRS` | Default destination field for all stations |
| `APRS_DEFAULT_PATH` | `TCPIP*` | Default digipeater path for all stations |

## Station Fields

Each object in the `APRS_CALLSIGNS_JSON` array represents one station.

### Required fields

| Field | Type | Description |
|---|---|---|
| `callsign` | string | Amateur radio callsign, e.g. `"N0CALL"` |
| `ssid` | string | SSID suffix as a string; use `""` for no suffix |
| `passcode` | string | APRS-IS passcode for this callsign |
| `latitude` | string | WGS-84 latitude in `DDMM.MMMMN/S` format, e.g. `"4807.0380N"` |
| `longitude` | string | WGS-84 longitude in `DDDMM.MMMME/W` format, e.g. `"01134.0360E"` |

### Optional fields

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | `station-{index}` | Human-readable label used in logs |
| `enabled` | bool | `true` | Set to `false` to keep the config but skip sending |
| `comment` | string | `""` | Free-text comment appended to the packet; UTF-8 beacon text is supported |
| `destination` | string | `APRS` (or `APRS_DEFAULT_DESTINATION`) | APRS destination field |
| `path` | string | `TCPIP*` (or `APRS_DEFAULT_PATH`) | Digipeater path |
| `symbol_table` | string | `"/"` | APRS symbol table identifier (single character) |
| `symbol_code` | string | `">"` | APRS symbol code (single character) |
| `messaging_capable` | bool | `false` | `true` sets the data type identifier to `=`; `false` uses `!` |
| `course` | integer | — | Course in degrees (0-360). Used with `speed` as `CSE/SPD` |
| `speed` | integer | — | Speed in knots (0-999). Used with `course` as `CSE/SPD` |
| `altitude` | number | — | Altitude in meters. Encoded as `/A=xxxxxx` feet |
| `phg` | string | `""` | PHG extension: 4-digit string, e.g. `"5132"` |
| `rng` | string | `""` | Omni range: 4-digit string in miles, e.g. `"0050"` |
| `server` | string | `""` | Per-station APRS-IS server, overrides `APRS_SERVER` |
| `port` | integer | — | Per-station APRS-IS port, overrides `APRS_PORT` |

Mutual exclusion: `phg`, `rng`, and `course`/`speed` are separate extension groups. Only one group may be set per station.

## Coordinate Format

### Input format (configuration JSON)

Coordinates must use WGS-84 degree-minute strings with 4 decimal places:

- Latitude input: `DDMM.MMMMN` or `DDMM.MMMMS`
- Longitude input: `DDDMM.MMMME` or `DDDMM.MMMMW`

Examples:

- `"latitude": "3412.9800N"`
- `"longitude": "10853.6100E"`

### Internal conversion (before send)

Before sending APRS packets, the script converts input values to APRS fixed-width position fields:

- Latitude output: `DDMM.HHN` or `DDMM.HHS` (8 chars)
- Longitude output: `DDDMM.HHE` or `DDDMM.HHW` (9 chars)

This keeps JSON input precision while ensuring APRS parser compatibility.

## APRS_CALLSIGNS_JSON Examples

### Minimal station

```json
[
  {
    "callsign": "N0CALL",
    "ssid": "",
    "passcode": "00000",
    "latitude": "4807.0380N",
    "longitude": "01134.0360E"
  }
]
```

### Full-featured example

```json
[
  {
    "name": "Home",
    "callsign": "N0CALL",
    "ssid": "",
    "passcode": "00000",
    "latitude": "4807.0380N",
    "longitude": "01134.0360E",
    "comment": "Home beacon",
    "symbol_table": "/",
    "symbol_code": "-"
  },
  {
    "name": "Digipeater",
    "callsign": "N0CALL",
    "ssid": "8",
    "passcode": "00000",
    "latitude": "4807.0380N",
    "longitude": "01134.0360E",
    "comment": "Digi",
    "symbol_table": "/",
    "symbol_code": "#",
    "phg": "5132"
  },
  {
    "name": "Mobile",
    "callsign": "N0CALL",
    "ssid": "9",
    "passcode": "00000",
    "latitude": "4807.0380N",
    "longitude": "01134.0360E",
    "comment": "Mobile",
    "symbol_table": "/",
    "symbol_code": ">",
    "messaging_capable": true,
    "course": 90,
    "speed": 30,
    "altitude": 500
  },
  {
    "name": "Remote",
    "callsign": "N0CALL",
    "ssid": "2",
    "passcode": "00000",
    "enabled": false,
    "latitude": "5130.0200N",
    "longitude": "00007.4900W",
    "comment": "Remote site (disabled)",
    "server": "euro.aprs2.net",
    "port": 14580
  }
]
```

## Conversion Reference

| Input | JSON value |
|---|---|
| `34^12.98N` (Direwolf style) | `"3412.9800N"` |
| `108^53.61E` (Direwolf style) | `"10853.6100E"` |
| 34.21633 deg (decimal latitude) | `"3412.9800N"` |

Decimal degrees to `ddmm.mmmm`:

```
degrees = int(decimal)
minutes = (decimal - degrees) * 60
format as DDMM.MMMM or DDDMM.MMMM + hemisphere
```

Degree-minute text to decimal degrees:

```
decimal = degrees + minutes / 60
example: 34 deg 12.98 min N = 34 + 12.98/60 = 34.21633
```

## Workflow Schedule

The workflow runs every hour and also supports manual dispatch.

To change the schedule, edit `.github/workflows/aprs-beacon.yml`.

## Local Validation

Validate your configuration without sending any packets:

```bash
export APRS_CALLSIGNS_JSON='[{"callsign":"N0CALL","ssid":"","passcode":"00000","latitude":"4807.0380N","longitude":"01134.0360E"}]'
python3 scripts/send_aprs_beacons.py --validate-only
```

Output shows total stations, enabled stations, and rendered APRS packets for enabled entries.

## Contributor
<table>
  <tr>
    <td><a href="https://github.com/mixkover119"><img src="https://avatars.githubusercontent.com/u/68005040?v=4" width="100"><br>@BI9CXC</a></td>
  </tr>
</table>
