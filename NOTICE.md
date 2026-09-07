# Notices

RFID Store Simulator is an independent local development tool for emulating
EXA/NUR scanner behavior during RFID inventory software development and
testing.

It is not an official product of Nordic ID or Bumble. Nordic ID, EXA, and NUR
are trademarks of their respective owners; they are used here only to describe
compatibility. This project is not affiliated with or endorsed by Nordic ID.

## Third-Party Code, Data, Or Assets

- `bumble` (Apache-2.0, Google) is the runtime BLE dependency, installed from
  PyPI. Upstream: `https://github.com/google/bumble`. It is not vendored here.
- `src/scanner_emu/web_3d/vendor/three.module.js` vendors Three.js 0.160.0
  from `https://registry.npmjs.org/three/-/three-0.160.0.tgz` under the
  MIT License. The full license text is packaged at
  `src/scanner_emu/web_3d/vendor/THREE-LICENSE.txt`. npm integrity:
  `sha512-DLU8lc0zNIPkM7rH5/e1Ks1Z8tWCGRq6g8mPowdDJpw1CFBJMU7UoJjC6PefXW7z//SSl0b2+GCw14LB+uDhng==`;
  shasum: `cd1e4dbd01aee0719280a9086d75545db52b7a8f`.
- The Nordic ID NUR SDK (`https://github.com/NordicID/nur_sdk`) was used as
  protocol reference material. It carries no license and is not redistributed
  here; nothing from it is copied into this repository.
- Realtek Bluetooth firmware for the documented USB dongle is downloaded by
  the user from the linux-firmware project at setup time; it is not
  distributed with this repository.

## Data

- `scanner_emu.epc` generates synthetic SGTIN-96 EPC values from EAN-13
  input. All EANs, EPCs, serial numbers, and BLE addresses in this repository
  and its tests are synthetic.
- Do not commit real inventory exports, real product data,
  or operational scanner captures.
