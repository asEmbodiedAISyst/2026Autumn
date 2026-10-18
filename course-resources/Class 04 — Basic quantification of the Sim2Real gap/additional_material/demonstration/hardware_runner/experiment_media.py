#!/usr/bin/env python3
"""Control the separate iPhone capture service for a V5 hardware run."""

from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


HERE = Path(__file__).resolve().parent
PROFILE_TITLES = {
    "PILOT_LOW_AMPLITUDE": "low-amplitude safety pilot",
    "P01_slow_triangle": "slow triangle motion",
    "P02_multisine": "multisine motion",
    "P03_smooth_levels": "smooth-level motion",
    "P04_chirp": "chirp motion",
    "P05_wide_sine": "wide-sine motion",
    "P06_heldout_composite": "held-out composite motion",
    "P07_heldout_sine_hold": "held-out sine-and-hold motion",
}
BALANCED_PROFILE_CODES = {
    "P01_slow_triangle": "P01",
    "P02_multisine": "P02",
    "P03_smooth_levels": "P03",
    "P04_chirp": "P04",
    "P05_wide_sine": "P05",
}
BALANCED_PROFILE_SLUGS = {
    "P01_slow_triangle": "slow-triangle",
    "P02_multisine": "multisine",
    "P03_smooth_levels": "smooth-levels",
    "P04_chirp": "chirp",
    "P05_wide_sine": "wide-sine",
}
HELD_OUT_PROFILE_CODES = {
    "P06_heldout_composite": "P06",
    "P07_heldout_sine_hold": "P07",
}
SUPPORTED_MEDIA_CONFIGURATIONS = {"G1", "M0", "B0", "B1", "B2"}
G1_CAMPAIGN_TOTAL_EPISODES = 22
EXPERIMENT_NUMBER_PATTERN = re.compile(r"^[0-9]{6}-[0-9]{6}$")


