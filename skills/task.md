---
name: task
description: A task, to-do item, or something the user needs to do or follow up on, with or without a deadline.
applies_to: [text, voice, image, file]
extra_schema:
  due_date:
    type: ["string", "null"]
    description: ISO 8601 date (YYYY-MM-DD) if a deadline or date is mentioned or clearly implied, otherwise null.
  priority:
    type: ["string", "null"]
    description: One of "low", "medium", "high" if urgency is stated or implied, otherwise null.
promote:
  due_at: due_date
ask_if_missing:
  due_date: When does this need to be done by?
---
Only set due_date if a date is actually stated or unambiguously implied (e.g.
"tomorrow", "next Friday") -- resolve it against today's date given at the top
of the message. Don't guess a priority that isn't implied by the text.

Use `task` for something the user has to *do*. If they're mainly asking to be
told about something at a particular time, that's `reminder` instead; a note
can be both.
