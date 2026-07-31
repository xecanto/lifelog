---
name: receipt-expense
description: A receipt, invoice, or record of a one-off purchase or expense (often a photographed receipt or a note about money spent).
applies_to: [image, file, text, voice]
extra_schema:
  amount:
    type: ["number", "null"]
    description: The total amount, as a plain number with no currency symbol, or null if not stated.
  currency:
    type: ["string", "null"]
    description: Currency code or symbol if identifiable (e.g. "USD", "INR", "$"), otherwise null.
  merchant:
    type: ["string", "null"]
    description: The store, vendor, or who was paid, if stated.
  paid_with:
    type: ["string", "null"]
    description: Card, bank, or payment method used, if stated (e.g. "HDFC debit card", "PayPal").
  purchased_on:
    type: ["string", "null"]
    description: ISO 8601 date (YYYY-MM-DD) of the purchase if stated or clearly implied, otherwise null.
promote:
  amount: amount
  currency: currency
  vendor: merchant
---
Prefer the final total over subtotals.

This is for one-off spending. A recurring charge (anything with a billing
period or renewal date) is a `subscription` instead -- the difference matters,
because subscriptions are totalled as ongoing monthly cost and receipts
aren't.
