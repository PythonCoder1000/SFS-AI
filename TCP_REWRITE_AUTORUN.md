# TCP rewrite — AUTORUN: checkpoints 2-5, straight through

Read `TCP_REWRITE_SPEC.md` and `TCP_REWRITE_LOG.md` first for full
context and design detail — this file supersedes ONLY their
per-checkpoint "ask Christian first" gates, nothing else. Checkpoint 1
is done and live-validated (see the log); start at Checkpoint 2.

## Why the permission gates are lifted for this run

The original spec's caution was about installing an untested mod build
onto the SAME live game another session might be using. That's no
longer the situation: Checkpoint 1's build is already installed and
proven stable, live, side-by-side with the file-protocol path. This
branch (`tcp-rewrite`) is isolated by design — a bad commit costs a
`git revert`, nothing more. Christian's explicit instruction: **run
straight through checkpoints 2-5 without stopping to ask permission at
each one.** Commit and push after each checkpoint as the original spec
says, but do not pause for a go-ahead in between.

## The one exception — not lifted

**Checkpoint 4 sends real `throttle`/`turn`/`stage` commands to the live
craft.** That's a physical-safety question (a real rocket moves), not a
code-safety question a git revert fixes. Per this project's standing
convention (`sfsprobe/mod_changelog.md`, `OPTION_A_BUILD_SPEC.md` §1):
**a human must be present and watching at the moment those commands are
actually sent.** Christian is present for this run. Do the rest of
Checkpoint 4's setup (wiring `agent_interface.py`, writing the dry-run
harness) without pausing, but announce clearly, right before the FIRST
real command goes out over the TCP path, so he can watch that moment —
one announcement, not a pause-and-wait for a reply.

## Scope reminder (Christian's explicit framing)

The actual goal here is narrow: **speed up throttle, turn (angle), and
stage commands** — the three commands `pilot_loop.py`'s `act_fn` sends
every cycle. Checkpoint 4 doesn't need to migrate everything
`agent_interface.py` does to TCP — just prove `observe()`/`act()` can
use the TCP path for these three, with a real measured Hz improvement
over the 2.48 Hz file-protocol baseline already logged tonight. Don't
scope-creep into rewriting `predict()` or anything else.

## Checkpoint 2 — Python client round trip

`analysis/sfsprobe_tcp_client.py` already exists with a `__main__`
self-test (10x `ping`, reports min/mean/max). Just run it for real
against the live mod (already TCP-enabled) and confirm: 10/10 succeed,
no reconnects logged, game stays stable. Record the real numbers in
`TCP_REWRITE_LOG.md`. Commit, push.

## Checkpoint 3 — Batching + latency

Use `SfsProbeTcpClient.send_batch()` (already implemented) to confirm
`["throttle 0.5", "turn 0.0"]` sent in one write produces two correct
result lines. Then measure real round-trip latency the same way
tonight's file-protocol numbers were measured (10+ calls, report
min/mean/max) and compare directly against the ~0.055s file-protocol
mean already in `TCP_REWRITE_LOG.md`. If TCP isn't actually faster,
**say so plainly in the log** — don't proceed to Checkpoint 4 on an
unproven assumption. Commit, push.

## Checkpoint 4 — Wire in, live-validate on throttle/turn/stage

Add a TCP-backed path to `agent_interface.py` for `observe()`/`act()`,
behind an explicit flag (`use_tcp=True` or similar) — file-protocol
stays the default, unchanged. Then run a short live test that mirrors
`pilot_loop.py`'s real cycle shape: `observe()` → `act("throttle ...")`
→ `act("turn ...")`, repeated ~20-30 times, using the SAME achieved-Hz
logging pattern `pilot_loop.py` already has (`N cycles in Ts = X Hz`).
**Announce before the first real command goes out, per the exception
above.** Compare the achieved Hz against tonight's 2.48 Hz file-protocol
baseline. Commit, push, with the real before/after numbers in the log.

(`stage` doesn't need its own separate test cycle — it goes through the
identical `act()` path as `throttle`/`turn`; confirming those two live
is sufficient evidence for `stage` too, same code path.)

## Checkpoint 5 — Wrap-up

Update `sfsprobe/mod_changelog.md` (version bump, TCP capability, the
real Checkpoint 3 and 4 latency/Hz numbers). Note in `TCP_REWRITE_LOG.md`
that the file-protocol path remains the default in `pilot_loop.py` until
Christian explicitly flips it — don't make that call yourself. Final
commit, push.

## If something breaks

This is the isolated branch this setup exists for. Revert with `git
revert`/`git reset` as needed, note what broke and why in
`TCP_REWRITE_LOG.md`, and keep going — don't stop the whole run over a
recoverable mistake. Do stop and report clearly if a checkpoint's actual
exit condition (the real numbers, the real test) can't be met after a
genuine attempt — don't fake a result to keep moving.
