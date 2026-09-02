# CoreWeave Hacks — plan of action

**Event:** CoreWeave Hacks, 400 Alabama Street, in-person only.
Sat June 6 (doors 9am, kickoff 10:30am, hacking starts 11:15am) through
Sun June 7 (submissions due 1:00pm, judging 1:30pm, awards 4:30pm).
Must be present Saturday to be prize-eligible; W&B/Weave integration
required for eligibility ("2 lines of code" per handbook).

## Intent
Submit an SFS Agent build to this hackathon — specifically, a
**self-improving AI loop** built on top of the project's existing
physics/probe backend. Ties directly to the top judging criterion
("Best Loop — is the agent self-correcting?").

## Eligibility read (not official — confirm with Anna/Lorenzo on-site)
Handbook rule: *"Entire project must be built at the hackathon... it's
ok to build something that connects to a larger whole, but you must be
clear on what was previously built, and you will only be evaluated on
the hackathon work."*

Conclusion reached: the following is allowed, since none of it is the
thing actually submitted/judged —
- **Pre-built before the event:** the non-AI backend (physics research,
  `sfsprobe`/`sfsprobe_mcp`, mod/game-connection plumbing) — this is
  infrastructure, not the submission.
- **Small tool-calling integration tests beforehand** (confirming an AI
  can call a probe command and it actually affects the game) — plumbing
  verification, not project code.
- **A written plan with fallback branches** (in case live accuracy
  during the event undershoots the research numbers) — ordinary
  engineering prep, not "experiments" in the sense the rule restricts.
- **Built fresh AT the event:** the actual self-improving AI loop
  (design-phase LLM / reflex controller work), in a fresh repo with
  hackathon-dated commit history, using the pre-existing physics
  knowledge but not reusing its code.

Must-do regardless: confirm this reading with Anna/Lorenzo in person,
and be explicit in the submission write-up about exactly what predates
the hackathon vs. what was built during it — don't leave it implicit.

## Still needed before the event
- W&B/Weave instrumentation — not yet added anywhere in the project.
  Required for eligibility. Best slot: wherever the design-phase LLM's
  calls end up living.
- Decide the actual fallback branches for the written plan (which
  confirmed-physics numbers to fall back to if live telemetry disagrees
  during the event).
