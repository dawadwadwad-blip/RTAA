# RVA: Aggressive Altruism

## Project contract

RVA is an original Richmond open-world civic sandbox. Competing groups agree on a few goals and fight over who pays, who benefits, who gets displaced and who runs the meeting. Play takes place at street level and on a physical city map. Decisions change traffic, storefronts, permits and the people who show up in the next neighborhood. Crude humor, profanity, fictional talk radio and cartoon physics make these consequences visible. Factions and characters belong to the game world.

The technical plan remains in [Richmond Open World Architecture](docs/Richmond_Open_World_Architecture.md). Spend **$0 beyond the existing subscription and hardware**. Use free Blender, QGIS, PDAL, Python, Git and civic code with built-in Unreal Engine 5 systems. Keep 2025 Richmond LiDAR and native DEM, OSM and Virginia Road Centerlines, measured building heights with source confidence, procedural Blender façades, World Partition, PCG, Nanite, Lumen, Substrate, Chaos and MassEntity. Existing GIS locks and the civic runtime have separate inputs and verification. The current project area still begins with Church Hill and Shockoe Bottom, then grows through The Fan, Monument Avenue and Belle Isle. Scott's Addition, Manchester, Oregon Hill and the county edges enter with connectivity and asset coverage.

## Campaign and local stories

The [campaign plan](docs/RVA_Campaign.md) follows Mara Bell, a temporary city maintenance worker who shares her late mother's Church Hill rowhouse with her brother Cal. A forged overnight job puts her truck at a scaffold fire. The threatened parcel and the truck's movement log tie her to the ghost Connector project and to Winslow Tate's housing fund. The [mission outline](docs/RVA_Mission_Beats.md) sets out 30 main jobs, four acts and four conditional outcomes.

The Standing Committee uses giant yard skeletons as an early clue. The hand-truck favor remains an optional street encounter. The campaign reveals a long-unadjourned council committee whose records and procedural leverage matter in Acts III and IV.

## Factions and policy

The playable roster is The Albanico Association, The Pod, Transit & Cargo-Bike Militia, Asphalt & Truck-Nutz Coalition, and Small Independents. The [campaign territory map](docs/RVA_Campaign.md#playable-factions-and-territories) lists their bases and opposing wings. Outside Capital acts through Tate's patronage, Compliance runs permits and enforcement, and the city–county boundary changes who responds. The Standing Committee runs across neighborhoods and factions.

The campaign's Work Orders, Method Dial, Hi-Vis rules, Net Good ledger and district Strain swaps extend the civic runtime. The first slice prototypes the work-zone boundary and authored lane-state changes. Longer-lived visual changes can continue using World Partition Runtime Data Layers.

### Current civic prototype

`UCivicFactionSubsystem` owns one active game or PIE world. The existing prototype keeps its broader reputation keys, fiscal calculations, permit eligibility, heat and Layer overrides. These keys support the tested prototypes. Campaign wing contacts and jurisdiction are future integrations. Enforcement at heat 60 currently drives a prototype override. The campaign ladder needs the ordered response behaviors in the mission outline.

### In-game actions

| Tool | Graybox behavior |
|---|---|
| Industrial Line-Striper | Paint a car or mark the road. Marked road segments use an overlap trigger to lift a sufficiently fast simulated vehicle once per marking. |
| Pneumatic Pothole Patcher | Fill a tagged, authored pothole actor. On a simulated towable, a temporary Chaos world constraint stands in for sticky asphalt. |
| High-Velocity Leaf-Blower and Compost Launcher | The launcher applies a short-range falloff impulse to physics bodies and walking characters. Every affected actor gets a single impulse and solid obstructions can block the burst. The held blower variant belongs to a later tools pass. |

Use by-player swept routes and short-lived physics props, with bounded use range and placement count. Create all tool visuals and dialogue in-house or from rights-cleared free assets. Use façade signage slots, event-tagged street barks and the entirely fictional `WRVA-UNHINGED` radio parody. Provide independent controls for strong language and voice volume as the audio systems are added.

### Council and street-audit loops

- **Public Comment.** Reuse the floor map for witnesses, exhibits and points of order. Physical props and the hearing clock create pressure. The hearing puts a workable alternative on record before the procedural freeze in Act IV.
- **The Listening Tour.** Scout a moving inspector's route and mark or repair an approach before the visit. Reuse the same work zones and street state as regular jobs.
- **Implementation status.** The council timer, convoy checks, campaign AI, authored faction contacts, arrival routes, audio and saving need map or systems work. Existing tools supply callable state and physical interactions.

## Engine integration

Copy [Plugins/RVACivic](Plugins/RVACivic) into the UE5 C++ project and enable it through the project plugin list. The runtime module uses C++20 and targets the UE5.5+ Runtime Data Layer API. The subsystem initializes itself in Game and PIE worlds. Add `UCivicToolComponent` to the player pawn and call `UseTool` from each tool action using the world-space camera direction. A Blueprint may bind the tool-result and city-state delegates for UI, radio and VFX. [Runtime Data Layer API](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/WorldPartition/DataLayer/UDataLayerManager?application_version=5.5)

- On BeginPlay, pass authored Runtime Data Layer assets to `ConfigureLayerOverrides`. Set both active and inactive states. A failed return means at least one binding could not apply. Call `RefreshLayerOverrides` after the manager and assets are available. Keep managed asset layers unparented or explicitly account for their parent's effective state.
- Terrain and placeholder props should block the configured aim trace. Enable overlap events on the simulated Chaos vehicle mesh, with object type Vehicle or the actor tag `CivicTowable`. Tool impacts apply to the simulated body on the hit component. The owner ignores its own traps.
- Author a detachable pothole surface actor tagged `CivicPothole` over an intact traffic surface. The repair hides that actor and disables its collision. Use `CivicPermittedSite` for authored legal sites.
- The current module runs its changes on the local authority. A networked build needs replication and request validation. Game-world state ends on world travel until save and restore are added.

### Verification gate

Compile the plugin with UnrealBuildTool and UnrealHeaderTool in the target editor version. In PIE, cross the reputation and enforcement thresholds on two Runtime Data Layers. Verify a slow and a fast Chaos vehicle, an attached paint marker, a repaired pothole, a towable that releases after five seconds, a compost burst with an occluding wall and effect cleanup on pawn destruction. The standalone tests compile the policy calculations and check their numeric gates. The editor build and physics behavior require that PIE run.
