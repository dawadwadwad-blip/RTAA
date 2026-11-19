# RVA: Aggressive Altruism — Gameplay & Production Contract (v2)

**Design authority:** Creator's Nov 18, 2026 Project Plan & Design Handoff (v2). Read [the story contract](RVA_V2_STORY.md) for cast, factions, geography, mission order and endings. This document states intended systems; **do not treat the table as an implemented-feature list**.

## Game identity and player loop

Drive a heavy city vehicle through real, hilly Richmond while using the legitimacy of a vest, cones and a work order to belong anywhere. Choose how far to go on behalf of groups you believe are helping.

**Work Order loop:** receive job → scout → select **Method Dial** → execute → resolve heat, Net Good and collateral → update limited neighborhood state.

A shared Work Order grammar supplies **seven verbs**: `stripe`, `patch`, `tow`, `deliver`, `swap`, `block`, `tail`. Mission-specific set pieces combine and configure these verbs; they are not seven independent minigames.

## Must-have for the first vertical slice

| System | Intended contract | Approx. v2 difficulty |
| --- | --- | --- |
| **Heavy vehicle driving** | City truck, weight and load mass, hills, limited brake and cargo grip, surface friction. Eventually six classes: city truck, flatbed, cargo bike, pickup, sedan, bus. Actual distance/speed must match GIS street measurements. | High |
| **Work Order template** | Work order data: verb, location, objective, timer and cargo, work-zone bounds, restrictions, outcomes. Build shared mission state and completion callbacks. | Medium |
| **Method Dial** | `Kind`, `Pointed` or `Hard` per offered job. Hard gives greater immediate pay but creates heat/Collateral and may grow district Strain. Author tailored alternatives on only ~12 key missions; others use risk/guard/collateral modifiers. | Medium |
| **Hi-Vis immunity** | Valid vest + cones + active signed Work Order allows Mara to stand in sight within a bounded work zone. The protection is reduced in high-Strain areas and expires with mission or zone exit. This is a readable rules-based suspicion mechanic, **not** full stealth AI. | Low–Medium |
| **Line-Striper** | Mark *authored road segment states*: normal, bike lane, closed, reversed. AI navigation/traffic chooses behavior at **next junction after a delay**. Keep segment states limited, reversible and auditable. The earlier physical 'speed-bump launcher' implementation is a prototype, **not the v2 final road mechanic**. | Medium |
| **Compliance** | Progressive response: citation → tow → code enforcement → police → county sheriff behavior after city boundary. Hard method may begin at tier 2; Believer contact may reduce a tier once per act. Reuse traffic/navigation actors; author rules, do not claim county agencies actually behave this way. | Medium |
| **Net Good ledger** | For each resolved Work Order, track integer **households helped** and **households harmed**, not a single moral score. Show accumulated totals. Tate's in-story 412/38 is narrative reference, not the player's starting ledger. | Low |

## High-value optional after core slice

- **Collateral + district Strain:** Each district has 0–3 Strain levels caused by Hard methods and negative collateral outcomes. A *capped* set of 12–16 World Partition Data Layer swaps across the world (boarded shops, banners, scaffolding) expresses state. Do not simulate a fully dynamic city.
- **Wing contacts:** Each of five groups has a Believer and a Means contact. Believers offer safe access, discounts, Strain/Collateral help; Means offer targeted mission tools. No unbounded faction reputation simulation is required.
- **Honest Work:** Lawful striping, pothole repair and tow-outs earn positive Net Good and reduce Strain. Essential tonal contrast; low-cost uses same Work Order verbs.
- **Patch Gun:** Reinterpret old Pothole Cannon as a **limited-charge** bump/ramp/grip-patch prop for chases. Do not make it a full urban excavation mechanic. Prior `PotholeCannon` code can be adapted instead of deleted before UE verification.
- **Standing Committee hunt:** Skeleton pattern side content, using existing exploration and story unlock interactions.

### Authored Means and Believer contact effects

| Contact | Means-wing reward |
| --- | --- |
| Pod Closers | Forged permit: one gate or citation per job |
| Albanico Mortar Circle | Scripted non-lethal scaffold-fire objective tool (mission-only) |
| Militia Spoke Cell | Hold authored traffic light state for 30 sec |
| Truck-Nutz Hitch | Tow hook pulling a vehicle out of pursuit |
| Independent Landlord Club | Keys to a rival shop back room |
| Compliance Procedure Office | Backdated stamp to skip one procedural step |
| Committee Files | Leverage chip to bypass one procedural minigame |

Believer rewards: Albanico Review Board support letter reduces heat; Pod Prime Builders give crane/forklift access; Militia Dispatch grants alleys and trail shortcuts; Asphalt Samaritans supply a free tow-out; Pike's clerks dismiss one citation per act. All effects are game-fiction abstractions.

