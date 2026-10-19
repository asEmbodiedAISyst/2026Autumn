"""Small, V5-local XC330-M288-T Protocol 2.0 I/O layer."""

from __future__ import annotations

import fcntl
import time
import termios
from dataclasses import dataclass
from typing import Any


PROTOCOL_VERSION = 2.0
EXPECTED_MODEL_NUMBER = 1240

# XC330-M288-T control table: name -> (address, byte width).
REGISTERS: dict[str, tuple[int, int]] = {
    "model_number": (0, 2),
    "firmware_version": (6, 1),
    "id": (7, 1),
    "baud_rate": (8, 1),
    "return_delay_time": (9, 1),
    "drive_mode": (10, 1),
    "operating_mode": (11, 1),
    "secondary_id": (12, 1),
    "homing_offset": (20, 4),
    "temperature_limit": (31, 1),
    "max_voltage_limit": (32, 2),
    "min_voltage_limit": (34, 2),
    "pwm_limit": (36, 2),
    "current_limit": (38, 2),
    "velocity_limit": (44, 4),
    "max_position_limit": (48, 4),
    "min_position_limit": (52, 4),
    "startup_configuration": (60, 1),
    "pwm_slope": (62, 1),
    "shutdown": (63, 1),
    "torque_enable": (64, 1),
    "status_return_level": (68, 1),
    "hardware_error_status": (70, 1),
    "velocity_i_gain": (76, 2),
    "velocity_p_gain": (78, 2),
    "position_d_gain": (80, 2),
    "position_i_gain": (82, 2),
    "position_p_gain": (84, 2),
    "feedforward_2nd_gain": (88, 2),
    "feedforward_1st_gain": (90, 2),
    "bus_watchdog": (98, 1),
    "goal_pwm": (100, 2),
    "goal_current": (102, 2),
    "goal_velocity": (104, 4),
    "profile_acceleration": (108, 4),
    "profile_velocity": (112, 4),
    "goal_position": (116, 4),
    "realtime_tick": (120, 2),
    "moving": (122, 1),
    "moving_status": (123, 1),
    "present_pwm": (124, 2),
    "present_current": (126, 2),
    "present_velocity": (128, 4),
    "present_position": (132, 4),
    "velocity_trajectory": (136, 4),
    "position_trajectory": (140, 4),
    "input_voltage": (144, 2),
    "temperature": (146, 1),
}


