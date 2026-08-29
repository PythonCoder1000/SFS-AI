# SFS AI — New Session Startup Prompt

Paste this verbatim at the start of a new chat in the SFS AI project.
Purpose: load context and let Christian VERIFY it transferred correctly
before any real work starts.

---

Read the project context before doing anything else. Specifically:

1. Read every file in the project's `docs/` folder:
   `sfs_physics_reference.md`, `sfs_source_reference.md`,
   `high_level_checklist.md`, and the most recent `session-*.md`
   handoff file (there may be more than one — read the latest by date).
2. Read the project's `README.md`, `mod_changelog.md`, and
   `python_changelog.md`.
3. Read Mnemoverse memory, domain `project:sfs-agent`, for anything not
   yet reflected in the files above — a `memory_read` with a query like
   "SFS agent project status recent findings" is a good start.

**Do not start working on anything yet.** Once you've read everything,
give me a short status report, structured as:

- **Where the project stands** — one paragraph, in your own words
- **What's confirmed vs. still open** — pull from
  `high_level_checklist.md`, don't just repeat it verbatim
- **The single most recent finding or decision** — whatever's newest
- **Anything unclear or conflicting** — if two sources disagree, or
  something in the checklist doesn't match what a doc says, flag it
  rather than silently picking one

I'll confirm the context landed correctly before we continue.
