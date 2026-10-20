#!/usr/bin/env python3
"""TA-only XC330 connection inspection and identity, baud, and operating-mode configuration tool."""

from __future__ import annotations

import argparse
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hardware_runtime"))
from xc330_io import DynamixelBus, EXPECTED_MODEL_NUMBER, snapshot  # noqa: E402

BAUD_RATE_CODES = {9600: 0, 57600: 1, 115200: 2, 1_000_000: 3, 2_000_000: 4, 3_000_000: 5, 4_000_000: 6, 4_500_000: 7}
CONFIRMATION = "APPLY_XC330_CONFIG"
OPERATING_MODES = {0: "Current Control", 1: "Velocity Control", 3: "Position Control", 4: "Extended Position", 5: "Current-Based Position", 16: "PWM Control"}


@dataclass(frozen=True)
class SetupPlan:
    port: str
    source_id: int
    source_baud: int
    target_id: int
    target_baud: int
    target_mode: int


def require_supported_baud(value: int) -> int:
    if value not in BAUD_RATE_CODES:
        options = ", ".join(str(rate) for rate in BAUD_RATE_CODES)
        raise ValueError(f"Unsupported XC330 baud rate {value}. Choose one of: {options}")
    return value


def require_motor_id(value: int, label: str) -> int:
    if not 0 <= value <= 252:
        raise ValueError(f"{label} must be between 0 and 252; 253 and 254 are reserved.")
    return value


def require_operating_mode(value: int) -> int:
    if value not in OPERATING_MODES:
        choices = ", ".join(str(mode) for mode in OPERATING_MODES)
        raise ValueError(f"Unsupported XC330 operating mode {value}. Choose one of: {choices}")
    return value


def scan_port(port: str) -> list[tuple[int, int, int, int]]:
    """Broadcast-ping each documented XC330 baud rate without writing a register."""
    matches: list[tuple[int, int, int, int]] = []
    for baud in BAUD_RATE_CODES:
        bus = None
        try:
            bus = DynamixelBus(port, baud)
            for device_id, details in bus.discover().items():
                matches.append((baud, device_id, details["model_number"], details["firmware_version"]))
        except RuntimeError:
            pass
        finally:
            if bus is not None:
                bus.close()
    return matches


def auto_detect_plan(values: dict[str, Any], args: argparse.Namespace) -> SetupPlan:
    port = str(args.port or values["serial_port"])
    matches = [item for item in scan_port(port) if item[2] == EXPECTED_MODEL_NUMBER]
    if len(matches) != 1:
        summary = ", ".join(f"ID {device_id} at {baud:,} bps (model {model})" for baud, device_id, model, _ in matches) or "none"
        raise RuntimeError(f"Automatic setup needs exactly one XC330 on the bus; found: {summary}. Disconnect other motors or use explicit connection values.")
    baud, device_id, _, _ = matches[0]
    target_id = require_motor_id(args.new_id if args.new_id is not None else device_id, "Desired ID")
    target_baud = require_supported_baud(args.new_baud if args.new_baud is not None else baud)
    target_mode = require_operating_mode(args.operating_mode if args.operating_mode is not None else int(values["operating_mode"]))
    return SetupPlan(port, device_id, baud, target_id, target_baud, target_mode)


def plan_from_values(values: dict[str, Any], args: argparse.Namespace) -> SetupPlan:
    source_id = require_motor_id(args.current_id if args.current_id is not None else int(values["motor_id"]), "Current ID")
    source_baud = require_supported_baud(args.current_baud if args.current_baud is not None else int(values["baud_rate_bps"]))
    target_id = require_motor_id(args.new_id if args.new_id is not None else source_id, "Desired ID")
    target_baud = require_supported_baud(args.new_baud if args.new_baud is not None else source_baud)
    target_mode = require_operating_mode(args.operating_mode if args.operating_mode is not None else int(values["operating_mode"]))
    return SetupPlan(str(args.port or values["serial_port"]), source_id, source_baud, target_id, target_baud, target_mode)


