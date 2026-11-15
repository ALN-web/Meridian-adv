# Prompt: Meridian "Night Network" — cinematic WebGL scroll story

*Written from research into 3D prompt libraries (YouMind, aireiter's tested 3D-website prompts, the
motionsites collection) and technique write-ups (Shopify's BFCM globe: bloom is what makes a data globe
glow; Codrops: scroll-driven cameras behind a normal HTML page; particle globes with flight arcs).*

Build a single-file, **dark, cinematic, scroll-driven WebGL story** for **Meridian Portal Agent**, a
fictional freight forwarder's browser agent that checks every carrier invoice against what was actually
delivered. Plain HTML, CSS and JavaScript; **Three.js r160** from a CDN via an import map, with
`EffectComposer` + `UnrealBloomPass` + `OutputPass`. No framework, no build step, no external models or
textures: every visual is generated in code.

## Mood

Night-shift control room. Deep space background `#04060c`, glowing cobalt `#3d6bff` and cyan `#5ef2ff`
light, soft bloom, floating dust. Frosted-glass UI panels (`backdrop-filter: blur`) with thin 1px borders
at 12% white. Status colours only with a text label: pass `#39e58c`, overcharge `#ff4d5e`, attention `#ffb547`.

Type: **Space Grotesk** 400–700 for headlines and UI, **JetBrains Mono** for numbers, codes and counters.
Headlines large (clamp 44–96px), tight tracking (−0.03em), cyan-to-cobalt gradient on the key phrase.

## The world (positions in scene units)

1. **Particle Earth** at the origin, radius 10: ~9,000 Fibonacci-sphere points, dim navy, round and soft,
   with a fresnel atmosphere rim. **India** is a lit region: points inside an India outline polygon glow
   cyan. City markers with pulsing rings: **Pune** (hub), Bengaluru, Hyderabad, Chennai, Delhi, Ahmedabad.
   **Five great-circle arcs** from Pune lift off the surface; a light pulse travels along each.
2. **Station A, "The portal"** at x = 60: nine floating 2009-style portal windows in a curved wall
   (blue title bars, grey grids). They glitch between states: *Server Error in '/' Application* (red),
   *Enter one-time password → a person* (amber), *Notice* overlay (yellow), *Session expired*. An agent orb
   hops between windows on a cyan beam. By the end of the segment every window settles to a green "200 OK ✓".
3. **Station B, "The rules ring"** at x = 110: a glowing torus ring with eight labelled rule nodes
   (WEIGHT +2%, RATE @ BOOKING, FUEL % BY MONTH, DETENTION vs POD, BILLED TWICE, UNKNOWN SHIPMENT, NO POD,
   LINES + 12% GST). A stream of ~220 invoice-line chips flows through the ring; leaving it, they split
   into a green upper lane and a red lower lane. Live counters: lines checked, overcharged.
4. **Station C, "One dispute"** at x = 156: a large glass invoice card (TIR/26-27/10118: billed ₹91,457.96,
   correct ₹88,829.62, over ₹2,628.34, `weight_over`). An approval ring draws around it; when closed the card
   is stamped **APPROVED BY A PERSON**, then slides into a stack labelled *Portal dispute list* with
   ✓ checked before, ✓ checked after, **0 duplicates**.
5. Background: 2,500 faint dust points in a large sphere that drift slightly, so camera moves feel fast.

## Scroll story (progress p, 0 → 1; camera eased between keyframes, damped)

| p | Section copy | Camera |
|---|---|---|
| 0.00 | Kicker "Meridian Freight · Accounts payable". **The carrier bills. *We check every line.*** | Wide on the slowly turning globe. |
| 0.16 | **Five lanes. *600 invoices a month.*** One carrier, a 2009 portal, no API. | Glides in over India; arcs draw from Pune; city codes appear. |
| 0.32 | **A portal that *fights back.*** Errors, pop-ups, expired sessions, one-time passwords to a person; resume, never restart. | Flies to Station A. |
| 0.50 | **Eight rules. *Zero guesses.*** Checked in code to within ₹1; the model never does arithmetic. | Flies to Station B. |
| 0.68 | **Disputes, *only when right.*** Over ₹500, approved by a person, checked before and after; never twice. | Flies to Station C. |
| 0.84 | **Every step, *on the record.*** One trace per task, masked screenshots, an evaluation scored against the answer key. | Back to the globe, all arcs pulsing. |
| 1.00 | **Did the carrier bill us *for what it delivered?*** CTA buttons. | Slow wide pull-back. |

- A right-hand rail shows the six chapters (dot + label) and highlights the current one.
- Section text sits in a glass panel on the left; it fades and rises in when its section is centred.
- Scroll drives everything; scrolling up reverses it. Idle motion (globe spin, pulses, dust, chip stream)
  runs on time but is disabled under `prefers-reduced-motion`.

## Quality bar

- 60fps on a laptop: one render loop, pixel ratio ≤ 2 (≤ 1.5 on phones), pause when the tab is hidden.
  Phones: bloom at half resolution, fewer points, text panels full width at the bottom.
- Bloom threshold high enough that panel text never smears; only arcs, rings, markers and chips glow.
- No real brands, logos or people. Fictional companies only; numbers from the project's demo data.
- Without WebGL, the text reads top to bottom on the dark background.

## Acceptance (1440×960)

- Load: glowing globe with India lit and the headline readable; no console errors.
- 16%: India fills the right half, five arcs with travelling pulses, city codes visible.
- 32%: portal windows glitching red / amber, agent beam hopping; by the end all green.
- 50%: chips stream through the ring and split green / red; counters climb.
- 68%: approval ring closes, card stamped, slides into the dispute list, "0 duplicates".
- 84%–100%: back to the globe, all arcs live, CTA visible. Scrolling back reverses everything.