class MediaCaptureError(RuntimeError):
    """Raised when required camera evidence cannot be captured safely."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def validated_experiment_number(value: str) -> str:
    """Return a strict Dubai-local YYMMDD-HHMMSS experiment number."""

    experiment_number = str(value)
    if EXPERIMENT_NUMBER_PATTERN.fullmatch(experiment_number) is None:
        raise ValueError(
            "experiment_number must match YYMMDD-HHMMSS exactly"
        )
    try:
        datetime.strptime(experiment_number, "%y%m%d-%H%M%S")
    except ValueError:
        raise ValueError(
            "experiment_number is not a valid YYMMDD-HHMMSS timestamp"
        ) from None
    return experiment_number


def _validated_mechanical_configuration(value: Any) -> str:
    configuration = str(value).strip().upper()
    if configuration not in SUPPORTED_MEDIA_CONFIGURATIONS:
        supported = ", ".join(sorted(SUPPORTED_MEDIA_CONFIGURATIONS))
        raise ValueError(
            "media mechanical_configuration must be one of " + supported
        )
    return configuration


def _validated_campaign_total_episodes(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("campaign_total_episodes must be a positive integer")
    return value


def _balanced_repeat_number(repeat_id: str | None) -> str:
    if repeat_id not in {"R01", "R02", "R03"}:
        raise ValueError(
            "M0/B0/B2 media identity requires repeat R01, R02, or R03"
        )
    return str(repeat_id)[1:]


def _b1_repeat_number(repeat_id: str | None, *, role: str) -> str:
    allowed = (
        {"R01", "R02", "R03"}
        if role == "calibration"
        else {"R01", "R02", "R03", "R04", "R05"}
    )
    if repeat_id not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(
            f"B1 {role} media identity requires repeat {allowed_text}"
        )
    return str(repeat_id)[1:]


def episode_media_identity(
    ordinal: int,
    episode_id: str,
    role: str,
    condition_id: str,
    profile_id: str,
    repeat_id: str | None,
    *,
    experiment_number: str,
    mechanical_configuration: str = "G1",
    campaign_total_episodes: int = G1_CAMPAIGN_TOTAL_EPISODES,
) -> dict[str, Any]:
    """Return stable human-facing names without changing canonical episode IDs."""

    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
        raise ValueError("media campaign ordinal must be a positive integer")
    mechanical_configuration = _validated_mechanical_configuration(
        mechanical_configuration
    )
    campaign_total_episodes = _validated_campaign_total_episodes(
        campaign_total_episodes
    )
    if ordinal > campaign_total_episodes:
        raise ValueError(
            "media campaign ordinal cannot exceed campaign_total_episodes"
        )

    profile_title = PROFILE_TITLES.get(
        profile_id, profile_id.replace("_", " ").strip()
    )
    if mechanical_configuration == "G1":
        if condition_id not in {"H1", "H2"}:
            raise ValueError("G1 media identity condition must be H1 or H2")
        if role == "pilot":
            if profile_id != "PILOT_LOW_AMPLITUDE" or repeat_id is not None:
                raise ValueError(
                    "pilot media identity requires PILOT_LOW_AMPLITUDE and no repeat"
                )
            title = f"{condition_id} {profile_title}"
            suffix = f"{condition_id.lower()}-safety-pilot"
            display_code = f"{condition_id}-G1-PILOT"
        elif role == "held_out":
            profile_code = HELD_OUT_PROFILE_CODES.get(profile_id)
            if profile_code is None:
                raise ValueError(
                    "held-out G1 media identity only supports P06 and P07"
                )
            if (
                not isinstance(repeat_id, str)
                or len(repeat_id) != 3
                or not repeat_id.startswith("R")
                or not repeat_id[1:].isdigit()
            ):
                raise ValueError("held-out G1 media identity requires repeat RNN")
            repeat_text = repeat_id[1:]
            title = f"{condition_id} {profile_title}, repeat {repeat_text}"
            profile_slug = (
                "composite"
                if profile_id == "P06_heldout_composite"
                else "sine-and-hold"
                if profile_id == "P07_heldout_sine_hold"
                else profile_id.lower().replace("_", "-")
            )
            suffix = (
                f"{condition_id.lower()}-{profile_slug}-repeat-{repeat_text.lower()}"
            )
            display_code = f"{condition_id}-G1-{profile_code}-{repeat_id}"
        else:
            raise ValueError("G1 media identity role must be pilot or held_out")
    elif mechanical_configuration == "M0":
        if condition_id not in {"H1", "H2"}:
            raise ValueError("M0 media identity condition must be H1 or H2")
        if role == "pilot":
            if profile_id != "PILOT_LOW_AMPLITUDE" or repeat_id is not None:
                raise ValueError(
                    "pilot media identity requires PILOT_LOW_AMPLITUDE and no repeat"
                )
            title = f"{condition_id} {profile_title}"
            suffix = f"{condition_id.lower()}-safety-pilot"
            display_code = f"{condition_id}-M0-PILOT"
        elif role == "calibration":
            profile_code = BALANCED_PROFILE_CODES.get(profile_id)
            profile_slug = BALANCED_PROFILE_SLUGS.get(profile_id)
            if profile_id not in {
                "P01_slow_triangle",
                "P02_multisine",
                "P03_smooth_levels",
            } or profile_code is None or profile_slug is None:
                raise ValueError(
                    "M0 calibration media identity only supports P01 through P03"
                )
            repeat_text = _balanced_repeat_number(repeat_id)
            title = (
                f"{condition_id} {profile_title}, calibration repeat "
                f"{repeat_text}"
            )
            suffix = (
                f"{condition_id.lower()}-{profile_slug}-repeat-"
                f"{repeat_text.lower()}"
            )
            display_code = f"{condition_id}-M0-{profile_code}-{repeat_id}"
        else:
            raise ValueError(
                "M0 media identity role must be pilot or calibration"
            )
    elif mechanical_configuration == "B1":
        if condition_id not in {"H1", "H2"}:
            raise ValueError("B1 media identity condition must be H1 or H2")
        if role == "pilot":
            if profile_id != "PILOT_LOW_AMPLITUDE" or repeat_id is not None:
                raise ValueError(
                    "pilot media identity requires PILOT_LOW_AMPLITUDE and no repeat"
                )
            title = f"{condition_id} {profile_title}"
            suffix = f"{condition_id.lower()}-safety-pilot"
            display_code = f"{condition_id}-B1-PILOT"
        elif role == "calibration":
            profile_code = BALANCED_PROFILE_CODES.get(profile_id)
            profile_slug = BALANCED_PROFILE_SLUGS.get(profile_id)
            if profile_id not in {
                "P01_slow_triangle",
                "P02_multisine",
                "P03_smooth_levels",
            } or profile_code is None or profile_slug is None:
                raise ValueError(
                    "B1 calibration media identity only supports P01 through P03"
                )
            repeat_text = _b1_repeat_number(repeat_id, role=role)
            title = (
                f"{condition_id} {profile_title}, calibration repeat "
                f"{repeat_text}"
            )
            suffix = (
                f"{condition_id.lower()}-{profile_slug}-repeat-"
                f"{repeat_text.lower()}"
            )
            display_code = f"{condition_id}-B1-{profile_code}-{repeat_id}"
        elif role == "held_out":
            if profile_id != "P06_heldout_composite":
                raise ValueError(
                    "B1 held-out media identity only supports P06"
                )
            repeat_text = _b1_repeat_number(repeat_id, role=role)
            title = f"{condition_id} {profile_title}, repeat {repeat_text}"
            suffix = (
                f"{condition_id.lower()}-composite-repeat-"
                f"{repeat_text.lower()}"
            )
            display_code = f"{condition_id}-B1-P06-{repeat_id}"
        else:
            raise ValueError(
                "B1 media identity role must be pilot, calibration, or held_out"
            )
    else:
        if condition_id not in {"H1", "H2", "H3", "H4", "H5"}:
            raise ValueError(
                "balanced B0/B2 media identity condition must be H1 through H5"
            )
        if role == "pilot":
            allowed_pilot_conditions = (
                {"H1", "H2", "H4", "H5"}
                if mechanical_configuration == "B0"
                else {"H1", "H4", "H5"}
            )
            if condition_id not in allowed_pilot_conditions:
                raise ValueError(
                    "balanced pilot media identity received an unsupported "
                    f"{mechanical_configuration} condition: {condition_id}"
                )
            if profile_id != "PILOT_LOW_AMPLITUDE" or repeat_id is not None:
                raise ValueError(
                    "pilot media identity requires PILOT_LOW_AMPLITUDE and no repeat"
                )
            title = f"{condition_id} {profile_title}"
            suffix = f"{condition_id.lower()}-safety-pilot"
            display_code = (
                f"{condition_id}-{mechanical_configuration}-PILOT"
            )
        elif role in {"calibration", "model_selection"}:
            profile_code = BALANCED_PROFILE_CODES.get(profile_id)
            profile_slug = BALANCED_PROFILE_SLUGS.get(profile_id)
            if profile_code is None or profile_slug is None:
                raise ValueError(
                    "balanced B0/B2 media identity only supports P01 through P05"
                )
            if role == "calibration" and profile_id not in {
                "P01_slow_triangle",
                "P02_multisine",
                "P03_smooth_levels",
            }:
                raise ValueError(
                    "balanced calibration media identity only supports P01 through P03"
                )
            if role == "model_selection":
                if profile_id not in {"P04_chirp", "P05_wide_sine"}:
                    raise ValueError(
                        "balanced model-selection media identity only supports P04 and P05"
                    )
                if condition_id not in {"H1", "H2"}:
                    raise ValueError(
                        "balanced model-selection media identity requires H1 or H2"
                    )
            repeat_text = _balanced_repeat_number(repeat_id)
            role_title = (
                "calibration" if role == "calibration" else "model selection"
            )
            title = (
                f"{condition_id} {profile_title}, {role_title} repeat "
                f"{repeat_text}"
            )
            suffix = (
                f"{condition_id.lower()}-{profile_slug}-repeat-"
                f"{repeat_text.lower()}"
            )
            display_code = (
                f"{condition_id}-{mechanical_configuration}-{profile_code}-"
                f"{repeat_id}"
            )
        else:
            raise ValueError(
                "balanced B0/B2 media identity role must be pilot, calibration, "
                "or model_selection"
            )
    experiment_number = validated_experiment_number(experiment_number)
    artifact_prefix = f"{experiment_number}_{display_code}"
    return {
        "episode_id": episode_id,
        "title": title,
        "directory_name": f"{artifact_prefix}_{ordinal:02d}-{suffix}",
        "campaign_ordinal": ordinal,
        "display_code": display_code,
        "scene_label": display_code,
        "experiment_number": experiment_number,
        "artifact_prefix": artifact_prefix,
        "mechanical_configuration": mechanical_configuration,
        "campaign_total_episodes": campaign_total_episodes,
    }


def _relative_to_run(run_root: Path, value: str | Path | None) -> str | None:
    if value is None:
        return None
    path = Path(value)
    try:
        return path.resolve().relative_to(run_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


class ExperimentMediaCapture:
    """Lifecycle client for the persistent asMagic AR capture subprocess."""

    def __init__(
        self,
        values: dict[str, Any],
        run_root: Path,
        *,
        experiment_number: str | None = None,
    ) -> None:
        self.values = values
        self.config = dict(values["iphone_media_capture"])
        self.mechanical_configuration = _validated_mechanical_configuration(
            values.get("mechanical_configuration", "G1")
        )
        configured_total = self.config.get("campaign_total_episodes")
        if configured_total is None:
            if self.mechanical_configuration != "G1":
                raise ValueError(
                    "iphone_media_capture.campaign_total_episodes is required "
                    "for documented M0/B0/B1/B2 runs"
                )
            configured_total = G1_CAMPAIGN_TOTAL_EPISODES
        self.campaign_total_episodes = _validated_campaign_total_episodes(
            configured_total
        )
        self.experiment_number = (
            validated_experiment_number(experiment_number)
            if experiment_number is not None
            else None
        )
        self.run_root = run_root.resolve()
        self.media_root = self.run_root / "media"
        self.episode_root = self.media_root / "episodes"
        self.log_root = self.media_root / "service-logs"
        self.control_socket = Path(tempfile.gettempdir()) / (
            f"v5-{self.mechanical_configuration.lower()}-camera-"
            f"{uuid.uuid4().hex}.sock"
        )
        self.process: subprocess.Popen[str] | None = None
        self.stdout_handle: Any = None
        self.stderr_handle: Any = None
        self.ready_status: dict[str, Any] | None = None
        self.setup_snapshot: dict[str, Any] | None = None
        self.current_session: dict[str, Any] | None = None
        self.session_results: list[dict[str, Any]] = []
        self.finalize_result: dict[str, Any] | None = None
        self.lifecycle_errors: list[str] = []
        self.lifecycle_path = self.media_root / "capture-lifecycle.jsonl"

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled_for_run", False))

    @property
    def required(self) -> bool:
        return bool(self.config.get("required_before_motion", False))

    def _service_script(self) -> Path:
        value = Path(str(self.config["service_script"]))
        return value if value.is_absolute() else HERE / value

    def _write_lifecycle(
        self,
        *,
        command: str,
        request_wall_ns: int,
        request_monotonic_ns: int,
        ack_wall_ns: int,
        ack_monotonic_ns: int,
        response: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        self.media_root.mkdir(parents=True, exist_ok=True)
        row = {
            "command": command,
            "request_host_wall_time_ns": request_wall_ns,
            "request_host_monotonic_ns": request_monotonic_ns,
            "ack_host_wall_time_ns": ack_wall_ns,
            "ack_host_monotonic_ns": ack_monotonic_ns,
            "round_trip_s": (ack_monotonic_ns - request_monotonic_ns) * 1e-9,
            "response": response,
            "error": error,
        }
        with self.lifecycle_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _request(
        self,
        payload: dict[str, Any],
        *,
        timeout_s: float | None = None,
        require_ok: bool = True,
    ) -> dict[str, Any]:
        if timeout_s is None:
            timeout_s = float(self.config["command_timeout_s"])
        request_wall_ns = time.time_ns()
        request_monotonic_ns = time.monotonic_ns()
        response: dict[str, Any] | None = None
        error_text: str | None = None
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(timeout_s)
                connection.connect(str(self.control_socket))
                connection.sendall(
                    (json.dumps(payload, separators=(",", ":")) + "\n").encode(
                        "utf-8"
                    )
                )
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > 32 * 1024 * 1024:
                        raise MediaCaptureError(
                            "camera service response exceeded 32 MiB"
                        )
                    if b"\n" in chunk:
                        break
            raw = b"".join(chunks).split(b"\n", 1)[0]
            if not raw:
                raise MediaCaptureError("camera service returned no response")
            decoded = json.loads(raw.decode("utf-8"))
            if not isinstance(decoded, dict):
                raise MediaCaptureError("camera service returned non-object JSON")
            response = decoded
            if require_ok and response.get("ok") is not True:
                raise MediaCaptureError(
                    str(response.get("error", "camera service command failed"))
                )
            return response
        except (
            json.JSONDecodeError,
            OSError,
            TimeoutError,
            MediaCaptureError,
        ) as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, MediaCaptureError):
                raise
            raise MediaCaptureError(error_text) from exc
        finally:
            ack_wall_ns = time.time_ns()
            ack_monotonic_ns = time.monotonic_ns()
            try:
                self._write_lifecycle(
                    command=str(payload.get("command", "UNKNOWN")),
                    request_wall_ns=request_wall_ns,
                    request_monotonic_ns=request_monotonic_ns,
                    ack_wall_ns=ack_wall_ns,
                    ack_monotonic_ns=ack_monotonic_ns,
                    response=response,
                    error=error_text,
                )
            except OSError as exc:
                self.lifecycle_errors.append(
                    f"{type(exc).__name__}: {exc}"
                )

    def start_service(self) -> dict[str, Any]:
        """Start the receiver and block until a recent real AR frame exists."""

        if not self.enabled:
            raise MediaCaptureError("iPhone media capture is disabled in config")
        python = Path(str(self.config["python_executable"]))
        script = self._service_script()
        if not python.is_file() or not os.access(python, os.X_OK):
            raise MediaCaptureError(f"camera Python is unavailable: {python}")
        if not script.is_file():
            raise MediaCaptureError(f"camera service script is unavailable: {script}")

        self.episode_root.mkdir(parents=True, exist_ok=True)
        self.log_root.mkdir(parents=True, exist_ok=True)
        self.stdout_handle = (
            self.log_root / "capture-service.stdout.log"
        ).open("w", encoding="utf-8")
        self.stderr_handle = (
            self.log_root / "capture-service.stderr.log"
        ).open("w", encoding="utf-8")
        command = [
            str(python),
            str(script),
            "--iphone-ip",
            str(self.config["iphone_ip"]),
            "--socket",
            str(self.control_socket),
            "--output-root",
            str(self.episode_root),
            "--port",
            str(int(self.config.get("ar_port", 8000))),
            "--hwm",
            str(int(self.config.get("hwm", 256))),
            "--poll-timeout-ms",
            str(int(self.config.get("poll_timeout_ms", 100))),
            "--max-recording-duration-s",
            str(
                float(self.config["maximum_recording_duration_s"])
            ),
        ]
        self.process = subprocess.Popen(
            command,
            stdout=self.stdout_handle,
            stderr=self.stderr_handle,
            text=True,
            start_new_session=True,
        )

        deadline = time.monotonic() + float(
            self.config["readiness_timeout_s"]
        )
        last_response: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise MediaCaptureError(
                    "camera service exited before a real AR frame arrived; "
                    "see media/service-logs"
                )
            if self.control_socket.exists():
                try:
                    status = self._request({"command": "STATUS"}, timeout_s=0.75)
                    last_response = status
                    age = status.get("last_color_frame_age_s")
                    if age is None:
                        age = status.get("last_frame_age_s")
                    ready = bool(
                        status.get("ready", status.get("stream_ready", False))
                    )
                    recent = age is not None and float(age) <= float(
                        self.config["snapshot_max_age_s"]
                    )
                    version = str(status.get("asmagic_sdk_version", "unknown"))
                    expected = str(self.config["required_asmagic_sdk_version"])
                    if ready and recent and version == expected:
                        self.ready_status = status
                        return status
                except MediaCaptureError:
                    pass
            time.sleep(0.1)
        raise MediaCaptureError(
            "no recent iPhone AR frame arrived before the readiness timeout; "
            f"last status={last_response}"
        )

    def status(self) -> dict[str, Any]:
        return self._request({"command": "STATUS"})

    def snapshot(self, label: str) -> dict[str, Any]:
        result = self._request(
            {
                "command": "SNAPSHOT",
                "label": label,
                "max_age_s": float(self.config["snapshot_max_age_s"]),
            }
        )
        if self.current_session is None:
            self.setup_snapshot = result
        return result

    def start_episode(
        self,
        *,
        identity: dict[str, Any],
        role: str,
        condition_id: str,
        profile_id: str,
        repeat_id: str | None,
    ) -> dict[str, Any]:
        if self.current_session is not None:
            raise MediaCaptureError("a camera episode is already recording")
        if self.experiment_number is None:
            raise MediaCaptureError(
                "recording requires a run-wide experiment_number"
            )
        if identity.get("experiment_number") != self.experiment_number:
            raise MediaCaptureError(
                "episode identity experiment_number does not match the run"
            )
        if (
            identity.get("mechanical_configuration")
            != self.mechanical_configuration
        ):
            raise MediaCaptureError(
                "episode identity mechanical_configuration does not match the run"
            )
        if (
            identity.get("campaign_total_episodes")
            != self.campaign_total_episodes
        ):
            raise MediaCaptureError(
                "episode identity campaign_total_episodes does not match the run"
            )
        expected_prefix = (
            self.experiment_number
            + "_"
            + str(identity["display_code"])
        )
        if identity.get("artifact_prefix") != expected_prefix:
            raise MediaCaptureError(
                "episode identity artifact_prefix does not match its scene"
            )
        fixture = self.values.get("fixture", {})
        default_centers = (
            [60, 100] if self.mechanical_configuration == "G1" else []
        )
        fixture_centers = fixture.get(
            "payload_center_positions_mm", default_centers
        )
        self.status()
        payload = {
            "command": "START",
            "session_id": identity["episode_id"],
            "directory_name": identity["directory_name"],
            "title": identity["title"],
            "metadata": {
                "canonical_episode_id": identity["episode_id"],
                "campaign_ordinal": int(identity["campaign_ordinal"]),
                "campaign_total_episodes": self.campaign_total_episodes,
                "display_code": str(identity["display_code"]),
                "scene_label": str(identity["scene_label"]),
                "experiment_number": self.experiment_number,
                "artifact_prefix": str(identity["artifact_prefix"]),
                "mechanical_configuration": self.mechanical_configuration,
                "fixture_centers_mm": list(fixture_centers),
                "fixture_total_external_moving_mass_g": int(
                    fixture.get("total_external_moving_mass_g", 110)
                ),
                "role": role,
                "controller_condition": condition_id,
                "profile_id": profile_id,
                "repeat_id": repeat_id,
                "audio_available": bool(
                    self.config.get("audio_available", False)
                ),
            },
            "timeout_s": float(self.config["readiness_timeout_s"]),
            "save_depth": bool(self.config.get("save_depth", True)),
            "flush_every_frames": int(
                self.config.get("flush_every_frames", 30)
            ),
        }
        try:
            result = self._request(
                payload,
                timeout_s=float(self.config["readiness_timeout_s"]) + 2.0,
            )
        except MediaCaptureError as start_error:
            reconciliation = "no matching service session was found"
            try:
                status = self.status()
                active = status.get("current_session")
                if (
                    isinstance(active, dict)
                    and active.get("session_id") == identity["episode_id"]
                ):
                    self.current_session = {
                        "identity": dict(identity),
                        "start_response": {
                            "ambiguous_ack": True,
                            "service_status": active,
                        },
                    }
                    stop = self._request(
                        {
                            "command": "STOP",
                            "outcome": "aborted_ambiguous_start_ack",
                            "events": [],
                        }
                    )
                    raw_status = str(
                        stop.get("raw_capture_status", "unknown")
                    )
                    combined = {
                        **self.current_session,
                        "stop_response": stop,
                        "status": (
                            "captured"
                            if stop.get("state") == "stopped"
                            and raw_status == "complete"
                            and stop.get("error") is None
                            else "partial"
                        ),
                    }
                    self.session_results.append(combined)
                    self.current_session = None
                    reconciliation = (
                        "matching service session was found and STOP was "
                        "acknowledged"
                    )
            except MediaCaptureError as reconcile_error:
                reconciliation = (
                    "STATUS/STOP reconciliation failed: "
                    f"{type(reconcile_error).__name__}: {reconcile_error}"
                )
            raise MediaCaptureError(
                f"START acknowledgement was ambiguous ({start_error}); "
                f"{reconciliation}"
            ) from start_error
        self.current_session = {
            "identity": dict(identity),
            "start_response": result,
        }
        return result

    def stop_episode(
        self,
        *,
        outcome: str,
        events: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        if self.current_session is None:
            raise MediaCaptureError("no camera episode is recording")
        post_roll_s = float(self.config.get("post_roll_s", 0.0))
        if post_roll_s > 0:
            time.sleep(post_roll_s)
        result = self._request(
            {
                "command": "STOP",
                "outcome": outcome,
                "events": list(events),
            }
        )
        state = str(result.get("state", "unknown"))
        raw_status = str(result.get("raw_capture_status", "unknown"))
        error = result.get("error")
        status = result.get("status")
        if status is None:
            status = (
                "captured"
                if state == "stopped"
                and raw_status == "complete"
                and error is None
                else "partial"
            )
        combined = {
            **self.current_session,
            "stop_response": result,
            "status": status,
        }
        self.session_results.append(combined)
        self.current_session = None
        return combined

    def finalize(self, run_metadata: dict[str, Any]) -> dict[str, Any]:
        if self.current_session is not None:
            raise MediaCaptureError(
                "cannot finalize while a camera episode is recording"
            )
        if self.experiment_number is None:
            raise MediaCaptureError(
                "FINALIZE requires a run-wide experiment_number"
            )
        if run_metadata.get("experiment_number") != self.experiment_number:
            raise MediaCaptureError(
                "FINALIZE experiment_number does not match the capture run"
            )
        mechanical_configuration = str(
            run_metadata.get("mechanical_configuration", "")
        )
        expected_prefix = (
            f"{self.experiment_number}_{mechanical_configuration}"
        )
        if run_metadata.get("campaign_artifact_prefix") != expected_prefix:
            raise MediaCaptureError(
                "FINALIZE campaign_artifact_prefix does not match the run"
            )
        result = self._request(
            {
                "command": "FINALIZE",
                "video_fps": float(self.config["derived_video_fps"]),
                "run_metadata": run_metadata,
            },
            timeout_s=float(self.config.get("finalize_timeout_s", 1800.0)),
        )
        self.finalize_result = result
        return result

    def shutdown(self) -> None:
        """Stop the service while making local cleanup unconditional."""

        process = self.process
        try:
            if process is not None:
                if process.poll() is None and self.control_socket.exists():
                    try:
                        self._request(
                            {"command": "SHUTDOWN"}, timeout_s=10.0
                        )
                    except MediaCaptureError:
                        pass
                if process.poll() is None:
                    try:
                        process.wait(timeout=10.0)
                    except (subprocess.TimeoutExpired, OSError):
                        try:
                            process.send_signal(signal.SIGINT)
                            process.wait(timeout=5.0)
                        except (subprocess.TimeoutExpired, OSError):
                            try:
                                process.terminate()
                                process.wait(timeout=5.0)
                            except (subprocess.TimeoutExpired, OSError):
                                try:
                                    process.kill()
                                    process.wait(timeout=5.0)
                                except (
                                    subprocess.TimeoutExpired,
                                    OSError,
                                ) as exc:
                                    self.lifecycle_errors.append(
                                        "camera process cleanup: "
                                        f"{type(exc).__name__}: {exc}"
                                    )
        finally:
            try:
                self.control_socket.unlink(missing_ok=True)
            except OSError as exc:
                self.lifecycle_errors.append(
                    "camera socket cleanup: "
                    f"{type(exc).__name__}: {exc}"
                )
            for attribute in ("stdout_handle", "stderr_handle"):
                handle = getattr(self, attribute)
                if handle is not None:
                    try:
                        handle.close()
                    except OSError as exc:
                        self.lifecycle_errors.append(
                            f"{attribute} cleanup: "
                            f"{type(exc).__name__}: {exc}"
                        )
                    finally:
                        setattr(self, attribute, None)
            self.process = None

    def relative_session_media(
        self, combined: dict[str, Any]
    ) -> dict[str, Any]:
        stop = combined.get("stop_response", {})
        session = stop.get("session", stop)
        directory = (
            session.get("session_directory")
            or session.get("directory")
            or combined["identity"]["directory_name"]
        )
        relative = _relative_to_run(self.run_root, directory)
        if relative is not None and not relative.startswith("media/"):
            candidate = self.episode_root / str(directory)
            relative = _relative_to_run(self.run_root, candidate)
        return {
            "display_code": combined["identity"]["display_code"],
            "scene_label": combined["identity"]["scene_label"],
            "experiment_number": combined["identity"]["experiment_number"],
            "artifact_prefix": combined["identity"]["artifact_prefix"],
            "campaign_ordinal": int(combined["identity"]["campaign_ordinal"]),
            "mechanical_configuration": combined["identity"][
                "mechanical_configuration"
            ],
            "campaign_total_episodes": int(
                combined["identity"]["campaign_total_episodes"]
            ),
            "status": combined.get(
                "status",
                session.get("status", session.get("state", "unknown")),
            ),
            "title": combined["identity"]["title"],
            "directory": relative,
            "video": None,
            "unlabeled_video": None,
            "key_frame_count": int(session.get("key_frame_count", 0)),
            "source_frame_count": int(
                session.get(
                    "source_frame_count",
                    session.get(
                        "jpeg_frames",
                        session.get("frame_count", session.get("frames", 0)),
                    ),
                )
            ),
            "capture_service": "persistent asMagic AR receiver",
            "raw_jpegs_are_primary_evidence": True,
            "derived_video_has_audio": False,
        }

    def apply_finalize_result(
        self, manifests: Sequence[dict[str, Any]]
    ) -> dict[str, Any]:
        """Merge finalized camera artifacts into motor episode manifests."""

        result = self.finalize_result
        if not isinstance(result, dict):
            raise MediaCaptureError("camera FINALIZE has not completed")

        raw_sessions = result.get("sessions")
        if isinstance(raw_sessions, list):
            sessions = [
                item for item in raw_sessions if isinstance(item, dict)
            ]
        elif result.get("session_id") is not None:
            sessions = [result]
        else:
            sessions = []
        by_id = {
            str(item["session_id"]): item
            for item in sessions
            if item.get("session_id") is not None
        }

        completed = 0
        failures: list[str] = []
        for manifest in manifests:
            episode_id = str(manifest["episode_id"])
            previous = dict(manifest.get("media", {}))
            session = by_id.get(episode_id)
            if session is None:
                previous.update(
                    {
                        "status": "failed",
                        "video": None,
                        "key_frame_count": 0,
                        "source_frame_count": int(
                            previous.get("source_frame_count", 0)
                        ),
                        "error": "FINALIZE returned no matching media session",
                    }
                )
                manifest["media"] = previous
                failures.append(f"{episode_id}: missing finalized session")
                continue

            media_index = session.get("media_index")
            if not isinstance(media_index, dict):
                raw_index_path = session.get("media_index_path")
                if raw_index_path is not None:
                    candidate = Path(str(raw_index_path)).resolve()
                    try:
                        candidate.relative_to(self.run_root)
                    except ValueError:
                        failures.append(
                            f"{episode_id}: media index escaped the run folder"
                        )
                    else:
                        try:
                            decoded = json.loads(
                                candidate.read_text(encoding="utf-8")
                            )
                        except (OSError, json.JSONDecodeError) as exc:
                            failures.append(
                                f"{episode_id}: could not read media index: {exc}"
                            )
                        else:
                            if isinstance(decoded, dict):
                                media_index = decoded

            session_directory = session.get(
                "session_directory", previous.get("directory")
            )
            relative_directory = _relative_to_run(
                self.run_root, session_directory
            )
            primary = (
                media_index.get("primary_evidence", {})
                if isinstance(media_index, dict)
                else {}
            )
            human = (
                media_index.get("human_viewable", {})
                if isinstance(media_index, dict)
                else {}
            )
            video_info = (
                human.get("video", {}) if isinstance(human, dict) else {}
            )
            if not isinstance(video_info, dict):
                video_info = {}
            keyframes = (
                human.get("keyframes", []) if isinstance(human, dict) else []
            )
            if not isinstance(keyframes, list):
                keyframes = []

            def artifact_relative(value: Any) -> str | None:
                if value is None or relative_directory is None:
                    return None
                return (
                    Path(relative_directory) / str(value)
                ).as_posix()

            state = str(session.get("state", "unknown"))
            session_status = str(
                session.get(
                    "status", "complete" if state == "finalized" else state
                )
            )
            video_path = artifact_relative(video_info.get("path"))
            unlabeled_video_path = artifact_relative(
                video_info.get("unlabeled_path")
            )
            frame_map = artifact_relative(video_info.get("frame_map"))
            source_count = int(
                primary.get(
                    "jpeg_count", previous.get("source_frame_count", 0)
                )
            )
            if (
                session_status == "complete"
                and isinstance(media_index, dict)
                and source_count > 0
                and video_path is not None
                and unlabeled_video_path is not None
                and frame_map is not None
            ):
                completed += 1
            else:
                failures.append(
                    f"{episode_id}: final media status {session_status}"
                )

            previous.update(
                {
                    "status": session_status,
                    "directory": relative_directory,
                    "video": video_path,
                    "unlabeled_video": unlabeled_video_path,
                    "frame_map": frame_map,
                    "experiment_number": video_info.get(
                        "experiment_number",
                        previous.get("experiment_number"),
                    ),
                    "scene_label": video_info.get(
                        "scene_label",
                        previous.get("scene_label"),
                    ),
                    "artifact_prefix": video_info.get(
                        "artifact_prefix",
                        previous.get("artifact_prefix"),
                    ),
                    "display_code": video_info.get(
                        "episode_display_code",
                        previous.get("display_code"),
                    ),
                    "mechanical_configuration": video_info.get(
                        "mechanical_configuration",
                        previous.get(
                            "mechanical_configuration",
                            self.mechanical_configuration,
                        ),
                    ),
                    "campaign_ordinal": video_info.get(
                        "campaign_ordinal",
                        previous.get("campaign_ordinal"),
                    ),
                    "campaign_total_episodes": video_info.get(
                        "campaign_total_episodes",
                        previous.get(
                            "campaign_total_episodes",
                            self.campaign_total_episodes,
                        ),
                    ),
                    "burned_in_labels": video_info.get(
                        "burned_in_labels",
                        previous.get("burned_in_labels"),
                    ),
                    "raw_jpegs_modified": video_info.get(
                        "raw_jpegs_modified",
                        previous.get("raw_jpegs_modified"),
                    ),
                    "video_frame_count": video_info.get(
                        "video_frame_count", 0
                    ),
                    "decoded_frame_count_verified": video_info.get(
                        "decoded_frame_count_verified", 0
                    ),
                    "unlabeled_decoded_frame_count_verified": (
                        video_info.get(
                            "unlabeled_decoded_frame_count_verified", 0
                        )
                    ),
                    "unlabeled_video_frame_count": video_info.get(
                        "unlabeled_video_frame_count", 0
                    ),
                    "paired_frame_timing_identical": video_info.get(
                        "paired_frame_timing_identical"
                    ),
                    "unlabeled_burned_in_labels": video_info.get(
                        "unlabeled_burned_in_labels"
                    ),
                    "width_px": video_info.get("width_px"),
                    "height_px": video_info.get("height_px"),
                    "unlabeled_width_px": video_info.get(
                        "unlabeled_width_px"
                    ),
                    "unlabeled_height_px": video_info.get(
                        "unlabeled_height_px"
                    ),
                    "codec": video_info.get("codec"),
                    "unlabeled_codec": video_info.get("unlabeled_codec"),
                    "constant_frame_rate_fps": video_info.get(
                        "constant_frame_rate_fps"
                    ),
                    "unlabeled_constant_frame_rate_fps": video_info.get(
                        "unlabeled_constant_frame_rate_fps"
                    ),
                    "shared_frame_map": video_info.get("shared_frame_map"),
                    "source_resolution_consistent": video_info.get(
                        "source_resolution_consistent"
                    ),
                    "source_jpeg_count": video_info.get(
                        "source_jpeg_count", source_count
                    ),
                    "capture_manifest": artifact_relative("capture.json"),
                    "media_index": artifact_relative("media-index.json"),
                    "key_frame_count": len(keyframes),
                    "source_frame_count": source_count,
                    "depth_frame_count": int(primary.get("depth_count", 0)),
                    "timing_gap_statistics": (
                        media_index.get("timing_gap_statistics")
                        if isinstance(media_index, dict)
                        else None
                    ),
                    "capture_service": "persistent asMagic AR receiver",
                    "raw_jpegs_are_primary_evidence": True,
                    "derived_video_has_audio": False,
                }
            )
            error = session.get("error") or session.get("finalize_error")
            if error is not None:
                previous["error"] = str(error)
            manifest["media"] = previous

        raw_full_video = result.get("full_experiment_video")
        if isinstance(raw_full_video, dict):
            full_experiment_video = dict(raw_full_video)
        else:
            full_experiment_video = {
                "status": "not_created",
                "reason": (
                    "FINALIZE returned no full_experiment_video result"
                ),
            }
        for artifact_key in (
            "path",
            "unlabeled_path",
            "frame_map",
            "chapters",
        ):
            artifact_value = full_experiment_video.get(artifact_key)
            if artifact_value in (None, ""):
                continue
            artifact_path = Path(str(artifact_value))
            if artifact_path.is_absolute():
                mapped = _relative_to_run(self.run_root, artifact_path)
            elif artifact_path.parts and artifact_path.parts[0] == "media":
                mapped = artifact_path.as_posix()
            else:
                mapped = (Path("media") / artifact_path).as_posix()
            full_experiment_video[artifact_key] = mapped

        aggregate_status = str(result.get("status", "unknown"))
        if aggregate_status == "complete" and completed != len(manifests):
            aggregate_status = "partial"
        full_video_status = str(
            full_experiment_video.get("status", "not_created")
        )
        if full_video_status != "complete":
            detail = (
                full_experiment_video.get("error")
                or full_experiment_video.get("reason")
            )
            failure = f"full experiment video: status {full_video_status}"
            if detail:
                failure += f" ({detail})"
            failures.append(failure)
            if aggregate_status == "complete":
                aggregate_status = "partial"

        if self.lifecycle_errors:
            failures.extend(
                f"capture lifecycle log: {error}"
                for error in self.lifecycle_errors
            )
            if aggregate_status == "complete":
                aggregate_status = "partial"
        root_html = _relative_to_run(
            self.run_root, result.get("root_media_html_path")
        )
        setup_photo = _relative_to_run(
            self.run_root, result.get("setup_photo_path")
        )
        return {
            "status": aggregate_status,
            "session_count": len(sessions),
            "expected_session_count": len(manifests),
            "complete_session_count": completed,
            "index": root_html or "media/index.html",
            "setup_photo": setup_photo,
            "full_experiment_video": full_experiment_video,
            "primary_camera_evidence": [
                "raw/<experiment_number>_<scene>_ar.csv",
                "raw/color_frames/<experiment_number>_<scene>_frame_*.jpg",
                "raw/depth_frames/<experiment_number>_<scene>_depth_*.npy",
            ],
            "camera_compatibility_aliases": ["raw/ar.csv"],
            "derived_video_has_audio": False,
            "errors": failures,
        }

    def __enter__(self) -> "ExperimentMediaCapture":
        self.start_service()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        self.shutdown()
        return False


def write_start_here(
    run_root: Path,
    values: dict[str, Any],
    *,
    run_manifest: dict[str, Any] | None = None,
    media_summary: dict[str, Any] | None = None,
    manifests: Sequence[dict[str, Any]] = (),
) -> Path:
    """Write the plain-language entry point for the complete experiment folder."""

    fixture = values["fixture"]
    mechanical_configuration = _validated_mechanical_configuration(
        values.get("mechanical_configuration", "G1")
    )
    media_config = values.get("iphone_media_capture", {})
    configured_total = media_config.get("campaign_total_episodes")
    if configured_total is None:
        if mechanical_configuration != "G1":
            raise ValueError(
                "iphone_media_capture.campaign_total_episodes is required "
                "for documented M0/B0/B1/B2 runs"
            )
        configured_total = G1_CAMPAIGN_TOTAL_EPISODES
    campaign_total = _validated_campaign_total_episodes(configured_total)
    if mechanical_configuration == "G1":
        fixture_line = (
            "- Fixture: two payloads on the positive side at +60 mm and +100 mm."
        )
        zero_line = (
            "- Torque-off gravity rest is not experiment zero; experiment zero is "
            "measured encoder tick 2048 ±5 under torque."
        )
        keyframe_line = (
            "- media/episodes/*/keyframes/: five event-aligned images: before "
            "motion, experiment zero/profile start, motion finished, torque "
            "disabled, and gravity settled."
        )
    elif mechanical_configuration == "M0":
        centers = list(fixture.get("payload_center_positions_mm", []))
        if centers:
            raise ValueError(
                "motor-only M0 START_HERE requires no payload centers"
            )
        if (
            int(fixture.get("payload_count", -1)) != 0
            or int(fixture.get("total_external_moving_mass_g", -1)) != 0
            or float(fixture.get("external_gravity_moment_Nm", -1.0)) != 0.0
        ):
            raise ValueError(
                "motor-only M0 START_HERE requires zero payloads, external "
                "moving mass, and external gravity moment"
            )
        fixture_line = (
            "- Fixture: motor-only; no external horn, link, pin, or payload "
            "is installed, so payload centers are not applicable."
        )
        zero_line = (
            "- Experiment zero is measured encoder tick 2048 ±5 under torque; "
            "M0 uses the standard zero/recenter path and never G1's "
            "torque-off gravity-rest rule."
        )
        keyframe_line = (
            "- media/episodes/*/keyframes/: four event-aligned images: before "
            "motion, experiment zero/profile start, motion finished, and torque "
            "disabled."
        )
    else:
        centers = list(fixture.get("payload_center_positions_mm", []))
        if len(centers) != 2:
            raise ValueError(
                "balanced B0/B1/B2 START_HERE requires two payload center positions"
            )
        fixture_line = (
            "- Fixture: balanced equal payloads centered at "
            f"{float(centers[0]):+g} mm and {float(centers[1]):+g} mm."
        )
        zero_line = (
            "- Experiment zero is measured encoder tick 2048 ±5 under torque; "
            "the balanced fixture does not use G1's torque-off gravity-rest rule."
        )
        keyframe_line = (
            "- media/episodes/*/keyframes/: four event-aligned images: before "
            "motion, experiment zero/profile start, motion finished, and torque "
            "disabled."
        )
    status = (
        run_manifest.get("terminal_status", "not started")
        if run_manifest
        else "preparing"
    )
    host_preflight = (
        run_manifest.get("host_timing_preflight", {})
        if run_manifest
        else {}
    )
    campaign_design_lines: list[str] = []
    if mechanical_configuration == "B1":
        campaign_design_lines = [
            "- B1 captured design: H1/H2 only; 2 pilots, 18 calibration "
            "episodes (P01-P03 x H1/H2 x R01-R03), and 10 held-out "
            "episodes (P06 x H1/H2 x R01-R05)."
        ]
    elif (
        mechanical_configuration == "M0"
        and values.get("runner_mode") == "documented_media"
        and campaign_total == 20
    ):
        campaign_design_lines = [
            "- M0 captured design: H1/H2 only; 2 pilots and 18 "
            "calibration episodes (P01-P03 x H1/H2 x R01-R03).",
            "- M0 has no P04/P05 model-selection or P06 held-out "
            "sessions; the design contract excludes model selection from M0.",
        ]
    elif (
        mechanical_configuration == "B0"
        and values.get("runner_mode") == "documented_media"
        and campaign_total == 32
    ):
        campaign_design_lines = [
            "- B0 captured design: H1/H2 only; 2 pilots, 18 calibration "
            "episodes (P01-P03 x H1/H2 x R01-R03), and 12 model-selection "
            "episodes (P04-P05 x H1/H2 x R01-R03)."
        ]
    lines = [
        f"# START HERE — {mechanical_configuration} XC330 experiment",
        "",
        f"This folder is the record of the {mechanical_configuration} motor "
        "campaign. When camera capture succeeds, synchronized iPhone evidence "
        "is kept alongside the motor measurements.",
        "",
        "## What was installed",
        "",
        "- Motor: XC330-M288-T, ID 5.",
        fixture_line,
        f"- Moving mass declared for this run: "
        f"{fixture['total_external_moving_mass_g']} g.",
        zero_line,
        "",
        "## Run status",
        "",
        f"- Collection status before independent verification: **{status}**.",
        (
            f"- Campaign error: {run_manifest.get('campaign_error') or 'none'}."
            if run_manifest
            else "- The hardware campaign has not started yet."
        ),
        (
            "- Read-only host timing gate: "
            f"passed={host_preflight.get('passed', 'not run')}; "
            f"observed latency={host_preflight.get('observed_latency_timer_ms', 'unknown')} ms."
        ),
        f"- Planned motion-and-media episodes: {campaign_total}.",
        *campaign_design_lines,
        "",
        "## Where to look",
        "",
        "- episode-summary.csv: one-row-per-episode motor and media summary.",
        "- episodes/: full command, telemetry, zero-acquisition, register, "
        "and episode manifest data.",
        "- HOST_PREFLIGHT.json: read-only U2D2 latency-timer evidence.",
        "- VERIFICATION.json: per-run independent verification report.",
        "- inventory.sha256: hashes every retained artifact, including VERIFICATION.json.",
    ]
    if media_summary is not None:
        session_count = int(
            media_summary.get("session_count", len(manifests)) or 0
        )
        media_index = media_summary.get("index")
        raw_full_video = media_summary.get("full_experiment_video")
        full_video = (
            raw_full_video if isinstance(raw_full_video, dict) else None
        )
        lines.extend(
            [
                "",
                "## Camera capture result",
                "",
                f"- Status: **{media_summary.get('status', 'unknown')}**.",
                f"- Episode media sessions: {session_count}/{campaign_total}.",
            ]
        )
        if full_video is not None:
            labeled_path = full_video.get("path")
            unlabeled_path = full_video.get("unlabeled_path")
            labeled_link = (
                f"[open labeled video]({labeled_path})"
                if labeled_path
                else "not created"
            )
            unlabeled_link = (
                f"[open unlabeled video]({unlabeled_path})"
                if unlabeled_path
                else "not created"
            )
            lines.extend(
                [
                    "",
                    "### Full experiment viewing copies",
                    "",
                    f"- Full-video status: **{full_video.get('status', 'unknown')}**.",
                    f"- Full labeled video: {labeled_link}.",
                    f"- Full unlabeled video: {unlabeled_link}.",
                    "- Full-video frame map: "
                    f"{full_video.get('frame_map') or 'not created'}.",
                    "- Full-video chapter map: "
                    f"{full_video.get('chapters') or 'not created'}.",
                    "- Presentation: on the labeled copy, episode and phase "
                    "labels are burned into the frames; the paired unlabeled copy "
                    "has no overlays. There is no audio track; inter-episode gaps "
                    "are omitted.",
                ]
            )
        if media_index:
            lines.extend(
                [
                    f"- Visual index: {media_index}.",
                    "- media/episodes/: one plainly named folder per motion episode.",
                    "- Each episode has a timestamp-prefixed labeled video and "
                    "a matching timestamp-prefixed unlabeled video (derived, no "
                    "audio).",
                    keyframe_line,
                    "- media/episodes/*/snapshots/: a separate timestamp-prefixed "
                    "pre-motion photograph; it is not counted as a phase "
                    "keyframe.",
                    "- media/episodes/*/raw/color_frames/: exact JPEG frames "
                    "received from the iPhone; these are primary evidence.",
                    "- media/episodes/*/raw/depth_frames/: received uint16 depth "
                    "arrays.",
                    "- media/episodes/*/raw/<number>_<scene>_ar.csv: authoritative "
                    "iPhone time, host wall time, host monotonic time, pose, and "
                    "camera intrinsics. raw/ar.csv is only a compatibility symlink.",
                    "",
                    "Retain the JPEGs, depth arrays, CSV tables, and inventory "
                    "with every derived MP4.",
                ]
            )
        elif session_count:
            lines.extend(
                [
                    "- Visual index: unavailable because capture was not finalized.",
                    "- Available raw episode evidence, if any: media/episodes/.",
                ]
            )
        else:
            lines.append(
                "- No episode camera evidence or visual index was created."
            )
    if manifests:
        lines.extend(
            [
                "",
                "## Episode guide",
                "",
                "| # | Friendly name | Robot result | Media folder | Labeled video | Unlabeled video |",
                "|---:|---|---|---|---|---|",
            ]
        )
        for index, manifest in enumerate(manifests, start=1):
            media = manifest.get("media", {})
            labeled_path = media.get("video")
            unlabeled_path = media.get("unlabeled_video")
            labeled_link = (
                f"[open]({labeled_path})" if labeled_path else "not available"
            )
            unlabeled_link = (
                f"[open]({unlabeled_path})"
                if unlabeled_path
                else "not available"
            )
            lines.append(
                f"| {index} | {media.get('title', manifest['episode_id'])} | "
                f"{manifest['completion_status']} | "
                f"{media.get('directory', 'not available')} | "
                f"{labeled_link} | {unlabeled_link} |"
            )
    path = run_root / "START_HERE.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def camera_only_status(values: dict[str, Any]) -> dict[str, Any]:
    """Check the iPhone AR stream without opening the Dynamixel serial port."""

    mechanical_configuration = _validated_mechanical_configuration(
        values.get("mechanical_configuration", "G1")
    )
    prefix = f"v5-{mechanical_configuration.lower()}-camera-check-"
    with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
        run_root = Path(temporary) / "camera-check"
        run_root.mkdir()
        capture = ExperimentMediaCapture(values, run_root)
        try:
            status = capture.start_service()
            return {
                "operation": "iphone_camera_status_only",
                "iphone_ip": capture.config["iphone_ip"],
                "ready": bool(
                    status.get("ready", status.get("stream_ready", False))
                ),
                "last_frame_age_s": status.get(
                    "last_color_frame_age_s",
                    status.get("last_frame_age_s"),
                ),
                "asmagic_sdk_version": status.get("asmagic_sdk_version"),
                "motor_device_opened": False,
                "recording_started": False,
                "passed": bool(
                    status.get("ready", status.get("stream_ready", False))
                ),
            }
        finally:
            capture.shutdown()
