# Build an Elegant TUI


Build a **terminal user interface (TUI)** application with a refined, modern, "boutique software" aesthetic. Treat the terminal as a design surface, not just a log stream. Quality of presentation matters as much as functionality.

## Stack
- Use a mature TUI framework rather than raw `print`/ANSI: prefer **Textual** or **Rich** (Python), **Bubble Tea + Lip Gloss** (Go), or **Ratatui** (Rust). Pick one and justify it in one sentence.
- No raw escape codes scattered through logic. Centralize all styling in a theme module.

## Visual language
- **Borders:** rounded or thin box-drawing characters (`╭ ─ ╮ │ ╰ ╯`), used consistently. Never mix border styles.
- **Color:** a single cohesive palette of 4–6 colors (one accent, one muted/secondary, plus foreground/background/border). Use a tasteful dark theme by default; support `NO_COLOR` and degrade gracefully on 16-color terminals. Avoid loud, saturated rainbows.
- **Typography in-terminal:** use weight and dimming (bold / dim / italic) for hierarchy instead of color alone. Align numbers, pad columns, and keep tables tidy.
- **Iconography:** sparing, meaningful Unicode glyphs (e.g. `●`, `→`, `✓`, `⚠`) — never decorative clutter. Provide an ASCII-only fallback flag.

## Interaction & motion
- Keyboard-first navigation with discoverable, single-key bindings shown in a persistent footer hint bar.
- Smooth, non-flickering redraws. Subtle transitions/spinners for async work; no spammy progress text.
- Helpful empty states and a clean focus indicator on the active element.

## Engineering quality
- Separate concerns: state / view / theme / input handling.
- Responsive to terminal resize.
- A `--help` screen that itself looks polished.
- Cross-platform (macOS/Linux at minimum; note Windows caveats).

## Deliverables
1. Runnable project with clear run instructions.
2. The theme/style module isolated and well-commented so colors and borders can be swapped in one place.
3. A short README with a screenshot description and the keybindings.

Start by proposing the framework choice, the color palette (with hex values), and a quick ASCII sketch of the main screen layout. Wait for nothing — then build it.