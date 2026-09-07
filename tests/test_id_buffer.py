from __future__ import annotations

import unittest

from scanner_emu.nur_protocol import (
    FLAG_UNSOL,
    HEADER_SIZE,
    PACKET_PREAMBLE,
    STATUS_SUCCESS,
    NurFrameDecoder,
    calculate_header_checksum,
    crc16_ccitt,
    encode_u16,
)
from scanner_emu.nur_session import (
    NUR_CMD_CLEAR_ID_BUFFER,
    NUR_CMD_NOTIFY_INVENTORY,
    NurSession,
)
from scanner_emu.state import ScannerModel, build_default_state


EPC_ONE = "300000000000000000000001"
EPC_TWO = "300000000000000000000002"


class IdBufferTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.sent_packets: list[bytes] = []
        self.state = build_default_state(ScannerModel.EXA51)
        self.session = NurSession(self.state, self._send_bytes)

    async def _send_bytes(self, data: bytes) -> None:
        self.sent_packets.append(data)

    async def test_duplicate_epc_emits_once_while_inventory_runs(self) -> None:
        await self.session.start_inventory()
        self.sent_packets.clear()

        first = await self.session.queue_tag("30 00 00 00 00 00 00 00 00 00 00 01", -45, 0)
        second = await self.session.queue_tag(EPC_ONE.lower(), -45, 0)

        self.assertTrue(first.accepted)
        self.assertEqual(first.epc_hex, EPC_ONE)
        self.assertEqual(first.flushed, 1)
        self.assertFalse(second.accepted)
        self.assertEqual(second.epc_hex, EPC_ONE)
        self.assertEqual(len(self.state.id_buffer), 1)
        self.assertEqual(len(self.state.queued_tags), 0)

        events = inventory_events(self.sent_packets)
        self.assertEqual(len(events), 1)
        self.assertEqual(sum(len(inventory_records(event)) for event in events), 1)

    async def test_clear_id_buffer_allows_same_epc_again(self) -> None:
        await self.session.start_inventory()
        self.sent_packets.clear()

        first = await self.session.queue_tag(EPC_ONE, -45, 0)
        await self.session.feed_bytes(encode_request(NUR_CMD_CLEAR_ID_BUFFER))
        second = await self.session.queue_tag(EPC_ONE, -45, 0)

        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)
        self.assertEqual(second.flushed, 1)
        self.assertEqual(len(self.state.id_buffer), 1)

        events = inventory_events(self.sent_packets)
        self.assertEqual(sum(len(inventory_records(event)) for event in events), 2)

    async def test_clear_id_buffer_removes_unsent_queued_tags(self) -> None:
        result = await self.session.queue_tag(EPC_ONE, -45, 0)

        self.assertTrue(result.accepted)
        self.assertEqual(len(self.state.id_buffer), 1)
        self.assertEqual(len(self.state.queued_tags), 1)

        await self.session.feed_bytes(encode_request(NUR_CMD_CLEAR_ID_BUFFER))

        self.assertEqual(len(self.state.id_buffer), 0)
        self.assertEqual(len(self.state.queued_tags), 0)

        self.sent_packets.clear()
        await self.session.start_inventory()
        self.assertEqual(inventory_events(self.sent_packets), [])

    async def test_backend_restart_state_starts_with_empty_id_buffer(self) -> None:
        result = await self.session.queue_tag(EPC_ONE, -45, 0)
        restarted_state = build_default_state(ScannerModel.EXA51)

        self.assertTrue(result.accepted)
        self.assertEqual(len(self.state.id_buffer), 1)
        self.assertEqual(len(restarted_state.id_buffer), 0)

    async def test_disconnect_cleanup_does_not_clear_id_buffer(self) -> None:
        await self.session.start_inventory()
        result = await self.session.queue_tag(EPC_ONE, -45, 0)

        await self.session.disconnect_cleanup()

        self.assertTrue(result.accepted)
        self.assertFalse(self.state.inventory_running)
        self.assertEqual(len(self.state.id_buffer), 1)

    async def test_invalid_epc_does_not_modify_id_buffer(self) -> None:
        with self.assertRaises(ValueError):
            await self.session.queue_tag("ABC", -45, 0)

        self.assertEqual(len(self.state.id_buffer), 0)
        self.assertEqual(len(self.state.queued_tags), 0)

    async def test_distinct_epcs_are_still_emitted(self) -> None:
        await self.session.start_inventory()
        self.sent_packets.clear()

        first = await self.session.queue_tag(EPC_ONE, -45, 0)
        second = await self.session.queue_tag(EPC_TWO, -44, 1)

        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)
        self.assertEqual(len(self.state.id_buffer), 2)

        events = inventory_events(self.sent_packets)
        self.assertEqual(len(events), 2)
        self.assertEqual(sum(len(inventory_records(event)) for event in events), 2)


def encode_request(command: int, payload: bytes = b"", flags: int = 0) -> bytes:
    body = bytearray()
    body.append(command & 0xFF)
    body.extend(payload)
    body.extend(encode_u16(crc16_ccitt(bytes(body))))

    packet = bytearray(HEADER_SIZE)
    packet[0] = PACKET_PREAMBLE
    packet[1:3] = encode_u16(len(body))
    packet[3:5] = encode_u16(flags)
    packet[5] = calculate_header_checksum(packet)
    packet.extend(body)
    return bytes(packet)


def decoded_frames(packets: list[bytes]):
    decoder = NurFrameDecoder()
    frames = []
    for packet in packets:
        frames.extend(decoder.feed(packet))
    return frames


def inventory_events(packets: list[bytes]):
    return [
        frame
        for frame in decoded_frames(packets)
        if frame.command == NUR_CMD_NOTIFY_INVENTORY and frame.flags & FLAG_UNSOL
    ]


def inventory_records(frame) -> list[bytes]:
    payload = frame.payload
    if not payload:
        return []
    if payload[0] != STATUS_SUCCESS:
        return []

    event_payload = payload[1:]
    offset = 5
    records: list[bytes] = []
    while offset < len(event_payload):
        record_len = event_payload[offset]
        start = offset + 1
        end = start + record_len
        records.append(event_payload[start:end])
        offset = end
    return records
