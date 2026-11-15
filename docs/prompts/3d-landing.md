# Prompt: Meridian 3D scroll story — "One invoice's journey"

Build a single-file **scroll-driven 3D story** for **Meridian Portal Agent** (a fictional freight
forwarder's invoice-checking browser agent) in plain HTML, CSS and JavaScript with **Three.js r160**
loaded from a CDN through an import map. No framework, no build step, no downloaded 3D models:
every object is modelled in code from primitives, so there are no licences to check.

The story: a truck arrives with a container; the agent weighs what was billed against what was
delivered; the invoice lines flip to *match* or *overcharge*; a person approves the one dispute that
is right; the camera rises to show the five lanes out of Pune.

## Look

- Clean studio, not a game: white background `#ffffff`, ground `#f4f4f2` that fades to white at the
  horizon (fog), ink `#111111`, cobalt accent `#2f63ff`.
- Status colours used only with a text label: match `#0ca30c`, overcharge `#d03b3b`, cancelled `#8a8a8a`.
- Type: **Anton** (big caps), **Archivo** 400–600 (body, UI), **JetBrains Mono** (numbers, readouts).
- Soft shadows (one directional light + hemisphere fill), ACES tone mapping, sRGB output.
- Low-poly but crafted: rounded boxes for the cab and container, dark glass windshield, six wheel sets,
  container corrugation drawn on a canvas texture, door bars on the back.

## Layout

- A fixed full-screen `<canvas>` behind the page.
- Seven `<section>`s, each 100vh tall, holding the story text on the left (max 440px), so the 3D
  stays visible on the right. Text fades and rises 16px in when its section is in view.
- A thin progress bar at the top and a "scroll" hint on the first screen.
- Fixed nav: "Meridian" wordmark left; "2D story", "Operator screen", and an outline pill
  "Run a task" right. Buttons open the operator screen (port 8510, override with `?app=`).

## Sections and what the 3D does (scroll progress p from 0 to 1)

| p | Section text | 3D |
|---|---|---|
| 0.00 | **Every invoice, checked against what was delivered.** Kicker "Meridian Freight · Accounts payable". | 3/4 hero view of the truck; slow idle orbit (±3°). |
| 0.17 | **The portal fights back.** 600 invoices a month, a 2009 portal with no API; the agent logs in, hands one-time passwords to a person, and survives errors, pop-ups and expired sessions. | Camera orbits to the other side; a ring of small "page" tiles flickers around the cab: some red (error), one amber (OTP), then all settle cobalt. |
| 0.33 | **Weigh what was billed.** Billed 1,974.4 kg; Meridian's record says 1,828.1 kg; the limit is +2% (1,864.7 kg). → `weight_over`. | Container turns 75% transparent and shows the shipment crates inside; a cobalt scan plane sweeps along the container; a mono readout tracks it and ends on **+8.0%** in red. |
| 0.50 | **Eight rules, in code.** The rules engine never guesses; amounts compare within ₹1. Chips: weight, rate, fuel %, detention, duplicate, unknown, no POD, totals. | Five invoice cards rise above the truck and flip one by one: 10118 overcharge, 10119 cancelled, 10120 overcharge, 10121 overcharge, 10122 match. |
| 0.67 | **Disputes, only when right.** Over ₹500, approved by a person, checked in the dispute list before and after. Never twice. | Card 10118 gets an "APPROVED" stamp, moves into a dispute tray, and a "1 raised · 0 duplicates" counter appears. |
| 0.83 | **Five lanes out of Pune.** BLR, HYD, CHN, DEL, AMD; every lane-month reconciled. | Camera rises to a near top-down view; the truck sits on the Pune hub; five arcs draw out to city pads; small trucks travel each arc. |
| 1.00 | **Did the carrier bill us for what it delivered?** Buttons: Open the operator screen · See the evaluation · 2D story. | Wide, slow final view of the network. |

## Motion rules

- Scroll drives everything and reverses on scroll-up. The camera eases toward keyframed positions
  (smoothstep between keys, then damped lerp at 0.08 per frame).
- Small idle motion only (wheels at rest, trucks on arcs, a soft camera drift), switched off under
  `prefers-reduced-motion`.
- Hold 60fps on a laptop: one render loop, pixel ratio ≤ 2, pause when the tab is hidden.
- Phones (< 768px or portrait): pixel ratio ≤ 1.5, no shadows, wider FOV, text full-width over a
  white gradient at the bottom, so the 3D sits in the top half.
- If WebGL isn't available, the text still reads top to bottom over a plain background.

## Content rules

- Fictional companies only (Meridian Freight, TransIndus Roadways); no real brands or logos.
- Numbers come from the project's demo data (invoice numbers, amounts, the 1,974.4 / 1,828.1 kg line).

## Acceptance check (1440×960)

- On load: the truck and navy container in a 3/4 studio view; the headline left; the scroll hint shows.
- At 33%: the container is see-through with crates, the scan sweeps, and the readout ends on +8.0% red.
- At 50%: five cards above the truck, each flipped to its result with a label.
- At 67%: the approved card sits in the tray; the counter reads "1 raised · 0 duplicates".
- At 83%: top-down view, five lanes drawn, trucks moving.
- Scrolling back reverses everything. No horizontal scroll. Console has no errors.
