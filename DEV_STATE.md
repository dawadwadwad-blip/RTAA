## V2 story and gameplay pivot — design integration (Nov 18, 2026)

- **Created** [current narrative/world contract](docs/RVA_V2_STORY.md), including the ghost Richmond Connector, Mara/Cal/Dell/Tate/Pike, Five faction wings and territories, Standing Committee, 30 ordered missions and conditional endings.
- **Created** [gameplay and vertical-slice contract](docs/RVA_V2_GAMEPLAY.md): Work Orders (seven verbs), Kind/Pointed/Hard Method Dial, Hi-Vis zones, road-segment Line-Striper, Compliance ladder, Net Good ledger, capped Strain, and no firearms.
- **Created** [campaign JSON](design/v2_campaign.json) and catalog checks. These are **design data only** and not UE-authored mission assets.
- **Existing code status:** `RVACivic` faction tax/reputation and physical tools implement the **v1 graybox**, not the new v2 Method Dial, traffic repath or campaign. Do not treat legacy tax model/road traps as current production behavior.
- **Open gates:** local UE5 build/UHT and PIE tests, DEM/LAZ vertical-offset reconciliation (~1.33 m previously observed), traffic rerouting feasibility, driving grade feel, Method Dial playtest, and historic research for Jackson Ward. No claim of full game integration yet.

---

# Richmond Open World · Development state

<!-- richmond-run-history:begin -->
## Current task status

- **S0-01 · PASS** — Review the evidence and advance to the tasks whose prerequisites are met.
- **S0-02 · PASS** — Review the evidence and advance to the tasks whose prerequisites are met.
- **S0-04 · PASS** — Review the evidence and advance to the tasks whose prerequisites are met.

## Run history

- `20261119T003601930043Z-c2a91d62` · S0-01 · **PASS** · 2026-11-19T00:36:01+00:00 → 2026-11-19T00:36:02+00:00 · [run evidence](reports/runs/20261119T003601930043Z-c2a91d62.json)
- `20261119T003602882113Z-4e82b1b6` · S0-01 · **PASS** · 2026-11-19T00:36:02+00:00 → 2026-11-19T00:36:03+00:00 · [run evidence](reports/runs/20261119T003602882113Z-4e82b1b6.json)
- `20261119T003721531161Z-a13bb57b` · S0-01 · **PASS** · 2026-11-19T00:37:21+00:00 → 2026-11-19T00:37:22+00:00 · [run evidence](reports/runs/20261119T003721531161Z-a13bb57b.json)
- `20261119T003722549595Z-3531e87a` · S0-01 · **PASS** · 2026-11-19T00:37:22+00:00 → 2026-11-19T00:37:22+00:00 · [run evidence](reports/runs/20261119T003722549595Z-3531e87a.json)
- `20261119T005710603518Z-28815309` · S0-02 · **PASS** · 2026-11-19T00:57:10+00:00 → 2026-11-19T00:57:11+00:00 · [run evidence](reports/runs/20261119T005710603518Z-28815309.json)
- `20261119T005711221016Z-fedb142b` · S0-02 · **PASS** · 2026-11-19T00:57:11+00:00 → 2026-11-19T00:57:12+00:00 · [run evidence](reports/runs/20261119T005711221016Z-fedb142b.json)
- `20261119T022150098025Z-ca98ee62` · S0-04 · **PASS** · 2026-11-19T02:21:50+00:00 → 2026-11-19T02:21:51+00:00 · [run evidence](reports/runs/20261119T022150098025Z-ca98ee62.json)
- `20261119T022243319852Z-f77703cf` · S0-04 · **PASS** · 2026-11-19T02:22:43+00:00 → 2026-11-19T02:22:44+00:00 · [run evidence](reports/runs/20261119T022243319852Z-f77703cf.json)
<!-- richmond-run-history:end -->

## Civic pivot

- **Built** the `RVA: Aggressive Altruism` architecture and named The Albanico Association as the preservation faction. Added the UE5 C++20 `RVACivic` module, faction and fiscal state, Runtime Data Layer rules, and the three Chaos tool behaviors.
- **Verification** all 13 local tests passed, including the compiled C++20 policy checks. The plugin sources passed the placeholder scan. The full UnrealBuildTool build and PIE interaction checks require the UE5 editor on the target PC.
- **Terrain evidence** the recent source intake delivered the first pair's NOAA DEM and LAZ files. The class-2 comparison found LAZ elevations about 1.33 m below the DEM. Carry that discrepancy into the terrain review before placing LiDAR-derived assets.
- **Bottlenecks to profile** the compost launcher makes one visibility trace per candidate and the temporary tool effects spawn actors. Measure trace cost and actor churn in Unreal Insights. Keep faction-managed layer assets separate from terrain streaming.

### Next usage window prompt

> Build RVACivic on the target UE5 PC. In one World Partition PIE map, verify faction and enforcement Data Layer transitions, run the three tool interactions against authored graybox targets, and capture the build log and pass/fail evidence in DEV_STATE.md. Fix any UnrealBuildTool, UnrealHeaderTool or runtime issues this test exposes.
