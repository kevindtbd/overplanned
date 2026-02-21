# Globe Hero Merge — Design Plan

## Problem Statement
The current landing page hero has two separate globe implementations:
1. **Desktop (md+)**: Full-bleed absolute-positioned globe behind hero text in a `min-h-screen` section
2. **Mobile (<md)**: A separate 320px tall `<div>` below the hero section

Issues identified from screenshots:
- Mobile: Globe banner eats 320px of vertical space as a disconnected band
- Desktop: `min-h-screen` creates excessive whitespace; globe feels separate from content
- City node glows/shadows are too heavy — distracting from the data visualization
- Globe could be bigger to fill the space better

## Proposed Change: Single Unified Hero

### Layout
- **Kill the two-div pattern**: Remove the separate `md:hidden` mobile globe banner entirely
- **Single hero section**: Globe renders in ONE container for all breakpoints
- **Globe bleeds into hero text**: Position globe so it overlaps the bottom portion of the text area
- **Reduce hero height**: Drop `min-h-screen` to something tighter like `min-h-[85vh]` or height-auto with generous padding
- **Globe bigger**: Increase R multiplier so globe fills more of the available space

### Responsive Behavior (single GlobeCanvas instance)
- **Mobile (W < 768)**: Globe centered horizontally, positioned in the lower portion of the hero. Text sits above it with z-index layering. Globe peeks up from below the CTA buttons.
- **Desktop (W >= 768)**: Globe offset right as before, but with a larger radius.

### Specific CSS/Layout Changes
1. Remove `<div className="md:hidden relative h-[320px] ..."><GlobeCanvas /></div>` (mobile banner)
2. Remove `hidden md:block` from desktop globe container
3. Make globe container span full hero section for all breakpoints
4. Reduce hero section from `min-h-screen` to `min-h-[85vh]` or less
5. Add bottom gradient overlay so globe fades out before the next section

### GlobeCanvas.tsx Changes
- **Mobile positioning**: `cx = W * 0.5`, `cy = H * 0.65` (lower in section), `R = Math.min(W * 0.55, H * 0.4)`
- **Desktop positioning**: Keep right-offset, bump R from `H * 0.48` to `H * 0.52`
- **Tone down city node glows**: Reduce outer glow radius from `c.r + 8` to `c.r + 5`, reduce glow alpha
- **Tooltips**: Already hidden on mobile from previous fix; keep that

### Visual Effect
The globe should feel like it's emerging from behind the text content, partially visible, creating depth. Like the globe is a background element that the hero text floats over. On mobile, the globe sits in the lower 40% of the hero, text in the upper 60%.

## Files Changed
- `apps/web/app/page.tsx` — Hero section layout restructure
- `apps/web/components/landing/GlobeCanvas.tsx` — Positioning, sizing, glow reduction