def signed(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return value - (1 << bits) if value & sign else value


class DynamixelBus:
    def __init__(self, port_name: str, baud_rate_bps: int) -> None:
        try:
            import dynamixel_sdk
        except ImportError as exc:  # pragma: no cover - environment error
            raise RuntimeError("dynamixel-sdk is not installed in this Python environment") from exc
        self.sdk = dynamixel_sdk
        self.port_name = port_name
        self.port = dynamixel_sdk.PortHandler(port_name)
        self.packet = dynamixel_sdk.PacketHandler(PROTOCOL_VERSION)
        if not self.port.openPort():
            raise RuntimeError(f"could not open serial port {port_name}")
        try:
            fcntl.ioctl(self.port.ser.fileno(), termios.TIOCEXCL)
            if not self.port.setBaudRate(int(baud_rate_bps)):
                raise RuntimeError(f"could not set {baud_rate_bps} bps on {port_name}")
        except BaseException:
            self.port.closePort()
            raise

    def close(self) -> None:
        self.port.closePort()

    def _recover_port_state(self) -> None:
        self.port.is_using = False
        try:
            self.port.clearPort()
        finally:
            self.port.is_using = False

    def read(self, device_id: int, name: str, attempts: int = 3) -> int:
        address, size = REGISTERS[name]
        method = {
            1: self.packet.read1ByteTxRx,
            2: self.packet.read2ByteTxRx,
            4: self.packet.read4ByteTxRx,
        }[size]
        errors: list[str] = []
        for attempt in range(1, attempts + 1):
            value, communication, device_error = method(self.port, device_id, address)
            if communication == self.sdk.COMM_SUCCESS and not device_error:
                return int(value)
            errors.append(
                f"attempt {attempt}: {self.packet.getTxRxResult(communication)}; "
                f"device_error={device_error}"
            )
            self._recover_port_state()
            time.sleep(0.002)
        raise RuntimeError(f"read {name} from ID {device_id} failed: {' | '.join(errors)}")

    def write(self, device_id: int, name: str, value: int, attempts: int = 3) -> None:
        address, size = REGISTERS[name]
        method = {
            1: self.packet.write1ByteTxRx,
            2: self.packet.write2ByteTxRx,
            4: self.packet.write4ByteTxRx,
        }[size]
        errors: list[str] = []
        for attempt in range(1, attempts + 1):
            communication, device_error = method(
                self.port, device_id, address, int(value)
            )
            if communication == self.sdk.COMM_SUCCESS and not device_error:
                return
            errors.append(
                f"attempt {attempt}: {self.packet.getTxRxResult(communication)}; "
                f"device_error={device_error}"
            )
            self._recover_port_state()
            time.sleep(0.002)
        raise RuntimeError(
            f"write {name}={value} to ID {device_id} failed: {' | '.join(errors)}"
        )

    def discover(self) -> dict[int, dict[str, int]]:
        values, communication = self.packet.broadcastPing(self.port)
        if communication != self.sdk.COMM_SUCCESS:
            detail = self.packet.getTxRxResult(communication)
            raise RuntimeError(f"broadcast ping failed: {detail}")
        return {
            int(device_id): {
                "model_number": int(details[0]),
                "firmware_version": int(details[1]),
            }
            for device_id, details in values.items()
        }

    def torque_disable(self, device_id: int) -> None:
        self._recover_port_state()
        self.write(device_id, "torque_enable", 0)
        if self.read(device_id, "torque_enable") != 0:
            raise RuntimeError(f"terminal torque-disable readback failed for ID {device_id}")


@dataclass
class BulkTelemetryReader:
    bus: DynamixelBus
    device_id: int

    START_ADDRESS = 98
    LENGTH = 49

    def __post_init__(self) -> None:
        self.group = self.bus.sdk.GroupBulkRead(self.bus.port, self.bus.packet)
        if not self.group.addParam(self.device_id, self.START_ADDRESS, self.LENGTH):
            raise RuntimeError("could not configure XC330 bulk telemetry reader")
        self.poll_index = 0
        self.hardware_error = self.bus.read(self.device_id, "hardware_error_status")
        self.torque_enable = self.bus.read(self.device_id, "torque_enable")
        self.operating_mode = self.bus.read(self.device_id, "operating_mode")

    def close(self) -> None:
        self.group.clearParam()

    def _value(self, address: int, size: int) -> int:
        if not self.group.isAvailable(self.device_id, address, size):
            raise RuntimeError(f"bulk telemetry field {address}/{size} unavailable")
        return int(self.group.getData(self.device_id, address, size))

    def read(self) -> dict[str, Any]:
        communication = self.group.txRxPacket()
        if communication != self.bus.sdk.COMM_SUCCESS:
            detail = self.bus.packet.getTxRxResult(communication)
            raise RuntimeError(f"bulk telemetry transaction failed: {detail}")
        if self.poll_index % 20 == 0:
            self.hardware_error = self.bus.read(
                self.device_id, "hardware_error_status"
            )
            self.torque_enable = self.bus.read(self.device_id, "torque_enable")
            self.operating_mode = self.bus.read(self.device_id, "operating_mode")
        self.poll_index += 1
        return {
            "torque_enable": self.torque_enable,
            "operating_mode": self.operating_mode,
            "bus_watchdog": self._value(98, 1),
            "goal_pwm": self._value(100, 2),
            "goal_current": self._value(102, 2),
            "goal_velocity": self._value(104, 4),
            "profile_acceleration": self._value(108, 4),
            "profile_velocity": self._value(112, 4),
            "goal_position": self._value(116, 4),
            "realtime_tick": self._value(120, 2),
            "moving": self._value(122, 1),
            "moving_status": self._value(123, 1),
            "present_pwm": self._value(124, 2),
            "present_current": self._value(126, 2),
            "present_velocity": self._value(128, 4),
            "present_position": self._value(132, 4),
            "velocity_trajectory": self._value(136, 4),
            "position_trajectory": self._value(140, 4),
            "input_voltage": self._value(144, 2),
            "temperature": self._value(146, 1),
            "hardware_error_status": self.hardware_error,
        }


SNAPSHOT_FIELDS = (
    "model_number",
    "firmware_version",
    "id",
    "baud_rate",
    "return_delay_time",
    "drive_mode",
    "operating_mode",
    "secondary_id",
    "homing_offset",
    "temperature_limit",
    "max_voltage_limit",
    "min_voltage_limit",
    "pwm_limit",
    "current_limit",
    "velocity_limit",
    "max_position_limit",
    "min_position_limit",
    "startup_configuration",
    "pwm_slope",
    "shutdown",
    "torque_enable",
    "status_return_level",
    "hardware_error_status",
    "velocity_i_gain",
    "velocity_p_gain",
    "position_d_gain",
    "position_i_gain",
    "position_p_gain",
    "feedforward_2nd_gain",
    "feedforward_1st_gain",
    "bus_watchdog",
    "goal_pwm",
    "goal_current",
    "profile_acceleration",
    "profile_velocity",
    "goal_position",
    "present_position",
    "input_voltage",
    "temperature",
)


def snapshot(bus: DynamixelBus, device_id: int) -> dict[str, int]:
    return {name: bus.read(device_id, name) for name in SNAPSHOT_FIELDS}
