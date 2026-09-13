# SFS AI — Option A Build Spec: tsAI as Pilot
### Self-contained. Machine-readable. Written for an executing Claude agent.

Read this entire document before writing any code. Every checkpoint has an
explicit exit condition — do not proceed past a failed checkpoint. If a
checkpoint fails, stop and report which one and why; do not improvise past it.

Repo root: `/Users/christianjin/Documents/VSCode/SFS AI`
Remote: `https://github.com/PythonCoder1000/SFS-AI.git`, branch `optionA-autonomous-build`.
Working area for this build: `SFS AI/hackathon/`.

You are running unattended. The user is AFK and cannot answer questions.
Do not stop to ask for clarification — make the most reasonable choice
consistent with this document, log it clearly in your commit messages and
in a running `hackathon/BUILD_LOG.md`, and keep going. If you hit a true
blocker (a checkpoint's exit condition cannot be met after real attempts),
stop, write exactly what's blocking you and what you tried to
`hackathon/BUILD_LOG.md`, commit and push, and end the session rather than
guessing further or leaving uncommitted work.

Commit after every checkpoint, not just at the end. Push after every
commit. This is the only way the user can see progress while away.

---

## Checkpoint 0 — Safety commit (already done, do not repeat)

Already committed as `checkpoint 0: snapshot before Option A (tsAI-as-pilot)
autonomous build` on this branch. Confirm with `git log --oneline -5`
before starting Checkpoint 1.

---

## 1. What already exists (do not rebuild)

- **`agent_interface.py`**: `observe()`, `act(command, allow_full_authority=False)`
  (hard clamps: max turn 0.5/call, max throttle step 0.3/call), `predict(state,
  waypoints, duration_s)` (forward-sim, returns `confidence: "high"|"low"`).
- **`sfsprobe`**: C# mod, MCP tools for live telemetry read + command send,
  file-polling IPC under the hood.
- **Physics**: gravity, thrust, drag, aero torque, gimbal, staging — all
  IL-confirmed, validated formulas already available for delta-v and
  turn-rate/torque calculations.
- **Known catastrophic failure mode**: blanket `ignite` on a multi-stage
  rocket destroys it. Stages must be armed via `stage <index>`, in order.
  **`ignite` (or any equivalent blanket-fire command) must never appear as
  an option in any menu built below. Not filtered after the fact — never
  present in the vocabulary at all.**

## 2. What changed — the architecture this spec builds

**tsAI is the pilot.** Every flight-control decision (throttle, pitch,
staging) each cycle is answered by TypeSafe's `jev-latest` model via
`POST https://api.typesafe.ai/v1/systemone`, as a `choice` question over a
fixed, safe-by-construction menu. A deterministic layer computes
*information* (feasibility bounds, `predict()` output) and feeds it into
tsAI's `state` — it does not decide anything and does not override tsAI's
answer once that answer clears the guardrail below.

```
observe() ──┬──► predict() ──► residual vs. last prediction
            │
            ├──► delta-v budget check (Tsiolkovsky, current mass/fuel/ISP)
            ├──► turn-rate bound (α_max = τ_max / I, using confirmed gimbal/RCS torque)
            │
            ▼
    enriched state (§5) ──► ONE /v1/systemone call per cycle,
                             bundling throttle_action + pitch_action +
                             (stage_check when relevant) as parallel questions
            │
            ▼
    GUARDRAIL (§4/§5) — confidence bands, insufficient_data check,
                         pre-vetted joint-action safety
            │
       accept │ reject/miss
            │        │
            ▼        ▼
          act()   watchdog fallback (§6)
```

## 3. tsAI API reference (confirmed live already — do not re-verify, use directly)

- `POST https://api.typesafe.ai/v1/systemone`, header
  `Authorization: Bearer $TYPESAFE_AI_API_KEY` (already in `.env` in this
  repo), `Content-Type: application/json`.
- Body: `{"model": "jev-latest", "state": <any JSON>, "questions": {<name>: <question>}}`.
- Question types:
  - `choice`: `{"type":"choice","instructions":str,"criteria":{option_name: description, ...}}`
    → returns `{"choice": str, "confidence": 0-1, "probabilities": {opt: p, ...}}`
  - `noul`: `{"type":"noul","instructions":str}` → returns `{"noul": 0-1}`.
    **No `confidence` field exists on `noul` answers — confirmed both in
    vendor docs and empirically. Never write code that reads
    `answer.confidence` on a `noul` result.**
  - `score`: `{"type":"score","instructions":str,"criteria":[level0,level1,...]}`
    → returns `{"score": float, "confidence": 0-1, "probabilities": {...}}`.
- **Questions in one call run in parallel and cannot see each other's
  answers.** (Vendor-confirmed.) Never assume throttle_action and
  pitch_action reasoned about each other — safety must be pre-vetted across
  their combination, not assumed coherent at call time. See §4.3.
- Rate limit: empirically clean at ~4 calls/sec sustained (210/210, zero
  429s over 52s); vendor-confirmed verbal ceiling ~20 calls/sec, sequential
  calling "basically never" hits it. Not a concern at any planned cadence.
- Determinism: same input produces the same top choice reliably;
  probabilities vary only ±0.03–0.05 call to call. Not a source of
  chattering.
- Vendor guidance confirmed live at `docs.typesafe.ai` (fetch
  `https://docs.typesafe.ai/confidence.md` and
  `https://docs.typesafe.ai/primitives/choice.md` directly if anything
  below is unclear — this is real, current documentation, verified
  reachable).

## 4. Guardrail design

### 4.1 Confidence bands

Vendor's own documented pattern (`docs.typesafe.ai/confidence.md`): three
bands — high confidence: act automatically; medium: proceed with caution;
low: do not act. Vendor's own example uses `<0.5` as the universal "don't
guess" floor, explicitly stating thresholds must be adapted to domain and
stakes.

**This project's adapted bands** (inference, grounded in real testing —
not copied blindly from the vendor's banking-chatbot example):

| Question class | Reject (`insufficient_data`, or below) | Act with extra scrutiny | Act normally |
|---|---|---|---|
| `throttle_action`, `pitch_action` (`choice`) | `confidence < 0.5` | `0.5 ≤ confidence < 0.7` — act, but log as medium-confidence and require the feasibility check (§4.2) to pass with margin, not just pass | `confidence ≥ 0.7` |
| `stage_now` / any irreversible action (`choice` or `noul`) | `< 0.7` reject | `0.7 ≤ x < 0.9` — require feasibility check to pass with margin | `≥ 0.9` (vendor's own "destructive operation" band) |
| `noul` questions generally | Use `abs(noul − 0.5) × 2` as the confidence analog (no native field exists) — same bands as above by class |

**Why 0.7/0.5 rather than the vendor's flat 0.5:** real testing put good,
correct decisions across a 0.5–0.9 range depending on situation clarity —
a flat 0.5 floor would pass through some answers this project has no way
to double-check afterward (no human in the loop, unlike the vendor's
example). The stricter band is a deliberate adaptation, not a vendor
requirement — revisit if it proves too conservative in dry runs, and note
in `BUILD_LOG.md` if you do.

### 4.2 Feasibility check (unchanged from prior physics work, still required)

Before any accepted `choice` becomes a real command: verify it against
- delta-v budget (Tsiolkovsky, current mass/fuel/ISP — already-confirmed physics)
- turn-rate bound (`α_max = τ_max / I`, using confirmed gimbal/RCS torque values)

If the chosen action fails this check even though it cleared the
confidence band, treat it as a rejection (§6), not a silent override —
log which check failed.

### 4.3 Menu design rules — apply to every `choice` question built

1. **Every menu must include an explicit `insufficient_data` option**
   whenever "no supported action" is physically possible. Phrasing
   (vendor-aligned, tested to work): *"The supplied current state
   lacks, has stale, or has contradictory information required to
   distinguish the operational choices. Select this only when no
   operational choice is supported — not merely because two supported
   choices are close."* Do not phrase it as "I don't know" (weaker,
   vendor/literature-confirmed) — use a "none of the above"-style framing.
   Do not make it sound like the safest/easiest option (risk of
   over-selection).
2. **Never include a catastrophic option in any menu** (§1 — pre-shielding,
   not runtime filtering). This is the single hardest safety property of
   this architecture and it is non-negotiable.
3. **Menu completeness**: after excluding catastrophic options, verify
   with `predict()` (offline, at design time) that at least one remaining
   option keeps the mission goal reachable from realistic states — an
   over-pruned menu that traps the pilot with no good option is its own
   failure mode.
4. **Joint-action safety across one cycle's bundled questions is your
   responsibility, not tsAI's** (§3 — questions don't see each other).
   Before shipping the menus, enumerate the Cartesian product of
   throttle_action × pitch_action × stage_now outcomes and confirm no
   combination is unsafe even though each option looks fine in isolation.
   Use `predict()` to check this offline before the live build, not live
   per-cycle (too slow, and the point is to have pre-vetted it).
