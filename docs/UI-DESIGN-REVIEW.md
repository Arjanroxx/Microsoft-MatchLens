# MatchLens match-centre UI review

Status: **reviewed UI approved for commit and push**. The backend, generated event files, ratings and xG calculation are unchanged by this design pass.

## Review the build

The running preview is http://127.0.0.1:8081/. If the server has stopped, start it from the repository root:

```powershell
py -3.13 -m simulator.ui_server --input data/examples/movement-match --port 8081
```

The editable [Figma foundations board](https://www.figma.com/design/S1C47pWsH2LJDyiZZjO6hc?node-id=3-14) documents the palette, score header and statistics hierarchy. It is a handoff board, not a complete interactive mirror of the application. Figma Starter supports one variable mode here, so the board has light-theme variables; the application supports both light and dark themes. Its Inter specimens document hierarchy; the app retains DM Sans and Manrope.

## Design direction

Use the compact score-first hierarchy of established sports products such as [Sofascore](https://www.sofascore.com/football) as a reference, while retaining MatchLens's own replay and evidence workflow. This is an adaptation of the existing application, not a clone of Sofascore or an official Premier League visual identity.

- Navy application header, restrained light surfaces, consistent spacing and larger timeline text.
- Blue home and purple away cues across statistics, pitch markers, trails and comparisons. The orange ball-carrier highlight remains distinct from team identity.
- A compact match header above the pitch, with the replay clock and synthetic source clearly labelled.
- Timeline / Statistics / Inspector tabs preserve existing event and player inspection.
- Numeric comparison bars use the actual current replay totals. They compare the two shown values; they are not probabilities or invented momentum scores. Composite and negative values do not receive a misleading proportion bar.
- A persistent light/dark toggle changes presentation only. It uses `matchlens.theme` in local storage when available; storage failures do not prevent playback.
- Local MIT-licensed Phosphor icons replace inconsistent navigation and timeline glyphs. Their licence is retained in `frontend/assets/icons/LICENSE`.
- The seek slider uses millisecond steps so its maximum is exactly reachable even when the generated duration is not divisible by ten.

## Source files and teammate handoff

| File | Responsibility |
|---|---|
| `frontend/index.html` | Existing application layout, revised labels, navigation icons, theme control, CSS entrypoint and exact-end seeking |
| `frontend/match-centre.css` | Reviewable visual layer after the existing stylesheet; semantic tokens, responsive rules, component states and dark theme |
| `frontend/app.mjs` | Existing replay logic with updated presentation colours, library event icons, evidence-based comparison bars and guarded theme preference |
| `frontend/assets/icons/` | Vendored SVG icons and MIT licence; no runtime icon service required |

`frontend/styles.css` still supplies the existing replay and decision presentation foundation. The new stylesheet deliberately overrides it rather than rewriting the referee and moment components. When reviewing, pay special attention to these layered selectors before moving rules between files. The existing pitch SVG represents the actual match board and source geometry, not decorative artwork.

Semantic colours live at the top of `match-centre.css`: `--bg`, `--panel`, `--line`, `--muted`, `--text`, `--home`, `--away`, `--lime`, `--navy`, `--soft` and `--accent-soft`. Dark equivalents live under `html[data-theme=dark]`. Pitch marker colours are intentionally lighter for contrast on grass; their hues match the team cues. If changing team hues, update the matching marker/trail literals in `app.mjs` as well.

Keep all existing DOM IDs, `data-tab`, `data-player`, `data-event`, source-event relationships and playback timing when iterating. Preserve `valid_for_statistics` handling, null/coverage behaviour, and the visible uncalibrated xG qualification. Do not populate live panels from final summary values.

## Captured review and verification

Screenshots are saved under `data/generated/design-review/` (ignored by Git). The original screen was captured before editing. The new light/dark layouts, mobile layout and player/event behaviour were reviewed in the in-app browser.

| Step | Surface | Result |
|---|---|---|
| 1 | Original match overview | Working baseline; oversized introductory area and very small timeline text motivated the redesign |
| 2 | Redesigned match centre | Score, clock, pitch, source labels and overview remain connected to actual replay data; desktop screenshot accepted |
| 3 | Team statistics in dark mode | Current xG and other values render with comparison bars; theme change preserves the clock |
| 4 | Mobile match centre | Wordmark and selector clipping corrected; no horizontal overflow in the checked mobile viewport |
| 5 | Playback and match decisions | Play/pause, exact full-time seeking, foul/advantage, substitutions and goal popups exercised |
| 6 | Player inspector | Player selection opens running rating, minutes, xG and evidence; local API response verified in the UI |

The existing frontend regression suite passes. Browser checks supplement those tests with visual inspection; screenshots do not establish full accessibility compliance. Visible focus styles, labelled controls, reduced-motion handling, readable source qualifications and contrast were considered. A full screen-reader audit, every possible viewport, every uploaded club-name length and all operating-system font fallbacks have not been exhaustively tested.

This UI pass was kept local for review and subsequently approved for commit and push. No dependencies were added to the application runtime, and no deployment or publication was performed. External font loading retains the existing system-font fallback.
