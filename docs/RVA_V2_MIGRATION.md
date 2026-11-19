# RVA v2 — implementation migration and next engineering handoff

**Canonical creator plan:** [v2 Project Plan & Design Handoff](RVA_Project_Plan_and_Design_Handoff_v2.md). The [v2 story contract](RVA_V2_STORY.md) and [v2 gameplay contract](RVA_V2_GAMEPLAY.md) are implementation-focused extractions. This page distinguishes actual code from planned gameplay.

## Completed in this branch

- A source-faithful copy of the creator's **v2 plan** (not just a paraphrase).
- Updated README and architecture manifest to establish v2 precedence over older civic-sandbox lore.
- `design/v2_campaign.json`: titles, act sequence, group wings / geography, story beats and mechanic names for a data-driven future mission loader. Unknown mission details are intentionally not invented.
- `UCivicWorkOrderSubsystem` (Blueprint-visible UE5 runtime C++) with Begin → Select Method → Complete, one-resolution-per-ID, Net Good/collateral totals, per-district 0–3 Strain, 0–4 Compliance tier, wing contact unlocks, a bounded work-zone authorization predicate and conditional ending eligibility.
- `CivicCampaignRules.h`: engine-free validated math and eligibility rules, plus standalone C++ tests and Python test launcher.
- Contract checks in `tests/test_v2_campaign_catalog.py` for count/order, factions, beats and method names.

**Not claimed:** Unreal compilation, editor Play-in-Editor (PIE), traffic navigation updates, 3D authored missions, playable narrative, actual theft/chases, save persistence or production-ready driving.

## Planned migration from the older plugin

| Legacy implementation | V2 decision | Migration action |
| --- | --- | --- |
| `UCivicFactionSubsystem` nine-enum faction/reputation model | Five playable groups with Believer/Means contacts; Compliance and outside capital as pressure systems | Keep legacy API until engine build verified; migrate authored faction logic in separate change with tests, not by renaming enums blindly. |
| Fiscal/tax gauge and 95% admin-share satire | Ghost Connector, grant/contracts/parcel leverage, Net Good | Preserve as graybox historical logic; don't put legacy tax UI in the current campaign unless revived intentionally. |
| `UCivicToolComponent` Line-Striper collision launch effect | Authored street **segment** state transitions with deferred traffic reroute | New segment-state authoring API, one target segment per stroke, next-junction repathing; remove/retire old collision boost only after gameplay proof. |
| Pothole Cannon physics anchor | Optional limited-charge **Patch Gun** (ramps/bumps/grip patches) | Reuse physics assets and rename via migration; not essential to first slice. |
| Compost Launcher | Defer/not a v2 pillar | Keep source isolated; avoid dependency in new missions. |
| Existing council and street audit graybox concepts | Work Order verbs / Method Dial / Hi-Vis | Retain usable authored props and city map; reframe activity around new contract, not separate modes. |
| Faction-triggered Data Layer assets | Capped 12–16 Strain-driven world-state swaps | Give Strain layers discrete ownership; do not let old faction overrides fight the new controller over one layer. |

## Next implementable tasks in order

1. **Build check:** Compile on the target UE5 editor and run UnrealHeaderTool for `UCivicWorkOrderSubsystem`; validate dynamic delegates, reflection, Blueprint callable structs and world lifetime. Existing tests do not prove this.
2. **Blueprint smoke map:** Start two sample Work Orders, choose Kind/Hard, complete, verify once-only totals, district strain and completion event; test entering/leaving work zone and invalid input. Verify no persistence across map travel is yet promised.
3. **Data loader:** Validate and import v2 JSON or turn it into Unreal Data Assets with stable `M01`–`M30` mission IDs. Title-only missions must remain stub data, not silently filled with generic content.
4. **Church Hill driving:** Terrain-height audit before final asset placement, measured speed, truck loading/grip/brake tune, surface friction, bridge slope and stable wheels on DEM.
5. **Road graph state:** Line-Striper segment normal/bike/closed/reversed; delayed intersection-based AI route selection. Prove 1 block before using it across bridges or highways.
6. **Hi-Vis detection:** Work order + vest + cones + geometric work zone, with Strain-degraded effective radius; avoid full stealth AI.
7. **Compliance:** Script authored citation, tow and code officers as distinct escalation; city/county boundary transition should be a map rule not a stock faction reputation change.
8. **Playtest:** *Night Shift*, shortened *Hill Climb*, a third Kind/Hard job and one Standing Committee skeleton; conduct a go/no-go review before authoring Acts II–IV.
9. **Save and endings:** Persist resolved IDs and counters; tune Collateral thresholds with creator input. **The Third Alignment and Fixer endings remain locked by -1 threshold sentinels until then.**

## Quality and source constraints

- **Never** delete GIS contract data or overwrite the draft terrain PR while migrating gameplay.
- Existing elevation mismatch: NOAA LAZ ~1.33 m below the DEM in the sampled intake; investigate before using for physical street/building alignment.
- Avoid inventing actual bridge names/configuration; use the real map data and verify. Fictional name in dialogue does not change physical geometry.
- For the Jackson Ward historical mission, obtain local-history input before publishing authored scenes.
- No firearm combat. Any burning set piece is scripted, non-lethal, mostly offscreen and not a real-world sabotage tutorial.
- Keep each PR narrowly testable; don't merge or call the game playable without running UE5 and PIE.
