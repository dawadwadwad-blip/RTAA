# RVA: Aggressive Altruism — Project Plan & Design Handoff (v2)

Nov 18, 2026 · @Dank

This document consolidates the final recommendations from the creative direction review into one plan. It replaces the provisional premise, factions and mechanics in the original handoff wherever they differ. Companion document: the Creative Direction Review, which holds the critique and the reasoning behind each change.

## 1. Project overview

**Working title:** RVA: Aggressive Altruism

**Genre:** third-person open-world action/adventure with driving, light crime and dark comedy. Combat is slapstick (props and vehicles), not firearms.

**Setting:** a recognizable recreation of Richmond, Virginia, with real street layouts, elevation, bridges and neighborhood identities. Institutions, companies and bridges carry fictional names.

**One-line pitch:** a temp city worker with a truck and a hi-vis vest learns that every group fighting over Richmond's future is sincerely trying to help, and that each one has a number of people it is willing to hurt to do it.

### Scope and constraints

- **Campaign:** 30 main missions, about 9 to 12 hours, four acts, plus optional side activities and secrets.
- **Team:** solo or small team with substantial AI assistance.
- **Engine and data:** Unreal Engine 5 with World Partition, OpenStreetMap street geometry, public Richmond LiDAR/DEM elevation, public building footprints and heights, and procedural facades through Blender.
- **Budget:** $0 or extremely low cost.
- **Design rule:** a few deep, reusable systems beat many disconnected features. Judge every feature by fun per development hour.

### Status labels used in this plan

