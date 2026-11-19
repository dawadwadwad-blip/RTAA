# Church Hill driving playtest

Mara takes a forged striping job, hauls a cornice uphill, then chooses how to handle the stakes at two occupied homes. This test puts the three shortened jobs on one practice road. Its order is Night Shift (`M01`), Hill Climb (`M13`), then Survey Stakes (`M04`). The campaign order remains in the [mission outline](RVA_Mission_Beats.md).

## Make the level

1. Build and enable `RVACivic` in the target UE5 C++ project. Enable the built-in Python Editor Script Plugin and reopen the editor if prompted. Use an existing vehicle GameMode with a working default vehicle pawn. Use the vehicle template if the project needs a test vehicle.
2. In the editor Output Log command box, use **Cmd** mode. Run this command with the real checkout path and the GameMode's generated Blueprint class path. The class path ends in `_C`.

   ```text
   py "C:/RTAA/tools/build_church_hill_playtest.py" "/Game/VehicleTemplate/Blueprints/BP_VehicleGameMode.BP_VehicleGameMode_C"
   ```

3. The script opens and saves `/Game/RVA/Tests/ChurchHillSlice`. To create another test level, append `--map /Game/RVA/Tests/ChurchHillSliceB`. The script rejects existing packages. If actor placement fails after creating a package, review the Output Log and use a fresh test package for a retry.
4. Start single-player **Play In Editor** from the vehicle Player Start. The director tags the supplied GameMode's default pawn as the work truck. Use the vehicle's normal controls. The test actors use **E** for interaction and Night Shift uses **R** for its checkpoint.

The editor-built level has a lower striping road, a 5.7% gentle route, a 16.5% direct route and an upper delivery pad. The fixture uses built-in meshes and a separate level package. Author placement on the streamed Richmond terrain after the [pilot data checks](Pilot_Data_Contract.md) and the vehicle test. [Unreal Editor Python](https://dev.epicgames.com/documentation/unreal-engine/scripting-the-unreal-editor-using-python)

## Check the full drive

| Job | What to do | What to verify |
| --- | --- | --- |
| Night Shift | Brief at the yard, stripe both segments, use an exit and return for debrief. Retry after the first stripe with **R**. | Retry preserves the earned stripe. Only the debrief files `M01`. Hill Climb activates after the filing. |
| Hill Climb | Load the cornice, pick a route at its signed gate, climb and stop at the pull-off to re-secure the load. Deliver at the upper pad. | The load slips sooner with sustained speed on the steeper grade. The delivery files `M13` as Kind for the gentle route or Hard for the direct route. |
| Survey Stakes | Take the Review Board or Mortar Circle brief and visit both stoop zones. On a separate Hard attempt, move one stake and let the timer expire before trying again. | Kind leaves loading access open. A completed Hard attempt raises a barrier. Expiry resets the stake and files no result. Finishing both sites files `M04` and ends the slice. |

Filter the Output Log for `LogChurchHillSlice`. A full drive should have three filings with `Completed` counts 1, 2 and 3. Revisit the objective zones and press **E** again to check for extra filings. Start a fresh session for the alternate Hill Climb and Survey Stakes methods. The fixture's values produce 4 helped, 0 harmed, 0 Collateral and 0 Church Hill Strain with the Kind Survey result. The Hard Survey result produces 4 helped, 1 harmed, 1 Collateral and 1 Strain. These values are illustrative.

This test tracks outcomes for a single play session. Standalone Night Shift disk-checkpoint verification uses its own setup. For the native Night Shift automation test and individual retry checks, see [Church Hill vertical slice checks](RVA_Church_Hill_Slice.md).
