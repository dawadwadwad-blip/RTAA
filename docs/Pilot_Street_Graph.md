# East-side pilot street graph

The export converts the locked Richmond OpenStreetMap capture into a two-dimensional street and footway graph. It includes the pilot core and a 100 m buffer, retaining complete node pairs that touch the clip. The graph records the original node and way IDs, versions, horizontal distance in meters and Unreal X/Y in centimeters. Way geometry, turn rules and the source hash travel together. [© OpenStreetMap contributors, ODbL 1.0](https://www.openstreetmap.org/copyright)

## Build the graph

Install the existing `requirements-gis.txt` and place the exact [locked capture](../pilot/controls.json) at `inputs/osm_pilot.osm`. The capture hash must match before export. From the repository root, run:

```shell
python tools/run_task.py S1-03 -- python tools/pilot_street_graph.py
```

The graph is written to `outputs/pilot_street_graph.json`. The small checked-in [report](../reports/pilot_street_graph.json) includes the output hash, counts and source witnesses so the team can reproduce the exact result. Initial witnesses cover the North 17th Street one-way section, the Richmond Slave Trail footbridge and the Richmond–Petersburg Turnpike passing above East Main Street.

## Graph rules

| Record | Consumer behavior |
| --- | --- |
| `nodes` | Use the source node ID as the junction key. Shared endpoints connect adjacent roads and bridge approaches. A geometric crossing without a shared endpoint creates no turn. |
| `edges` | Read `a` to `b` as the source order. Create arcs only for the modes on `forward` and `backward` respectively. Preserve the undirected edge ID so a later closure can affect both directions. |
| `blocked_car_turns` | At the stated `via_node`, disallow transfer from the named incoming edge to the outgoing edge. Simple via-node restrictions produce directed turn checks. |
| `unresolved_turn_restrictions` | Review turn relations that use a via way or whose required directed arcs are missing from the clip before using the export for general traffic routing. |

The first pass models public access and mapped ways. Node barriers, lane assignment, turn schedules, sidewalk offsets and bridge-deck heights require separate authoring or source checks. The layer number describes relative separation. Actual deck Z must come from measured deck points and an approved terrain reference. [OSM junctions](https://wiki.openstreetmap.org/wiki/Junctions) · [OSM one-way rules](https://wiki.openstreetmap.org/wiki/Key:oneway)
