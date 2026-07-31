---
name: project
description: An ongoing project or pursuit -- work, a side project, a hobby, a game being played, or something being built or learned over time.
applies_to: [text, voice, image, file, link]
extra_schema:
  project_name:
    type: string
    description: What the project or pursuit is called, as the user refers to it.
  area:
    type: ["string", "null"]
    description: Which part of life it belongs to -- one of "work", "side-project", "hobby", "game", "learning", "home", or another short label. Null if unclear.
  status:
    type: ["string", "null"]
    description: Where it stands if stated or implied -- one of "idea", "active", "paused", "blocked", "done". Null if unclear.
  next_step:
    type: ["string", "null"]
    description: The next concrete action mentioned for this project, if any, otherwise null.
  next_step_due:
    type: ["string", "null"]
    description: ISO 8601 date (YYYY-MM-DD) for that next step if a date is given, otherwise null.
promote:
  vendor: project_name
  due_at: next_step_due
---
Use this for something with continuity -- a thing the user will come back to
and add more notes about over time. A one-off thought about a project is
better captured as a `general` note or an `idea`.

`area` is what separates work from hobby from games later on, so infer it from
context when the user doesn't say it outright (a note about a raid schedule is
"game", a note about a client deadline is "work").
