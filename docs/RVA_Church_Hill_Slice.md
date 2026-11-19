# Church Hill vertical slice checks

The slice tests three jobs from the [v2 mission outline](RVA_Mission_Beats.md). The shortened missions can share one test level. Place their start and interaction zones apart so a single input reaches only the intended job. Hill Climb and Survey Stakes need a walkable or drivable surface supplied by the level.

## Night Shift verification

Build `RVACivic` in the target Unreal project and run `RVA.Graybox.NightShiftNativeFlow` in the editor's Automation panel. The test spawns the native work order and a possessed test pawn, then moves the pawn between the actor's actual components. It exercises the briefing, the authorized striping zone, an invalid midfield start, one checkpoint retry, the physical closure, the alternate exit and the yard debrief. It compares the evidence before and after a completed retry. [Unreal C++ automation tests](https://dev.epicgames.com/documentation/unreal-engine/write-cplusplus-tests-in-unreal-engine)

For driving acceptance, use the actual vehicle and run the [Night Shift playthrough](RVA_Night_Shift_Graybox.md). Check both exits and the disk save. The portable stripe tests verify that arming works from either end, crossing a side or losing authorization cancels the pass, and a completed pass cannot be credited again.

## Hill Climb · M13 slice

Place `HillClimbGraybox`. A tagged city truck can load the visible cornice at the pickup. Move the pickup, Gentle Hill and Direct Hill markers to the start of two usable routes. Put Final Grade Warning on their common approach to Strap Pull Off and Cornice Delivery. Position the cargo using `Cargo Offset Cm` for the actual truck bed. The local key is **E**.

1. Stop inside pickup and load. Choose the longer gentle route or a shorter direct grade at the corresponding gate.
2. Drive on the actual slope. The visible load creeps backward as sustained speed and pitch increase. Use the same speed on both routes to test the difference. Pass the common final-grade warning to trigger the scripted strap check even on a gentle run.
3. Stop at the pull-off and press **E** to re-secure. Pressing while moving should fail safely. At the final site, stop and press **E** to unload. Confirm the cornice stays at the delivery point.
4. Destroy the carrying vehicle before delivery in a separate test. Return with a replacement tagged vehicle and confirm that the job can begin again.

Cargo uses an attached prop and a pitch-and-speed gameplay model for the first slice. Brake fade and physical load forces require vehicle tuning in a separate pass. `OnDelivered` reports the chosen route once.

## Survey Stakes · M04 slice

Place `SurveyStakesGraybox`. Set the Review Board and Mortar Circle briefs apart, with two walkable stoop zones nearby. Position the loading barrier across a loading approach that has a clear path around it. Interaction uses **E** while on foot or nearly stopped. Neither method requires the truck.

| Method | Player action | Consequence after both sites |
| --- | --- | --- |
| **Kind** | Take the Review Board brief and mark both homes as occupied. | The original stakes remain in place, occupied-home signs appear, and the loading approach stays open. |
| **Hard** | Take the Mortar Circle brief and move both stakes before its timer expires. | The stakes stay moved and the signed loading barrier blocks the approach. |

Let one Hard run expire after the first site. Confirm the moved stake returns, the barrier stays open, and another briefing starts a clean attempt. Then finish the Hard route in reverse site order. Revisit both zones and confirm `OnResolved` emits its result once. AI delivery repathing is a later integration with the actual road network.

## Shared campaign integration

The placeable jobs own their local interaction and presentation. When the shared Work Order subsystem from [PR #5](https://github.com/dawadwadwad-blip/RTAA/pull/5) is combined with the slice, map `OnDelivered` to `M13` and `OnResolved` to `M04`. Record the authored outcome through the shared completion flag. The grayboxes are session-scoped. Durable rewards need the shared campaign ledger and save flow.

## Evidence

The standalone C++20 suite covers both Hill Climb routes, slip and recovery, the pull-off requirement, timed Survey reset, the untimed Kind route and one-time completion. The native Unreal test and the full drive still need the target engine. Confirm tile alignment separately before placing the grayboxes on the streamed Church Hill map.
