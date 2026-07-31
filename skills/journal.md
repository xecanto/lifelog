---
name: journal
description: A personal journal entry, reflection, or note about how the user is thinking or feeling, not tied to a specific task.
applies_to: [text, voice]
extra_schema:
  mood:
    type: ["string", "null"]
    description: A one or two word mood/tone if it's clearly expressed (e.g. "anxious", "excited"), otherwise null.
---
Be respectful and understated in the summary -- reflect what the user said,
don't editorialize or add advice.
