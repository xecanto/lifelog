---
name: task
description: A task, reminder, to-do item, or something the user needs to do or follow up on.
applies_to: [text, voice]
extra_schema:
  due_date:
    type: ["string", "null"]
    description: ISO 8601 date (YYYY-MM-DD) if a deadline or date is mentioned or clearly implied, otherwise null.
  priority:
    type: ["string", "null"]
    description: One of "low", "medium", "high" if urgency is stated or implied, otherwise null.
---
Only set due_date if a date is actually stated or unambiguously implied (e.g.
"tomorrow", "next Friday") -- resolve relative dates using the entry's saved
timestamp as "today". Don't guess a priority that isn't implied by the text.
