# Prompt: Meridian website — industrial freight style with 3D

*Visual language inspired by modern freight-company sites (white space, black and industrial yellow,
containers on crane hooks, monospace micro-copy). Original brand, layout and copy for Meridian; no
third-party logos, names or assets.*

Build a single-file marketing website for **Meridian Portal Agent**: a browser agent that checks every
carrier invoice against what was actually delivered, and raises a dispute only after a person approves.
Plain HTML/CSS/JS with **Three.js r160** from a CDN (import map). Every 3D object is modelled in code.

## Look

- Palette: white `#ffffff`, paper `#f3f3f1`, ink `#0e0e0e`, industrial yellow `#f5c400`, steel greys.
- Type: **Manrope** 400–800 for headlines and UI (tight tracking), **IBM Plex Mono** for tiny uppercase
  captions, numbers and labels.
- Brand mark: two yellow slanted bars + "MERIDIAN" wordmark.
- Lots of white space, hairline dividers, small mono labels like `● ABOUT MERIDIAN`, pill buttons.

## Sections

1. **Nav**: mark left; centre pill bar (About · How it works · What it checks · Results); right black pill
   "Open operator →".
2. **Hero (pinned, ~220vh of scroll)**: headline *Checking freight bills. / One invoice at a time.*; proof
   row (avatars + "600+ invoices a month"); mono blurb and two buttons. 3D: a crane cable comes from above,
   a yellow-and-black striped hook block, four slings to a **black container branded MERIDIAN**, swaying.
   Below, stacks of yellow, white and black containers bleed off the bottom. On scroll the container
   turns, lowers and lands on the stack; the camera eases closer.
3. **About (black band)**: *Built on one question: did the carrier bill us for what it delivered?* plus
   a mono paragraph and a yellow button. Container roofs peek over the top edge.
4. **How it works (white)**: five numbered steps (Operate · Collect · Reconcile · Dispute · Report) with
   mono descriptions, beside a grid of black/yellow stat tiles: 600+ invoices/month, 8 rules in code,
   ₹1 tolerance, 0 duplicate disputes.
5. **Top-down ship (3D)**: a container ship seen from above sails up the screen as you scroll; a yellow
   scan line sweeps its bays and turns checked containers green or red; callouts count lines checked.
6. **What it checks (dark)**: eight rule cards (code, title, one-line rule, example), yellow tags.
7. **Results / trust**: three short proof points (safety, robustness, evidence) and the evaluation targets.
8. **CTA + footer**: *Ready when the next 600 invoices land.*; operator and evaluation buttons; fine print.

## Motion

- Scroll drives the hero and the ship; idle sway is time-based and disabled under reduced motion.
- Sections reveal with a 16px rise. One render loop per canvas; canvases pause when off-screen.
- Phones: canvas sits behind the hero text at reduced opacity of detail; tiles become two columns.

## Acceptance

- Load at 1440×900: container hanging over stacks, headline left, no console errors.
- Hero scroll: container rotates and lands on the stack; scrolling back reverses it.
- Ship section: ship moves with scroll, scan line colours containers, counters climb.
- All buttons open the operator screen on port 8510 (override with `?app=`).
