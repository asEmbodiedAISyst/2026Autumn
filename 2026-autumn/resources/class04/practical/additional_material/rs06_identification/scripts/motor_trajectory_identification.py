#!/usr/bin/env python3
"""Control selected RS06 motors by CAN ID and record identification data.

The script talks directly to the current MagicLimb control-box USB CDC
protocol. It does not import ROS. Hardware access is disabled unless
--execute is supplied explicitly.

The control box always transports 16 fixed motor slots. Only the CAN IDs
selected by --motor-ids receive non-zero KP/KD. Unselected slots are sent
zero gains and a neutral position command.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


PROTOCOL_NAME = "MagicLimb control box 16-slot protocol"
PROTOCOL_VERSION = "observed-2026-08-08"
MOTOR_MODEL = "RS06"
DEFAULT_CONTROL_FREQUENCY_HZ = 50.0

FRAME_HEADER = b"\xFE\x00"
FRAME_TRAILER = b"\x00\xEF"
FEEDBACK_FRAME_SIZE = 163
MOTOR_RECORD_SIZE = 9
MOTOR_RECORD_COUNT = 16
SBUS_SIZE = 15

# USB/controller slots are fixed by the SUM, FLRL, and FRRR firmware.
SLOT_TO_CAN_ID: Tuple[int, ...] = (
    1, 2, 3, 4,       # FLRL / CAN1
    9, 10, 11, 12,    # FLRL / CAN2
    5, 6, 7, 8,       # FRRR / CAN1
    13, 14, 15, 16,   # FRRR / CAN2
)
CAN_ID_TO_SLOT: Dict[int, int] = {
    can_id: slot for slot, can_id in enumerate(SLOT_TO_CAN_ID)
}

CAN_ROUTE: Dict[int, Tuple[str, str]] = {
    **{can_id: ("FLRL", "CAN1") for can_id in range(1, 5)},
    **{can_id: ("FRRR", "CAN1") for can_id in range(5, 9)},
    **{can_id: ("FLRL", "CAN2") for can_id in range(9, 13)},
    **{can_id: ("FRRR", "CAN2") for can_id in range(13, 17)},
}

RS06_LIMITS: Dict[str, Tuple[float, float]] = {
    "position": (-12.57, 12.57),
    "velocity": (-50.0, 50.0),
    "torque": (-36.0, 36.0),
    "kp": (0.0, 5000.0),
    "kd": (0.0, 100.0),
}

TYPE_OPCODE = 0x01
MODE_OPCODE = 0x02
KP_OPCODE = 0x03
KD_OPCODE = 0x04
SET_ZERO_OPCODE = 0x05
COMMAND_OPCODE = 0x00

TYPE_TAG = 0x10
MODE_TAG = 0x20
KP_TAG = 0x30
KD_TAG = 0x40
SET_ZERO_TAG = 0x50
COMMAND_TAG = 0x00

RS06_TYPE_WORD = 0x0606
POSITION_MODE_WORD = 0x0000
TORQUE_MODE_WORD = 0x2222
SET_ZERO_CLOSE_WORD = 0x0000
SET_ZERO_APPLY_WORD = 0x1111


CSV_FIELDS: Tuple[str, ...] = (
    "sample_index",
    "host_time_utc",
    "elapsed_s",
    "feedback_elapsed_s",
    "phase",
    "trajectory_time_s",
    "loop_dt_s",
    "schedule_lateness_s",
    "can_id",
    "controller_slot",
    "selected",
    "motor_model",
    "kp",
    "kd",
    "q_start_rad",
    "q_command_requested_rad",
    "q_command_encoded_rad",
    "q_command_saturated",
    "q_feedback_rad",
    "qdot_feedback_rad_s",
    "torque_feedback_nm",
    "target_feedback_rad",
    "target_matches_current_command",
    "tracking_error_rad",
    "raw_q_u16",
    "raw_qdot_u16",
    "raw_torque_u16",
    "raw_target_u16",
    "raw_record_hex",
)


class ProtocolError(RuntimeError):
    """Raised when a valid control-box packet cannot be read or written."""


@dataclass(frozen=True)
class EncodedValue:
    requested: float
    clamped: float
    raw: int
    decoded: float
    saturated: bool


@dataclass(frozen=True)
class MotorFeedback:
    slot: int
    expected_can_id: int
    reported_can_id: int
    q: float
    qdot: float
    torque: float
    target: float
    raw_q: int
    raw_qdot: int
    raw_torque: int
    raw_target: int
    raw_record: bytes


@dataclass(frozen=True)
class FeedbackFrame:
    motors: Tuple[MotorFeedback, ...]
    raw_frame: bytes
    received_monotonic: float
    received_utc: str


@dataclass(frozen=True)
class CommandEncoding:
    requested_positions: Tuple[float, ...]
    encoded_positions: Tuple[EncodedValue, ...]
    packet: bytes


@dataclass(frozen=True)
class TorqueCommandEncoding:
    """One 16-slot torque command and its exact wire representation."""

    requested_torques: Tuple[float, ...]
    encoded_torques: Tuple[EncodedValue, ...]
    packet: bytes


def _uint16(byte_high: int, byte_low: int) -> int:
    return (byte_high << 8) | byte_low


def _decode_uint16(raw: int, value_min: float, value_max: float) -> float:
    return value_min + (value_max - value_min) * raw / 65535.0


def _encode_float(value: float, value_min: float, value_max: float) -> EncodedValue:
    clamped = min(max(float(value), value_min), value_max)
    raw = int((clamped - value_min) / (value_max - value_min) * 65535.0)
    raw = min(max(raw, 0), 65535)
    decoded = _decode_uint16(raw, value_min, value_max)
    return EncodedValue(
        requested=float(value),
        clamped=clamped,
        raw=raw,
        decoded=decoded,
        saturated=not math.isclose(clamped, float(value), rel_tol=0.0, abs_tol=1e-12),
    )


def _word_bytes(word: int) -> Tuple[int, int]:
    if not 0 <= word <= 0xFFFF:
        raise ValueError(f"16-bit word out of range: {word}")
    return (word >> 8) & 0xFF, word & 0xFF


def build_host_packet(opcode: int, tag: int, payload_words: Sequence[int]) -> bytes:
    """Build the two 20-byte subframes expected by the SUM board."""

    if len(payload_words) != MOTOR_RECORD_COUNT:
        raise ValueError(f"Expected 16 payload words, got {len(payload_words)}")

    packet = bytearray()
    for group_start in (0, 8):
        packet.extend((0xFE, opcode))
        for word in payload_words[group_start : group_start + 8]:
            packet.extend(_word_bytes(int(word)))
        packet.extend((tag, 0xEF))

    if len(packet) != 40:
        raise AssertionError(f"Internal packet construction error: {len(packet)} bytes")
    return bytes(packet)


def build_position_command(position_by_slot: Sequence[float]) -> CommandEncoding:
    if len(position_by_slot) != MOTOR_RECORD_COUNT:
        raise ValueError(f"Expected 16 position commands, got {len(position_by_slot)}")

    p_min, p_max = RS06_LIMITS["position"]
    encoded = tuple(_encode_float(value, p_min, p_max) for value in position_by_slot)
    packet = build_host_packet(
        COMMAND_OPCODE,
        COMMAND_TAG,
        [value.raw for value in encoded],
    )
    return CommandEncoding(
        requested_positions=tuple(float(value) for value in position_by_slot),
        encoded_positions=encoded,
        packet=packet,
    )


def build_torque_command(torque_by_slot: Sequence[float]) -> TorqueCommandEncoding:
    """Build a motion packet whose payload is interpreted in RS06 torque mode."""

    if len(torque_by_slot) != MOTOR_RECORD_COUNT:
        raise ValueError(f"Expected 16 torque commands, got {len(torque_by_slot)}")

    torque_min, torque_max = RS06_LIMITS["torque"]
    encoded = tuple(
        _encode_float(value, torque_min, torque_max) for value in torque_by_slot
    )
    packet = build_host_packet(
        COMMAND_OPCODE,
        COMMAND_TAG,
        [value.raw for value in encoded],
    )
    return TorqueCommandEncoding(
        requested_torques=tuple(float(value) for value in torque_by_slot),
        encoded_torques=encoded,
        packet=packet,
    )


def build_set_zero_packet(selected_can_ids: Sequence[int] = ()) -> bytes:
    """Build a set-zero packet for explicitly selected physical CAN IDs."""

    if len(set(selected_can_ids)) != len(selected_can_ids):
        raise ValueError("Set-zero CAN IDs contain duplicates")
    invalid_ids = [can_id for can_id in selected_can_ids if can_id not in CAN_ID_TO_SLOT]
    if invalid_ids:
        raise ValueError(
            "Set-zero CAN IDs must be in 1..16; invalid: "
            + ", ".join(str(can_id) for can_id in invalid_ids)
        )
    words = [SET_ZERO_CLOSE_WORD] * MOTOR_RECORD_COUNT
    for can_id in selected_can_ids:
        words[CAN_ID_TO_SLOT[can_id]] = SET_ZERO_APPLY_WORD
    return build_host_packet(SET_ZERO_OPCODE, SET_ZERO_TAG, words)


def build_rs06_position_configuration_packets(
    kp_by_slot: Sequence[float],
    kd_by_slot: Sequence[float],
    *,
    set_zero_can_ids: Sequence[int] = (),
) -> Tuple[Tuple[str, bytes], ...]:
    """Build the five ordered configuration packets consumed by the firmware."""

    if len(kp_by_slot) != MOTOR_RECORD_COUNT or len(kd_by_slot) != MOTOR_RECORD_COUNT:
        raise ValueError(
            f"KP and KD configuration must each contain {MOTOR_RECORD_COUNT} slots"
        )

    kp_min, kp_max = RS06_LIMITS["kp"]
    kd_min, kd_max = RS06_LIMITS["kd"]
    kp_words = [_encode_float(value, kp_min, kp_max).raw for value in kp_by_slot]
    kd_words = [_encode_float(value, kd_min, kd_max).raw for value in kd_by_slot]
    zero_label = (
        "set-zero = Apply CAN IDs "
        + ", ".join(str(can_id) for can_id in set_zero_can_ids)
        if set_zero_can_ids
        else "set-zero = Close"
    )

    return (
        (
            "motor type = RS06",
            build_host_packet(
                TYPE_OPCODE,
                TYPE_TAG,
                [RS06_TYPE_WORD] * MOTOR_RECORD_COUNT,
            ),
        ),
        (
            "mode = position",
            build_host_packet(
                MODE_OPCODE,
                MODE_TAG,
                [POSITION_MODE_WORD] * MOTOR_RECORD_COUNT,
            ),
        ),
        ("KP", build_host_packet(KP_OPCODE, KP_TAG, kp_words)),
        ("KD", build_host_packet(KD_OPCODE, KD_TAG, kd_words)),
        (zero_label, build_set_zero_packet(set_zero_can_ids)),
    )


def build_rs06_torque_configuration_packets() -> Tuple[Tuple[str, bytes], ...]:
    """Build the five-packet RS06 torque-mode configuration sequence.

    KP and KD are deliberately written as zero for every slot. They are not
    part of the RS06 torque-mode command, and keeping them zero makes the
    configuration intent explicit if firmware behavior changes.
    """

    zero_words = [0] * MOTOR_RECORD_COUNT
    return (
        (
            "motor type = RS06",
            build_host_packet(
                TYPE_OPCODE,
                TYPE_TAG,
                [RS06_TYPE_WORD] * MOTOR_RECORD_COUNT,
            ),
        ),
        (
            "mode = torque",
            build_host_packet(
                MODE_OPCODE,
                MODE_TAG,
                [TORQUE_MODE_WORD] * MOTOR_RECORD_COUNT,
            ),
        ),
        ("KP = 0", build_host_packet(KP_OPCODE, KP_TAG, zero_words)),
        ("KD = 0", build_host_packet(KD_OPCODE, KD_TAG, zero_words)),
        ("set-zero = Close", build_set_zero_packet()),
    )


def parse_feedback_frame(frame: bytes) -> FeedbackFrame:
    if len(frame) != FEEDBACK_FRAME_SIZE:
        raise ProtocolError(
            f"Invalid feedback frame length: expected {FEEDBACK_FRAME_SIZE}, got {len(frame)}"
        )
    if frame[:2] != FRAME_HEADER:
        raise ProtocolError(
            f"Invalid feedback header: expected FE 00, got {frame[:2].hex(' ').upper()}"
        )
    if frame[-2:] != FRAME_TRAILER:
        raise ProtocolError(
            f"Invalid feedback trailer: expected 00 EF, got {frame[-2:].hex(' ').upper()}"
        )

    p_min, p_max = RS06_LIMITS["position"]
    v_min, v_max = RS06_LIMITS["velocity"]
    t_min, t_max = RS06_LIMITS["torque"]

    motors: List[MotorFeedback] = []
    for slot, expected_can_id in enumerate(SLOT_TO_CAN_ID):
        begin = 2 + slot * MOTOR_RECORD_SIZE
        record = frame[begin : begin + MOTOR_RECORD_SIZE]
        raw_q = _uint16(record[1], record[2])
        raw_qdot = _uint16(record[3], record[4])
        raw_torque = _uint16(record[5], record[6])
        raw_target = _uint16(record[7], record[8])
        motors.append(
            MotorFeedback(
                slot=slot,
                expected_can_id=expected_can_id,
                reported_can_id=record[0],
                q=_decode_uint16(raw_q, p_min, p_max),
                qdot=_decode_uint16(raw_qdot, v_min, v_max),
                torque=_decode_uint16(raw_torque, t_min, t_max),
                target=_decode_uint16(raw_target, p_min, p_max),
                raw_q=raw_q,
                raw_qdot=raw_qdot,
                raw_torque=raw_torque,
                raw_target=raw_target,
                raw_record=bytes(record),
            )
        )

    return FeedbackFrame(
        motors=tuple(motors),
        raw_frame=bytes(frame),
        received_monotonic=time.perf_counter(),
        received_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
    )


class ControlBox:
    """Minimal pyserial driver for the current 16-slot control-box protocol."""

    def __init__(
        self,
        port: str,
        baudrate: int,
        serial_timeout_s: float,
        allow_shared_port: bool,
    ) -> None:
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError(
                "pyserial is required for --execute. Install it with "
                "python -m pip install pyserial."
            ) from exc

        serial_kwargs: Dict[str, Any] = {
            "port": port,
            "baudrate": baudrate,
            "timeout": serial_timeout_s,
            "write_timeout": serial_timeout_s,
        }
        if os.name != "nt" and not allow_shared_port:
            serial_kwargs["exclusive"] = True

        self.serial = serial.Serial(**serial_kwargs)
        self._rx_buffer = bytearray()
        self.frames_read = 0
        self.invalid_candidates = 0

    def close(self) -> None:
        self.serial.close()

    def clear_input(self) -> None:
        self._rx_buffer.clear()
        self.serial.reset_input_buffer()

    def _read_more(self) -> bytes:
        try:
            waiting = int(self.serial.in_waiting)
        except (AttributeError, OSError):
            waiting = 0
        return self.serial.read(min(max(waiting, 1), 4096))

    def read_feedback(self, timeout_s: float) -> FeedbackFrame:
        deadline = time.perf_counter() + timeout_s
        last_bad_trailer: Optional[bytes] = None

        while time.perf_counter() < deadline:
            header_index = self._rx_buffer.find(FRAME_HEADER)
            if header_index < 0:
                if self._rx_buffer.endswith(b"\xFE"):
                    self._rx_buffer[:] = b"\xFE"
                else:
                    self._rx_buffer.clear()
            elif header_index > 0:
                del self._rx_buffer[:header_index]

            if (
                self._rx_buffer.startswith(FRAME_HEADER)
                and len(self._rx_buffer) >= FEEDBACK_FRAME_SIZE
            ):
                candidate = bytes(self._rx_buffer[:FEEDBACK_FRAME_SIZE])
                if candidate[-2:] == FRAME_TRAILER:
                    del self._rx_buffer[:FEEDBACK_FRAME_SIZE]
                    frame = parse_feedback_frame(candidate)
                    self.frames_read += 1
                    return frame

                last_bad_trailer = candidate[-2:]
                self.invalid_candidates += 1
                del self._rx_buffer[0]
                continue

            chunk = self._read_more()
            if chunk:
                self._rx_buffer.extend(chunk)

        if last_bad_trailer is not None:
            raise ProtocolError(
                "Timed out while resynchronizing feedback; last 163-byte "
                f"candidate ended with {last_bad_trailer.hex(' ').upper()}"
            )
        raise ProtocolError("Timed out waiting for a complete 163-byte FE 00 ... 00 EF frame")

    def write_packet(self, packet: bytes, flush: bool = False) -> None:
        if len(packet) != 40:
            raise ProtocolError(f"Refusing to write non-40-byte host packet: {len(packet)}")
        written = self.serial.write(packet)
        if written != len(packet):
            raise ProtocolError(f"Short serial write: expected 40 bytes, wrote {written}")
        if flush:
            self.serial.flush()

    def configure_rs06_position_mode(
        self,
        kp_by_slot: Sequence[float],
        kd_by_slot: Sequence[float],
        delay_s: float,
        *,
        set_zero_can_ids: Sequence[int] = (),
    ) -> None:
        configuration = build_rs06_position_configuration_packets(
            kp_by_slot,
            kd_by_slot,
            set_zero_can_ids=set_zero_can_ids,
        )

        for index, (label, packet) in enumerate(configuration, start=1):
            print(f"Configuration {index}/5: {label}")
            self.write_packet(packet, flush=True)
            if delay_s > 0:
                time.sleep(delay_s)
            self.clear_input()

    def configure_rs06_torque_mode(self, delay_s: float) -> None:
        """Configure all fixed slots as RS06 torque mode with zero gains."""

        configuration = build_rs06_torque_configuration_packets()
        for index, (label, packet) in enumerate(configuration, start=1):
            print(f"Configuration {index}/5: {label}")
            self.write_packet(packet, flush=True)
            if delay_s > 0:
                time.sleep(delay_s)
            self.clear_input()

    def send_positions(self, position_by_slot: Sequence[float]) -> CommandEncoding:
        encoding = build_position_command(position_by_slot)
        self.write_packet(encoding.packet)
        return encoding

    def send_torques(self, torque_by_slot: Sequence[float]) -> TorqueCommandEncoding:
        encoding = build_torque_command(torque_by_slot)
        self.write_packet(encoding.packet)
        return encoding


def acquire_required_feedback(
    controller: ControlBox,
    required_can_ids: Sequence[int],
    frame_timeout_s: float,
    max_failures: int,
    context: str,
) -> FeedbackFrame:
    failures = 0
    required = tuple(required_can_ids)
    while failures < max_failures:
        try:
            frame = controller.read_feedback(frame_timeout_s)
            mismatches = []
            for can_id in required:
                slot = CAN_ID_TO_SLOT[can_id]
                reported = frame.motors[slot].reported_can_id
                if reported != can_id:
                    mismatches.append(
                        f"CAN ID {can_id} slot {slot} reported ID {reported}"
                    )
            if mismatches:
                raise ProtocolError("; ".join(mismatches))
            return frame
        except ProtocolError as exc:
            failures += 1
            print(
                f"{context} feedback failed ({failures}/{max_failures}): {exc}",
                file=sys.stderr,
            )

    raise ProtocolError(
        f"{context}: no valid feedback for selected CAN IDs "
        + ", ".join(str(value) for value in required)
    )


def wait_for_required_motors_online(
    controller: ControlBox,
    required_can_ids: Sequence[int],
    online_timeout_s: float,
    frame_timeout_s: float,
    context: str,
) -> FeedbackFrame:
    """Wait through lower-board startup until selected fixed slots are populated."""

    required = tuple(required_can_ids)
    deadline = time.perf_counter() + online_timeout_s
    next_progress = time.perf_counter() + 1.0
    valid_frames = 0
    last_frame: Optional[FeedbackFrame] = None
    last_read_error: Optional[str] = None

    while time.perf_counter() < deadline:
        remaining = deadline - time.perf_counter()
        try:
            frame = controller.read_feedback(min(frame_timeout_s, remaining))
        except ProtocolError as exc:
            last_read_error = str(exc)
            continue

        valid_frames += 1
        last_frame = frame
        mismatches = []
        for can_id in required:
            slot = CAN_ID_TO_SLOT[can_id]
            reported = frame.motors[slot].reported_can_id
            if reported != can_id:
                mismatches.append((can_id, slot, reported))
        if not mismatches:
            return frame

        now = time.perf_counter()
        if now >= next_progress:
            details = ", ".join(
                f"ID {can_id}/slot {slot} -> {reported}"
                for can_id, slot, reported in mismatches
            )
            print(
                f"{context}: waiting for selected motor feedback ({details})...",
                file=sys.stderr,
            )
            next_progress = now + 1.0

    selected_details = "no valid feedback frame received"
    nonzero_details = "none"
    if last_frame is not None:
        selected_details = ", ".join(
            f"ID {can_id}/slot {CAN_ID_TO_SLOT[can_id]} -> "
            f"{last_frame.motors[CAN_ID_TO_SLOT[can_id]].reported_can_id}"
            for can_id in required
        )
        nonzero_records = [
            f"slot {record.slot}: ID {record.reported_can_id}"
            for record in last_frame.motors
            if record.reported_can_id != 0
        ]
        nonzero_details = ", ".join(nonzero_records) if nonzero_records else "none"

    suffix = f"; last read error: {last_read_error}" if last_read_error else ""
    raise ProtocolError(
        f"{context}: selected motors did not become available within "
        f"{online_timeout_s:.3f}s; selected slot reports: {selected_details}; "
        f"last non-zero slot records: {nonzero_details}; "
        f"valid frames observed: {valid_frames}{suffix}"
    )


def wait_for_command_echo(
    controller: ControlBox,
    required_can_ids: Sequence[int],
    encoding: CommandEncoding,
    timeout_s: float,
    frame_timeout_s: float,
) -> FeedbackFrame:
    expected_raw = {
        can_id: encoding.encoded_positions[CAN_ID_TO_SLOT[can_id]].raw
        for can_id in required_can_ids
    }
    deadline = time.perf_counter() + timeout_s
    last_seen: Dict[int, int] = {}

    while time.perf_counter() < deadline:
        remaining = deadline - time.perf_counter()
        try:
            frame = controller.read_feedback(min(frame_timeout_s, remaining))
        except ProtocolError:
            continue
        valid_ids = True
        matches = True
        for can_id in required_can_ids:
            record = frame.motors[CAN_ID_TO_SLOT[can_id]]
            last_seen[can_id] = record.raw_target
            if record.reported_can_id != can_id:
                valid_ids = False
                matches = False
            elif record.raw_target != expected_raw[can_id]:
                matches = False
        if valid_ids and matches:
            return frame

    details = ", ".join(
        f"ID {can_id}: expected 0x{expected_raw[can_id]:04X}, "
        f"last 0x{last_seen.get(can_id, -1) & 0xFFFF:04X}"
        for can_id in required_can_ids
    )
    raise ProtocolError(f"Timed out waiting for selected-motor command echo ({details})")


def wait_for_torque_command_echo(
    controller: ControlBox,
    required_can_ids: Sequence[int],
    encoding: TorqueCommandEncoding,
    timeout_s: float,
    frame_timeout_s: float,
) -> FeedbackFrame:
    """Wait until torque-mode target bytes echo the selected slot commands."""

    expected_raw = {
        can_id: encoding.encoded_torques[CAN_ID_TO_SLOT[can_id]].raw
        for can_id in required_can_ids
    }
    deadline = time.perf_counter() + timeout_s
    last_seen: Dict[int, int] = {}

    while time.perf_counter() < deadline:
        remaining = deadline - time.perf_counter()
        try:
            frame = controller.read_feedback(min(frame_timeout_s, remaining))
        except ProtocolError:
            continue
        valid_ids = True
        matches = True
        for can_id in required_can_ids:
            record = frame.motors[CAN_ID_TO_SLOT[can_id]]
            last_seen[can_id] = record.raw_target
            if record.reported_can_id != can_id:
                valid_ids = False
                matches = False
            elif record.raw_target != expected_raw[can_id]:
                matches = False
        if valid_ids and matches:
            return frame

    details = ", ".join(
        f"ID {can_id}: expected 0x{expected_raw[can_id]:04X}, "
        f"last 0x{last_seen.get(can_id, -1) & 0xFFFF:04X}"
        for can_id in required_can_ids
    )
    raise ProtocolError(
        f"Timed out waiting for selected-motor torque command echo ({details})"
    )


def expand_values(
    values: Optional[Sequence[float]],
    count: int,
    option_name: str,
    required: bool,
) -> List[Optional[float]]:
    if values is None:
        if required:
            raise ValueError(f"{option_name} is required with --execute")
        return [None] * count
    if len(values) == 1:
        return [float(values[0])] * count
    if len(values) == count:
        return [float(value) for value in values]
    raise ValueError(
        f"{option_name} expects one value or {count} values to match --motor-ids"
    )


def trajectory_envelope(t: float, duration: float, ramp_duration: float) -> float:
    if ramp_duration <= 0:
        return 1.0
    if t < ramp_duration:
        return 0.5 * (1.0 - math.cos(math.pi * t / ramp_duration))
    if t > duration - ramp_duration:
        remaining = max(0.0, duration - t)
        return 0.5 * (1.0 - math.cos(math.pi * remaining / ramp_duration))
    return 1.0


def trajectory_value(args: argparse.Namespace, t: float, amplitude: float) -> float:
    envelope = trajectory_envelope(t, args.duration, args.ramp_duration)
    if args.trajectory == "sine":
        phase = 2.0 * math.pi * args.frequency * t
    else:
        frequency_rate = (args.end_frequency - args.start_frequency) / args.duration
        phase = 2.0 * math.pi * (
            args.start_frequency * t + 0.5 * frequency_rate * t * t
        )
    return amplitude * envelope * math.sin(phase)


def metadata_path_for(csv_path: Path) -> Path:
    return csv_path.with_suffix(".metadata.json")


def plot_experiment_csv(
    csv_path: Path,
    *,
    show: bool,
    output: Optional[Path],
) -> None:
    """Plot only values carried by controller feedback records."""

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV does not exist: {csv_path}")
    try:
        if not show:
            import matplotlib

            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "Plotting requires Matplotlib. Install it with "
            "python -m pip install matplotlib."
        ) from exc

    required_fields = {
        "feedback_elapsed_s",
        "can_id",
        "selected",
        "q_feedback_rad",
        "qdot_feedback_rad_s",
        "torque_feedback_nm",
        "target_feedback_rad",
    }
    grouped: Dict[int, List[Dict[str, str]]] = defaultdict(list)
    with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = sorted(required_fields.difference(reader.fieldnames or ()))
        if missing:
            raise ValueError("CSV is missing plot fields: " + ", ".join(missing))
        for row in reader:
            if row["selected"] == "1":
                grouped[int(row["can_id"])].append(row)

    if not grouped:
        raise ValueError("CSV contains no selected-motor samples to plot")

    figure, axes = plt.subplots(
        4,
        1,
        figsize=(11, 10),
        sharex=True,
        constrained_layout=True,
    )

    for can_id in sorted(grouped):
        rows = grouped[can_id]
        feedback_elapsed = [float(row["feedback_elapsed_s"]) for row in rows]
        feedback_position = [float(row["q_feedback_rad"]) for row in rows]
        feedback_velocity = [float(row["qdot_feedback_rad_s"]) for row in rows]
        feedback_torque = [float(row["torque_feedback_nm"]) for row in rows]
        feedback_target = [float(row["target_feedback_rad"]) for row in rows]

        axes[0].plot(
            feedback_elapsed,
            feedback_target,
            label=f"ID {can_id} target feedback",
            linewidth=1.5,
        )
        axes[0].plot(
            feedback_elapsed,
            feedback_position,
            label=f"ID {can_id} feedback @ receive",
            linewidth=1.1,
        )
        axes[1].plot(
            feedback_elapsed,
            feedback_velocity,
            label=f"ID {can_id} qdot feedback",
            linewidth=1.1,
        )
        axes[2].plot(
            feedback_elapsed,
            feedback_torque,
            label=f"ID {can_id} torque feedback",
            linewidth=1.2,
        )
        axes[3].plot(
            feedback_elapsed,
            [
                target - position
                for target, position in zip(feedback_target, feedback_position)
            ],
            label=f"ID {can_id}: target - q",
            linewidth=1.1,
        )

    axes[0].set_ylabel("Position [rad]")
    axes[1].set_ylabel("Velocity [rad/s]")
    axes[2].set_ylabel("Torque [Nm]")
    axes[3].set_ylabel("Target - q [rad]")
    axes[3].set_xlabel("Feedback time [s]")
    axes[3].axhline(0.0, color="0.5", linewidth=0.8)
    for axis in axes:
        axis.grid(True, alpha=0.25)
        axis.legend()

    motor_text = ", ".join(str(value) for value in sorted(grouped))
    figure.suptitle(
        f"RS06 controller feedback | CAN ID {motor_text} | {csv_path.name}"
    )

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=160)
        print(f"Plot:     {output}")
    if show:
        plt.show()
    else:
        plt.close(figure)


def check_output_paths(csv_path: Path, overwrite: bool) -> Path:
    metadata_path = metadata_path_for(csv_path)
    existing = [path for path in (csv_path, metadata_path) if path.exists()]
    if existing and not overwrite:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(
            f"Refusing to overwrite existing output(s): {names}. "
            "Choose a new --output path or add --overwrite."
        )
    return metadata_path


def print_motor_table() -> None:
    print("Current control-box CAN ID mapping")
    print("CAN ID  slot  lower board  CAN bus")
    print("------  ----  -----------  -------")
    for can_id in range(1, 17):
        slot = CAN_ID_TO_SLOT[can_id]
        board, bus = CAN_ROUTE[can_id]
        print(f"{can_id:6d}  {slot:4d}  {board:11s}  {bus}")


def build_parser() -> argparse.ArgumentParser:
    default_port = "COM7" if os.name == "nt" else "/dev/ttyACM0"
    parser = argparse.ArgumentParser(
        description=(
            "Drive selected RS06 motors by physical CAN ID through the current "
            "16-slot MagicLimb control-box protocol and log feedback to CSV."
        )
    )

    parser.add_argument("--list-motors", action="store_true", help="print CAN routing and exit")
    parser.add_argument("--motor-ids", nargs="+", type=int, help="physical motor CAN IDs, 1..16")
    parser.add_argument("--port", default=default_port)
    parser.add_argument("--baudrate", type=int, default=1_000_000)
    parser.add_argument("--serial-timeout", type=float, default=0.02)
    parser.add_argument("--frame-timeout", type=float, default=0.5)
    parser.add_argument("--max-bad-frames", type=int, default=3)
    parser.add_argument(
        "--online-timeout",
        type=float,
        default=10.0,
        help=(
            "seconds to wait for selected CAN IDs before and after configuration; "
            "lower-board startup can take more than 6 seconds"
        ),
    )
    parser.add_argument(
        "--allow-shared-port",
        action="store_true",
        help="disable POSIX exclusive open; never use while another controller is active",
    )

    parser.add_argument("--trajectory", choices=("sine", "chirp"), default="sine")
    parser.add_argument(
        "--amplitude",
        nargs="+",
        type=float,
        default=[0.05],
        help="relative position amplitude in rad; one value or one per CAN ID",
    )
    parser.add_argument("--frequency", type=float, default=0.5, help="sine frequency in Hz")
    parser.add_argument("--start-frequency", type=float, default=0.1, help="chirp start Hz")
    parser.add_argument("--end-frequency", type=float, default=3.0, help="chirp end Hz")
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--ramp-duration", type=float, default=1.0)
    parser.add_argument(
        "--cycles",
        type=int,
        help=(
            "sine cycle count; when set, effective duration is cycles/frequency "
            "like sine_control_loop_rs06.py"
        ),
    )
    parser.add_argument(
        "--ramp-cycles",
        type=float,
        help=(
            "sine ramp length at each end in cycles; when set, effective "
            "ramp duration is ramp-cycles/frequency"
        ),
    )
    parser.add_argument("--pre-hold", type=float, default=2.0)
    parser.add_argument("--post-hold", type=float, default=2.0)
    parser.add_argument(
        "--command-rate",
        "--control-frequency",
        dest="command_rate",
        type=float,
        default=DEFAULT_CONTROL_FREQUENCY_HZ,
        help=(
            "host loop rate in Hz; default "
            f"{DEFAULT_CONTROL_FREQUENCY_HZ:g} (--control-frequency is a compatibility alias)"
        ),
    )

    parser.add_argument(
        "--kp",
        nargs="+",
        type=float,
        help="RS06 position KP; required for --execute; one value or one per CAN ID",
    )
    parser.add_argument(
        "--kd",
        nargs="+",
        type=float,
        help="RS06 position KD; required for --execute; one value or one per CAN ID",
    )
    parser.add_argument(
        "--config-delay",
        type=float,
        default=1.0,
        help="delay between the five firmware configuration packets",
    )
    parser.add_argument(
        "--command-echo-timeout",
        type=float,
        default=3.0,
        help="time allowed for selected motors to echo the initial target",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/motor_identification/rs06_trajectory.csv"),
    )
    parser.add_argument(
        "--record-all-online",
        action="store_true",
        help="also record unselected slots whose reported ID matches the fixed slot",
    )
    parser.add_argument("--plot", action="store_true", help="show plots after COM closes")
    parser.add_argument("--save-plot", type=Path, help="save plots to a PNG/PDF/SVG file")
    parser.add_argument(
        "--plot-csv",
        type=Path,
        help="plot an existing CSV without opening the serial port",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="open hardware, initialize motors, send commands, and create output files",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.list_motors:
        return
    if args.plot_csv is not None:
        if args.execute:
            raise ValueError("--plot-csv cannot be combined with --execute")
        if not args.plot and args.save_plot is None:
            raise ValueError("--plot-csv requires --plot and/or --save-plot")
        return
    if not args.motor_ids:
        raise ValueError("--motor-ids is required unless --list-motors is used")
    if len(set(args.motor_ids)) != len(args.motor_ids):
        raise ValueError("--motor-ids contains duplicates")
    invalid_ids = [value for value in args.motor_ids if value not in CAN_ID_TO_SLOT]
    if invalid_ids:
        raise ValueError(
            "Current firmware only supports CAN IDs 1..16; invalid: "
            + ", ".join(str(value) for value in invalid_ids)
        )

    if args.trajectory == "sine" and args.frequency <= 0:
        raise ValueError("--frequency must be positive")
    if args.trajectory == "chirp" and (
        args.start_frequency <= 0 or args.end_frequency <= 0
    ):
        raise ValueError("chirp frequencies must be positive")
    if args.cycles is not None or args.ramp_cycles is not None:
        if args.trajectory != "sine":
            raise ValueError("--cycles and --ramp-cycles are only valid for sine")
    if args.cycles is not None:
        if args.cycles <= 0:
            raise ValueError("--cycles must be a positive integer")
        args.duration = args.cycles / args.frequency
    if args.ramp_cycles is not None:
        if args.ramp_cycles < 0:
            raise ValueError("--ramp-cycles must not be negative")
        args.ramp_duration = args.ramp_cycles / args.frequency

    positive_options = {
        "--baudrate": args.baudrate,
        "--serial-timeout": args.serial_timeout,
        "--frame-timeout": args.frame_timeout,
        "--max-bad-frames": args.max_bad_frames,
        "--online-timeout": args.online_timeout,
        "--duration": args.duration,
        "--command-rate": args.command_rate,
        "--command-echo-timeout": args.command_echo_timeout,
    }
    for name, value in positive_options.items():
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    for name, value in {
        "--ramp-duration": args.ramp_duration,
        "--pre-hold": args.pre_hold,
        "--post-hold": args.post_hold,
        "--config-delay": args.config_delay,
    }.items():
        if value < 0:
            raise ValueError(f"{name} must not be negative")
    if args.ramp_duration * 2.0 > args.duration:
        raise ValueError("--ramp-duration must not exceed half of --duration")
    args.amplitude_values = [
        float(value)
        for value in expand_values(
            args.amplitude, len(args.motor_ids), "--amplitude", required=True
        )
    ]
    args.kp_values = expand_values(
        args.kp, len(args.motor_ids), "--kp", required=args.execute
    )
    args.kd_values = expand_values(
        args.kd, len(args.motor_ids), "--kd", required=args.execute
    )

    kp_min, kp_max = RS06_LIMITS["kp"]
    kd_min, kd_max = RS06_LIMITS["kd"]
    for can_id, kp in zip(args.motor_ids, args.kp_values):
        if kp is not None and not kp_min <= kp <= kp_max:
            raise ValueError(f"CAN ID {can_id} KP must be within {kp_min}..{kp_max}")
    for can_id, kd in zip(args.motor_ids, args.kd_values):
        if kd is not None and not kd_min <= kd <= kd_max:
            raise ValueError(f"CAN ID {can_id} KD must be within {kd_min}..{kd_max}")


def print_plan(args: argparse.Namespace) -> None:
    print(f"Protocol:     {PROTOCOL_NAME} ({PROTOCOL_VERSION})")
    print(f"Motor model: {MOTOR_MODEL}")
    print(f"Serial:      {args.port} @ {args.baudrate}")
    print(f"Online wait: {args.online_timeout:.3f}s before/after configuration")
    print(
        f"Trajectory:  {args.trajectory}, duration={args.duration:.3f}s, "
        f"rate={args.command_rate:.3f}Hz"
    )
    if args.trajectory == "sine":
        timing_source = "duration arguments"
        if args.cycles is not None or args.ramp_cycles is not None:
            timing_source = "cycle-compatible arguments"
        print(f"Frequency:   {args.frequency:.6g} Hz ({timing_source})")
        if args.cycles is not None:
            print(f"Cycles:      {args.cycles}")
        if args.ramp_cycles is not None:
            print(f"Ramp cycles: {args.ramp_cycles:.6g} at each end")
    else:
        print(
            f"Frequency:   {args.start_frequency:.6g} -> "
            f"{args.end_frequency:.6g} Hz"
        )
    print("Selected motors:")
    for index, can_id in enumerate(args.motor_ids):
        slot = CAN_ID_TO_SLOT[can_id]
        board, bus = CAN_ROUTE[can_id]
        kp = args.kp_values[index]
        kd = args.kd_values[index]
        kp_text = "required for --execute" if kp is None else f"{kp:g}"
        kd_text = "required for --execute" if kd is None else f"{kd:g}"
        print(
            f"  CAN ID {can_id:2d} -> slot {slot:2d}, {board}/{bus}, "
            f"amplitude={args.amplitude_values[index]:g} rad, "
            f"KP={kp_text}, KD={kd_text}"
        )
    print("Unselected slots: RS06 position mode, KP=0, KD=0, command=0")
    print("Host mechanical position limits: disabled")
    print(
        "RS06 wire encoding remains finite at "
        f"{RS06_LIMITS['position'][0]}..{RS06_LIMITS['position'][1]} rad."
    )
    print(f"CSV:          {args.output}")
    print(f"Metadata:     {metadata_path_for(args.output)}")


def _args_for_metadata(args: argparse.Namespace) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in vars(args).items():
        if isinstance(value, Path):
            result[key] = str(value)
        else:
            result[key] = value
    return result


def _write_metadata(path: Path, metadata: Dict[str, Any]) -> None:
    path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _send_hold(
    controller: ControlBox,
    selected_can_ids: Sequence[int],
    q_by_can_id: Dict[int, float],
    repeats: int = 3,
) -> None:
    positions = [0.0] * 16
    for can_id in selected_can_ids:
        if can_id in q_by_can_id:
            positions[CAN_ID_TO_SLOT[can_id]] = q_by_can_id[can_id]
    for _ in range(repeats):
        controller.send_positions(positions)
        time.sleep(0.02)


def run_experiment(args: argparse.Namespace) -> int:
    metadata_path = check_output_paths(args.output, args.overwrite)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    selected_ids = tuple(args.motor_ids)
    selected_set = set(selected_ids)
    kp_by_slot = [0.0] * 16
    kd_by_slot = [0.0] * 16
    amplitude_by_can_id: Dict[int, float] = {}
    for can_id, amplitude, kp, kd in zip(
        selected_ids, args.amplitude_values, args.kp_values, args.kd_values
    ):
        slot = CAN_ID_TO_SLOT[can_id]
        amplitude_by_can_id[can_id] = float(amplitude)
        kp_by_slot[slot] = float(kp)
        kd_by_slot[slot] = float(kd)

    started_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    metadata: Dict[str, Any] = {
        "protocol": {
            "name": PROTOCOL_NAME,
            "version": PROTOCOL_VERSION,
            "feedback_frame_bytes": FEEDBACK_FRAME_SIZE,
            "host_packet_bytes": 40,
            "slot_to_can_id": list(SLOT_TO_CAN_ID),
        },
        "motor_model": MOTOR_MODEL,
        "rs06_limits": {
            name: {"min": limits[0], "max": limits[1]}
            for name, limits in RS06_LIMITS.items()
        },
        "host_mechanical_position_limits_enabled": False,
        "unselected_policy": "RS06 position mode with KP=0, KD=0, command=0",
        "selected_motors": [
            {
                "can_id": can_id,
                "controller_slot": CAN_ID_TO_SLOT[can_id],
                "lower_board": CAN_ROUTE[can_id][0],
                "can_bus": CAN_ROUTE[can_id][1],
                "amplitude_rad": amplitude_by_can_id[can_id],
                "kp": kp_by_slot[CAN_ID_TO_SLOT[can_id]],
                "kd": kd_by_slot[CAN_ID_TO_SLOT[can_id]],
            }
            for can_id in selected_ids
        ],
        "arguments": _args_for_metadata(args),
        "started_utc": started_utc,
        "status": "running",
        "csv_path": str(args.output),
        "metadata_path": str(metadata_path),
    }

    controller: Optional[ControlBox] = None
    csv_file = None
    writer: Optional[csv.DictWriter] = None
    motion_armed = False
    start_q: Dict[int, float] = {}
    latest_q: Dict[int, float] = {}
    sample_count = 0
    csv_row_count = 0
    saturation_count = 0
    status = "error"
    error_text: Optional[str] = None
    exit_code = 1

    try:
        controller = ControlBox(
            port=args.port,
            baudrate=args.baudrate,
            serial_timeout_s=args.serial_timeout,
            allow_shared_port=args.allow_shared_port,
        )
        print(f"Opened {args.port}; checking selected CAN ID feedback...")
        controller.clear_input()
        wait_for_required_motors_online(
            controller,
            selected_ids,
            args.online_timeout,
            args.frame_timeout,
            "Pre-configuration",
        )
        print("Selected CAN IDs are present in their fixed feedback slots.")

        controller.configure_rs06_position_mode(
            kp_by_slot=kp_by_slot,
            kd_by_slot=kd_by_slot,
            delay_s=args.config_delay,
        )

        print("Reading post-configuration RS06 positions...")
        controller.clear_input()
        configured_frame = wait_for_required_motors_online(
            controller,
            selected_ids,
            args.online_timeout,
            args.frame_timeout,
            "Post-configuration",
        )
        for can_id in selected_ids:
            q = configured_frame.motors[CAN_ID_TO_SLOT[can_id]].q
            start_q[can_id] = q
            latest_q[can_id] = q
            print(f"  CAN ID {can_id}: start q = {q:.6f} rad")

        p_min, p_max = RS06_LIMITS["position"]
        for can_id in selected_ids:
            amplitude = abs(amplitude_by_can_id[can_id])
            if start_q[can_id] - amplitude < p_min or start_q[can_id] + amplitude > p_max:
                print(
                    f"WARNING: CAN ID {can_id} requested excursion can exceed the "
                    "RS06 wire range and will be saturated by 16-bit encoding.",
                    file=sys.stderr,
                )

        initial_positions = [0.0] * 16
        for can_id in selected_ids:
            initial_positions[CAN_ID_TO_SLOT[can_id]] = start_q[can_id]
        initial_encoding = controller.send_positions(initial_positions)
        controller.clear_input()
        initial_echo = wait_for_command_echo(
            controller,
            selected_ids,
            initial_encoding,
            args.command_echo_timeout,
            args.frame_timeout,
        )
        for can_id in selected_ids:
            latest_q[can_id] = initial_echo.motors[CAN_ID_TO_SLOT[can_id]].q
        motion_armed = True
        print("Initial hold command echoed by all selected motors.")

        csv_file = args.output.open("w", newline="", encoding="utf-8", buffering=1)
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()

        total_duration = args.pre_hold + args.duration + args.post_hold
        run_start = time.perf_counter()
        next_tick = run_start
        last_command_time: Optional[float] = None

        print(
            f"Starting acquisition for {total_duration:.3f}s "
            f"({args.pre_hold:.3f}s hold + {args.duration:.3f}s trajectory + "
            f"{args.post_hold:.3f}s hold)."
        )

        while True:
            now = time.perf_counter()
            if now < next_tick:
                time.sleep(next_tick - now)
            command_time = time.perf_counter()
            elapsed = command_time - run_start
            if elapsed >= total_duration:
                break

            lateness = max(0.0, command_time - next_tick)
            loop_dt = (
                0.0 if last_command_time is None else command_time - last_command_time
            )
            last_command_time = command_time

            if elapsed < args.pre_hold:
                phase = "pre_hold"
                trajectory_time = 0.0
            elif elapsed < args.pre_hold + args.duration:
                phase = "trajectory"
                trajectory_time = elapsed - args.pre_hold
            else:
                phase = "post_hold"
                trajectory_time = args.duration

            requested_positions = [0.0] * 16
            for can_id in selected_ids:
                q_command = start_q[can_id]
                if phase == "trajectory":
                    q_command += trajectory_value(
                        args,
                        trajectory_time,
                        amplitude_by_can_id[can_id],
                    )
                requested_positions[CAN_ID_TO_SLOT[can_id]] = q_command

            encoding = controller.send_positions(requested_positions)
            saturation_count += sum(
                1
                for can_id in selected_ids
                if encoding.encoded_positions[CAN_ID_TO_SLOT[can_id]].saturated
            )

            # Drop frames produced before this command. The control box streams
            # continuously, so the next complete frame is used as this sample.
            controller.clear_input()
            feedback = acquire_required_feedback(
                controller,
                selected_ids,
                args.frame_timeout,
                args.max_bad_frames,
                "Acquisition",
            )

            for can_id in selected_ids:
                latest_q[can_id] = feedback.motors[CAN_ID_TO_SLOT[can_id]].q

            if args.record_all_online:
                slots_to_record: Iterable[int] = (
                    slot
                    for slot, expected_id in enumerate(SLOT_TO_CAN_ID)
                    if feedback.motors[slot].reported_can_id == expected_id
                )
            else:
                slots_to_record = (CAN_ID_TO_SLOT[can_id] for can_id in selected_ids)

            for slot in slots_to_record:
                record = feedback.motors[slot]
                can_id = SLOT_TO_CAN_ID[slot]
                encoded_command = encoding.encoded_positions[slot]
                selected = can_id in selected_set
                row = {
                    "sample_index": sample_count,
                    "host_time_utc": feedback.received_utc,
                    "elapsed_s": f"{elapsed:.9f}",
                    "feedback_elapsed_s": (
                        f"{feedback.received_monotonic - run_start:.9f}"
                    ),
                    "phase": phase,
                    "trajectory_time_s": f"{trajectory_time:.9f}",
                    "loop_dt_s": f"{loop_dt:.9f}",
                    "schedule_lateness_s": f"{lateness:.9f}",
                    "can_id": can_id,
                    "controller_slot": slot,
                    "selected": int(selected),
                    "motor_model": MOTOR_MODEL,
                    "kp": f"{kp_by_slot[slot]:.9g}",
                    "kd": f"{kd_by_slot[slot]:.9g}",
                    "q_start_rad": (
                        f"{start_q[can_id]:.9f}" if selected else ""
                    ),
                    "q_command_requested_rad": f"{encoded_command.requested:.9f}",
                    "q_command_encoded_rad": f"{encoded_command.decoded:.9f}",
                    "q_command_saturated": int(encoded_command.saturated),
                    "q_feedback_rad": f"{record.q:.9f}",
                    "qdot_feedback_rad_s": f"{record.qdot:.9f}",
                    "torque_feedback_nm": f"{record.torque:.9f}",
                    "target_feedback_rad": f"{record.target:.9f}",
                    "target_matches_current_command": int(
                        record.raw_target == encoded_command.raw
                    ),
                    "tracking_error_rad": (
                        f"{encoded_command.decoded - record.q:.9f}"
                    ),
                    "raw_q_u16": record.raw_q,
                    "raw_qdot_u16": record.raw_qdot,
                    "raw_torque_u16": record.raw_torque,
                    "raw_target_u16": record.raw_target,
                    "raw_record_hex": record.raw_record.hex(" "),
                }
                writer.writerow(row)
                csv_row_count += 1

            sample_count += 1
            next_tick = max(
                next_tick + 1.0 / args.command_rate,
                time.perf_counter(),
            )

        _send_hold(controller, selected_ids, start_q)
        status = "complete"
        exit_code = 0
        print("Trajectory complete; start-position hold command sent.")

    except KeyboardInterrupt:
        status = "interrupted"
        exit_code = 130
        error_text = "KeyboardInterrupt"
        print("\nInterrupted by user.", file=sys.stderr)
    except Exception as exc:
        status = "error"
        exit_code = 1
        error_text = f"{type(exc).__name__}: {exc}"
        print(f"ERROR: {error_text}", file=sys.stderr)
    finally:
        if controller is not None and motion_armed and status != "complete":
            try:
                hold_source = latest_q if latest_q else start_q
                _send_hold(controller, selected_ids, hold_source)
                print(
                    "Latest-feedback hold command sent after interruption/error.",
                    file=sys.stderr,
                )
            except Exception as hold_exc:
                print(f"WARNING: failed to send final hold: {hold_exc}", file=sys.stderr)

        if csv_file is not None:
            csv_file.close()

        if controller is not None:
            try:
                metadata["serial_statistics"] = {
                    "valid_frames_read": controller.frames_read,
                    "invalid_163_byte_candidates": controller.invalid_candidates,
                }
                controller.close()
            except Exception as close_exc:
                print(f"WARNING: failed to close serial port: {close_exc}", file=sys.stderr)

        metadata.update(
            {
                "status": status,
                "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "error": error_text,
                "start_q_rad": start_q,
                "feedback_samples": sample_count,
                "csv_rows": csv_row_count,
                "position_command_saturations": saturation_count,
            }
        )
        try:
            _write_metadata(metadata_path, metadata)
        except Exception as metadata_exc:
            print(f"WARNING: failed to write metadata: {metadata_exc}", file=sys.stderr)
            if exit_code == 0:
                exit_code = 1

        print(f"CSV:      {args.output}")
        print(f"Metadata: {metadata_path}")
        if motion_armed:
            print(
                "WARNING: closing the COM port does not disable motor torque; "
                "use the hardware stop/power control."
            )

    return exit_code


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_args(args)
        if args.list_motors:
            print_motor_table()
            return 0
        if args.plot_csv is not None:
            try:
                plot_experiment_csv(
                    args.plot_csv,
                    show=args.plot,
                    output=args.save_plot,
                )
            except Exception as exc:
                print(
                    f"ERROR: plotting failed: {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
                return 1
            return 0

        print_plan(args)
        if not args.execute:
            print()
            print("DRY RUN ONLY: no serial port was opened and no files were created.")
            print("Add explicit --kp, --kd, and --execute only after hardware checks.")
            return 0

        exit_code = run_experiment(args)
        if exit_code == 0 and (args.plot or args.save_plot is not None):
            try:
                plot_experiment_csv(
                    args.output,
                    show=args.plot,
                    output=args.save_plot,
                )
            except Exception as exc:
                print(
                    f"ERROR: experiment completed, but plotting failed: "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
                return 1
        return exit_code
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
