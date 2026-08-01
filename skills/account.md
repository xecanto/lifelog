---
name: account
description: An account the user has with a service, site, or app -- which service, which email/username they signed up with, and how they access it.
applies_to: [text, voice, image, file, link]
extra_schema:
  service:
    type: string
    description: The service, site, or app the account is with (e.g. "Notion", "GitHub", "HDFC Bank").
  account_identifier:
    type: ["string", "null"]
    description: The email address, username, or phone number the account is under, exactly as stated, or null if not stated.
  signup_method:
    type: ["string", "null"]
    description: How the account is signed in to if stated -- e.g. "Google SSO", "Apple sign-in", "email + password", "GitHub OAuth". Null if not stated.
  platform:
    type: ["string", "null"]
    description: Where the account is used if stated -- e.g. "website", "iOS app", "desktop app". Null if not stated.
  plan:
    type: ["string", "null"]
    description: The tier or plan name if stated (e.g. "free", "Pro", "Plus"), otherwise null.
promote:
  vendor: service
  identity: account_identifier
ask_if_missing:
  account_identifier: Which email or username is this account under?
---
This is the record that answers "which email did I use for X?" months later,
so `account_identifier` is the most important field -- copy it exactly as
written, don't normalize or guess at it.

Never invent or reconstruct an identifier that isn't in the content. If the
user only says "my work email", put that phrase in and nothing more.

**Never extract passwords, PINs, security answers, recovery codes, or 2FA
secrets, even when they appear in the content.** Note only that a credential
was mentioned, if it's relevant at all.

If the account also costs money on a recurring basis, `subscription` covers
the money side -- this skill stays focused on identity and access.
