---
name: feature-request
description: The user describing something this assistant itself should be able to do but can't yet -- a missing capture type, a field it doesn't record, a view or behaviour they want added or changed.
applies_to: [text, voice]
extra_schema:
  change_title:
    type: string
    description: A short imperative title for the change, max 10 words (e.g. "Track car service dates").
  change_kind:
    type: string
    enum: ["skill", "code"]
    description: "\"skill\" if this is only about capturing/organizing a new kind of content and needs no new behaviour; \"code\" if it needs new UI, endpoints, or changes to how the app works."
  change_prompt:
    type: string
    description: A complete, self-contained instruction an engineer or coding agent could act on without seeing the original note. State what should exist and why, not how to implement it.
---
This skill is only for the user talking *about the assistant itself* -- "it
should also track...", "I wish this could...", "this app needs...". A note
that merely mentions software, or an idea for a separate product they want to
build, is an `idea`, not a feature request.

Choosing `change_kind` well matters, because the two are treated differently:

- **skill** -- the app already does the right things, it just doesn't
  recognize this *kind of content* yet. "Remember which gym classes I book",
  "track my car's service history". These become a new skill file.
- **code** -- needs behaviour that doesn't exist: a new screen, a
  notification, an export, a change to existing logic. "Email me the morning
  agenda", "let me edit an entry after saving".

Write `change_prompt` as a standalone brief. It's stored and may be acted on
days later, by something that never sees the note it came from, so spell out
what the user actually wants rather than referring back to "this" or "that".
