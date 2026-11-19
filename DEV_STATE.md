# Richmond Open World · Development state

<!-- richmond-run-history:begin -->
## Current task status

- **S0-01 · PASS** — Review the evidence and advance to the tasks whose prerequisites are met.
- **S0-02 · PASS** — Review the evidence and advance to the tasks whose prerequisites are met.
- **S0-04 · PASS** — Review the evidence and advance to the tasks whose prerequisites are met.
- **S0-05 · PASS** — Review the evidence and advance to the tasks whose prerequisites are met.
- **S0-06 · PASS** — Review the evidence and advance to the tasks whose prerequisites are met.
- **S0-07 · PASS** — Review the evidence and advance to the tasks whose prerequisites are met.
- **S0-08 · PASS** — Review the evidence and advance to the tasks whose prerequisites are met.

## Run history

- `20261119T003601930043Z-c2a91d62` · S0-01 · **PASS** · 2026-11-19T00:36:01+00:00 → 2026-11-19T00:36:02+00:00 · [run evidence](reports/runs/20261119T003601930043Z-c2a91d62.json)
- `20261119T003602882113Z-4e82b1b6` · S0-01 · **PASS** · 2026-11-19T00:36:02+00:00 → 2026-11-19T00:36:03+00:00 · [run evidence](reports/runs/20261119T003602882113Z-4e82b1b6.json)
- `20261119T003721531161Z-a13bb57b` · S0-01 · **PASS** · 2026-11-19T00:37:21+00:00 → 2026-11-19T00:37:22+00:00 · [run evidence](reports/runs/20261119T003721531161Z-a13bb57b.json)
- `20261119T003722549595Z-3531e87a` · S0-01 · **PASS** · 2026-11-19T00:37:22+00:00 → 2026-11-19T00:37:22+00:00 · [run evidence](reports/runs/20261119T003722549595Z-3531e87a.json)
- `20261119T005710603518Z-28815309` · S0-02 · **PASS** · 2026-11-19T00:57:10+00:00 → 2026-11-19T00:57:11+00:00 · [run evidence](reports/runs/20261119T005710603518Z-28815309.json)
- `20261119T005711221016Z-fedb142b` · S0-02 · **PASS** · 2026-11-19T00:57:11+00:00 → 2026-11-19T00:57:12+00:00 · [run evidence](reports/runs/20261119T005711221016Z-fedb142b.json)
- `20261119T022150098025Z-ca98ee62` · S0-04 · **PASS** · 2026-11-19T02:21:50+00:00 → 2026-11-19T02:21:51+00:00 · [run evidence](reports/runs/20261119T022150098025Z-ca98ee62.json)
- `20261119T022243319852Z-f77703cf` · S0-04 · **PASS** · 2026-11-19T02:22:43+00:00 → 2026-11-19T02:22:44+00:00 · [run evidence](reports/runs/20261119T022243319852Z-f77703cf.json)
- `20261119T023956740444Z-67cb4c93` · S0-05 · **PASS** · 2026-11-19T02:39:56+00:00 → 2026-11-19T02:39:58+00:00 · [run evidence](reports/runs/20261119T023956740444Z-67cb4c93.json)
- `20261119T032037767315Z-4fb548a4` · S0-06 · **PASS** · 2026-11-19T03:20:37+00:00 → 2026-11-19T03:20:39+00:00 · [run evidence](reports/runs/20261119T032037767315Z-4fb548a4.json)
- `20261119T033153008041Z-eab08a10` · S0-07 · **PASS** · 2026-11-19T03:31:53+00:00 → 2026-11-19T03:31:54+00:00 · [run evidence](reports/runs/20261119T033153008041Z-eab08a10.json)
- `20261119T035103695033Z-f0b6adb4` · S0-08 · **PASS** · 2026-11-19T03:51:03+00:00 → 2026-11-19T03:51:05+00:00 · [run evidence](reports/runs/20261119T035103695033Z-f0b6adb4.json)
<!-- richmond-run-history:end -->

## Civic pivot

