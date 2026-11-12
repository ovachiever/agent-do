# Pangram skin — measured from pangram.com live, 2026-09-16 (agent-do browse computed styles)

Job: re-skin ONE advanced Portfolio candidate in this color scheme. STRUCTURE, LAYOUT, COPY,
DATA, CHART GEOMETRY, AND SPACING STAY BYTE-FOR-BYTE THE SAME — only color tokens, type faces,
and the surface treatment of controls change. Do not move, resize, add, or remove anything.
Do not "fix" the candidate. If a color in the candidate has no mapping below, map it by role
(ground / ink / muted / hairline / good / miss / accent) — never invent a new hue.

## Ground and ink (measured)
- page ground: rgb(248,247,245) — warm paper (body background)
- secondary field / sunken panels: rgb(243,243,243); card / raised surface: rgb(255,255,255)
- ink: rgb(20,32,30) green-black (body text); headings rgb(33,38,49)
- muted text: rgba(20,32,30,0.6); faint text: rgb(119,119,119)
- hairline / borders: rgb(226,232,240)
- deep green fields (used for a dark section and the primary "confirm" button): rgb(1,43,36) ·
  rgb(0,26,22) · button green rgb(21,80,46) with white text, radius 10px
- color-blocked fields (used sparingly as section grounds on pangram.com): butter rgb(255,231,130)
  · lilac rgb(244,190,255) · sky rgb(170,216,249) · chocolate rgb(52,21,0) / rgb(97,39,0)

## Accent (measured)
- orange rgb(255,97,6): primary action button bg (white text, radius 6–8px); also link/label color
- orange tint rgb(254,227,218): secondary action bg with orange text

## Role mapping for the candidates (dark → Pangram)
- --bg / dark ground → rgb(248,247,245)
- raised / lift panels → rgb(255,255,255); sunken → rgb(243,243,243)
- --ink → rgb(20,32,30); --muted → rgba(20,32,30,0.6); --faint → rgb(119,119,119)
- hairlines (rgba white 0.14/0.28) → rgb(226,232,240) (stronger rule: rgb(20,32,30) at 0.18 alpha)
- sage (good / observed / on thesis) → green rgb(21,80,46); sage fills → rgba(21,80,46,0.10)
- clay (miss / below / due) → orange rgb(255,97,6); clay fills → rgb(254,227,218)
- envelope / 90% fills (rgba white 0.09) → rgba(20,32,30,0.07); 50% → rgba(20,32,30,0.16)
- selected-row highlight → rgb(255,255,255) card on the paper ground with a 2px green left bar
- controls (verb buttons): primary act → orange bg / white text, radius 6px; secondary acts →
  white bg, hairline border rgb(226,232,240), ink text, radius 6px; the "confirm" of a form → green
  rgb(21,80,46). Keep every control's position and size.
- greyed / closed rows → ink at 0.45 alpha on the paper ground
- the motto line → muted ink

## Type (measured)
- body: "IBM Plex Sans" (Google Fonts) 16px base on pangram.com — keep the candidate's own sizes.
- headings: pangram.com uses a custom quiet serif ("headingFont", 60px/400, letter-spacing −1px);
  substitute Google's "Newsreader" at weight 400 for serif roles (headings, thesis line, names).
  Note the substitution in your report.
- mono: "IBM Plex Mono" for every monospace role.
- Load via one Google Fonts link:
  https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Newsreader:opsz,wght@6..72,400;6..72,500&display=swap
- Weights: keep the candidate's weight roles (bold stays bold).

## Not Pangram, keep out
No illustrations, no color-blocked section fields unless the candidate already had a distinct
band (then butter rgb(255,231,130) may ground ONE band at most — the BOOK strip — and only if it
does not fight legibility). No gradients, no drop shadows beyond a 1px hairline.

## Verify
Render at 1440 in browse (`--session <yours>`), screenshot --full, READ the PNG: contrast must
hold everywhere (orange text only on paper/white, never on green; muted text ≥ 0.6 alpha), no
element moved. Diff the DOM: `agent-do browse eval` the text content of body before/after must
be identical (same visible strings). Report the substitution and anything you could not map.
