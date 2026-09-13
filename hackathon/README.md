# SFS AI — CoreWeave Hacks Submission (Rocket Labs LLC)

**Team:** Christian Jin, Arthur Peng
**Event:** CoreWeave Hacks, Sept 12–13, 2026
**W&B/Weave project:** https://wandb.ai/chrisbobacats-rocket-labs-llc/sfs-ai-hackathon/weave

This file is the submission package for the hackathon judges — disclosure
of what's pre-existing vs. built this weekend, the architecture, sponsor
tool usage, a 3-minute demo script, and backup evidence in case the live
demo hits a snag. The code itself lives in this folder (`hackathon/`);
everything it calls into under `../analysis/` and `../sfsprobe/` is the
pre-existing backend described below.

## Disclosure — what predates the hackathon vs. what was built here

Per the event's eligibility rule ("you must be clear on what was
previously built, and you will only be evaluated on the hackathon
work"):

**Pre-existing (built over several prior weeks, NOT part of this
submission):**
- `sfsprobe/` — a custom reflection-based C# mod that bridges Spaceflight
  Simulator (a game with no existing agent SDK, unlike e.g. Kerbal Space
  Program's kRPC) to an external process via a file-protocol command
  channel.
- `sfsprobe_mcp/` — a Python MCP server wrapping that mod's commands for
  live game control and telemetry analysis.
- `analysis/forward_sim.py`, `analysis/sfs_telemetry.py` — validated,
  live-tested physics formulas (gravity, drag, thrust, rotation,
  staging, heat, RCS, parachute drag) reverse-engineered from the game's
  decompiled source and confirmed against real flight telemetry, most to
  well under 0.5% error. See `docs/high_level_checklist.md` for the full
  validation history.
- This is the "larger whole" the eligibility rule allows connecting to —
  infrastructure, not the submission itself.

**Built during the hackathon (this weekend, in `hackathon/`):**
- `controller.py` — the actual self-correcting flight-control loop:
  `AltitudePD`/`AttitudePD` (deterministic throttle + attitude control),
  the rolling-prediction/residual/replan-trigger pipeline, the LLM
  correction hook, and the full gravity-turn-to-orbit sequence.
- `residual.py` — residual computation, trend tracking, cause
  classification (actuator saturation vs. underperformance vs.
  overshoot).
- `supervisor.py` — the LLM (Claude) correction-proposal interface.
- `gateway.py` — the guardrail gateway (validates every LLM-proposed
  correction against real physics/state before it can touch the game)
  and the disablement latch (temporarily revokes LLM authority after
  sustained rejections in one regime).
- `gateway_corpus_test.py` — offline validation corpus for the gateway.
- All Weave/W&B instrumentation (`weave.init()`, `@weave.op()` tracing on
  every observe/act/predict/residual/classify/supervisor/gateway
  boundary, plus custom `log_cycle_decision`/`log_correction_effectiveness`
  ops).
- Every live flight test, the fault-injection demo, the attitude-control
  sign-bug incident and fix, and the orbital-mechanics work — all dated
  and committed during the event window.

## What it does

An LLM-supervised flight controller for a real (if obscure) physics
simulator: a deterministic PD loop flies the rocket tick-by-tick, a
rolling forward-simulation continuously predicts where the rocket
*should* be, and when reality diverges from that prediction by enough to
matter, the loop classifies *why* (actuator fault vs. genuine
under/over-performance) and calls an LLM to propose a correction — which
a guardrail gateway checks against real physics before it's ever allowed
to touch the game. Every cycle's decision and every correction's
measured effectiveness is logged to Weave, so the loop's own improvement
(or harm) is a real, inspectable metric — not just "it flew."

## How it's built

| Layer | What it does |
|---|---|
| Deterministic fast loop (5Hz) | `AltitudePD` (throttle) + `AttitudePD` (rotation) — real-time control, no LLM in the loop |
| Rolling predictor | `predict()` forward-simulates a hypothetical control plan against validated real physics, compared against reality every ~5s |
| Residual/replan trigger | Classifies the cause of any divergence, decides when escalation is warranted |
| LLM supervisor | Claude (Anthropic API), called only when the replan gate fires; proposes a structured correction |
| Guardrail gateway | Validates every LLM correction against real state/physics constraints; retries once with the rejection cause fed back, then safe-holds |
| Disablement latch | Revokes LLM authority for a flight phase after sustained, similar rejections — prevents a bad LLM streak from repeatedly re-attempting the same illegal action |
| Weave instrumentation | Traces every boundary call plus custom per-cycle decision and correction-effectiveness (harm-rate) logging |

No multi-agent framework (no A2A/CrewAI/LangChain) — a single LLM
supervisor call pattern, direct to the Anthropic API. MCP is used
heavily in *development* (Claude Code driving `sfsprobe_mcp`'s ~30 tools
to fly test flights, inspect telemetry, and debug live), though the
actual runtime controller talks to the game directly via the mod's file
protocol for speed, not through MCP.

## Sponsor tools used

- **Weights & Biases Weave** — `weave.init()` + `@weave.op()` tracing on
  every real-time decision boundary (observe/act/predict, residual
  computation, cause classification, supervisor calls, gateway
  evaluation), plus two custom logging ops
  (`log_cycle_decision`, `log_correction_effectiveness`) built
  specifically to make the "Best Loop" judging criterion inspectable:
  a real `correction_effectiveness`/`correction_harm_rate` metric,
  tracked cycle over cycle, not just a pass/fail demo.

## Demo script — 3 minutes, strict

**0:00–0:15 — Hook.** "SFS has no agent SDK — no kRPC like KSP. We built
the bridge from scratch [gesture at pre-existing infra, 5 seconds], then
built a self-correcting flight controller on top of it this weekend."

**0:15–1:15 — Live (or backup-recorded) fault demo.** Show a real
actuator fault (engine cutout) injected mid-flight:
- Point out `[FAULT INJECTED]` in the log
- Point out `[residual]` crossing threshold and the `cause=` classification
- Point out `[supervisor] CORRECTION` — the LLM's proposed fix
- Point out `[effectiveness] error_before=... error_after=... effectiveness=+...` — the loop *measuring its own improvement*, live

**1:15–1:50 — Weave dashboard.** Pull up the project and show the
per-cycle decision trace + the effectiveness/harm-rate metric over the
flight — this is the direct answer to "is the agent self-correcting?"

**1:50–2:25 — Safety layer.** One sentence each: the guardrail gateway
rejected an illegal LLM correction live, retried with the cause fed
back, and safe-held when the retry also failed — the loop never lets a
bad LLM call touch the real game unchecked.

**2:25–2:50 — Disclosure + close.** "The physics/game-bridge layer
[hackathon/README.md link] predates this weekend — everything you just
saw, the control loop, the LLM supervisor, the guardrail, and every
Weave trace, was built during the event."

**2:50–3:00 — Buffer.** Stop talking. Take questions.

**Rehearsal note:** time this out loud at least twice before presenting
— 3 minutes disappears fast once questions about "what's pre-built" come
up during Q&A, so the disclosure line above should be ready verbatim.

## Backup evidence (if live demo has issues)

Full Weave project (all traces, browsable by time or by
`correction_effectiveness`/`rejection_cause` fields):
https://wandb.ai/chrisbobacats-rocket-labs-llc/sfs-ai-hackathon/weave

Specific moments worth pulling up if live demo isn't cooperating:
- A clean fault-injection recovery: a genuine actuator dropout, followed
  by an LLM correction that produced a large, unambiguous
  `correction_effectiveness` improvement with `harm_rate=0.00` —
  filter the trace list by `log_correction_effectiveness` calls and sort
  by `correction_effectiveness` descending to find it quickly.
- A rejected illegal correction: filter by `rejection_cause` non-null to
  show the guardrail gateway catching a bad LLM proposal live.

## Submission checklist (per the official Hackathon Rules)

- [ ] Public GitHub repo link (confirm repo is public before submitting)
- [x] Team name: Rocket Labs LLC
- [x] Team members: Christian Jin, Arthur Peng
- [ ] Screen recording demo (<2 min) — record the same beats as the demo
      script above, trimmed
- [ ] X/LinkedIn handles — Christian: linkedin.com/in/christian-jin-99a616396;
      Arthur: **needs Arthur's handle**
- [ ] 2–3 sentence summary (draft below, trim if needed)
- [x] What it does / how it's built (above)
- [x] Sponsor tools used (above)
- [ ] Confirm both team members' AGI House accounts have emails/socials set

**Draft 2–3 sentence summary:**
"An LLM-supervised flight controller for Spaceflight Simulator, built
this weekend on top of a from-scratch physics/game-bridge platform we'd
already spent weeks validating. A deterministic loop flies the rocket in
real time; when reality diverges from a rolling physics prediction, the
loop classifies why and calls an LLM for a correction — which a
guardrail gateway checks against real physics before it's ever allowed
to touch the game. Every decision and every correction's measured
effectiveness is traced to Weave, so the loop's self-correction is a
real, inspectable metric, not just a demo that happened to work once."
