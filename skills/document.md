---
name: document
description: A personal document or official record -- passport, licence, insurance policy, warranty, lease, certificate, or similar, often with an expiry date.
applies_to: [image, file, text, voice]
extra_schema:
  document_type:
    type: string
    description: What kind of document it is (e.g. "passport", "driving licence", "health insurance policy", "laptop warranty").
  issuer:
    type: ["string", "null"]
    description: Who issued it -- authority, company, or institution -- if stated, otherwise null.
  holder:
    type: ["string", "null"]
    description: Whose document it is, if stated (the user, a family member), otherwise null.
  expires_on:
    type: ["string", "null"]
    description: ISO 8601 date (YYYY-MM-DD) of expiry or renewal if stated or visible, otherwise null.
  stored_where:
    type: ["string", "null"]
    description: Where the physical or digital original is kept, if the user mentions it, otherwise null.
promote:
  vendor: issuer
  due_at: expires_on
ask_if_missing:
  expires_on: When does it expire or need renewing?
---
The highest-value field here is `expires_on` -- an expiring passport or policy
that surfaces a month early is the main reason to record a document at all.

**Do not extract document numbers, policy numbers, national ID numbers, or
any other identifying number, even when they're plainly visible in an image.**
Record what the document is, who issued it, and when it expires. The original
image or file stays attached to the entry if the user needs the number itself.
