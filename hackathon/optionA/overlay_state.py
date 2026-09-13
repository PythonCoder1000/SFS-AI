"""
overlay_state.py -- pushes a small JSON snapshot of the current pilot
cycle over TCP to the standalone Swift overlay app (hackathon/overlay/
JudgmentOverlay), for the fullscreen HUD Christian demos to judges.
Pure side-effecting write, no decision logic -- mirrors the "boundary
tracing, not decision-making" convention the rest of this project's
@weave.op() wrappers already follow.

2026-09-13 LATER SAME DAY rewrite (Christian's explicit request):
replaced the original file-write-and-poll design with a direct TCP
push -- same reasoning as this project's own TCP rewrite for game
commands (TCP_REWRITE_LOG.md: ~9x faster than file-protocol polling,
no disk I/O latency). JudgmentOverlay.swift now runs a small TCP
listener (it's the long-lived process across a whole demo session);
this module is the client, connecting fresh each time pilot_loop.py
runs and pushing one newline-delimited JSON object per write. The
connection is lazy and self-healing: any send/connect failure just
drops that cycle's overlay update (never affects flight control --
callers in pilot_loop.py already wrap every call here in a broad
try/except) and the next call reconnects fresh.

2026-09-13 EVEN LATER SAME DAY (Christian's explicit request): bar
order is fixed to the menu's own definition order instead of being
re-sorted by probability every cycle (was causing bars to visibly swap
position cycle to cycle -- only the highlighted/chosen bar should
move). throttle_score's bar order is additionally reversed to read
high-throttle-on-top / low-throttle-on-bottom, like a vertical gauge.
Confidence and the guardrail's real reject-threshold are now both sent
per judgment, for the overlay to show next to ACCEPT/REJECT.
"""
import json
import socket
import time
from typing import Optional

from guardrail import QUESTION_CLASS, BANDS, effective_confidence  # noqa: E402 -- so the
# threshold shown on the overlay can never drift from what guardrail.py
# actually gates on.

OVERLAY_HOST = "127.0.0.1"
OVERLAY_PORT = 47822
_CONNECT_TIMEOUT_S = 0.3

_sock: Optional[socket.socket] = None
# Local cache of the last full state pushed -- write_overlay_status_only
# needs this to resend a complete object with just `status` changed
# (the overlay is a pure receiver now, no file to read back and merge
# against the way the old design did).
_last_state: dict = {}

# Human-readable labels for throttle_score's continuous anchor points --
# mirrors THROTTLE_SCORE_LEVELS in menus.py (kept as a plain local copy,
# not imported, so this module has zero dependency on menus.py's own
# import chain -- purely cosmetic labeling, not decision logic).
# Index order matches the real score scale (0=cut .. 5=increase_large) --
# used to resolve `chosen` from a score, and to look up each label's
# real probability regardless of how it's displayed.
THROTTLE_SCORE_LABELS_BY_INDEX = ["cut", "decrease_large", "decrease_small",
                                  "hold", "increase_small", "increase_large"]
THROTTLE_SCORE_INDEX_BY_LABEL = {lbl: i for i, lbl in enumerate(THROTTLE_SCORE_LABELS_BY_INDEX)}
# Display order for the overlay's bars -- HIGH throttle on top, LOW on
# bottom (Christian's explicit request: reads like a vertical gauge,
# reverse of the underlying low-to-high score scale).
THROTTLE_SCORE_DISPLAY_ORDER = list(reversed(THROTTLE_SCORE_LABELS_BY_INDEX))


def _get_socket() -> socket.socket:
    global _sock
    if _sock is not None:
        return _sock
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(_CONNECT_TIMEOUT_S)
    s.connect((OVERLAY_HOST, OVERLAY_PORT))
    s.settimeout(None)  # blocking sends after connect -- payloads are tiny JSON
    _sock = s
    return _sock


def _send_json(obj: dict) -> None:
    """Sends one JSON object, newline-delimited, over the persistent TCP
    connection to the overlay app. Raises on any failure -- callers
    catch broadly (pilot_loop.py) and treat that as "overlay not
    connected this cycle", same fail-open behavior as the old file-write
    path had for a failed write."""
    global _sock
    data = (json.dumps(obj) + "\n").encode("utf-8")
    try:
        sock = _get_socket()
        sock.sendall(data)
    except OSError:
        if _sock is not None:
            try:
                _sock.close()
            except OSError:
                pass
        _sock = None
        raise