## Explicit de-scopes

- **No firearm combat or cover shooting.** Use slapstick object contact, cones, bumper nudges, vehicle mishaps, non-lethal consequences.
- **No full stealth AI.** Work-zone Hi-Vis permissions plus narrow authored detection suffice.
- **No continuous world-wide traffic/economy/politics simulation.**
- **No mission-specific driving models per faction.**
- **No major branching mission trees.** One final choice + a small number of conditioned ending/epilogue states.
- **No mandatory large interior set:** prioritize hearing room, records office and Committee basement.
- Legacy `CompostLauncher`, fiscal tax-gauge and blanket reputation rivalries are older graybox concepts. Preserve working source initially, but do **not** treat them as essential v2 pillars.

## Readable state model (recommended for implementation)

Per active Work Order:
- `missionId`, `verb`, `district`, `contractWing`, `offeredMethods`, `chosenMethod`, `zoneId`, `objectives`, `outcome`.
- `helpedHouseholds`, `harmedHouseholds` are **non-negative whole counts** recorded **once** per job.
- `collateral` is a separate consequence count; this is not interchangeable with harmed-household count.
- `heatTier` is clamped to an authored tier range; `Strain` per district is clamped 0–3.
- Do not expose `Third Alignment` when Collateral is above the threshold or needed Believer contacts are absent; do not expose `Fixer` when Collateral / Means conditions are missing. **Threshold values are tuning data, not yet approved.**
- Plot milestones (15,16,22,23,25,29,30) are explicit script gates. The mission-23 fire/auction branch is visibly foreshadowed from prior choice state.

For any save/load implementation, serialize once-resolved job IDs so mission rewards cannot be farmed by retry/reloading.

## Geography and route constraints

- Geographic truth comes from OSM + municipal elevation/building data and existing GIS contract; **do not replace it with decorative fake grids**.
- Fictional names in dialogues should not change physical bridge locations, street distances or GIS road routing.
- **River crossings:** small number of bridge options, with scripted closures/reroutes. Don't implement cross-map closure until traffic can repath at next junction.
- **Rail crossing:** scripted timing and visible safety rules, not uncontrolled physical train collisions.
- **City–county edge:** fictional enforcement handoff upon polygon boundary crossing.
- **Terrain:** prototype load grip and braking on actual Church Hill slopes before tuning dramatic chases.

## Production priority and validation

### Vertical slice (20–30 minutes intended, not yet built)

1. **Area:** connected Church Hill → Shockoe Bottom → short downtown strip, preserving World Partition, elevation and OSM geometry.
2. **Missions:** `Night Shift` (forged order, hi-vis and striping); abbreviated `Hill Climb` (grades and cargo); one faction job with **Kind** and **Hard** method alternatives.
3. **Mechanics:** scalable truck physics, Work Orders, Hi-Vis immunity, road-segment state updates, Compliance tiers 1–3, Method Dial, Net Good totals.
4. **Drama:** scaffolding fire framed as sabotage, lien notice, Dell mentorship and first Tate contact.
5. **Discovery:** one giant skeleton with a short optional payoff.

### Go/no-go checklist

- [ ] Two adjacent terrain tiles, OSM roads and physical grade align and vehicle speed is world-scaled.
- [ ] The same mission can complete with Kind or Hard methods and produce **different observable** consequences.
- [ ] Hi-Vis permission works only with an active valid work zone.
- [ ] Line-Striper updates exactly the targeted road segment; traffic reacts at a junction without teleporting or choosing invalid paths.
- [ ] Citation/tow/code response feels readable; escalation does not trap player in an unwinnable loop.
- [ ] Net Good records exactly once; no negative helped/harmed numbers.
- [ ] The skeleton clue is discoverable without a lore dump.
- [ ] Gameplay is fun without 27 more missions or many city swaps.
- [ ] UnrealBuildTool + UnrealHeaderTool build and PIE tests pass on the target UE5 installation; standalone unit tests are **not** a substitute.

### Phased delivery

1. Vertical slice and playtest; gate further work on feel of driving and Method Dial.
2. Harden six shared vehicle classes, Work Orders, Compliance, Strain and authored segment navigation.
3. Acts I–II + bridge unlock, supported by data-driven mission catalog.
4. Act III set pieces (bridges, rail, house consequence).
5. Act IV and endings, then balance and polish.

**Known risks:** traffic repathing for Line-Striper; asset authoring for 12 method variants; runtime data-layer interactions with World Partition; preserving source-accurate elevation (existing DEM vs LiDAR discrepancy); tone of arson/blackmail; local-history research. These are gates, not solved features.
