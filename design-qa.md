# Lattice visual QA

## Comparison target

- Source visual truth: `C:\Users\hmw20\AppData\Local\Temp\codex-clipboard-892131a6-f8f7-4c90-8986-9f8c4f185843.png`
- Source implementation: `C:\Users\hmw20\Downloads\lattice-research-copilot-source.zip`
- Rendered implementation: `artifacts/visual-audit/06-lattice-hypothesis-stable-1705.png`
- Full-view comparison: `artifacts/visual-audit/compare-hypothesis-final.png`
- Focused hero/composer comparison: `artifacts/visual-audit/compare-hypothesis-composer-focus.png`
- Viewport and state: 1705 × 909 CSS pixels; desktop hypothesis generator, before any model run.

The supplied source capture was 2557 × 1420 physical pixels and included a 56px Windows taskbar. For a like-for-like comparison, its 2557 × 1364 application region was normalized to 1705 × 909 before placing it beside the rendered implementation.

## Primary interactions checked

1. Research workspace navigation — passed.
2. Paper-library navigation and live knowledge-base loading — passed; the list rendered real API papers rather than prototype-only records.
3. Hypothesis-generator navigation — passed.
4. Research-question input and source toggles — passed.
5. Candidate-generation action availability — passed. The button is bound to the real run API but was not invoked during QA because it starts a live model/literature workflow.

## Comparison history

### Baseline

- [P1] The previous workbench used a different visual system and information architecture from the supplied Lattice source: a dense product shell, different navigation hierarchy, and no stable left/main/right research layout.
- Fix: ported the supplied Lattice source layout and tokens into the Vite application, then bound the paper library, run start, hypothesis persistence, and experiment-plan actions to the existing FastAPI client.

### Final review

No actionable P0, P1, or P2 visual differences remain for the desktop hypothesis-generator empty state. The full-view and focused comparison show matching hierarchy, column geometry, serif display typography, color tokens, border radii, hero orbit, prompt-composer proportions, and evidence rail.

## Required fidelity surfaces

- Fonts and typography: matched the source stack (`Inter`/system sans for UI and `Georgia`/`Noto Serif SC` fallback for display text), including the large two-line hypothesis headline and compact metadata.
- Spacing and layout rhythm: matched 250px left navigation, 86px top bar, main/right two-column grid, hero spacing, 16/22px radii, and composer geometry.
- Colors and visual tokens: matched paper white, sage sidebar, deep green, violet hypothesis accent, soft violet evidence card, and low-contrast border system from the source CSS.
- Image and asset fidelity: the original source’s orbit and brand mark code were retained; no substitute raster or placeholder asset was introduced.
- Copy and content: core Lattice labels are preserved. Paper rows now render live knowledge-base data; hypothesis generation, save, and experiment actions call the existing backend instead of simulated timeout behavior.

## Follow-up polish

- [P3] Some legacy knowledge-base records use filename-like titles or have no author metadata. This is source-data cleanup, not a layout mismatch.
- [P3] Advanced administration, terminal, and diagnostics remain outside the default Lattice path. They should return through an explicit expert-mode entry rather than re-entering the primary navigation.

final result: passed
