# Richmond Open World

RVA: Aggressive Altruism is an offline Unreal civic sandbox set in Richmond. The [architecture manifest](ARCHITECTURE_MANIFEST.md) defines its civic tools and street gameplay. The [campaign plan](docs/RVA_Campaign.md) and [mission beats](docs/RVA_Mission_Beats.md) cover the story and first playable slice. The [architecture](docs/Richmond_Open_World_Architecture.md) tracks scope, GIS sources, façade rules and the five-sprint plan. [DEV_STATE.md](DEV_STATE.md) records the work completed and links to the checks from each run.

The [v2 design handoff](docs/RVA_Project_Plan_and_Design_Handoff_v2.md) records the campaign's source design. The [Church Hill driving playtest](docs/RVA_Church_Hill_Playtest.md) shows how to generate a test level in Unreal and drive three connected jobs through the shared Work Order ledger.

## Run the first-drive audit

Use Python 3.11+ from the project root. Place the existing `Richmond_Unreal_First_Drive.zip` and optional `Richmond_Driving_Test.html` in `inputs/`. Keep the original download notices with both files.

```shell
python tools/run_task.py S0-01 -- python -m unittest discover -s tests -v
python tools/run_task.py S0-01 -- python tools/baseline_inventory.py --bundle inputs/Richmond_Unreal_First_Drive.zip --html inputs/Richmond_Driving_Test.html
```

`reports/baseline.json` gives the exact bundle hash, member list, route length and data counts. Repeating the audit gives the same inventory for the same input bytes. Attempts and their logs accumulate in `reports/runs/` and the runner refreshes `DEV_STATE.md` automatically.

The [pilot data contract](docs/Pilot_Data_Contract.md) records east-side coverage, source licenses, projection grids and three street controls. **S1-01** begins with two adjacent terrain tiles. **S0-03** is the separate Unreal smoke test on the target PC.