- **Built** the `RVA: Aggressive Altruism` architecture and named The Albanico Association as the preservation faction. Added the UE5 C++20 `RVACivic` module, faction and fiscal state, Runtime Data Layer rules, and the three Chaos tool behaviors.
- **Verification** all 13 local tests passed, including the compiled C++20 policy checks. The plugin sources passed the placeholder scan. The full UnrealBuildTool build and PIE interaction checks require the UE5 editor on the target PC.
- **Terrain evidence** the recent source intake delivered the first pair's NOAA DEM and LAZ files. The class-2 comparison found LAZ elevations about 1.33 m below the DEM. Carry that discrepancy into the terrain review before placing LiDAR-derived assets.
- **Bottlenecks to profile** the compost launcher makes one visibility trace per candidate and the temporary tool effects spawn actors. Measure trace cost and actor churn in Unreal Insights. Keep faction-managed layer assets separate from terrain streaming.

## Standing Committee first favor

- **Built** Mara's updated campaign outline and one optional borrow-and-return encounter. Its native actor includes two 20-foot decoration variants, a visible hand truck and an assignable courtyard gate reward.
- **Verification** the standalone C++20 state tests cover completion, no premature or repeated return, and retry after losing the borrower. Unreal build and placement checks remain open.
- **Bottlenecks to profile** move a single graybox actor through the placement workflow before widening to a two-cell street. Verify borrowed prop attachment, visual scale and overlap settings in PIE.

## Campaign v2 and mission outline

- **Built** the v2 campaign and all 30 mission beats with district, faction, and production scope updated. Adopted the ghost Connector, shared Church Hill rowhouse, and recurring Standing Committee as working defaults. The existing hand-truck encounter now foreshadows the formal reveal in mission 11.
- **Resolved story continuity** Tate pays the initial lien before Cal sells his share. The later sale threat comes from the new co-ownership dispute. The finale combines the Night Shift Log, the dispatch record and Dell's corroboration.
- **Ready for graybox** Night Shift has a four-beat build card and checkpoint acceptance cases. Keep the short Hill Climb and Survey Stakes method variants on the same slice budget.
- **Verification boundary** mission order, ending routes and local links were reviewed. The existing 14-test suite passed. Assembling and playing the first slice in Unreal remain open.

## Night Shift graybox

- **Built** a placeable work-order actor with a briefing, tagged city truck, two end-to-end striping passes, a physical closure with two clearance routes, and yard debrief. The dispatch stub and first truck log record are exposed to the next mission.
- **Checkpoint behavior** in-session retry is available. An optional versioned save slot restores the serialized route and evidence. Authored closure and debrief delegates fire when their milestones are earned.
- **Verification** all 15 local tests passed. The C++20 Night Shift test covers both exit routes, duplicate transitions, incomplete and completed checkpoints, and invalid restore data. The full Unreal build and PIE remain unverified.
- **Profile in the editor** check vehicle input and pose on retry, marker visibility from the cab, work-zone registration on a slope, and a missed detour. The flat rig is for objective verification. Author the real block and timing separately.

## Church Hill slice jobs

- **Night Shift verification** expanded the portable tests for a real authorized stripe pass and added `RVA.Graybox.NightShiftNativeFlow` for the native actor. It drives the work-order components with a possessed test pawn and checks closure, alternate exit, checkpoint retry and evidence. Running it in Unreal remains open.
- **Hill Climb** added the placeable cornice delivery with a gentle and direct route, pitch-and-speed cargo slip, scheduled strap warning, stopped recovery and delivery.
- **Survey Stakes** added the untimed occupied-home route and the timed stake swap. The Hard result raises a blocker at loading access. Expiry resets the moved props and leaves the approach open.
- **Test status** all 16 local tests passed. The Unreal build, native automation and real vehicle PIE still need the target editor. Campaign ledger wiring and AI traffic repathing remain integration work.

### Next usage window prompt

> Build RVACivic in the target UE5 project. Run RVA.Graybox.NightShiftNativeFlow, then stage the three actors on the same Church Hill graybox following docs/RVA_Church_Hill_Slice.md. Record real-vehicle Night Shift retries, both Hill Climb routes, and a completed plus an expired Survey Stakes Hard run in DEV_STATE.md.