| Label | Meaning |
| --- | --- |
| **Established** | A decision already made in earlier planning: the engine and data stack, four acts, about 30 missions, Mara Bell, the Standing Committee name, Lenora Pike, and the Albanico (Church Hill and Fan) and Pod (Scott's Addition and Manchester) territories |
| **Recommended** | New or changed in this plan, adopted as the working default |
| **Open** | Needs creator approval; collected with working defaults in section 11 |

## 2. Story premise and theme

**Central theme (Established, sharpened):** everyone thinks they're saving Richmond, and everyone is willing to destroy part of it to do so. Every major character is sincerely helping someone, and each has a line they will cross.

### The Richmond Connector: a ghost project (Recommended)

The Connector is a fictional redevelopment and transportation project linking the eastern neighborhoods, downtown and the James River waterfront. It is perpetually "in planning." Its route moves depending on who is paying, and its real product is funded studies, contracts and land purchases. Everyone fights over something that barely exists. This keeps the original premise and gives the satire a sharper point.

### The two-wing rule (Recommended)

Every faction has a **Believer wing** (the sincere public face, limited in methods) and a **Means wing** (operators who have decided the cause is too important to lose). Mara can work for either, and the game tracks the consequences.

### Story in one paragraph

Mara Bell, a Richmond native back home, works a temp job on a city maintenance crew. A forged work order sends her crew to stripe a Church Hill street overnight; a scaffold fire breaks out on the same block, and her truck is photographed at the scene. That week a tax lien lands on the family rowhouse she co-owns with her brother Cal, and it sits on the Connector's preferred route. To keep the house she takes off-the-books work orders from factions that all need a city worker with a truck. At the midpoint she learns the Connector is a ghost project and that investor Winslow Tate engineered the lien, but also that his fund really does pay for housing elsewhere. Cal then sells his share. In the last act Mara uses everything she has learned against Tate at the groundbreaking, and decides what kind of altruist she is.

### Story devices that carry the plot

- **The Night Shift Log:** the telematics record on Mara's truck, the only proof of who was where that night. Everyone wants it.
- **The holdout parcel:** the rowhouse is the one lot blocking the preferred alignment.
- **The Net Good ledger:** counters for households helped and households harmed. Tate keeps one in the story; the player keeps one in the game.
- **The escalation ladder:** Act I is gray (paperwork and sign swaps), Act II misdemeanor (trespass, tampering), Act III felony (sabotage, blackmail), Act IV the player's own choice of methods.

## 3. Protagonist and supporting cast

### Mara Bell (Established name; background Recommended)

A Richmond native who left and came back, now a temporary municipal street-maintenance worker. She co-owns her late mother's Church Hill rowhouse with her brother Cal. Practical, good with heavy equipment, bad at asking for help.

- **Why her job works:** it gives a legal reason to be anywhere with a truck, cones and a work order. Nobody questions a person in a hi-vis vest.
- **Why factions hire her:** she is cheap, deniable and invisible, and she holds the parcel and the Night Shift Log.
- **Why she turns to crime:** a forged order puts her at a fire, a lien threatens the house, and the city job that protects her is at risk.
- **Her arc:** from "I'm just keeping the house" to deciding whether helping people justifies hurting others.

### Supporting cast

Placeholder names; change freely. Each character helps someone sincerely and has a line they will cross.

| Character | Role | Aim | The line they cross |
| --- | --- | --- | --- |
| **Cal Bell** | Mara's brother; emotional spine | Keep his small repair business and its employees afloat | Sells his share of the house (mission 22) |
| **Dell Okafor** | Crew foreman and mentor | Fund the pensions the city cut from her crew | Skims from contracts and flags the parcel (mission 16) |
| **Winslow Tate** | Primary antagonist; outside investor | Fund housing and a small-business rescue fund | Engineers liens to force sales; his ledger reads 412 households helped, 38 harmed |
| **Lenora Pike** | Chair of the Red-Tape Commission (Established) | Protect citizens from unpredictable rules | Bends and backdates rules for the "right" people; becomes an ally in Act IV |
| **Restoration Front leader** | Albanico, Church Hill | Preserve homes and the neighborhood's memory | Lets the Mortar Circle burn what "can't be saved otherwise" |
| **Pod Prime Builder** | The Pod, Scott's Addition | House the priced-out | Quietly lets the Closers squeeze holdouts |
| **Militia dispatcher** | Transit Militia | Fewer traffic deaths | Tolerates the Spoke Cell's gridlock hostage-taking |
| **Convoy captain** | Truck-Nutz | Keep working people mobile | Looks away from the Hitch's parking rackets |
| **Committee chair** | A retired city clerk | Keep the city's institutional memory | Uses "the Files" for gentle persuasion |

## 4. Factions and territories

Eight factions become **five playable groups plus two pressure systems**, with the Standing Committee as a separate story layer. Territory assignments for Albanico and the Pod are Established; the rest are Recommended.

| Faction | Believers and Means wing | Primary HQ | Secondary influence | Rivals | Gameplay enabled |
| --- | --- | --- | --- | --- | --- |
| **Albanico Association** | Review Board (Fan) and Mortar Circle (Church Hill) | Church Hill (radical wing) | The Fan (moderate wing) | The Pod; Compliance | Stoop surveillance, cobblestone and hill driving, sabotaging survey stakes and demolition permits |
| **The Pod** (with Outside Capital as hidden patron) | Prime Builders and the Closers | Scott's Addition | Manchester | Albanico; Truck-Nutz over parking and street width | Construction-site infiltration, crane and forklift physics, rezoning-sign swaps |
| **Transit & Cargo-Bike Militia** | Dispatch and the Spoke Cell | VCU/Broad Street corridor | Riverfront trail edge by Shockoe Bottom | Truck-Nutz; the Pod | Alley and trail escapes, lane repainting, courier runs, bridge and bus disruption |
| **Asphalt & Truck-Nutz Coalition** | Asphalt Samaritans and the Hitch | Southside (Hull Street and Midlothian Turnpike corridors) | Chippenham Parkway and the Chesterfield edge | Transit Militia (bridges); Compliance | Convoys, blockades, signal sabotage, street races |
| **Small Independents** | Most owners, and the Landlord Club | None (a client network) | Carytown; Shockoe Bottom market | Varies by owner | Delivery runs, rival-shop sabotage, ownership disputes, favors |

### Pressure systems and story layers

- **Outside Corporate Capital (merged into the Pod's patronage):** no headquarters. Tate works through intermediaries, a downtown office and a site trailer in Manchester.
- **City vs County (a recurring conflict, not a faction):** expressed as a gameplay rule. At the city boundary, enforcement drops one tier and a county sheriff takes over with different behavior.
- **Red-Tape Commission, rebranded as "Compliance":** based in the downtown municipal district, led by Lenora Pike. It is the player's enforcement ladder and a source of permit and hearing missions.
- **The Standing Committee:** distributed; see section 5.

### Headquarters decisions

- **Church Hill:** Albanico's radical wing only, so the hill stays visually coherent.
- **The Fan:** Albanico's moderates, plus the densest cluster of Standing Committee houses.
- **Scott's Addition:** the Pod's flagship.
- **Manchester:** owned by no one. It is the contested frontier where Pod construction, Capital's site trailer, Truck-Nutz traffic and Militia river access collide.
- **Jackson Ward:** not a faction headquarters. It is an earnest, authored sliver tied to the story of the interstate's impact on the neighborhood, researched with local historians. **Open**

Five groups need a physical base (Albanico in two places, the Pod, the Militia and Truck-Nutz). Independents, Capital, the city-county rivalry and the Committee work better without one.

## 5. The Standing Committee

**Name:** Established. **Role and answers to the open questions:** Recommended.

**What it is:** a city council standing committee from decades ago that was never formally adjourned. It still holds a few obscure powers: unrevoked ordinances, forgotten easements and a veto nobody remembers to challenge. Its members display the giant plastic skeletons because they are, in effect, "standing," and because they enjoy the pun.

**Role in the game:** a recurring underground organization with meaningful supporting influence. It is not the final villain.

- **What it wants:** to keep the city's institutional memory intact and the city running.
- **Is it powerful?** Narrowly. Its power is procedural, not financial, which makes it both real and absurd.
- **Who are the members:** an unlikely mixture of retired clerks, eccentric homeowners and a few well-placed old-timers, scattered across the Fan, Church Hill and other historic neighborhoods.
- **Its Means wing:** "the Files," a drawer of old secrets used for gentle persuasion.
- **How it affects the story:** it sells loopholes for favors, holds the original plat of Mara's parcel (mission 21), and supplies the procedure that can freeze the Connector (mission 25 and the Frozen ending).
- **Foreshadowing:** the skeletons appear in the first hour, their dress changes with civic calendar dates, and a collectible hunt teaches the player the pattern long before the reveal.

**Why not a central conspiracy:** a surprise villain reveal would not answer a question the story had already raised, and it would push Tate, Cal and Dell into the background. Any larger role for the Committee would need new foreshadowing and creator approval.

## 6. Geography and world structure

Caveat: bridge names, road configurations and neighborhood history come from background knowledge and need verification before they become level-design requirements.

### Handcrafted versus procedural

| Area | Treatment | Why |
| --- | --- | --- |
| **Church Hill** | Fully handcrafted | Home district, strongest identity and most missions |
| **Shockoe Bottom and the downtown strip** | Handcrafted spine | Connects Church Hill to the rest of the map and carries rail and bridge set pieces |
| **Scott's Addition** | Partly handcrafted: one or two hero blocks | The Pod's flagship and construction set pieces |
| **The Fan** | Partly handcrafted: key blocks and the Committee basement | Dense and procedural-friendly, with a few hero streets |
| **Jackson Ward** | A small authored sliver | One earnest mission with a bespoke data layer |
| **Manchester, Carytown, VCU, Southside** | Procedural, with two or three landmarks each | OSM-driven geometry and generated facades, plus memorable authored spots |
| **Henrico and Chesterfield edges** | Procedural, minimal | They exist for the city-line rule, not for content |

### Map access

The whole map exists physically, but is gated **diegetically** by bridge and permit closures. Act I is north of the river, Act II opens the bridge to Southside, and Act III opens everything. This avoids invisible walls, and the Line-Striper's closures double as progression.

### Territorial conflicts built on geography

- **River bridges:** few crossings, each of which can be closed. Truck-Nutz, the Militia and the Pod all need them, and a closure reroutes every vehicle.
- **Rail lines:** freight crossings in Shockoe Bottom and Manchester block streets for minutes. Independents need deliveries, the Pod needs concrete trucks, and the Militia wants a car-free crossing.
- **Interstates:** highways divide Church Hill, Shockoe and downtown. Interchanges host chases and lane-repainting set pieces.
- **Neighborhood edges:** Church Hill to Shockoe is a drop of several steep blocks. The Fan and VCU edge is where preservation meets student housing demand.
- **The James:** river-view towers in Manchester against Church Hill's historic skyline set up Albanico versus the Pod on the water.
- **The city line:** enforcement rules change at the Chesterfield and Henrico boundaries.

No faction can reach its goal without crossing another's ground, which keeps Richmond a connected system rather than a set of mission hubs.

### Terrain as gameplay

Slope drives cargo slip and brake fade. Cobbles and rail crossings slow precise driving. Dense rowhouse blocks create short line-of-sight puzzles. A river with few crossings turns every closure into a routing decision. Neighborhoods change visually through a capped set of state swaps tied to Strain (section 8), not world simulation.

## 7. Campaign structure

Thirty missions in four acts. The act lengths (6, 8, 9, 7) are Established; the content is Recommended.

| Act | Purpose | Main factions and places | Gameplay escalation | Twist and transition |
| --- | --- | --- | --- | --- |
| **I. Work Orders** (1–6) | Establish Mara, her crew, the house and the lien; teach the core loop | Albanico, the Pod, Commission; Church Hill, Shockoe Bottom, downtown | Driving, Line-Striper and Hi-Vis tutorials; Compliance tiers 1–2 | The forged order came from inside her own office. She takes her first paid "overtime" |
| **II. Clients** (7–14) | Widen the map and cast; each faction shows a distinct style; comedy peak | Militia, Truck-Nutz, Independents, first Committee contact; VCU/Broad, Southside, Carytown, the Fan, Scott's Addition | Southside opens by bridge; wing contacts and the Method Dial appear; Compliance tier 3 | Tate has met every faction leader and each thinks he is an ally. He pays off the lien for her "consulting," and she accepts |
| **III. Escalation** (15–23) | Pay off setups, reverse the story, reach the lowest point | All five, Compliance, the Committee; Manchester, downtown, bridges, Shockoe rails, the city line | Bridge closures, rail set piece, Compliance tier 4 and county handoff, Strain at its peak | **Midpoint (15):** the Connector is a ghost project and Tate's fund is real. Cal sells (22); a Means wing strikes (23). She loses the house and the job |
| **IV. Richmond's Future** (24–30) | Converge the personal and political threads; resolve emotionally | All, as an uneasy coalition against Tate; downtown, riverfront, Church Hill | Every system at full difficulty | Pike's reversal and the Committee's price lead to the ending choice |

### Mission list

**Act I:** 1 *Night Shift*; 2 *Cold Patch*; 3 *Notice of Public Interest*; 4 *Survey Stakes* (Albanico); 5 *Density Bonus* (Pod); 6 *Overtime*.

**Act II:** 7 *Bike Lane* (Militia); 8 *Parking Minimum* (Truck-Nutz); 9 *Closing Time* (Independents); 10 *Paper Trail* (records heist); 11 *First Skeleton* (Committee); 12 *Double Booked*; 13 *Hill Climb*; 14 *The Listening Tour*.

**Act III:** 15 *Ghost Project*; 16 *Dead Weight* (Dell); 17 *Bridge Count*; 18 *Annexation Day*; 19 *Public Comment*; 20 *Freight Delay*; 21 *Skeleton Crew*; 22 *Closing Costs* (Cal); 23 *Rock Bottom*.

**Act IV:** 24 *Coalition of the Unwilling*; 25 *Motion to Adjourn* (Committee); 26 *Gridlock*; 27 *Dell's Last Shift*; 28 *River Days*; 29 *Groundbreaking*; 30 *Open House*.

### Key story beats

- **Inciting incident (mission 1):** a forged work order, a scaffold fire and a photographed truck in one night.
- **Midpoint (mission 15):** *Ghost Project*. The Net Good counter appears for the first time.
- **Betrayals:** Dell (16), Cal (22) and a Means wing (23). If the player has leaned on the Mortar Circle, it burns the family house "to protect it" from the sale; otherwise the house goes to auction. Either way the player's own methods have come home.
- **Final confrontation (29):** a convoy chase to the riverfront, infiltration of the ceremony in a hi-vis vest, then a podium choice with the Night Shift Log in Mara's hands.
- **Resolution (30):** *Open House*, a porch scene with Cal or Dell and her mother's old tool chest.

### Endings

Four endings from one final decision, with epilogue tone set by Collateral.

1. **Built:** Tate's version, with Mara taking a cut.
2. **Frozen:** the Committee's procedure stops the project forever, and Tate's fund freezes with it.
3. **The Third Alignment:** a small public use for the parcel and a smaller, honest version of Tate's fund. Requires low Collateral and Believer contacts.
4. **The Fixer:** Mara takes Tate's chair and becomes the next aggressive altruist. Requires high Collateral and Means contacts.

## 8. Gameplay systems

**Core loop (Established, extended):** receive a job, scout the environment, choose a method, execute, live with the consequences.

**Game identity (Recommended):** driving a heavy city vehicle through a real, hilly city while pretending to belong there, and choosing how far to go for people you believe you are helping.

Complexity estimates assume one developer with AI assistance. **Low** is 1–3 weeks, **Medium** is 4–8 weeks, **High** is three months or more. They are rough, not commitments.

### Essential

| System | Description | Complexity | Why it is fun |
| --- | --- | --- | --- |
| **Heavy-vehicle driving** | Cargo slip on grades, brake fade, cobbles, bridges, six vehicle classes | High | Weight and slope make routes puzzles, and the map teaches itself |
| **Work Order template** | One mission structure built from seven verbs: stripe, patch, tow, deliver, swap, block, tail | Medium | One template yields dozens of missions; scouting rewards curiosity |
| **Method Dial** | Most Work Orders offer Kind, Pointed or Hard methods. Hard pays more but adds heat and Collateral | Medium | The same objective plays as a quiet swap, a blockade or a staged fire |
| **Hi-Vis immunity** | A vest, cones and a work order let Mara stand in plain sight inside a work zone. The bubble shrinks in high-Strain districts | Low to Medium | One readable rule replaces stealth and disguises |
| **Line-Striper** | Segment states (normal, bike lane, closed, reversed) set by driving a road; AI traffic updates at the next junction after a delay | Medium | Traffic becomes a puppet you steer by drawing on the road |
| **Compliance ladder** | Citation, tow, code enforcement, police, then a county handoff at the city line. Hard methods can start at tier 2; a Believer contact can talk one tier down once per act | Medium | Escalation has personality and reuses traffic AI |
| **Net Good ledger** | Two counters per job: households helped and households harmed | Low | A small number that makes consequences personal and mirrors Tate |

### High-value optional

| System | Description | Complexity | Why it is fun |
| --- | --- | --- | --- |
| **Collateral and district Strain** | Each district has Strain 0–3 driven by Hard methods. A capped set of 12 to 16 data-layer swaps (boarded storefronts, banners, scaffold scars) follows it | Medium | The city shows what the player did, without simulation |
| **Wing contacts** | Each faction has a Believer and a Means contact. Believers give safe houses, discounts and Collateral relief; Means contacts give narrow tools | Low | Choosing a patron has a flavor and a price |
| **Honest Work** | Tow-outs, real pothole patches and proper striping that raise Net Good and lower Strain | Low | A kind baseline that makes the dark choices stand out |
| **Patch Gun** | A limited-charge tool that spawns bumps, ramps and grip patches | Low to Medium | A cheap physical tool for pursuits and set pieces |
| **Skeleton hunt** | Optional Standing Committee collectibles across the map | Low | Teaches the map and pays off the secret society |

### Means tools by contact

| Contact | Tool | Effect |
| --- | --- | --- |
| **Closers (Pod)** | Forged permit | Opens one gate or voids one citation per job |
| **Mortar Circle (Albanico)** | Scaffold torch (mission use only) | Starts a scripted, non-lethal scaffold fire for a specific objective |
| **Spoke Cell (Militia)** | Signal jammer | Holds a set of traffic lights for 30 seconds |
| **The Hitch (Truck-Nutz)** | Tow hook | Drags a vehicle out of a pursuit |
| **Landlord Club (Independents)** | Rival's keys | Opens a shop's back room during a mission |
| **Procedure Office (Commission)** | Backdated stamp | Skips one bureaucratic step in an infiltration |
| **The Files (Committee)** | Leverage chip | Skips a procedural minigame by cashing in a secret |

Believer contacts offer: letters of support that lower heat (Review Board), crane and forklift access (Prime Builders), trail and alley shortcuts (Dispatch), a free tow-out from any chase (Asphalt Samaritans) and one citation dismissed per act (Pike's clerks).

### Defer or eliminate

- **Firearms and cover-shooting:** expensive and off-brand. Use slapstick instead (cones, wrenches, bumper nudges, vehicle contact).
- **Full stealth AI:** Hi-Vis immunity delivers the same fantasy at a fraction of the cost.
- **Continuous world simulation and deep branching:** the Method Dial, Strain and the single final decision cover it.
- **Faction-specific vehicle handling models and extra authored interiors** beyond a hearing room, a records office and the Committee basement.

### Keeping it small

Method variants are authored for about 12 key missions; all others use a generic modifier (guard count, route risk, a collateral objective). Net Good is two integers per job. Strain is four states per district driving existing data layers.

## 9. Signature missions and location activities

### Five anchor missions (Recommended)

| Mission | Location | Stakes and mechanics | Memorable moment |
| --- | --- | --- | --- |
| **13. Hill Climb** (major driving) | Scott's Addition to Church Hill, via Broad Street and the steep streets below the hill | Deliver a cast-iron cornice rescued from a Pod demolition before dawn. Cargo slip, brake fade, cobbles, Compliance tiers 2–3 | A strap snaps on the last hill, and Mara re-straps while repainting the road to slow a tow truck |
| **20. Freight Delay** (environmental set piece) | Shockoe Bottom rail crossings and the Manchester bank | A train will block every crossing for ten minutes; whoever moves cargo first wins a contract. The train is a moving platform; signals, timed crossings, a crane | Mara drives across couplings while the train moves, then paints a "closed" line across the rails behind her |
| **17. Bridge Count** (geography) | The downtown river crossings (verify names; fictional names are an option) | A Truck-Nutz convoy and a Militia ride meet on one span. Line-Striper segment states, AI reaction, bridge closure rerouting the map | Reversing the middle lane mid-clash so both sides drive at each other politely, and then stop |
| **12. Double Booked** (competing factions) | One block in the Fan, overnight | Albanico pays Mara to remove survey markers and the Pod pays her to install more. Hi-Vis immunity, timing, sign swaps | Both leaders arrive at once, each sees what they want to see, and each thanks her |
| **21. Skeleton Crew** (Standing Committee) | A Fan rowhouse basement during the Committee's annual meeting | Find the original plat of Mara's parcel and win a vote. Hide-in-plain-sight as a giant skeleton, then a points-of-order dialogue minigame | The chair, a retired clerk, has been waiting years for someone to cite the correct ordinance |

### Location-specific activities (Recommended)

Built on mechanics, not neighborhood stereotypes, so players need no local knowledge.

| Location | Activity | Why it is fun mechanically |
| --- | --- | --- |
| **Church Hill** | *Grade Runs:* timed deliveries on the steepest streets with a heavy load | Slope turns momentum into the challenge |
| **The Fan** | *Stoop Watch:* cross a block unseen by porch-sitters using alleys and Hi-Vis cover | Dense blocks create readable line-of-sight puzzles |
| **Scott's Addition** | *Module Drop:* move prefab apartment modules with cranes and forklifts | A physics puzzle with big, slow objects |
| **Manchester** | *River Edge Run:* a chase along riverside industrial roads and rail spurs | Mixed surfaces and tight routes reward map knowledge |
| **Shockoe Bottom** | *Market Morning:* deliver pallets through narrow streets before the market opens | Cobbles, rail crossings and pedestrians in a small area |
| **Jackson Ward** | *Before the Highway:* a walking mission with a toggle showing the old street grid | An earnest discovery puzzle done with a data-layer swap |
| **Carytown** | *Lunch Rush:* courier runs between competing shops on a crowded strip | A timing game with a rival always one block ahead |
| **Downtown** | *Permit Window:* infiltrate a government building floor by floor with forms, stamps and a vest | A maze built on one rule: who belongs where |
| **River bridges** | *Closure Roulette:* a random bridge closes and the player reroutes a delivery | Routes change every time, keeping the map fresh |
| **Interstate interchanges** | *Overlap Dash:* use the Line-Striper to change exit lanes under pursuit | Speed plus a spatial puzzle |
| **City-county line** | *Line Drawn:* enforcement rules change the moment you cross | A map edge becomes a tactical decision |

## 10. Production plan

The original combination of eight factions, 30 missions, branching, a real-map city and persistent world change was not feasible at this scale. The scope in this plan is. All items are Recommended.

### What was reduced

- **Eight factions to five playable groups,** with two pressure systems and the Committee as a story layer.
- **Branching to one final decision,** with epilogue cards driven by Collateral and contact type.
- **Persistent world change to a capped set of 12 to 16 swaps,** keyed to four Strain states per district.
- **Combat to slapstick,** with no firearms and no full stealth AI.

### What is reused

- **One mission template:** the Work Order, built from seven verbs. Faction jobs are reskins of the same verbs; Method variants are authored for about 12 key missions.
- **One vehicle set:** about six classes (city truck, flatbed, cargo bike, pickup, sedan, bus) with faction paint and decals.
- **One enforcement AI:** the Compliance ladder reuses ordinary traffic AI with different behaviors.
- **One world-state mechanism:** World Partition data layers for every persistent change.
- **One NPC kit:** about a dozen archetypes, recolored by faction.

### First vertical slice

A 20 to 30 minute build that proves the core loop and the tone.

1. **Map:** Church Hill, Shockoe Bottom and a strip of downtown as one connected region.
2. **Missions:** *Night Shift* (Line-Striper and Hi-Vis tutorial), a shortened *Hill Climb*, and one faction job with a Kind and a Hard method.
3. **Systems:** driving on real terrain, the Work Order template, Hi-Vis immunity, Line-Striper segment states, Compliance tiers 1–3, the Method Dial and the Net Good counters.
4. **Story beats:** the forged order and fire, the lien notice, Dell's mentorship, a first Tate meeting.
5. **Secret:** one skeleton in a front yard with a short payoff.

If the slice is fun with nothing else, the rest of the game can be built from reusable parts. If it is not, no amount of extra content will fix it.

### Suggested build order

1. Vertical slice (above), with a go or no-go review on the driving and the Method Dial.
2. Core systems hardened: vehicles, Work Order template, Compliance ladder, Strain swaps.
3. Acts I and II, with the Southside bridge unlock.
4. Act III, including the rail and bridge set pieces and the conditional house fire.
5. Act IV, endings, and a polish and balance pass.

### Risks to watch

- **Method Dial authoring cost.** Keep variants to the 12 key missions; resist adding more.
- **Traffic AI reaction to Line-Striper states.** Prototype in the slice before committing to dependent missions.
- **Tone.** Arson, blackmail and gridlock hostage-taking must stay non-lethal, mostly offscreen and consequential.
- **Real-world accuracy.** Verify Richmond details, and consult local historians for Jackson Ward, before writing.

## 11. Creative standards and open decisions

### Creative standards

- **Story first:** players should care about Mara, Cal and Dell, not just complete assignments.
- **Gameplay first:** every plot development must produce an interactive mission.
- **Richmond authenticity without local knowledge:** terrain and geography shape play; jokes come from situations and incentives, not neighborhood stereotypes.
- **Humor with substance:** satire from sincere people with flawed methods, not repeated jokes about zoning.
- **Memorable personalities:** faction leaders are people with aims and lines they cross, not slogans.
- **Mechanical coherence:** a few reusable systems (Work Orders, Method Dial, Line-Striper, Compliance, Strain).
- **Earned twists:** the ghost project, the betrayals and the Committee's role are all foreshadowed.
- **Production discipline:** fun per development hour, not feature count.
- **Respect for real people and places:** fictional organizations in a recognizable city, not statements about residents. Fictional annexation efforts are never presented as current real-world policy.

### Open decisions and working defaults

Each default below is what this plan assumes until you decide otherwise.

| # | Decision | Options | Working default |
| --- | --- | --- | --- |
| 1 | Is the Connector real or a ghost project? | Real and imminent; ghost project; ambiguous until late | **Ghost project,** revealed at the midpoint |
| 2 | Does Mara own a family rowhouse on the route? | Yes, with a brother; rented apartment; a different asset | **Yes,** shared family rowhouse in Church Hill |
| 3 | Mara's background | Returning native; lifelong resident; transplant | **Returning native** |
| 4 | Standing Committee role | Easter egg; recurring power; central conspiracy | **Recurring power,** never the final villain |
| 5 | Combat and rating | Slapstick only; limited melee plus vehicles; full firearms | **Slapstick and vehicles,** teen-to-mature audience |
| 6 | Real or fictional names | Real geography with fictional institutions; fictional except neighborhoods; real throughout | **Real geography and streets,** fictional agencies, companies and bridges |
| 7 | Jackson Ward treatment | Earnest sliver with consultation; comic territory; omit | **Earnest sliver,** consult historians first |
| 8 | Map access | Open from the start; staged by closures; separate hubs | **Staged by bridge and permit closures** |
| 9 | How dark are the Means wings? | Light slapstick; dark comedy with offscreen harm; grim | **Dark comedy, non-lethal and mostly offscreen** |
| 10 | How is the mission 23 fire signaled? | A visible flag from earlier choices; a hidden consequence; no conditional | **A visible flag,** so the player sees their own methods come home |

Once decisions 1, 2 and 4 are confirmed, the next deliverable is a beat-level outline of all 30 missions.