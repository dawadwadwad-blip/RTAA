# RVA: Aggressive Altruism — v2 design direction

The creator's [verbatim Nov 18, 2026 v2 plan](docs/RVA_Project_Plan_and_Design_Handoff_v2.md) is the **current design baseline**. See also the [implementation migration handoff](docs/RVA_V2_MIGRATION.md). Read [Story & World](docs/RVA_V2_STORY.md), [Gameplay & Production](docs/RVA_V2_GAMEPLAY.md), and the machine-readable [30-mission catalog](design/v2_campaign.json). The historical Unreal civic prototype is not yet a playable implementation of the new campaign. The first target is a Church Hill → Shockoe Bottom → downtown vertical slice proving heavy-vehicle grades, Work Orders, Method Dial, Hi-Vis, route-state Line-Striper, Compliance and Net Good. Keep the GIS foundation and local UE5 validation gates.

---

# Richmond Open World

RVA: Aggressive Altruism is an offline Unreal civic sandbox set in Richmond. The [architecture manifest](ARCHITECTURE_MANIFEST.md) defines its factions, civic tools and street gameplay. The [architecture](docs/Richmond_Open_World_Architecture.md) tracks scope, GIS sources, façade rules and the five-sprint plan. [DEV_STATE.md](DEV_STATE.md) records the work completed and links to the checks from each run.

## Run the first-drive audit

Use Python 3.11+ from the project root. Place the existing `Richmond_Unreal_First_Drive.zip` and optional `Richmond_Driving_Test.html` in `inputs/`. Keep the original download notices with both files.

```shell
python tools/run_task.py S0-01 -- python -m unittest discover -s tests -v
python tools/run_task.py S0-01 -- python tools/baseline_inventory.py --bundle inputs/Richmond_Unreal_First_Drive.zip --html inputs/Richmond_Driving_Test.html
```

`reports/baseline.json` gives the exact bundle hash, member list, route length and data counts. Repeating the audit gives the same inventory for the same input bytes. Attempts and their logs accumulate in `reports/runs/` and the runner refreshes `DEV_STATE.md` automatically.

The [pilot data contract](docs/Pilot_Data_Contract.md) records east-side coverage, source licenses, projection grids and three street controls. **S1-01** begins with two adjacent terrain tiles. **S0-03** is the separate Unreal smoke test on the target PC.
