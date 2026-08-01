---
name: reminder
description: Something the user explicitly wants to be reminded about at or before a particular time in the future.
applies_to: [text, voice, image, file, link]
extra_schema:
  remind_about:
    type: string
    description: What the user should be reminded of, phrased as they'd want to read it later.
  remind_on:
    type: ["string", "null"]
    description: ISO 8601 date (YYYY-MM-DD), optionally with time as YYYY-MM-DDTHH:MM, for when the reminder should surface. Null only if no time reference at all is given.
  lead_time:
    type: ["string", "null"]
    description: How far ahead of the underlying event the user wants warning, if stated (e.g. "3 days before", "a week before"), otherwise null.
promote:
  due_at: remind_on
ask_if_missing:
  remind_on: When should this remind you?
---
The whole point of this facet is that it comes back to the user at the right
moment, so `remind_on` is what matters. Resolve every relative expression
("tomorrow", "next Friday", "in two weeks", "before it renews") against
today's date given at the top of the message.

When the user asks to be reminded *before* something ("remind me before it
renews on the 5th"), `remind_on` is the earlier reminder date, not the date of
the underlying event -- subtract the stated lead time, or a sensible few days
if none is stated.