5. Never wire a raw `noul` or `score` value directly to an irreversible
   command. Map it through the same pre-vetted, bounded menu vocabulary
   as `choice` — e.g., a `score` on "how aggressive should this correction
   be" still selects from a small pre-defined set of bounded corrections,
   not an arbitrary continuous value.

## 5. Per-cycle state schema (fed to tsAI)

```json
{
  "cycle_id": 418,
  "t": 93.9,
  "phase": "ASCENT_GRAVITY_TURN",
  "mission_target": {"apoapsis_m": 100000, "periapsis_m": 90000},
  "vehicle": {
    "altitude_m": 18420, "vertical_speed_mps": 612, "horizontal_speed_mps": 485,
    "angle_deg": 61.2, "angular_rate_dps": -1.8, "throttle": 0.83,
    "active_stage": 0, "fuel_remaining_pct": 55
  },
  "feasibility": {
    "delta_v_remaining_mps": 1800,
    "delta_v_required_for_target_mps": 1550,
    "max_angular_accel_dps2": 12.4
  },
  "prediction": {
    "confidence": "high", "horizon_s": 15,
    "terminal_error": {"altitude_m": -1260, "speed_mps": -94}
  },
  "note": "Include phase and mission_target on every call — omitting them measurably increases ambiguity and lowers confidence on otherwise-clear decisions."
}
```

