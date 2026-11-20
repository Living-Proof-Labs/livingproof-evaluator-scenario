<!-- SPDX-License-Identifier: Apache-2.0 -->

# Scenario evaluator icon

The Scenario evaluator's mark in the capability report. It is a small, one-colour version of the
Living Proof Labs mark: a bot head with two eyes, and the Living Proof check as its antenna. The ring,
ears and mouth of the full logo are left out so it stays clear at the report's smallest sizes.

- Artwork: [`scenario-evaluator-icon.svg`](../../src/livingproof_evaluator_scenario/scenario-evaluator-icon.svg).
  `result.ICON` reads this file, and the evaluator writes it as `evaluator.icon` and `descriptor.icon`.
- Accessible name: `descriptor.icon_accessible_name` is `Scenario`, the evaluator's title. The icon
  carries no `title` element, because the evaluator contract's SVG subset does not allow one.
- Colour: `currentColor` only. The report paints the mark with its own link colour in a tab and its
  own speaking colour in a callout row, on light and on dark. Hex colours are not allowed in the subset.
- Shape rules: 24 by 24 viewBox, 2px round strokes, `path`, `rect`, `circle` and `g` only, 352 bytes
  (the limit is 8192). No text, no raster image, no style.

## Where the report shows it

| Place | Size in the report | Source rule in the report |
| --- | --- | --- |
| Evaluator tab (the "mark") | 19.2px icon in a 37.6px round face | `.eval-mark .mark-svg svg` is 1.2rem; `.eval-face` is 2.35rem |
| Callout row, when the evaluator has something to say | 18.4px | `.callout-icon svg` is 1.15rem |

The verification site's run chips are text only today and have no icon slot.

## Previews

Rendered with the capability report's own renderer and stylesheet at
[this commit](https://github.com/Living-Proof-Labs/livingproof-capability-report/commit/69e2150c4d3103244d06e40a85d77701a81a0a0a)
of livingproof-capability-report, in headless Chromium. The partner marks beside it are the report's example marks (Roboto,
Run Integrity, Robot health, Human review), not real partner logos.

- [`scenario-evaluator-icon-preview-light.png`](scenario-evaluator-icon-preview-light.png) and
  [`scenario-evaluator-icon-preview-dark.png`](scenario-evaluator-icon-preview-dark.png): the tab and
  callout in a passing and a speaking card, a size ladder from 16px to 96px beside two other marks, and a large version. Shown at 2x pixel density.
- [`scenario-evaluator-icon-actual-pixels.png`](scenario-evaluator-icon-actual-pixels.png): the real
  1x pixels of each tab face and the callout, magnified 8x, light and dark.

## Keep it a variant, not a second logo

- No ring. A ring with a check is the grade badge, which reports a result. This mark says who judged it.
- Keep the antenna touching the head, as in the full mark. The check's point sits on the top edge of the head.
- Do not go below 16px. Below that the eyes and the short leg of the check run together.
