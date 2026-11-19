# RVA: Aggressive Altruism campaign

**Mara Bell** works on a temporary city street-maintenance contract and rents above a corner store in Shockoe Bottom. She knows the truck, the detours and the delivery schedule. In the opening mission, her approved bike lane cuts through the store's loading zone before a ribbon-cutting. Following the plan, routing around the store or moving the demonstration changes who calls Mara afterward. Lenora Pike makes her field lead on the fictional Richmond Connector, a package of safer crossings, loading zones, bus stops and public spaces. At the midpoint, a financing package puts Mara's building in the path of a new transit plaza. Pike offers her permanent employment in exchange for backing the deal.

Target **30 main missions and 9–12 story hours**. Give each mission a physical objective and a visible street consequence. Reuse towing, hauling, marking and placement across the four acts. Track faction favors, enforcement and changes to specific blocks.

| Act | Missions | Story beat |
|---|---:|---|
| Paint Before the Parade | 6 | Opening stripe job, an uphill delivery around the Albanico Association and a convoy audit. Players can run into the first skeleton favor while out on jobs. |
| Everybody Wants a Stop | 8 | The Connector reaches The Fan, Monument Avenue and downtown. Preserve older storefronts, open housing deals and work around deliveries. The plaza plan reaches Mara's building. |
| Public Comment | 9 | Mara rebuilds a coalition. The Standing Committee brings an alternate design and the people who can explain its costs. The floor-map hearing decides which plan can move forward. |
| Opening Day | 7 | Mara completes a route under a public deadline. The finale drives through the blocks the player changed. Free roam preserves key storefront, crossing and neighborhood outcomes. |

## The Standing Committee

The residents who put giant plastic skeletons in their front yards belong to the Standing Committee, a secret decoration swap and mutual-aid network. The members span public factions. They trade tools, find trucks and keep copies of public planning notices and site drawings. Bare means a member lives there. A safety vest means the block needs help. A folding chair at the feet means a meeting that night. Most seasonal outfits simply reflect whoever decorated the skeleton. All member households are authored for the story.

Give the Committee three optional encounters and one required story mission. The first, **Under the Safety Vest**, is a hand-truck favor. Mara helps an early contact with a pickup and learns to look for the vest. The later optional encounters can make a truck and a courtyard route available to her. **Twenty Feet of Public Comment** is the required Act 3 mission. Mara delivers witnesses, drawings and a giant skeleton to the rescheduled hearing. Earlier favors change who shows up. The alternate Connector alignment can save her building and fix a crossing, at the cost of a stretch of loading curb used by nearby shops.

## First favor graybox

Enable the local `RVACivic` runtime plugin and place one `StandingCommitteeFavor` actor into a walkable test block. The actor owns both sites and preview skeletons. Place the Loan Site and Return Site on walkable ground, then adjust the child skeleton offsets and rotations for the front yards. The default sites are 28 m apart. Move the overlap zones onto the actual sidewalk and aim the world-space prompts toward the approach. Both the player capsule and each trigger need overlap events. In a World Partition test, keep this graybox actor loaded for the route. [Unreal actor attachment](https://dev.epicgames.com/documentation/en-us/unreal-engine/BlueprintAPI/Transformation/AttachActorToComponent) · [Instanced static meshes](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/Components/UInstancedStaticMeshComponent/AddInstance?application_version=5.5)

1. Visit the safety-vest skeleton first. The return should remain inactive.
2. Walk up to the bare skeleton. The hand truck should attach to the character and the loan label should point you toward the vest.
3. Walk to the vest in the same character. The truck should park and the return label should confirm success. An assigned courtyard gate should open.
4. Reenter both sites after delivery. The completed favor should remain complete.
5. Restart PIE, borrow the cart and destroy the borrower. The cart should return to the loan site so the respawned character can finish.

Use `OnFavorChanged` for a HUD objective and `CourtyardGate` for the optional shortcut. The first favor keeps its state for that level session. The standalone transition tests are automated. The editor smoke test verifies overlap events, prop attachment and the gate in the actual level.
