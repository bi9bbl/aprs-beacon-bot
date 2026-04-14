# APRS Beacon Bot

This repository uses GitHub Actions to send scheduled APRS-IS position beacons.

## Features

- Scheduled beacon transmission with GitHub Actions
- Multiple callsigns, multiple SSIDs, and multiple positions
- Credentials stored in GitHub Secrets
- Beacon content stored in GitHub Repository Variables
- No third-party Python dependencies

## GitHub Secrets

Create this repository secret:

- `APRS_CALLSIGNS_JSON`

Example value:

```json
[
  {
    "name": "home-mobile",
    "callsign": "BI9XXX",
    "ssid": "9",
    "passcode": "12345",
    "latitude": 31.2304,
    "longitude": 121.4737,
    "comment": "Home beacon",
    "destination": "APRS",
    "path": "TCPIP*",
    "symbol_table": "/",
    "symbol_code": ">"
  },
  {
    "name": "remote-station",
    "callsign": "BI9YYY",
    "ssid": "",
    "passcode": "23456",
    "latitude": 39.9042,
    "longitude": 116.4074,
    "comment": "Remote site",
    "destination": "APRS",
    "path": "TCPIP*",
    "symbol_table": "/",
    "symbol_code": "r"
  }
]
```

Notes:

- Each JSON object is one complete station record.
- `callsign`、`ssid`、`passcode`、坐标、`comment` 等信息都维护在同一个对象中。
- If a callsign should not use an SSID suffix, use an empty string: `""`.

## GitHub Repository Variables

Create these repository variables if needed:

- `APRS_SERVER` optional, default `rotate.aprs2.net`
- `APRS_PORT` optional, default `14580`
- `APRS_LOGIN_VERSION` optional, default `aprs-beacon-bot/1.0`
- `APRS_DEFAULT_DESTINATION` optional, default `APRS`
- `APRS_DEFAULT_PATH` optional, default `TCPIP*`

Notes:

- Station-specific content is now maintained in `APRS_CALLSIGNS_JSON`.
- Repository variables are only used for optional global defaults.

## Workflow schedule

The workflow runs every hour and also supports manual trigger.

To change the schedule, edit [`.github/workflows/aprs-beacon.yml`](.github/workflows/aprs-beacon.yml).

## Local validation

You can validate the configuration format without sending packets:

```bash
export APRS_CALLSIGNS_JSON='[{"name":"test-station","callsign":"BI9XXX","ssid":"1","passcode":"12345","latitude":31.2304,"longitude":121.4737,"comment":"Test","symbol_table":"/","symbol_code":">"}]'
python scripts/send_aprs_beacons.py --validate-only
```
