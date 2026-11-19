# RVA: Aggressive Altruism

## Project contract

RVA is an original Richmond open-world civic sandbox. Competing groups agree on a few goals and fight over who pays, who benefits, who gets displaced and who runs the meeting. Play takes place at street level and on a physical city map. Decisions change traffic, storefronts, permits and the people who show up in the next neighborhood. Crude humor, profanity, fictional talk radio and cartoon physics make these consequences visible. Factions and characters belong to the game world.

The technical plan remains in [Richmond Open World Architecture](docs/Richmond_Open_World_Architecture.md). Spend **$0 beyond the existing subscription and hardware**. Use free Blender, QGIS, PDAL, Python, Git and civic code with built-in Unreal Engine 5 systems. Keep 2025 Richmond LiDAR and native DEM, OSM and Virginia Road Centerlines, measured building heights with source confidence, procedural Blender façades, World Partition, PCG, Nanite, Lumen, Substrate, Chaos and MassEntity. Existing GIS locks and the civic runtime have separate inputs and verification. The current project area still begins with Church Hill and Shockoe Bottom, then grows through The Fan, Monument Avenue and Belle Isle. Scott's Addition, Manchester, Oregon Hill and the county edges enter with connectivity and asset coverage.

## Factions and policy

| Faction | Street identity | Practical trade-off |
|---|---|---|
| **The Albanico Association** · Church Hill and The Fan | Costume aristocrats in vintage sedans heckle vinyl siding and lob theatrical masonry at renovations. | Historic fabric survives while compliance costs and rents can squeeze working-class tenants. |
| **The YIMBY Cult of “The Pod”** · Scott’s Addition and Manchester | Container-apartment developers treat cold brew, demolition and luxury rent as the same solution. | More units and construction jobs can arrive alongside demolition and displacement. |
| **Radical Transit & Cargo-Bike Militia** | Lycra organizers have a cargo bike, a street audit clipboard and a cartoon physics prop for every occasion. | Safer crossings, cleaner air and bus reliability compete for loading space and travel lanes. |
| **Asphalt & Truck-Nutz Coalition** | SUV devotees and highway contractors promise that I‑95 needs one more lane. | Brisk car trips and freight access compete with wider crossings, noise and induced traffic. |
| **Small Local Independents** | Shopkeepers pool favors and protect affordable storefronts. | A stronger local identity needs lower fixed costs and enough foot traffic to remain viable. |
| **Outside Corporate Capital** | Recruiters offer a ribbon-cutting and a reflective office façade for every subsidy. | Offices, employment and tax receipts can also raise costs and standardize the retail mix. |
| **Urban Core Focus** | Density advocates pick existing street grids and infrastructure. | Reuse saves new infrastructure per household while adding pressure to core blocks. |
| **County Annexation** | Map lobbyists keep drawing borders farther into Henrico and Chesterfield. | Regional reach can spread tax capacity while adding roads, services and governance costs. |
| **Municipal Red-Tape & Blue-Ribbon Commission** | Consultants cart mobile podiums, tax thermometers and new logos from study to study. | Higher taxes open official permit routes while the commission takes 95% for overhead by default. Unpermitted projects build enforcement heat. |

`UCivicFactionSubsystem` owns one active game or PIE world. Reputation spans −100 to +100. Four opposing pairs react by half of the actual change after clamping. Permit eligibility uses tax rate, heat and Commission reputation. A tax hike above the baseline raises resident and business pressure. The fiscal calculation conserves integer cents, with published administration and public-works amounts for each supplied tax base. Civic actions and scripted ordinances change this state through the subsystem. Enforcement at heat 60 can activate an authored Runtime Data Layer of municipal sedans, wheel boots and barricades. Permit and favor rules can activate alternate storefronts, campaign props or preserved façades. One rule owns one dedicated asset. Civil infrastructure and the base tile layout live in other layers.

### In-game actions

| Tool | Graybox behavior |
|---|---|
| Industrial Line-Striper | Paint a car or mark the road. Marked road segments use an overlap trigger to lift a sufficiently fast simulated vehicle once per marking. |
| Pneumatic Pothole Patcher | Fill a tagged, authored pothole actor. On a simulated towable, a temporary Chaos world constraint stands in for sticky asphalt. |
| High-Velocity Leaf-Blower and Compost Launcher | The launcher applies a short-range falloff impulse to physics bodies and walking characters. Every affected actor gets a single impulse and solid obstructions can block the burst. The held blower variant belongs to a later tools pass. |

Use by-player swept routes and short-lived physics props, with bounded use range and placement count. Create all tool visuals and dialogue in-house or from rights-cleared free assets. Use façade signage slots, event-tagged street barks and the entirely fictional `WRVA-UNHINGED` radio parody. Provide independent controls for strong language and voice volume as the audio systems are added.

### Council and street-audit loops

- **Council hearing.** A raised 3D map uses the same projected layout as the street world. Move proposed ordinances across the floor while bureaucrats steer them into a “180-Day Subcommittee Vortex.” Players get the slippery City Clerk to stamp the ordinance before the gavel timer. Cardboard boards, scale models and thermoses are bounce-safe game props. Approved ordinances call explicit fiscal and reputation changes.
- **Live street audit.** Get ahead of a moving council convoy on Church Hill grades, Oregon Hill slopes and James River approaches. Place bollards, parklets or preservation scaffolding inside authored zones. The convoy observes street state at checkpoints and resolves policy changes, civic reputation and per-site scores.
- **Implementation boundary.** The council timer, inspection convoy, boots, destructible red-tape barriers, authored factions, audio, saving and Mass traffic behavior need map or systems work. The first implementation provides the callable state and physical tool behavior for that work.

## Engine integration

Copy [Plugins/RVACivic](Plugins/RVACivic) into the UE5 C++ project and enable it through the project plugin list. The runtime module uses C++20 and targets the UE5.5+ Runtime Data Layer API. The subsystem initializes itself in Game and PIE worlds. Add `UCivicToolComponent` to the player pawn and call `UseTool` from each tool action using the world-space camera direction. A Blueprint may bind the tool-result and city-state delegates for UI, radio and VFX. [Runtime Data Layer API](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/WorldPartition/DataLayer/UDataLayerManager?application_version=5.5)

- On BeginPlay, pass authored Runtime Data Layer assets to `ConfigureLayerOverrides`. Set both active and inactive states. A failed return means at least one binding could not apply. Call `RefreshLayerOverrides` after the manager and assets are available. Keep managed asset layers unparented or explicitly account for their parent's effective state.
- Terrain and placeholder props should block the configured aim trace. Enable overlap events on the simulated Chaos vehicle mesh, with object type Vehicle or the actor tag `CivicTowable`. Tool impacts apply to the simulated body on the hit component. The owner ignores its own traps.
- Author a detachable pothole surface actor tagged `CivicPothole` over an intact traffic surface. The repair hides that actor and disables its collision. Use `CivicPermittedSite` for authored legal sites.
- The current module runs its changes on the local authority. A networked build needs replication and request validation. Game-world state ends on world travel until save and restore are added.

### Verification gate

Compile the plugin with UnrealBuildTool and UnrealHeaderTool in the target editor version. In PIE, cross the reputation and enforcement thresholds on two Runtime Data Layers. Verify a slow and a fast Chaos vehicle, an attached paint marker, a repaired pothole, a towable that releases after five seconds, a compost burst with an occluding wall and effect cleanup on pawn destruction. The standalone tests compile the policy calculations and check their numeric gates. The editor build and physics behavior require that PIE run.