One `/v1/systemone` call per cycle, bundling all of that cycle's
questions (`throttle_action`, `pitch_action`, and `stage_check` when
relevant) against this one state object — per vendor guidance on
parallel evaluation and to conserve rate-limit headroom (not that it's
needed, but it's free).

## 6. Watchdog / fallback

- **1 missed cycle** (timeout, malformed response, or state went stale
  before the response arrived — check response timestamp against a
  freshness threshold, per vendor guidance to "check freshness before
  applying a result to a changed situation"): hold the last accepted
  bounded throttle/pitch command for exactly this one cycle. Do not
  re-issue a stage command from a stale response — staging must be
  edge-triggered/idempotent (see below), never replayed.
- **2 consecutive misses**: degrade to a pre-declared deterministic
  safe-hold (attitude-hold, throttle frozen or reduced per the current
  phase's own safe default) until tsAI responds again. This number (2) is
  a conservative placeholder — there was no time to compute a real
  Fault-Tolerant-Time-Interval for this vehicle; tighten or loosen it
  after a real dry run if 2 proves too twitchy or too slow, and log the
  change and why in `BUILD_LOG.md`.
- **Staging commands specifically**: implement as edge-triggered
  (fire-once, tracked by a command ID the mod acknowledges) so a
  duplicate/replayed command from a retried or stale call cannot
  double-fire a stage. This is a distinct, more dangerous failure mode
  than holding a continuous value — treat it accordingly.

## 7. Build checkpoints — commit and push after each one

### Checkpoint 1 — tsAI client + menu library, no live game
- [ ] Thin client wrapping `/v1/systemone` (auth from `.env`, timeout,
      response-freshness timestamp check).
- [ ] Menu definitions for `throttle_action`, `pitch_action`, `stage_check`
      — each including `insufficient_data`, each excluding any
      catastrophic option, each reviewed against §4.3 point 4 (Cartesian
      product safety) on paper before coding continues.
- **Exit:** unit-test the client against a handful of the real states from
  `hackathon/manual_flight_log.jsonl` (real telemetry) and confirm sane,
  bounded output for each — no live game needed yet.
- **Commit message:** `checkpoint 1: tsAI client + menus`

### Checkpoint 2 — Feasibility + confidence gate
- [ ] Delta-v budget check, turn-rate bound check (§4.2).
- [ ] Confidence-band logic (§4.1) with the class-specific thresholds.
- **Exit:** feed the gate a deliberately low-confidence and a deliberately
  infeasible synthetic answer; confirm both are rejected with a logged,
  typed reason (not silently passed).
- **Commit message:** `checkpoint 2: feasibility + confidence gate`

### Checkpoint 3 — Watchdog + staging idempotency
- [ ] Miss-counting, hold-last-command, degrade-after-2 logic (§6).
- [ ] Edge-triggered staging command implementation.
- **Exit:** simulate a dropped response and a duplicate response in
  isolation (mocked, no live game) and confirm: dropped → hold-then-degrade
  correctly; duplicate → stage does not double-fire.
- **Commit message:** `checkpoint 3: watchdog + staging idempotency`

### Checkpoint 4 — Wire into `agent_interface.py` / `sfsprobe`, live dry run
- [ ] Full loop: `observe()` → enriched state → tsAI call → guardrail →
      `act()`/`stage()`.
- **Exit:** one real short live flight where tsAI is genuinely making
  every throttle/pitch decision, guardrail visibly rejects at least one
  low-confidence or infeasible answer during the run (induce one if
  needed — don't just hope for a clean run with nothing to show), and the
  flight reaches a stable state or a controlled safe-hold, not a crash
  from an unhandled case. If a live SFS session cannot be reached
  unattended, fall back to the richest available offline replay
  (`hackathon/manual_flight_log.jsonl` or the `analysis/telemetry_flat_*`
  files) driving the same loop end-to-end, note this substitution clearly
  in `BUILD_LOG.md`, and treat it as the checkpoint's exit condition
  instead.
- **Commit message:** `checkpoint 4: live loop wired, dry run complete`

### Checkpoint 5 — Wrap-up
- [ ] Update `hackathon/BUILD_LOG.md` with a clear summary: what got
      built, what got tested, what's still a placeholder (§8), and any
      deviations from this spec and why.
- [ ] Final commit and push.
- **Commit message:** `checkpoint 5: Option A build complete, see BUILD_LOG.md`

## 8. Known open gaps — do not re-research, just be aware

- The "2 consecutive misses" watchdog threshold is a placeholder, not a
  computed FTTI. If there's time after Checkpoint 4, tighten it using
  real observed miss behavior from the dry run.
- No formal calibration set exists for the confidence bands in §4.1 —
  they're grounded in a real but modest sample of test results, not a
  rigorous statistical guarantee. Treat them as a good starting point to
  adjust from, per the vendor's own explicit guidance to do exactly that.
- `trust_prediction`-style calibration (how much tsAI should weight a
  low-vs-high-confidence `predict()` forecast) showed a real but moderate
  separation (0.1–0.45 low-confidence vs. 0.64–0.72 high-confidence
  cluster) — not sharp. Don't design anything that depends on tsAI
  perfectly discounting a bad forecast; the feasibility check (§4.2) is
  the actual backstop for that, not tsAI's own judgment about the
  predictor.
