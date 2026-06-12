# Project Agent Instructions

## Caveman Mode

- Use caveman mode by default: short, direct, practical.
- Report only essentials: error cause, changed scope, verification result,
  dependency, blocker, or user-relevant risk.
- Do not narrate routine steps, infrastructure connection attempts, file reads,
  searches, command choices, or obvious mechanics.
- Do not send progress updates like "checking", "reading", "searching", or
  "now I will" for routine work. Stay silent until there is a result, blocker,
  risk, or required user decision.
- Do not report internal activity counters such as "explored N files", "read N
  files", "listed N files", "ran N commands", or similar tool-use summaries.
- Prefer the simplest working fix that matches the existing codebase. Do not add
  abstraction or process unless it solves a concrete problem.

## Central System Context

- Before any `kigo_xcvario_simulator` work, read the canonical system instructions at
  `/Users/slawekpiela/.codex/AGENTS.md`.
- Also read the central infrastructure and project profile files:
  `/Users/slawekpiela/.codex/.agents/infrastructure/ACCESS.md`,
  `/Users/slawekpiela/.codex/.agents/infrastructure/PERMISSIONS.md`,
  and
  `/Users/slawekpiela/.codex/.agents/project-awareness/projects/kigo_xcvario_simulator.md`.
- Treat the central system files as mandatory startup context. Project-local
  instructions in this file remain the authority for `kigo_xcvario_simulator`-specific
  rules.

## Documentation Discipline

These rules are mandatory for every coding or code-analysis task in this project.

1. After analyzing code, capture durable findings that can shorten future work in `project_tech_documentation/README.md`.
2. Before every commit, verify whether the change requires a documentation update.
3. If documentation is needed, update `project_tech_documentation/README.md` before committing.
4. If no documentation update is needed, state that explicitly in the commit message with a `Docs-Impact:` trailer.
5. Never make or approve a commit in this project without a documentation impact check.

Update documentation when work affects or reveals:

- architecture, module ownership, or data flow
- public behavior, UI, CLI, API, file formats, or generated outputs
- build, test, deployment, configuration, or release steps
- recurring debugging knowledge, pitfalls, invariants, assumptions, or constraints
- non-obvious implementation details discovered during investigation


User-facing documentation is mandatory when user-visible behavior changes:

- If behavior, UI, look/layout, labels, workflows, configuration UX, generated
  outputs, or operator-visible commands change, update the nearest user
  manual/help/README in the same task.
- If no user-facing manual/help exists, update `README.md` when present and
  record the gap in `project_tech_documentation/README.md`.
- Do not use `Docs-Impact: none` for user-visible changes unless you also state
  why no manual/help update applies.

Every commit message must include one of these trailers:

```text
Docs-Impact: updated project_tech_documentation/README.md
```

or:

```text
Docs-Impact: none - <short reason>
```
