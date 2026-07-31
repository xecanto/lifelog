---
name: event
description: A specific dated event -- an appointment, trip, deadline, birthday, booking, or anything happening at a particular time.
applies_to: [text, voice, image, file, link]
extra_schema:
  event_name:
    type: string
    description: What the event is (e.g. "Dentist appointment", "Flight to Delhi", "Sarah's birthday").
  starts_at:
    type: ["string", "null"]
    description: ISO 8601 date (YYYY-MM-DD), optionally with time as YYYY-MM-DDTHH:MM, when the event happens. Null only if genuinely undated.
  location:
    type: ["string", "null"]
    description: Where it happens, if stated, otherwise null.
  people:
    type: array
    items: {type: string}
    description: People involved or attending who are named in the content. Empty array if none.
  recurring:
    type: ["string", "null"]
    description: If it repeats, how often ("yearly" for a birthday, "weekly", etc.), otherwise null.
promote:
  due_at: starts_at
  cadence: recurring
---
Resolve relative dates ("next Tuesday", "the 14th") against today's date given
at the top of the message, and prefer including the time when one is stated --
"3pm on the 14th" is far more useful back than a bare date.

An event is something that *happens* at a time. A thing the user has to *do*
is a `task`, and an explicit request to be told about something is a
`reminder`; a note can be more than one of these.