def motor_info(state: dict[str, int], plan: SetupPlan, discovered: dict[int, dict[str, int]] | None = None) -> str:
    baud_register = state.get("baud_rate")
    decoded_baud = next((rate for rate, code in BAUD_RATE_CODES.items() if code == baud_register), None)
    lines = [
        "╔════════════════════════ XC330-M288-T STATUS ════════════════════════╗",
        f"║ Model             {state.get('model_number', '?'):>6}  (expected {EXPECTED_MODEL_NUMBER})                    ║",
        f"║ Firmware          {state.get('firmware_version', '?'):>6}                                      ║",
        f"║ Connected ID      {state.get('id', '?'):>6}                                      ║",
        f"║ Baud register     {baud_register!s:>6}  ({decoded_baud if decoded_baud else 'unknown'} bps)                 ║",
        f"║ Torque enabled    {'YES' if state.get('torque_enable') else 'no ':>6}                                      ║",
        f"║ Supply / temp     {state.get('input_voltage', 0) / 10:>5.1f} V / {state.get('temperature', '?')} °C                         ║",
        f"║ Operating mode    {state.get('operating_mode', '?'):>6}  (V5 uses 5: current-based position)   ║",
        "╠══════════════════════════════════════════════════════════════════════╣",
        f"║ Host port         {plan.port[:48]:<48} ║",
        f"║ Host baud         {plan.source_baud:>9} bps                               ║",
        f"║ Selected target   ID {plan.target_id:<3}   {plan.target_baud:>9} bps                       ║",
        f"║ Desired mode      {plan.target_mode:>6}  ({OPERATING_MODES[plan.target_mode]:<25}) ║",
        "╚══════════════════════════════════════════════════════════════════════╝",
        "The XC330 is a Protocol 2.0, coreless-DC smart servo. ID selects one motor on",
        "the shared bus; baud rate is the communication speed used by both host and motor.",
    ]
    if discovered is not None:
        lines.append("Broadcast-ping IDs at this host speed: " + (", ".join(map(str, sorted(discovered))) or "none"))
    return "\n".join(lines)


def inspect(plan: SetupPlan, *, discover: bool = False) -> tuple[dict[str, int], dict[int, dict[str, int]] | None]:
    bus = DynamixelBus(plan.port, plan.source_baud)
    try:
        found = bus.discover() if discover else None
        state = snapshot(bus, plan.source_id)
        if state["model_number"] != EXPECTED_MODEL_NUMBER:
            raise RuntimeError(f"ID {plan.source_id} is model {state['model_number']}, not XC330-M288-T ({EXPECTED_MODEL_NUMBER}).")
        return state, found
    finally:
        bus.close()


def apply(plan: SetupPlan) -> dict[str, int]:
    state, discovered = inspect(plan, discover=True)
    if discovered is not None and plan.target_id != plan.source_id and plan.target_id in discovered:
        raise RuntimeError(f"Cannot assign ID {plan.target_id}: it already responded on this bus. Disconnect it or choose a unique ID.")
    bus = DynamixelBus(plan.port, plan.source_baud)
    active_id = plan.source_id
    try:
        before = snapshot(bus, active_id)
        if before["model_number"] != EXPECTED_MODEL_NUMBER:
            raise RuntimeError("Connected device changed during setup; stopping without a write.")
        bus.torque_disable(active_id)
        if before["operating_mode"] != plan.target_mode:
            bus.write(active_id, "operating_mode", plan.target_mode)
        if plan.target_id != active_id:
            bus.write(active_id, "id", plan.target_id)
            active_id = plan.target_id
        if plan.target_baud != plan.source_baud:
            bus.write(active_id, "baud_rate", BAUD_RATE_CODES[plan.target_baud])
    finally:
        bus.close()
    time.sleep(0.05)
    verified, _ = inspect(SetupPlan(plan.port, plan.target_id, plan.target_baud, plan.target_id, plan.target_baud, plan.target_mode))
    if verified["id"] != plan.target_id or verified["baud_rate"] != BAUD_RATE_CODES[plan.target_baud] or verified["operating_mode"] != plan.target_mode:
        raise RuntimeError(f"Readback did not match requested configuration: {verified}")
    return verified


