# Richmond Open World

An offline Unreal driving sandbox set in five Richmond neighborhoods and landmarks. The [architecture](docs/Richmond_Open_World_Architecture.md) tracks scope, GIS sources, façade rules and the five-sprint plan. [DEV_STATE.md](DEV_STATE.md) records the work completed and links to the checks from each run.

## Run the first-drive audit

Use Python 3.11+ from the project root. Place the existing `Richmond_Unreal_First_Drive.zip` and optional `Richmond_Driving_Test.html` in `inputs/`. Keep the original download notices with both files.

```shell
python tools/run_task.py S0-01 -- python -m unittest discover -s tests -v
python tools/run_task.py S0-01 -- python tools/baseline_inventory.py --bundle inputs/Richmond_Unreal_First_Drive.zip --html inputs/Richmond_Driving_Test.html
```

`reports/baseline.json` gives the exact bundle hash, member list, route length and data counts. Repeating the audit gives the same inventory for the same input bytes. Attempts and their logs accumulate in `reports/runs/` and the runner refreshes `DEV_STATE.md` automatically.

The next card, **S0-02**, locks the east-side pilot coverage, coordinate transform, inputs and licenses. **S0-03** is the separate Unreal smoke test on the target PC.
