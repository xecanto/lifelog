---
name: receipt-expense
description: A receipt, invoice, or record of a purchase/expense (often a photographed receipt or a note about money spent).
applies_to: [image, file, text]
extra_schema:
  amount:
    type: ["number", "null"]
    description: The total amount, as a plain number with no currency symbol, or null if not stated.
  merchant:
    type: ["string", "null"]
    description: The store, vendor, or who was paid, if stated.
---
Prefer the final total over subtotals. If multiple currencies could apply,
keep the currency symbol/code in the summary text even though amount is
unitless.
