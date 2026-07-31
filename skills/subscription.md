---
name: subscription
description: A recurring paid subscription or bill -- a service billed monthly/yearly, with a cost, a payment method, and a renewal date.
applies_to: [text, voice, image, file, link]
extra_schema:
  service:
    type: string
    description: The service being paid for (e.g. "Notion Plus", "Netflix", "AWS").
  cost:
    type: ["number", "null"]
    description: The recurring charge as a plain number with no currency symbol, or null if not stated.
  currency:
    type: ["string", "null"]
    description: Currency code or symbol if identifiable (e.g. "USD", "INR", "$"), otherwise null.
  billing_period:
    type: ["string", "null"]
    description: How often it bills -- one of "monthly", "yearly", "quarterly", "weekly", "daily". Null if not stated or implied.
  next_renewal:
    type: ["string", "null"]
    description: ISO 8601 date (YYYY-MM-DD) of the next renewal/charge if stated or derivable, otherwise null.
  paid_with:
    type: ["string", "null"]
    description: The card, bank, or payment method it's charged to, as stated (e.g. "HDFC credit card", "PayPal"), otherwise null.
  account_identifier:
    type: ["string", "null"]
    description: The email or username the subscription is under, if stated, otherwise null.
promote:
  vendor: service
  amount: cost
  currency: currency
  cadence: billing_period
  due_at: next_renewal
  identity: account_identifier
---
This feeds both "what am I paying every month" and "what's about to renew",
so cost, billing_period and next_renewal carry the most weight.

For `next_renewal`, resolve a bare day-of-month ("renews on the 5th") against
today's date: if that day has already passed this month, use next month. If
the user gives a start date and a period but no renewal date, work the next
renewal forward from the start date rather than leaving it null.

Never record card numbers, CVVs, or full account numbers -- `paid_with` should
be a human description like "HDFC credit card", not a number.
