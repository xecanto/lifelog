---
name: contact
description: Information about a specific person -- who they are, how the user knows them, or details worth remembering about them.
applies_to: [text, voice, image]
extra_schema:
  person_name:
    type: ["string", "null"]
    description: The name of the person this entry is about, if stated.
identity_fields: [person_name]
---
Focus the summary on what's distinctive or useful to remember about this
person for next time (how the user met them, what they do, shared context).
