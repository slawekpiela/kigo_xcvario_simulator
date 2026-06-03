"""Small IGC FLARM passthrough emulator used by the XCvario TCP adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from .nmea import build_nmea_sentence


START_FRAME = 0x73
ESCAPE = 0x78
ESCAPE_ESCAPE = 0x55
ESCAPE_START = 0x31

MESSAGE_ERROR = 0x00
MESSAGE_ACK = 0xA0
MESSAGE_NACK = 0xB7
MESSAGE_PING = 0x01
MESSAGE_EXIT = 0x12
MESSAGE_SELECT_RECORD = 0x20
MESSAGE_GET_RECORD_INFO = 0x21
MESSAGE_GET_IGC_DATA = 0x22


@dataclass(frozen=True)
class FlarmRecordedFlight:
    record_info: str
    igc_text: str
    source_name: str = ""


@dataclass
class FlarmPassthroughConnectionState:
    binary_mode: bool = False
    selected_record: int | None = None
    download_offset: int = 0
    response_sequence: int = 0


class FlarmPassthroughSimulator:
    """Responds to the FLARM commands XCSoar sends through an XCvario link."""

    def __init__(self, *, records: tuple[FlarmRecordedFlight, ...] | None = None) -> None:
        self._records = records or load_default_igc_records()
        self._lock = Lock()
        self._settings: dict[str, str] = {
            "PILOT": "SIM PILOT",
            "COPIL": "",
            "GLIDERTYPE": "DG 800B/15",
            "GLIDERID": "SIM-001",
            "COMPID": "SIM",
            "COMPCLASS": "Club",
            "PRIV": "0",
            "RANGE": "6000",
            "BAUD": "5",
        }
        self._task_name = ""
        self._declared_waypoints: list[str] = []

    def new_connection_state(self) -> FlarmPassthroughConnectionState:
        return FlarmPassthroughConnectionState()

    @property
    def declaration(self) -> dict[str, object]:
        with self._lock:
            return {
                "pilot": self._settings.get("PILOT", ""),
                "aircraft_type": self._settings.get("GLIDERTYPE", ""),
                "aircraft_registration": self._settings.get("GLIDERID", ""),
                "competition_id": self._settings.get("COMPID", ""),
                "competition_class": self._settings.get("COMPCLASS", ""),
                "task_name": self._task_name,
                "waypoints": tuple(self._declared_waypoints),
            }

    @property
    def record_count(self) -> int:
        return len(self._records)

    @property
    def record_names(self) -> tuple[str, ...]:
        return tuple(record.source_name or _record_info_filename(record.record_info) for record in self._records)

    def handle_text_line(self, line: str, state: FlarmPassthroughConnectionState) -> bytes:
        body = _nmea_body(line)
        if body is None:
            return b""

        if body == "PFLAX":
            state.binary_mode = True
            state.selected_record = None
            state.download_offset = 0
            return b""

        if body.startswith("PFLAC,"):
            return self._handle_pflac(body)

        if body == "PFLAE,R":
            return _nmea_bytes("PFLAE,A,0,0")

        if body == "PFLAV,R":
            return _nmea_bytes("PFLAV,A,XCVario-Sim,1.0,")

        if body.startswith("PFLAR,"):
            state.binary_mode = False
            state.selected_record = None
            state.download_offset = 0
            return b""

        return b""

    def handle_binary_buffer(self, buffer: bytearray, state: FlarmPassthroughConnectionState) -> bytes:
        responses = bytearray()
        while state.binary_mode:
            frame = _pop_frame(buffer)
            if frame is None:
                break
            message_type, sequence_number, payload = frame
            response = self._handle_binary_frame(message_type, sequence_number, payload, state)
            responses.extend(response)
        return bytes(responses)

    def _handle_pflac(self, body: str) -> bytes:
        parts = body.split(",", 3)
        if len(parts) < 3:
            return b""
        command = parts[1]
        name = parts[2]
        value = parts[3] if len(parts) > 3 else ""

        if command == "S":
            self._store_setting(name, value)
            return _nmea_bytes(f"PFLAC,A,{name},{value}")

        if command == "R":
            with self._lock:
                value = self._settings.get(name, "")
            return _nmea_bytes(f"PFLAC,A,{name},{value}")

        return b""

    def _store_setting(self, name: str, value: str) -> None:
        with self._lock:
            self._settings[name] = value
            if name == "NEWTASK":
                self._task_name = value
                self._declared_waypoints.clear()
            elif name == "ADDWP":
                self._declared_waypoints.append(value)

    def _handle_binary_frame(
        self,
        message_type: int,
        sequence_number: int,
        payload: bytes,
        state: FlarmPassthroughConnectionState,
    ) -> bytes:
        if message_type == MESSAGE_PING:
            return _ack(sequence_number, state)

        if message_type == MESSAGE_EXIT:
            state.binary_mode = False
            state.selected_record = None
            state.download_offset = 0
            return b""

        if message_type == MESSAGE_SELECT_RECORD:
            if not payload:
                return _nack(sequence_number, state)
            record_index = int(payload[0])
            if record_index >= len(self._records):
                return _nack(sequence_number, state)
            state.selected_record = record_index
            state.download_offset = 0
            return _ack(sequence_number, state)

        if message_type == MESSAGE_GET_RECORD_INFO:
            record = self._selected_record(state)
            if record is None:
                return _nack(sequence_number, state)
            payload_bytes = _request_sequence_payload(sequence_number)
            payload_bytes += record.record_info.encode("ascii", "replace") + b"\0"
            return _build_frame(MESSAGE_ACK, payload_bytes, state)

        if message_type == MESSAGE_GET_IGC_DATA:
            record = self._selected_record(state)
            if record is None:
                return _nack(sequence_number, state)
            return self._download_chunk(sequence_number, record, state)

        return _nack(sequence_number, state)

    def _selected_record(self, state: FlarmPassthroughConnectionState) -> FlarmRecordedFlight | None:
        if state.selected_record is None:
            return None
        if state.selected_record >= len(self._records):
            return None
        return self._records[state.selected_record]

    def _download_chunk(
        self,
        sequence_number: int,
        record: FlarmRecordedFlight,
        state: FlarmPassthroughConnectionState,
    ) -> bytes:
        data = record.igc_text.encode("ascii", "replace")
        chunk_size = 256
        start = min(state.download_offset, len(data))
        end = min(len(data), start + chunk_size)
        state.download_offset = end
        chunk = data[start:end]
        is_last = end >= len(data)
        progress = 100 if is_last else int(round(100.0 * end / max(1, len(data))))
        payload = _request_sequence_payload(sequence_number) + bytes([max(0, min(100, progress))]) + chunk
        if is_last:
            payload += b"\x1a"
        return _build_frame(MESSAGE_ACK, payload, state)


def _nmea_body(line: str) -> str | None:
    text = line.strip()
    if not text:
        return None
    if text.startswith("$") or text.startswith("!"):
        text = text[1:]
    if "*" in text:
        text = text.split("*", 1)[0]
    return text


def _nmea_bytes(body: str) -> bytes:
    return build_nmea_sentence(body).encode("ascii")


def load_default_igc_records() -> tuple[FlarmRecordedFlight, ...]:
    kigo_nav_records = load_igc_records_from_directory(_kigo_nav_logs_dir())
    if kigo_nav_records:
        return kigo_nav_records
    packaged_records = load_igc_records_from_directory(_packaged_igc_logs_dir())
    if packaged_records:
        return packaged_records
    return (_default_record(),)


def load_igc_records_from_directory(directory: str | Path) -> tuple[FlarmRecordedFlight, ...]:
    source_dir = Path(directory)
    if not source_dir.is_dir():
        return ()
    records = []
    for path in sorted(source_dir.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.suffix.lower() != ".igc":
            continue
        record = _record_from_igc_path(path)
        if record is not None:
            records.append(record)
    return tuple(records)


def _record_from_igc_path(path: Path) -> FlarmRecordedFlight | None:
    try:
        igc_text = path.read_text(encoding="ascii", errors="replace")
    except OSError:
        return None
    if not igc_text.strip():
        return None
    return FlarmRecordedFlight(
        record_info=_record_info_from_igc(path.name, igc_text),
        igc_text=igc_text,
        source_name=path.name,
    )


def _record_info_from_igc(source_name: str, igc_text: str) -> str:
    lines = tuple(line.strip() for line in igc_text.splitlines())
    date_text = _igc_date_text(lines) or "2026-05-08"
    start_time, duration = _igc_time_range(lines)
    pilot = _igc_header_value(lines, "HFPLT") or "UNKNOWN"
    competition_id = _igc_header_value(lines, "HFCID")
    competition_class = _igc_header_value(lines, "HFCCL")
    return "|".join(
        [
            _clean_record_info_field(source_name),
            date_text,
            start_time,
            duration,
            pilot,
            competition_id,
            competition_class,
        ]
    )


def _igc_date_text(lines: tuple[str, ...]) -> str:
    for line in lines:
        if not line.startswith("HFDTE") or len(line) < 11:
            continue
        raw_date = line[5:11]
        if not raw_date.isdigit():
            continue
        day = int(raw_date[0:2])
        month = int(raw_date[2:4])
        year_suffix = int(raw_date[4:6])
        year = 1900 + year_suffix if year_suffix >= 80 else 2000 + year_suffix
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"
    return ""


def _igc_time_range(lines: tuple[str, ...]) -> tuple[str, str]:
    times = [
        line[1:7]
        for line in lines
        if line.startswith("B") and len(line) >= 7 and line[1:7].isdigit()
    ]
    if not times:
        return "00:00:00", "00:00:00"
    start_s = _time_text_to_seconds(times[0])
    end_s = _time_text_to_seconds(times[-1])
    duration_s = end_s - start_s
    if duration_s < 0:
        duration_s += 24 * 60 * 60
    return _format_hms(start_s), _format_hms(duration_s)


def _time_text_to_seconds(value: str) -> int:
    return int(value[0:2]) * 3600 + int(value[2:4]) * 60 + int(value[4:6])


def _format_hms(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _igc_header_value(lines: tuple[str, ...], prefix: str) -> str:
    for line in lines:
        if not line.startswith(prefix):
            continue
        value = line[len(prefix) :].strip()
        if ":" in value:
            value = value.split(":", 1)[1].strip()
        return _clean_record_info_field(value)
    return ""


def _clean_record_info_field(value: object) -> str:
    return str(value or "").replace("|", " ").replace("\0", "").strip()


def _record_info_filename(record_info: str) -> str:
    first_field = str(record_info or "").split("|", 1)[0].strip()
    return first_field if first_field.lower().endswith(".igc") else ""


def _kigo_nav_logs_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "kigo_nav" / "logs"


def _packaged_igc_logs_dir() -> Path:
    return Path(__file__).resolve().parent / "examples" / "igc_logs"


def _pop_frame(buffer: bytearray) -> tuple[int, int, bytes] | None:
    try:
        start_index = buffer.index(START_FRAME)
    except ValueError:
        buffer.clear()
        return None

    if start_index:
        del buffer[:start_index]
    header_result = _read_escaped(buffer, 1, 8)
    if header_result is None:
        return None
    header, payload_start = header_result
    frame_length = int.from_bytes(header[0:2], "little")
    if frame_length < 8:
        del buffer[0]
        return None
    payload_length = frame_length - 8
    payload_result = _read_escaped(buffer, payload_start, payload_length)
    if payload_result is None:
        return None
    payload, frame_end = payload_result
    del buffer[:frame_end]

    expected_crc = int.from_bytes(header[6:8], "little")
    actual_crc = _crc16_ccitt(header[:6] + payload)
    if expected_crc != actual_crc:
        return None

    sequence_number = int.from_bytes(header[3:5], "little")
    return int(header[5]), sequence_number, payload


def _read_escaped(buffer: bytearray, offset: int, size: int) -> tuple[bytes, int] | None:
    result = bytearray()
    index = offset
    while len(result) < size:
        if index >= len(buffer):
            return None
        octet = buffer[index]
        index += 1
        if octet == ESCAPE:
            if index >= len(buffer):
                return None
            escaped = buffer[index]
            index += 1
            if escaped == ESCAPE_START:
                result.append(START_FRAME)
            elif escaped == ESCAPE_ESCAPE:
                result.append(ESCAPE)
            else:
                return None
        else:
            result.append(octet)
    return bytes(result), index


def _ack(sequence_number: int, state: FlarmPassthroughConnectionState) -> bytes:
    return _build_frame(MESSAGE_ACK, _request_sequence_payload(sequence_number), state)


def _nack(sequence_number: int, state: FlarmPassthroughConnectionState) -> bytes:
    return _build_frame(MESSAGE_NACK, _request_sequence_payload(sequence_number), state)


def _request_sequence_payload(sequence_number: int) -> bytes:
    return int(sequence_number & 0xFFFF).to_bytes(2, "little")


def _build_frame(message_type: int, payload: bytes, state: FlarmPassthroughConnectionState) -> bytes:
    response_sequence = state.response_sequence & 0xFFFF
    state.response_sequence = (state.response_sequence + 1) & 0xFFFF
    header = bytearray()
    header.extend((8 + len(payload)).to_bytes(2, "little"))
    header.append(0)
    header.extend(response_sequence.to_bytes(2, "little"))
    header.append(message_type)
    crc = _crc16_ccitt(bytes(header) + payload)
    header.extend(crc.to_bytes(2, "little"))
    return bytes([START_FRAME]) + _escape(bytes(header) + payload)


def _escape(data: bytes) -> bytes:
    escaped = bytearray()
    for octet in data:
        if octet == START_FRAME:
            escaped.extend((ESCAPE, ESCAPE_START))
        elif octet == ESCAPE:
            escaped.extend((ESCAPE, ESCAPE_ESCAPE))
        else:
            escaped.append(octet)
    return bytes(escaped)


def _crc16_ccitt(data: bytes) -> int:
    crc = 0
    for octet in data:
        crc ^= octet << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _default_record() -> FlarmRecordedFlight:
    return FlarmRecordedFlight(
        record_info="2026-05-08|12:00:00|00:15:00|SIM PILOT|SIM|Club",
        igc_text=(
            "AFLXSIMKIGO XCVario Simulator\r\n"
            "HFDTE080526\r\n"
            "HFPLTPILOTINCHARGE:SIM PILOT\r\n"
            "HFGTYGLIDERTYPE:DG 800B/15\r\n"
            "HFGIDGLIDERID:SIM-001\r\n"
            "B1200004983000N01900202EA0040100401\r\n"
            "B1201004983100N01900500EA0045000450\r\n"
        ),
        source_name="synthetic.igc",
    )
