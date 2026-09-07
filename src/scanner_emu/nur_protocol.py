from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

PACKET_PREAMBLE = 0xA5
HEADER_SIZE = 6
CRC_INITIAL = 0xFFFF
CRC_POLY = 0x1021

FLAG_UNSOL = 0x0001

STATUS_SUCCESS = 0
STATUS_INVALID_COMMAND = 1
STATUS_INVALID_LENGTH = 2
STATUS_NOT_SUPPORTED = 13


@dataclass
class NurRequest:
    command: int
    flags: int
    payload: bytes


def read_u16(data: Sequence[int], offset: int) -> int:
    return (data[offset] & 0xFF) | ((data[offset + 1] & 0xFF) << 8)


def read_u32(data: Sequence[int], offset: int) -> int:
    return (
        (data[offset] & 0xFF)
        | ((data[offset + 1] & 0xFF) << 8)
        | ((data[offset + 2] & 0xFF) << 16)
        | ((data[offset + 3] & 0xFF) << 24)
    )


def encode_u16(value: int) -> bytes:
    return bytes((value & 0xFF, (value >> 8) & 0xFF))


def encode_u32(value: int) -> bytes:
    return bytes(
        (
            value & 0xFF,
            (value >> 8) & 0xFF,
            (value >> 16) & 0xFF,
            (value >> 24) & 0xFF,
        )
    )


def calculate_header_checksum(header: Sequence[int]) -> int:
    checksum = 0xFF
    for index in range(5):
        checksum ^= header[index] & 0xFF
    return checksum & 0xFF


def crc16_ccitt(data: bytes) -> int:
    crc = CRC_INITIAL
    for byte in data:
        crc ^= (byte & 0xFF) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ CRC_POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def encode_reply(command: int, status: int, payload: bytes, flags: int = 0) -> bytes:
    body = bytearray()
    body.append(command & 0xFF)
    body.append(status & 0xFF)
    body.extend(payload)
    body.extend(encode_u16(crc16_ccitt(bytes(body))))

    packet = bytearray(HEADER_SIZE)
    packet[0] = PACKET_PREAMBLE
    packet[1:3] = encode_u16(len(body))
    packet[3:5] = encode_u16(flags)
    packet[5] = calculate_header_checksum(packet)
    packet.extend(body)
    return bytes(packet)


class NurFrameDecoder:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def has_pending_data(self) -> bool:
        return bool(self._buffer)

    def feed(self, chunk: bytes) -> List[NurRequest]:
        if chunk:
            self._buffer.extend(chunk)

        frames = []
        while True:
            while self._buffer and self._buffer[0] != PACKET_PREAMBLE:
                del self._buffer[0]

            if len(self._buffer) < HEADER_SIZE:
                break

            header = self._buffer[:HEADER_SIZE]
            if calculate_header_checksum(header) != header[5]:
                del self._buffer[0]
                continue

            payload_len = read_u16(self._buffer, 1)
            if payload_len < 3:
                del self._buffer[0]
                continue

            packet_len = HEADER_SIZE + payload_len
            if len(self._buffer) < packet_len:
                break

            body = bytes(self._buffer[HEADER_SIZE:packet_len])
            del self._buffer[:packet_len]

            expected_crc = read_u16(body, len(body) - 2)
            if crc16_ccitt(body[:-2]) != expected_crc:
                continue

            frames.append(
                NurRequest(
                    command=body[0],
                    flags=read_u16(header, 3),
                    payload=body[1:-2],
                )
            )

        return frames
