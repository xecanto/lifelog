---
name: recipe
description: A cooking or baking recipe with ingredients and preparation steps.
applies_to: [text, link, file, image, voice]
extra_schema:
  ingredients:
    type: array
    items: {type: string}
    description: Each ingredient with its quantity, one per item (e.g. "2 cups flour").
  steps:
    type: array
    items: {type: string}
    description: Ordered, numbered-in-order preparation steps.
---
Extract exact ingredient quantities and units where given. Keep steps in the
original order and don't merge distinct steps together.
