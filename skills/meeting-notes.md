---
name: meeting-notes
description: Notes or a transcript from a meeting, call, or discussion with other people.
applies_to: [text, voice, file]
extra_schema:
  attendees:
    type: array
    items: {type: string}
    description: Names of people mentioned as present or participating, if any are named.
  action_items:
    type: array
    items: {type: string}
    description: Concrete follow-up actions or commitments mentioned, each with who owns it if stated.
---
Don't invent attendees or action items that aren't actually in the content --
empty arrays are fine if none are mentioned.
