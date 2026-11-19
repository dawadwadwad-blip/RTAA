# Night Shift graybox

Night Shift is the first mission from the [mission beats](RVA_Mission_Beats.md#night-shift-first-build). This pass provides one placeable `NightShiftWorkOrder` actor with a yard, two road segments, a site closure, two exits and checkpoint recovery. The default placement makes a small flat driving rig. It can also be placed on a Church Hill map once the approach, paint height and checkpoint anchors are authored for the actual grade.

## Setup in Unreal

1. Copy the repository's `Plugins/RVACivic` into an Unreal C++ project with a drivable pawn, or use the project's existing vehicle setup. Enable and build the plugin. Add the actor tag `NightShiftTruck` to the vehicle pawn used for the mission.
2. Place one `NightShiftWorkOrder` actor. For the flat rig, leave `Show Test Surface` enabled and put the vehicle start in the yard near the actor origin, facing the positive X direction. Use its labeled component positions as references. Disable the test surface on an existing level and adjust the zone boxes, paint meshes, barrier and checkpoints to the roadway.
3. In a single-player PIE session, use **E** for objectives and **R** to return to the latest completed checkpoint. The actor enables these test keys by default. Disable `Bind Test Keys` when connecting your own input. A project with its own input can call `PerformObjective` and `RetryCheckpoint` with the local pawn. The actor checks the locally controlled pawn and the vehicle tag before clearing a driving objective. [Unreal input bindings](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/Components/UInputComponent/BindKey/2?application_version=5.5)
4. In a streamed map, keep the test actor loaded for the width of the route. The optional `StandingCommitteeFavor` can sit on the same block with its own pickup and return zones.

## Playthrough

| Beat | Do this | Look for this |
| --- | --- | --- |
| Yard briefing | Press **E** in the yard to read the order. Possess the tagged truck and press **E** in the yard. A player who starts in the truck can acknowledge both objectives from there. | The work-zone sign changes to the striping objective. |
| Work zone | Drive into the authorized area. At either end of a yellow segment, press **E** and drive to the far end. Repeat for the other segment. | Each completed strip turns green. Crossing out the side of an armed strip cancels the partial pass. Repeating a green segment makes no change. |
| Closure | After the second strip, use the marked detour or the alternate exit. | The main exit gets a physical barrier, an orange wash marks the report of an offscreen scaffold fire, and the exit indicators appear. |
| Debrief | Drive back to the yard. Stop and press **E**. | The sign reports that the dispatch stub is filed and identifies which exit the log recorded. The narrative evidence also returns the recorded truck position and session time. |
| Recovery | Press **R** while driving after one stripe, after the closure, and after debrief. | The actor restores its latest completed checkpoint at the relevant anchor. The saved stripe, exit and evidence remain in place. There is no second closure or debrief event. |

The defaults retain checkpoints in the session. Enable `Persist Checkpoint` for a second test across PIE restarts, using a dedicated `Checkpoint Id` for the actor. Persistence uses a versioned Unreal save slot keyed by level and ID. Create a new test ID to start a fresh run. [Unreal SaveGame](https://dev.epicgames.com/documentation/unreal-engine/saving-and-loading-your-game-in-unreal-engine)

## Gameplay integration

- `OnProgressChanged` can refresh UI. It also broadcasts after a retry and can carry the same phase when the first strip completes.
- Use `OnClosure` and `OnDebriefCompleted` for one-time events. Neither is emitted by checkpoint restoration. `GetEvidence` exposes stable record IDs for Cold Patch.
- The graybox Line-Striper credits an authored, end-to-end roadway pass using the work-order input. The general civic tools continue to operate through their existing inputs and effects. The closure light and signs stand in for the authored scene, radio and VFX.
- The flat rig makes the route and checkpoint checks repeatable. Vehicle feel, street placement, timing and presentation still need the target editor and a Church Hill block. Recovery should be tested with the actual vehicle pawn and its collision setup.

## Acceptance in the target editor

Run the normal exit once and the alternate exit once, starting one run with segment B. Try arming a segment from outside its work area, stepping out halfway, driving back over a completed line, reaching the yard before taking a detour, and pressing **E** while moving through the finished yard. Retry from one completed line and after debrief. Check that the two evidence IDs and recorded exit data remain identical after a retry. Run a final fresh PIE session with disk persistence enabled and confirm that the scene restores without replaying closure VFX or completion callbacks.