def launch_visualizer(default_plan: SetupPlan) -> None:
    try:
        from PyQt6 import QtWidgets
    except ImportError as exc:
        raise RuntimeError("The desktop visualizer needs PyQt6. Run `uv sync` from this folder, then retry.") from exc

    class SetupWindow(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.detected_plan: SetupPlan | None = None
            self.setWindowTitle("Class 03 — XC330 connection setup")
            self.resize(760, 610)
            layout = QtWidgets.QVBoxLayout(self)
            title = QtWidgets.QLabel("XC330-M288-T  •  Connection & identity setup")
            title.setStyleSheet("font-size: 22px; font-weight: 700; color: #13315c;")
            layout.addWidget(title)
            intro = QtWidgets.QLabel("Click Scan first. It finds the connected XC330 automatically; then choose the desired ID and baud. Changing settings writes non-volatile values, disables torque, and verifies by reconnecting. No motion command is sent.")
            intro.setWordWrap(True)
            layout.addWidget(intro)
            form = QtWidgets.QFormLayout()
            self.port = QtWidgets.QLineEdit(default_plan.port)
            self.current_id = QtWidgets.QSpinBox(); self.current_id.setRange(0, 252); self.current_id.setValue(default_plan.source_id); self.current_id.setEnabled(False)
            self.target_id = QtWidgets.QSpinBox(); self.target_id.setRange(0, 252); self.target_id.setValue(default_plan.target_id)
            self.current_baud = self.baud_box(default_plan.source_baud); self.current_baud.setEnabled(False)
            self.target_baud = self.baud_box(default_plan.target_baud)
            self.target_mode = self.mode_box(default_plan.target_mode)
            form.addRow("Serial port", self.port)
            form.addRow("Detected motor ID (Scan fills this)", self.current_id)
            form.addRow("Detected motor baud (Scan fills this)", self.current_baud)
            form.addRow("Desired motor ID", self.target_id)
            form.addRow("Desired motor baud", self.target_baud)
            form.addRow("Desired operating mode", self.target_mode)
            layout.addLayout(form)
            buttons = QtWidgets.QHBoxLayout()
            scan_button = QtWidgets.QPushButton("Scan connected XC330 (read only)")
            self.inspect_button = QtWidgets.QPushButton("Inspect detected motor (read only)"); self.inspect_button.setEnabled(False)
            self.apply_button = QtWidgets.QPushButton("Apply desired ID / baud"); self.apply_button.setEnabled(False)
            self.apply_button.setStyleSheet("font-weight: 700; background: #f4a261; padding: 8px;")
            buttons.addWidget(scan_button); buttons.addWidget(self.inspect_button); buttons.addWidget(self.apply_button); layout.addLayout(buttons)
            self.status = QtWidgets.QPlainTextEdit(); self.status.setReadOnly(True)
            self.status.setStyleSheet("font-family: monospace; background: #102033; color: #d9edf7;")
            self.status.setPlainText("Click Scan connected XC330 before Inspect or Apply.\n\nXC330 quick facts\n• Model number 1240; Protocol 2.0; coreless DC servo\n• V5 teaching default: ID 5, 4,000,000 bps, mode 5\n• Recommended supply: verify 4.5–5.5 V before the motion lesson.")
            layout.addWidget(self.status)
            self.port.textChanged.connect(self.clear_detection)
            scan_button.clicked.connect(self.scan_clicked)
            self.inspect_button.clicked.connect(self.inspect_clicked)
            self.apply_button.clicked.connect(self.apply_clicked)

        @staticmethod
        def baud_box(value: int) -> QtWidgets.QComboBox:
            box = QtWidgets.QComboBox()
            for rate in BAUD_RATE_CODES:
                box.addItem(f"{rate:,} bps", rate)
            box.setCurrentIndex(list(BAUD_RATE_CODES).index(value))
            return box

        
        @staticmethod
        def mode_box(value: int) -> QtWidgets.QComboBox:
            box = QtWidgets.QComboBox()
            for mode, label in OPERATING_MODES.items():
                box.addItem(f"{mode}: {label}", mode)
            box.setCurrentIndex(list(OPERATING_MODES).index(value))
            return box

        def clear_detection(self) -> None:
            self.detected_plan = None
            self.inspect_button.setEnabled(False)
            self.apply_button.setEnabled(False)

        def plan(self) -> SetupPlan:
            if self.detected_plan is None:
                raise RuntimeError("Click Scan connected XC330 first; no motor has been detected yet.")
            return SetupPlan(self.detected_plan.port, self.detected_plan.source_id, self.detected_plan.source_baud, self.target_id.value(), int(self.target_baud.currentData()), int(self.target_mode.currentData()))

        def scan_clicked(self) -> None:
            try:
                matches = scan_port(self.port.text().strip())
                found = [item for item in matches if item[2] == EXPECTED_MODEL_NUMBER]
                text = "\n".join(f"ID {device_id} at {baud:,} bps · model {model} · firmware {firmware}" for baud, device_id, model, firmware in matches) or "No Protocol 2.0 motor replied at the XC330 supported baud rates."
                if len(found) == 1:
                    baud, device_id, _, _ = found[0]
                    self.current_id.setValue(device_id)
                    self.current_baud.setCurrentIndex(list(BAUD_RATE_CODES).index(baud))
                    self.detected_plan = SetupPlan(self.port.text().strip(), device_id, baud, device_id, baud, int(self.target_mode.currentData()))
                    self.inspect_button.setEnabled(True)
                    self.apply_button.setEnabled(True)
                    text = "Detected one XC330. You can now inspect it or choose desired values.\n\n" + text
                elif len(found) > 1:
                    self.clear_detection()
                    text = "More than one XC330 was found. Disconnect extras before changing an ID.\n\n" + text
                else:
                    self.clear_detection()
                self.status.setPlainText(text)
            except Exception as exc:
                self.status.setPlainText(f"Scan failed\n{type(exc).__name__}: {exc}")

        def inspect_clicked(self) -> None:
            try:
                state, found = inspect(self.plan(), discover=True)
                self.status.setPlainText(motor_info(state, self.plan(), found))
            except Exception as exc:
                self.status.setPlainText(f"Inspection failed\n{type(exc).__name__}: {exc}")

        def apply_clicked(self) -> None:
            plan = self.plan()
            answer = QtWidgets.QMessageBox.warning(self, "Confirm non-volatile change", f"Change the detected XC330 to ID {plan.target_id} / {plan.target_baud:,} bps in mode {plan.target_mode} ({OPERATING_MODES[plan.target_mode]})?\n\nTorque will be disabled. No motion is commanded.", QtWidgets.QMessageBox.StandardButton.Cancel | QtWidgets.QMessageBox.StandardButton.Apply, QtWidgets.QMessageBox.StandardButton.Cancel)
            if answer != QtWidgets.QMessageBox.StandardButton.Apply:
                return
            try:
                state = apply(plan)
                self.current_id.setValue(plan.target_id); self.current_baud.setCurrentIndex(list(BAUD_RATE_CODES).index(plan.target_baud))
                self.detected_plan = SetupPlan(plan.port, plan.target_id, plan.target_baud, plan.target_id, plan.target_baud, plan.target_mode)
                self.status.setPlainText("Verified configuration change\n\n" + motor_info(state, SetupPlan(plan.port, plan.target_id, plan.target_baud, plan.target_id, plan.target_baud, plan.target_mode)))
            except Exception as exc:
                self.status.setPlainText(f"Configuration stopped\n{type(exc).__name__}: {exc}")

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = SetupWindow(); window.show()
    application.exec()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "hardware.example.toml")
    parser.add_argument("--port")
    parser.add_argument("--current-id", type=int)
    parser.add_argument("--current-baud", type=int)
    parser.add_argument("--id", "--new-id", dest="new_id", type=int, help="desired motor ID")
    parser.add_argument("--baud", "--new-baud", dest="new_baud", type=int, help="desired motor baud rate in bps")
    parser.add_argument("--operating-mode", "--mode", dest="operating_mode", type=int, choices=tuple(OPERATING_MODES), help="desired XC330 operating mode; V5 collector requires 5")
    parser.add_argument("--scan", action="store_true", help="read-only scan across all XC330-supported baud rates")
    parser.add_argument("--auto-detect", action="store_true", help="find the one connected XC330, then inspect or apply the desired values")
    parser.add_argument("--inspect", action="store_true", help="open the serial bus and read the selected XC330")
    parser.add_argument("--visualizer", action="store_true", help="open the desktop setup visualizer")
    parser.add_argument("--apply", action="store_true", help="write selected ID and baud after safety checks")
    parser.add_argument("--confirm", help=f"required exact phrase: {CONFIRMATION}")
    args = parser.parse_args()
    values = tomllib.loads(args.config.read_text(encoding="utf-8"))
    try:
        plan = auto_detect_plan(values, args) if args.auto_detect else plan_from_values(values, args)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    if args.scan:
        matches = scan_port(str(args.port or values["serial_port"]))
        print("Read-only XC330 baud scan:")
        print("\n".join(f"ID {device_id} at {baud:,} bps · model {model} · firmware {firmware}" for baud, device_id, model, firmware in matches) or "No Protocol 2.0 motor replied.")
        return
    if args.visualizer:
        launch_visualizer(plan)
        return
    if args.apply:
        if args.confirm != CONFIRMATION:
            parser.error(f"--apply requires --confirm {CONFIRMATION}")
        print("Applying non-volatile XC330 configuration. Torque will be disabled; no motion is commanded.")
        print(motor_info(apply(plan), SetupPlan(plan.port, plan.target_id, plan.target_baud, plan.target_id, plan.target_baud, plan.target_mode)))
    elif args.inspect:
        state, found = inspect(plan, discover=True)
        print(motor_info(state, plan, found))
    else:
        print("Dry configuration preview; no motor settings were changed.\n")
        print(motor_info({}, plan))
        print("Use --inspect for a read-only check, --visualizer for the desktop interface, or --apply with the required confirmation phrase.")


if __name__ == "__main__":
    main()
