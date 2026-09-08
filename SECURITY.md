# Security Policy

RFID Store Simulator is a local development tool. It opens a BLE peripheral on a
local controller and, for the 3D simulator, a local HTTP server bound to
`127.0.0.1` by default. It does not contact any network service on its own.
The only outbound network access is the one-time firmware download that the
[operator guide](docs/usage.md#physical-device) asks you to run manually.

## Reporting a Vulnerability

Please do not open a public issue for security problems. Report them through
the repository's "Security" tab ("Report a vulnerability"). If that is
unavailable, contact the maintainer through the email address on the GitHub
profile of the repository owner.

Expect an acknowledgement within a week. There is no bug bounty.

## Scope

In scope: anything that lets a BLE peer or a browser page talking to the 3D
bridge execute code, read files, or reach beyond the emulator process.

Out of scope: protocol incompatibilities with real scanners or a connected
host; those are normal issues.
