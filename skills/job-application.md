---
name: job-application
description: A specific job application the user has submitted or is progressing through -- company, role, source/referral, current stage, comp details, and next follow-up. Use instead of task/event for anything tied to a specific job application.
applies_to: [text, voice, image, file, link]
extra_schema:
  company:
    type: string
    description: Name of the company the user applied to.
  role_title:
    type: string
    description: The job title or position applied for.
  date_applied:
    type: ["string", "null"]
    description: ISO date the application was submitted, or null if not stated.
  source:
    type: ["string", "null"]
    description: How the application came about -- referral name, recruiter, job board, or direct application. Null if not stated.
  stage:
    type: string
    description: Current status of the application -- e.g. applied, phone_screen, interview, offer, rejected, withdrawn. Use 'applied' if unclear.
  compensation:
    type: ["string", "null"]
    description: Salary or comp details mentioned (range, base, equity, etc.), or null if not stated. Do not invent figures.
  next_follow_up:
    type: ["string", "null"]
    description: ISO date of the next planned follow-up, interview, or deadline for this application, or null if none is stated.
cadence: null
promote:
  status: stage
  due_at: next_follow_up
  vendor: company
ask_if_missing:
  next_follow_up: When should you follow up on this?
identity_fields: [company, role_title]
---
Use this skill whenever the content describes progress on, or details of, a specific job application -- an application submitted, an interview scheduled, a recruiter conversation, an offer, or a rejection tied to one company/role. Extract company and role_title directly from the text; if the role isn't named, use a short generic description rather than inventing a title. Set stage based on the most recent status mentioned (default to 'applied' if the user just says they applied). Only fill compensation and source fields if explicitly mentioned -- do not guess salary figures or referral names. next_follow_up should capture any explicitly mentioned or clearly implied next action date (next interview, deadline to respond, when to check back); leave null if none is given rather than guessing a date.