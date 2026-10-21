"""Same-day planning from explicit stop times and user-entered travel estimates.

This module makes no source, traffic or model calls. ``arrival`` is a fixed
appointment time, not a predicted arrival. Flexible stops retain their input
order. The buffer is applied once, immediately before each fixed destination;
the plan can arrive early and wait, but it never moves the appointment.

Computed times use Istanbul wall-clock minutes on the supplied calendar date.
Cross-midnight plans are reported as conflicts rather than silently wrapped.
"""
from __future__ import annotations

from datetime import date as calendar_date
import re
from typing import Any


_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_CLOCK = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z")
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


def _object(value: Any, allowed: set[str], required: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} bir nesne olmalı.")
    if set(value) - allowed:
        raise ValueError(f"{label} içinde desteklenmeyen alan var.")
    if required - set(value):
        raise ValueError(f"{label} için zorunlu alanlar eksik.")
    return value


def _minutes(value: Any, label: str, *, nullable: bool = True) -> int | None:
    if value is None and nullable:
        return None
    # bool is an int subclass; accepting it would hide malformed user input.
    if type(value) is not int or not 0 <= value <= 1440:
        raise ValueError(f"{label}, 0–1440 arasında tam dakika olmalı.")
    return value


def _arrival(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _CLOCK.fullmatch(value):
        raise ValueError("Sabit varış saati HH:MM biçiminde olmalı.")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _clock(value: int | None) -> str | None:
    if value is None or not 0 <= value < 1440:
        return None
    return f"{value // 60:02d}:{value % 60:02d}"


def plan(payload: dict) -> dict:
    """Validate and calculate one ordered day; missing inputs never imply success.

    ``planned_departure`` is the earliest end of the stop. A leg's
    ``latest_departure`` is the latest departure that still permits all flexible
    stops before the next fixed appointment, including its arrival buffer.
    ``slack_minutes`` is latest departure minus earliest departure. A missing
    later fixed appointment leaves the corresponding upper bound unset.

    A last stop's unknown duration is not required to determine arrival there.
    Any other required input gap suppresses computed times and slack throughout
    the response. Fixed appointment times remain visible unchanged.
    """
    value = _object(
        payload,
        {"date", "stops", "travel_minutes", "arrival_buffer_minutes"},
        {"date", "stops", "travel_minutes"},
        "Plan",
    )
    day = value["date"]
    if not isinstance(day, str) or not _DATE.fullmatch(day):
        raise ValueError("Tarih YYYY-MM-DD biçiminde olmalı.")
    try:
        calendar_date.fromisoformat(day)
    except ValueError as exc:
        raise ValueError("Geçerli bir takvim tarihi gerekli.") from exc

    raw_stops = value["stops"]
    if not isinstance(raw_stops, list) or not 2 <= len(raw_stops) <= 12:
        raise ValueError("Plan 2–12 durak içermeli.")
    raw_travel = value["travel_minutes"]
    if not isinstance(raw_travel, list) or len(raw_travel) != len(raw_stops) - 1:
        raise ValueError("Ardışık her iki durak için bir yol süresi gerekli.")
    buffer = _minutes(
        value.get("arrival_buffer_minutes", 15),
        "Varış payı",
        nullable=False,
    )
    travel = [_minutes(item, "Yol süresi") for item in raw_travel]
    stops: list[dict] = []
    fixed: list[int | None] = []
    durations: list[int | None] = []
    ids: set[str] = set()
    for raw in raw_stops:
        stop = _object(
            raw,
            {"id", "label", "arrival", "duration_minutes"},
            {"id", "label", "arrival", "duration_minutes"},
            "Durak",
        )
        identifier = stop["id"]
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
            raise ValueError("Durak kimliği 1–64 harf, rakam, tire veya alt çizgi olmalı.")
        if identifier in ids:
            raise ValueError("Her durağın kimliği farklı olmalı.")
        ids.add(identifier)
        label = stop["label"]
        if (not isinstance(label, str) or not 1 <= len(label.strip()) <= 120
                or any(ord(char) < 32 or ord(char) == 127 for char in label)):
            raise ValueError("Durak adı 1–120 görünür karakter olmalı.")
        fixed.append(_arrival(stop["arrival"]))
        durations.append(_minutes(stop["duration_minutes"], "Durak süresi"))
        stops.append({
            "id": identifier,
            "label": label.strip(),
            "arrival": stop["arrival"],
            "duration_minutes": durations[-1],
            "planned_arrival": stop["arrival"],
            "planned_departure": None,
        })

    legs = [{
        "from_id": stops[index]["id"],
        "to_id": stops[index + 1]["id"],
        "minutes": minutes,
        "latest_departure": None,
        "slack_minutes": None,
    } for index, minutes in enumerate(travel)]
    missing: list[str] = []
    conflicts: list[str] = []
    notes = [
        "Yol süreleri sizin girdiğiniz tahminlerdir; canlı trafik kullanılmadı.",
        f"Sabit hedeflere {buffer} dakika erken varış payı ayrılır; randevu saatleri korunur.",
        "Hesap yalnız seçilen gün içindir; sonraki güne taşan planı ayrıca düzenleyin.",
    ]
    if fixed[0] is None:
        missing.append(f"{stops[0]['label']}: planın başlangıç saatini girin.")
    for index, duration in enumerate(durations[:-1]):
        if duration is None:
            missing.append(f"{stops[index]['label']}: kalış süresini girin.")
    for index, minutes in enumerate(travel):
        if minutes is None:
            missing.append(
                f"{stops[index]['label']} → {stops[index + 1]['label']}: yol süresini girin."
            )

    previous_fixed: tuple[int, int] | None = None
    for index, appointment in enumerate(fixed):
        if appointment is None:
            continue
        if previous_fixed is not None and appointment < previous_fixed[1]:
            previous_label = stops[previous_fixed[0]]["label"]
            conflicts.append(
                f"{stops[index]['label']} saati, önceki sabit durak {previous_label} saatinden erken."
            )
        previous_fixed = index, appointment
        duration = durations[index]
        if duration is not None and appointment + duration >= 1440:
            conflicts.append(f"{stops[index]['label']} için kalış süresi seçilen günü aşıyor.")

    result = {
        "status": "needs_input",
        "date": day,
        "stops": stops,
        "legs": legs,
        "missing": missing,
        "conflicts": conflicts,
        "notes": notes,
        "basis": "manual_estimates",
        "traffic_live": False,
    }
    if missing:
        # Missing minutes can only increase the time needed. Use zero solely
        # as a lower bound to expose conflicts that no missing value can fix;
        # never return these provisional times as a plan or departure claim.
        # An unknown first start is bounded by the beginning of this day.
        earliest = fixed[0] if fixed[0] is not None else 0
        for index, stop in enumerate(stops):
            if index:
                earliest += (durations[index - 1] or 0) + (travel[index - 1] or 0)
                appointment = fixed[index]
                if appointment is not None:
                    deficit = earliest - (appointment - buffer)
                    if deficit > 0:
                        conflicts.append(
                            f"{stop['label']} için bilinen süreler ve varış payı bile "
                            f"sabit saate sığmıyor; en az {deficit} dakika eksik."
                        )
                    earliest = appointment
            end = earliest + (durations[index] or 0)
            if earliest >= 1440 or end >= 1440:
                conflicts.append(
                    f"{stop['label']} için bilinen süreler bile seçilen günü aşıyor."
                )
        result["conflicts"] = list(dict.fromkeys(conflicts))
        if conflicts:
            result["status"] = "conflict"
        return result

    arrivals: list[int | None] = [None] * len(stops)
    departures: list[int | None] = [None] * len(stops)
    for index, stop in enumerate(stops):
        appointment = fixed[index]
        if index == 0:
            arrivals[index] = appointment
        else:
            predicted = departures[index - 1] + travel[index - 1]
            if appointment is not None:
                deadline = appointment - buffer
                if predicted > deadline:
                    deficit = predicted - deadline
                    conflicts.append(
                        f"{stop['label']} için sabit saat ve varış payı korunamıyor; "
                        f"en az {deficit} dakika eksik."
                    )
                # Waiting is permitted; the appointment itself never shifts.
                arrivals[index] = appointment
            else:
                arrivals[index] = predicted
        duration = durations[index]
        if duration is not None:
            departures[index] = arrivals[index] + duration
        if arrivals[index] >= 1440 or (departures[index] is not None and departures[index] >= 1440):
            issue = f"{stop['label']} için hesaplanan zaman seçilen günü aşıyor."
            if issue not in conflicts:
                conflicts.append(issue)
        stop["planned_arrival"] = _clock(arrivals[index])
        stop["planned_departure"] = _clock(departures[index])

    latest_starts: list[int | None] = [None] * len(stops)
    latest_starts[-1] = fixed[-1]
    for index in range(len(stops) - 2, -1, -1):
        next_start = latest_starts[index + 1]
        if next_start is not None:
            deadline = next_start - (buffer if fixed[index + 1] is not None else 0)
            latest_departure = deadline - travel[index]
            legs[index]["latest_departure"] = _clock(latest_departure)
            legs[index]["slack_minutes"] = latest_departure - departures[index]
            if latest_departure < 0:
                conflicts.append(
                    f"{stops[index]['label']} için gereken çıkış seçilen günün öncesine düşüyor."
                )
            latest_starts[index] = (
                fixed[index] if fixed[index] is not None
                else latest_departure - durations[index]
            )
        else:
            latest_starts[index] = fixed[index]
    if fixed[-1] is None:
        notes.append("Son durak esnek; sonraki sabit hedef olmadığı yerde en geç çıkış hesaplanmaz.")
    # Different checks can discover the same infeasibility. Keep one message per text.
    result["conflicts"] = list(dict.fromkeys(conflicts))
    result["status"] = "conflict" if conflicts else "feasible"
    return result
