# ADR 0005: Testing With A BLE Host On A Physical Device

## Status

Accepted on 2026-09-07.

## Context

The emulator was only used with the Android emulator through Bumble's
`android-netsim` transport. Testing a BLE host on a physical device requires
a real BLE radio driven by Bumble. macOS does not expose the built-in
Bluetooth controller over HCI, so a dedicated controller is needed.
Separately, `bumble` on PyPI now requires Python 3.10 or newer, while the
project still advertised a 3.9 floor.

## Decision

- The supported physical-device path is a dedicated USB HCI dongle passed to
  Bumble as `--transport usb:...`. The reference hardware is the ASUS
  USB-BT500 (Realtek RTL8761BU, USB `0b05:190e`), handled by Bumble's
  built-in Realtek driver with firmware from linux-firmware pinned by release
  tag and checksum in `README.md`.
- No emulator code changes are made for this path; `--transport` is passed
  through unchanged, and the advertising contract (connectable PDU, complete
  local name containing `EXA`, fixed static random address) already satisfies
  the host discovery rules in `README.md` (Host discovery notes).
- The minimum Python version is raised to 3.10 in `pyproject.toml`, the
  entrypoint version guards, and all documentation.

## Alternatives Considered

- nRF52840 dongle with the Zephyr `hci_usb` sample: viable per Bumble docs,
  not validated here; kept as a mention only.
- Remote controller through `bumble-hci-bridge` on a Linux host and
  `tcp-client`: viable, adds a second machine; not validated.
- Keeping Python 3.9 by pinning an older Bumble: rejected, the Realtek driver
  and USB transport fixes live in current releases.

## Consequences

- Operators need the one-time macOS setup (nvram switch behavior, firmware
  download) documented in `README.md` "Physical device".
- Documentation carries a checksum-pinned firmware download that must be
  refreshed deliberately when moving to a newer linux-firmware release.
- Environments on Python 3.9 stop at the entrypoint guard with an explicit
  message instead of failing on the Bumble import.

## Related

- `README.md` "Physical device" and "Host discovery notes"
- `docs/emulator.md` "Common Failure Modes"
- `docs/wiki/topics/operator-workflows.md` "Physical Device"
