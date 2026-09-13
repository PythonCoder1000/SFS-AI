"""
watchdog.py -- Checkpoint 3: miss-counting / hold-last / degrade-after-2
(sec 6) and edge-triggered staging idempotency. Pure state machine, no
network/game I/O -- pilot_loop.py (Checkpoint 4) drives it.
"""
from dataclasses import dataclass, field
from typing import Optional


# Placeholder threshold (sec 6 / sec 8: "not a computed FTTI" -- revisit
# after a real dry run if 2 proves too twitchy or too slow, logging the
# change in BUILD_LOG.md).
DEGRADE_AFTER_MISSES = 2


@dataclass
class CycleOutcome:
    """What the loop should actually command this cycle, after the
    watchdog has had a chance to override a missed/stale tsAI response."""
    throttle_choice: Optional[str]
    pitch_choice: Optional[str]
    degraded: bool          # True once 2+ consecutive misses forced safe-hold
    held_from_last: bool    # True on exactly 1 miss (holding last accepted command)


class Watchdog:
    """One instance per flight. `record_hit`/`record_miss` are called
    once per cycle by the loop; `resolve` decides what to actually
    command."""

    def __init__(self, degrade_after: int = DEGRADE_AFTER_MISSES):
        self.degrade_after = degrade_after
        self.miss_count = 0
        self._last_throttle_choice: Optional[str] = None
        self._last_pitch_choice: Optional[str] = None

    def record_hit(self, throttle_choice: str, pitch_choice: str) -> None:
        """Call when this cycle's tsAI response was accepted (passed the
        guardrail). Resets the miss streak and remembers the accepted
        continuous commands so a LATER miss has something to hold."""
        self.miss_count = 0
        self._last_throttle_choice = throttle_choice
        self._last_pitch_choice = pitch_choice

    def record_miss(self) -> None:
        """Call on timeout, malformed response, stale response, or a
        guardrail rejection with no safe substitute chosen this cycle."""
        self.miss_count += 1

    def resolve(self, safe_hold_throttle_choice: str, safe_hold_pitch_choice: str) -> CycleOutcome:
        """Sec 6 logic:
        - 0 misses: caller should use THIS cycle's live accepted answer
          directly, not this method (this method is only meaningful once
          record_miss() has been called at least once since the last hit).
        - 1 miss: hold the last accepted bounded throttle/pitch command
          for exactly this one cycle.
        - 2+ misses: degrade to the phase's pre-declared deterministic
          safe-hold default.
        """
        if self.miss_count == 0:
            return CycleOutcome(self._last_throttle_choice, self._last_pitch_choice,
                                 degraded=False, held_from_last=False)
        if self.miss_count < self.degrade_after:
            return CycleOutcome(self._last_throttle_choice, self._last_pitch_choice,
                                 degraded=False, held_from_last=True)
        return CycleOutcome(safe_hold_throttle_choice, safe_hold_pitch_choice,
                             degraded=True, held_from_last=False)


class StagingTracker:
    """Edge-triggered staging (sec 6): a stage index is fired AT MOST
    ONCE, tracked by that index itself as the command ID. A duplicate or
    replayed response that resolves to the SAME stage index (e.g. a
    stale response arriving after the real one already fired that stage)
    is a no-op, never a second `stage <index>` send. This is distinct
    from -- and strictly stricter than -- the continuous-command hold
    logic above: replaying a throttle/pitch hold is safe (bounded,
    reversible), replaying a stage command is not (irreversible,
    catastrophic if doubled per sec 1's known failure mode class)."""

    def __init__(self):
        self._fired_indices = set()

    def should_fire(self, stage_index: int) -> bool:
        """Returns True (and marks it fired) the first time this stage
        index is requested; False every time after, for that index."""
        if stage_index in self._fired_indices:
            return False
        self._fired_indices.add(stage_index)
        return True

    def has_fired(self, stage_index: int) -> bool:
        return stage_index in self._fired_indices
