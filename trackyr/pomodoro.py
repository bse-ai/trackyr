"""Pomodoro timer state machine."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func

from trackyr.db.engine import get_session
from trackyr.db.models import ActivitySample, PomodoroRecord, PomodoroTimer
from trackyr.utils import day_bounds, today as _today

log = logging.getLogger(__name__)

# Statuses that mean a timer is NOT active
_INACTIVE_STATUSES = ("idle", "completed")

# Statuses that can be paused
_PAUSABLE_STATUSES = ("work", "short_break", "long_break")


def _get_active_timer(session):
    """Return the currently active PomodoroTimer or None."""
    return (
        session.query(PomodoroTimer)
        .filter(PomodoroTimer.status.notin_(_INACTIVE_STATUSES))
        .order_by(PomodoroTimer.id.desc())
        .first()
    )


def _detect_primary_app(session, started_at: datetime, ended_at: datetime) -> str | None:
    """Find the most common non-idle process during a time period."""
    try:
        result = (
            session.query(
                ActivitySample.process_name,
                func.count(ActivitySample.id).label("cnt"),
            )
            .filter(
                ActivitySample.sampled_at >= started_at,
                ActivitySample.sampled_at <= ended_at,
                ActivitySample.is_idle.is_(False),
                ActivitySample.process_name.isnot(None),
            )
            .group_by(ActivitySample.process_name)
            .order_by(func.count(ActivitySample.id).desc())
            .first()
        )
        return result[0] if result else None
    except Exception:
        log.debug("Could not detect primary app for Pomodoro phase", exc_info=True)
        return None


def _timer_to_dict(timer) -> dict:
    """Convert a PomodoroTimer to a response dict."""
    now = datetime.now(timezone.utc)
    remaining = None
    if timer.phase_ends_at and timer.status not in ("idle", "completed", "paused"):
        remaining = max(0, int((timer.phase_ends_at - now).total_seconds()))

    return {
        "active": timer.status not in _INACTIVE_STATUSES,
        "status": timer.status,
        "label": timer.label,
        "phase_started_at": timer.phase_started_at.isoformat() if timer.phase_started_at else None,
        "phase_ends_at": timer.phase_ends_at.isoformat() if timer.phase_ends_at else None,
        "seconds_remaining": remaining,
        "pomodoro_count": timer.pomodoro_count,
        "interruption_count": timer.interruption_count,
        "timer_id": timer.id,
        "work_minutes": timer.work_minutes,
        "short_break_minutes": timer.short_break_minutes,
        "long_break_minutes": timer.long_break_minutes,
    }


def _idle_dict() -> dict:
    """Return an idle status dict when no timer is active."""
    return {
        "active": False,
        "status": "idle",
        "label": None,
        "phase_started_at": None,
        "phase_ends_at": None,
        "seconds_remaining": None,
        "pomodoro_count": 0,
        "interruption_count": 0,
        "timer_id": None,
        "work_minutes": None,
        "short_break_minutes": None,
        "long_break_minutes": None,
    }


def _advance_phase(timer, session) -> None:
    """Internal: advance the timer to the next phase after current phase ends.

    work -> record the work phase, then:
      if pomodoro_count % long_break_every == 0: status = "long_break"
      else: status = "short_break"
    break -> record the break phase, then: status = "work", pomodoro_count += 1

    Creates a PomodoroRecord for the completed phase.
    Sets new phase_started_at and phase_ends_at.
    """
    now = datetime.now(timezone.utc)
    old_status = timer.status
    phase_started = timer.phase_started_at
    phase_ended = timer.phase_ends_at or now

    # Detect primary app for the completed phase
    primary_app = _detect_primary_app(session, phase_started, phase_ended)

    # Record the completed phase
    record = PomodoroRecord(
        date=phase_started.date(),
        timer_id=timer.id,
        phase=old_status,
        started_at=phase_started,
        ended_at=phase_ended,
        completed=True,
        primary_app=primary_app,
    )
    session.add(record)

    # Determine the next phase
    if old_status == "work":
        # Increment pomodoro count after completing a work phase
        timer.pomodoro_count += 1

        if timer.pomodoro_count % timer.long_break_every == 0:
            timer.status = "long_break"
            duration = timedelta(minutes=timer.long_break_minutes)
        else:
            timer.status = "short_break"
            duration = timedelta(minutes=timer.short_break_minutes)
    else:
        # Coming back from a break -> start work
        timer.status = "work"
        duration = timedelta(minutes=timer.work_minutes)

    timer.phase_started_at = now
    timer.phase_ends_at = now + duration

    session.flush()


def start_timer(
    label: str | None = None,
    work_minutes: int = 25,
    short_break_minutes: int = 5,
    long_break_minutes: int = 15,
    long_break_every: int = 4,
) -> dict:
    """Start a new Pomodoro timer. Creates a PomodoroTimer row in 'work' status.

    Returns the timer state dict.
    If there's already an active timer (not idle/completed), return error.
    """

    session = get_session()
    try:
        # Check for an existing active timer
        existing = _get_active_timer(session)
        if existing is not None:
            return {
                "error": "A timer is already active.",
                "timer": _timer_to_dict(existing),
            }

        now = datetime.now(timezone.utc)
        timer = PomodoroTimer(
            label=label,
            status="work",
            work_minutes=work_minutes,
            short_break_minutes=short_break_minutes,
            long_break_minutes=long_break_minutes,
            long_break_every=long_break_every,
            phase_started_at=now,
            phase_ends_at=now + timedelta(minutes=work_minutes),
            pomodoro_count=0,
            interruption_count=0,
            paused_remaining_seconds=None,
        )
        session.add(timer)
        session.commit()
        log.info("Pomodoro timer started (id=%s, label=%s)", timer.id, label)
        return _timer_to_dict(timer)
    except Exception:
        session.rollback()
        log.exception("Failed to start Pomodoro timer")
        raise
    finally:
        session.close()


def get_status() -> dict:
    """Get the current timer status.

    Returns:
        A dict with keys: active, status, label, phase_started_at, phase_ends_at,
        seconds_remaining, pomodoro_count, interruption_count, timer_id.

    If no active timer, returns {"active": False, "status": "idle", ...}.
    """

    session = get_session()
    try:
        timer = _get_active_timer(session)
        if timer is None:
            return _idle_dict()

        # Check if the current phase has naturally ended
        now = datetime.now(timezone.utc)
        if (
            timer.phase_ends_at
            and timer.status in _PAUSABLE_STATUSES
            and now >= timer.phase_ends_at
        ):
            _advance_phase(timer, session)
            session.commit()

        return _timer_to_dict(timer)
    except Exception:
        session.rollback()
        log.exception("Failed to get Pomodoro status")
        raise
    finally:
        session.close()


def pause_timer() -> dict:
    """Pause the active timer. Only works if status is 'work', 'short_break', or 'long_break'.

    Saves the remaining time and sets status to 'paused'.
    """

    session = get_session()
    try:
        timer = _get_active_timer(session)
        if timer is None:
            return {"error": "No active timer to pause."}

        if timer.status not in _PAUSABLE_STATUSES:
            return {
                "error": f"Cannot pause timer in '{timer.status}' status. "
                         f"Must be one of: {', '.join(_PAUSABLE_STATUSES)}.",
                "timer": _timer_to_dict(timer),
            }

        now = datetime.now(timezone.utc)
        remaining = max(0, int((timer.phase_ends_at - now).total_seconds()))

        timer.paused_remaining_seconds = remaining
        timer.status = "paused"
        # Keep phase_started_at as-is for reference; clear phase_ends_at
        timer.phase_ends_at = None
        session.commit()

        log.info("Pomodoro timer paused (id=%s, remaining=%ds)", timer.id, remaining)
        return _timer_to_dict(timer)
    except Exception:
        session.rollback()
        log.exception("Failed to pause Pomodoro timer")
        raise
    finally:
        session.close()


def resume_timer() -> dict:
    """Resume a paused timer. Recalculates phase_ends_at based on saved remaining time."""

    session = get_session()
    try:
        timer = _get_active_timer(session)
        if timer is None:
            return {"error": "No active timer to resume."}

        if timer.status != "paused":
            return {
                "error": f"Timer is not paused (current status: '{timer.status}').",
                "timer": _timer_to_dict(timer),
            }

        now = datetime.now(timezone.utc)
        remaining = timer.paused_remaining_seconds or 0

        # Determine which phase we were in before pause by looking at the most
        # recent record and current pomodoro_count. Since we stored the status
        # as "paused", we need to figure out what to resume to. We can infer
        # from the paused_remaining_seconds relative to work/break durations,
        # but a simpler approach: store the pre-pause status. For now, we look
        # at the last PomodoroRecord to determine it. If there are no records
        # and pomodoro_count == 0, we're in the first work phase.
        last_record = (
            session.query(PomodoroRecord)
            .filter(PomodoroRecord.timer_id == timer.id)
            .order_by(PomodoroRecord.id.desc())
            .first()
        )

        if last_record is None:
            # First phase, must be work
            resumed_status = "work"
        elif last_record.phase == "work":
            # After work comes a break
            if timer.pomodoro_count % timer.long_break_every == 0 and timer.pomodoro_count > 0:
                resumed_status = "long_break"
            else:
                resumed_status = "short_break"
        else:
            # After a break comes work
            resumed_status = "work"

        timer.status = resumed_status
        timer.phase_started_at = now
        timer.phase_ends_at = now + timedelta(seconds=remaining)
        timer.paused_remaining_seconds = None
        session.commit()

        log.info(
            "Pomodoro timer resumed (id=%s, status=%s, remaining=%ds)",
            timer.id, resumed_status, remaining,
        )
        return _timer_to_dict(timer)
    except Exception:
        session.rollback()
        log.exception("Failed to resume Pomodoro timer")
        raise
    finally:
        session.close()


def skip_phase() -> dict:
    """Skip the current phase and advance to the next one.

    work -> short_break (or long_break if pomodoro_count % long_break_every == 0)
    short_break/long_break -> work (increments pomodoro_count)
    Records the skipped phase as completed=False in PomodoroRecord.
    """

    session = get_session()
    try:
        timer = _get_active_timer(session)
        if timer is None:
            return {"error": "No active timer to skip."}

        if timer.status not in _PAUSABLE_STATUSES:
            return {
                "error": f"Cannot skip phase in '{timer.status}' status.",
                "timer": _timer_to_dict(timer),
            }

        now = datetime.now(timezone.utc)
        old_status = timer.status
        phase_started = timer.phase_started_at

        # Record the skipped phase as incomplete
        record = PomodoroRecord(
            date=phase_started.date(),
            timer_id=timer.id,
            phase=old_status,
            started_at=phase_started,
            ended_at=now,
            completed=False,
            primary_app=None,  # Don't bother detecting app for skipped phases
        )
        session.add(record)

        # Advance to the next phase
        if old_status == "work":
            timer.pomodoro_count += 1
            if timer.pomodoro_count % timer.long_break_every == 0:
                timer.status = "long_break"
                duration = timedelta(minutes=timer.long_break_minutes)
            else:
                timer.status = "short_break"
                duration = timedelta(minutes=timer.short_break_minutes)
        else:
            # Break -> work
            timer.status = "work"
            duration = timedelta(minutes=timer.work_minutes)

        timer.phase_started_at = now
        timer.phase_ends_at = now + duration
        session.commit()

        log.info(
            "Pomodoro phase skipped (id=%s, %s -> %s)",
            timer.id, old_status, timer.status,
        )
        return _timer_to_dict(timer)
    except Exception:
        session.rollback()
        log.exception("Failed to skip Pomodoro phase")
        raise
    finally:
        session.close()


def stop_timer() -> dict:
    """Stop/abandon the current timer entirely. Sets status to 'completed'.
    Records any in-progress phase as completed=False.
    """

    session = get_session()
    try:
        timer = _get_active_timer(session)
        if timer is None:
            return {"error": "No active timer to stop."}

        now = datetime.now(timezone.utc)

        # Record the current in-progress phase as incomplete (if in a timed phase)
        if timer.status in _PAUSABLE_STATUSES and timer.phase_started_at:
            record = PomodoroRecord(
                date=timer.phase_started_at.date(),
                timer_id=timer.id,
                phase=timer.status,
                started_at=timer.phase_started_at,
                ended_at=now,
                completed=False,
                primary_app=None,
            )
            session.add(record)

        timer.status = "completed"
        timer.phase_ends_at = None
        session.commit()

        log.info("Pomodoro timer stopped (id=%s)", timer.id)
        return _timer_to_dict(timer)
    except Exception:
        session.rollback()
        log.exception("Failed to stop Pomodoro timer")
        raise
    finally:
        session.close()


def interrupt_timer() -> dict:
    """Record an interruption without stopping the timer. Increments interruption_count."""

    session = get_session()
    try:
        timer = _get_active_timer(session)
        if timer is None:
            return {"error": "No active timer to interrupt."}

        timer.interruption_count += 1
        session.commit()

        log.info(
            "Pomodoro interruption recorded (id=%s, total=%d)",
            timer.id, timer.interruption_count,
        )
        return _timer_to_dict(timer)
    except Exception:
        session.rollback()
        log.exception("Failed to record Pomodoro interruption")
        raise
    finally:
        session.close()


def _build_summary(target_date: date, session) -> dict:
    """Build a Pomodoro summary for a given date."""
    day_start, day_end = day_bounds(target_date)

    records = (
        session.query(PomodoroRecord)
        .filter(
            PomodoroRecord.started_at >= day_start,
            PomodoroRecord.started_at < day_end,
        )
        .order_by(PomodoroRecord.started_at)
        .all()
    )

    pomodoros_completed = 0
    pomodoros_interrupted = 0
    total_focus_seconds = 0.0
    total_break_seconds = 0.0
    total_interruptions = 0

    record_dicts = []
    for rec in records:
        duration = (rec.ended_at - rec.started_at).total_seconds() if rec.ended_at else 0.0

        if rec.phase == "work":
            if rec.completed:
                pomodoros_completed += 1
                total_focus_seconds += duration
            else:
                pomodoros_interrupted += 1
                # Still count partial focus time
                total_focus_seconds += duration
        elif rec.phase in ("short_break", "long_break"):
            total_break_seconds += duration

        record_dicts.append({
            "phase": rec.phase,
            "started_at": rec.started_at.isoformat() if rec.started_at else None,
            "ended_at": rec.ended_at.isoformat() if rec.ended_at else None,
            "completed": rec.completed,
            "primary_app": rec.primary_app,
        })

    # Count total interruptions from timers active on this date
    timer_ids = {rec.timer_id for rec in records}
    if timer_ids:
        timers = (
            session.query(PomodoroTimer)
            .filter(PomodoroTimer.id.in_(timer_ids))
            .all()
        )
        total_interruptions = sum(t.interruption_count for t in timers)

    return {
        "date": target_date.isoformat(),
        "pomodoros_completed": pomodoros_completed,
        "pomodoros_interrupted": pomodoros_interrupted,
        "total_focus_minutes": round(total_focus_seconds / 60.0, 1),
        "total_break_minutes": round(total_break_seconds / 60.0, 1),
        "total_interruptions": total_interruptions,
        "records": record_dicts,
    }


def get_today_summary() -> dict:
    """Summary of today's Pomodoro activity.

    Returns:
        A dict with date, pomodoros_completed, pomodoros_interrupted,
        total_focus_minutes, total_break_minutes, total_interruptions,
        and a list of records.
    """

    session = get_session()
    try:
        return _build_summary(_today(), session)
    except Exception:
        session.rollback()
        log.exception("Failed to get today's Pomodoro summary")
        raise
    finally:
        session.close()


def get_history(target_date: date) -> dict:
    """Get Pomodoro records for a specific date. Same format as today_summary."""

    session = get_session()
    try:
        return _build_summary(target_date, session)
    except Exception:
        session.rollback()
        log.exception("Failed to get Pomodoro history for %s", target_date)
        raise
    finally:
        session.close()