def _judgment_from_answer(name: str, label: str, question_text: str,
                           answer, gate_result, relevant: bool,
                           canonical_order: list, threshold: float) -> dict:
    """Builds one JUDGMENTS-panel entry the overlay renders as a bar
    group, from one menu's raw tsAI answer + its guardrail GateResult.
    `relevant` reflects pilot_loop.py's own phase-gating (e.g.
    launch_decision only matters during PAD_IDLE) -- the panel is still
    shown either way (Christian's explicit request), the overlay just
    greys it out when not relevant rather than hiding it.

    `canonical_order` fixes each bar's position (Christian's explicit
    request) -- options used to be sorted by probability each cycle,
    which reshuffled bar positions as scores drifted cycle to cycle.
    Now only the highlighted (chosen) bar moves; label positions stay
    put. `threshold` is the guardrail's real reject_below for this
    question's class, so the overlay can show it next to ACCEPT/REJECT."""
    if answer is None:
        return {"name": name, "label": label, "question": question_text,
                "options": [], "chosen": None, "confidence": 0.0,
                "accepted": False, "band": "miss", "reason": "no answer this cycle",
                "relevant": relevant, "threshold": threshold}

    probabilities = answer.get("probabilities") or {}
    if "score" in answer:
        chosen_idx = round(max(0.0, min(5.0, answer.get("score", 0.0))))
        chosen = THROTTLE_SCORE_LABELS_BY_INDEX[chosen_idx]
        options = [{"label": lbl,
                     "value": probabilities.get(str(THROTTLE_SCORE_INDEX_BY_LABEL[lbl]), 0.0)}
                   for lbl in canonical_order]
    else:
        chosen = answer.get("choice")
        options = [{"label": key, "value": probabilities.get(key, 0.0)}
                   for key in canonical_order]

    # The confidence shown MUST be the one the guardrail actually gated
    # on -- for throttle_score that's the pooled directional confidence
    # (guardrail.effective_confidence), not the raw native `confidence`
    # field, which can and does diverge from it (Christian's explicit
    # bug report: ACCEPT/REJECT didn't match the displayed number).
    display_confidence = effective_confidence(name, answer)

    return {
        "name": name, "label": label, "question": question_text,
        "options": options, "chosen": chosen,
        "confidence": display_confidence,
        "accepted": gate_result.accepted if gate_result else False,
        "band": gate_result.band if gate_result else "miss",
        "reason": gate_result.reason if gate_result else "no answer this cycle",
        "relevant": relevant,
        "threshold": threshold,
    }


def _canonical_order_for(qname: str, menu_def: dict) -> list:
    """The fixed bar order for a menu, taken from the menu's own
    definition (or a deliberate display-order override, e.g.
    throttle_score's gauge ordering) rather than from any single
    cycle's answer -- this is what keeps bar position stable across
    cycles (see _judgment_from_answer's docstring)."""
    if qname == "throttle_score":
        return THROTTLE_SCORE_DISPLAY_ORDER
    criteria = menu_def.get("criteria")
    if isinstance(criteria, dict):
        return list(criteria.keys())
    return []


def _threshold_for(qname: str) -> float:
    """The real reject_below threshold guardrail.py gates this question
    on -- read from guardrail.py's own BANDS/QUESTION_CLASS rather than
    hardcoded here, so it can never silently drift out of sync."""
    question_class = QUESTION_CLASS.get(qname, "routine")
    return BANDS[question_class]["reject_below"]


def write_overlay_state(*, status: str, cycle_id: int, t: float, phase: str,
                         mission_target: dict, answers: dict, gate_results: dict,
                         menus: dict, commanded_throttle: float,
                         commanded_turn_axis: float, watchdog_tag: str) -> None:
    """Called once per cycle from pilot_loop.py's run_cycle(), plus once
    more at run start (status='active') and run end (status='ended').
    Never raises on the caller's behalf beyond what _send_json raises --
    caller wraps this in a broad try/except, same as before."""
    global _last_state
    panels = []
    panel_specs = [
        ("launch_decision", "LAUNCH"), ("throttle_score", "THROTTLE"),
        ("pitch_action", "PITCH"), ("stage_check", "STAGE"),
        ("task_status", "TASK"),
    ]
    for qname, label in panel_specs:
        if qname not in menus:
            continue
        # Always show every panel (Christian's explicit request) --
        # `relevant` still reflects pilot_loop.py's own phase-gating
        # (see build_cycle_state) so the Swift app can grey out
        # whichever of launch_decision/throttle_score doesn't apply to
        # the current phase, instead of hiding it outright.
        if qname == "launch_decision":
            relevant = (phase == "PAD_IDLE")
        elif qname == "throttle_score":
            relevant = (phase != "PAD_IDLE")
        else:
            relevant = True
        question_text = menus[qname].get("instructions", "")[:160]
        canonical_order = _canonical_order_for(qname, menus[qname])
        threshold = _threshold_for(qname)
        panels.append(_judgment_from_answer(
            qname, label, question_text, answers.get(qname), gate_results.get(qname),
            relevant, canonical_order, threshold))

    state = {
        "status": status,
        "cycle_id": cycle_id,
        "t": round(t, 1),
        "phase": phase,
        "mission_target": mission_target,
        "commanded": {"throttle": round(commanded_throttle, 3),
                      "turn_axis": round(commanded_turn_axis, 3)},
        "watchdog_tag": watchdog_tag,
        "judgments": panels,
        "written_at": time.time(),
    }
    _last_state = state
    _send_json(state)


def write_overlay_status_only(status: str) -> None:
    """Cheap start/end marker push (run start before the first real
    cycle, and run end in the finally block) -- resends the last full
    state with just `status` (and a fresh timestamp) changed, so the
    overlay doesn't flash back to an empty panel set right as the run
    ends."""
    global _last_state
    payload = dict(_last_state)
    payload["status"] = status
    payload["written_at"] = time.time()
    _last_state = payload
    _send_json(payload)
