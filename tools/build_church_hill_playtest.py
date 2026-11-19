"""Create a new, disposable Church Hill driving test map from the Unreal editor."""

import argparse
from dataclasses import dataclass
import math
import re


DEFAULT_MAP = "/Game/RVA/Tests/ChurchHillSlice"
CUBE = "/Engine/BasicShapes/Cube.Cube"
CLASSES = {
    "night": "NightShiftWorkOrder",
    "hill": "HillClimbGraybox",
    "survey": "SurveyStakesGraybox",
    "director": "ChurchHillSliceDirector",
}
LANDING_X = 10800
LANDING_Z = 380


@dataclass(frozen=True)
class Ramp:
    label: str
    x_start: float
    y: float
    width: float = 670.0

    @property
    def grade(self):
        return LANDING_Z / (LANDING_X - self.x_start)

    def surface_z(self, x):
        return (x - self.x_start) * self.grade

    def cube_transform(self, thickness=42.0):
        length_x = LANDING_X - self.x_start
        angle = math.atan(self.grade)
        # Offset the cube away from its top face so both ends meet their landings.
        center = (
            (self.x_start + LANDING_X) / 2 + thickness * math.sin(angle) / 2,
            self.y,
            LANDING_Z / 2 - thickness * math.cos(angle) / 2,
        )
        scale = (math.hypot(length_x, LANDING_Z) / 100, self.width / 100, thickness / 100)
        return center, scale, math.degrees(angle)


GENTLE = Ramp("Long gentle grade", 4100, 1970)
DIRECT = Ramp("Short direct grade", 8500, -800)

HILL_ANCHORS = {
    "CornicePickup": (7000, 0, 70),
    "GentleHill": (4400, GENTLE.y, GENTLE.surface_z(4400) + 70),
    "DirectHill": (8800, DIRECT.y, DIRECT.surface_z(8800) + 70),
    "FinalGradeWarning": (11300, 420, LANDING_Z + 70),
    "StrapPullOff": (12000, 420, LANDING_Z + 70),
    "CorniceDelivery": (12800, 420, LANDING_Z + 70),
}

# Illustrative values for the isolated playtest map.
OUTCOMES = {
    "night_outcome": {"households_helped": 1},
    "hill_gentle_outcome": {"households_helped": 1},
    "hill_direct_outcome": {"households_helped": 1},
    "survey_kind_outcome": {"households_helped": 2},
    "survey_hard_outcome": {
        "households_helped": 2,
        "households_harmed": 1,
        "collateral": 1,
        "district_strain_delta": 1,
    },
}


def require_new_map(assets, path):
    if not re.fullmatch(r"/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+", path):
        raise RuntimeError("Use a new Unreal package path under /Game.")
    if assets.does_asset_exist(path):
        raise RuntimeError(f"The map already exists at {path}. Pick a new path.")


def load_prerequisites(unreal, vehicle_game_mode):
    mode = unreal.load_class(None, vehicle_game_mode)
    if not mode:
        raise RuntimeError(f"Vehicle GameMode class could not load: {vehicle_game_mode}")
    default = unreal.get_default_object(mode)
    if not isinstance(default, unreal.GameModeBase):
        raise RuntimeError("Pass an existing GameMode class. A Blueprint class path ends in _C.")
    pawn = default.get_editor_property("default_pawn_class")
    if not pawn or not isinstance(unreal.get_default_object(pawn), unreal.Pawn):
        raise RuntimeError("The supplied GameMode needs a drivable default pawn.")
    cube = unreal.load_asset(CUBE)
    if not cube:
        raise RuntimeError("The built-in Engine cube mesh could not load.")
    actors = {key: unreal.load_class(None, "/Script/RVACivic." + name) for key, name in CLASSES.items()}
    if not all(actors.values()):
        raise RuntimeError("Build and enable RVACivic before creating the test map.")
    return mode, pawn, cube, actors


def populate(unreal, actor_subsystem, world, prerequisites):
    mode, pawn_class, cube, classes = prerequisites

    def spawn(cls, position, label, *, yaw=0.0, pitch=0.0):
        rotation = unreal.Rotator(roll=0.0, pitch=pitch, yaw=yaw)
        actor = actor_subsystem.spawn_actor_from_class(cls, unreal.Vector(*position), rotation)
        if not actor:
            raise RuntimeError(f"Could not place {label}")
        actor.set_actor_label(label)
        return actor

    def solid(label, center, scale, pitch=0.0):
        actor = spawn(unreal.StaticMeshActor, center, label, pitch=pitch)
        mesh = actor.get_component_by_class(unreal.StaticMeshComponent)
        mesh.set_static_mesh(cube)
        mesh.set_collision_profile_name("BlockAll")
        actor.set_actor_scale3d(unreal.Vector(*scale))

    settings = unreal.GameplayStatics.get_actor_of_class(world, unreal.WorldSettings)
    if not settings:
        raise RuntimeError("The new map is missing its World Settings actor.")
    settings.set_editor_property("default_game_mode", mode)
    solid("Lower practice road", (4500, 0, -25), (127, 54, 0.5))
    solid("Upper stoops and delivery pad", (13550, 0, LANDING_Z - 25), (55, 54, 0.5))
    for ramp in (GENTLE, DIRECT):
        center, scale, pitch = ramp.cube_transform()
        solid(ramp.label, center, scale, pitch)
    spawn(unreal.DirectionalLight, (0, 0, 1500), "Daylight", yaw=-40, pitch=-43)
    spawn(unreal.SkyLight, (0, 0, 1200), "Sky fill")
    spawn(unreal.PlayerStart, (-180, 0, 120), "City truck start")

    night = spawn(classes["night"], (0, 0, 0), "M01 Night Shift")
    night.set_editor_property("show_test_surface", False)
    night.set_editor_property("persist_checkpoint", False)
    hill = spawn(classes["hill"], (7000, 0, 0), "M13 Hill Climb")
    components = {zone.get_name(): zone for zone in hill.get_components_by_class(unreal.BoxComponent)}
    origin = hill.get_actor_location()
    for name, position in HILL_ANCHORS.items():
        if name not in components:
            raise RuntimeError(f"Hill Climb is missing its {name} component.")
        components[name].set_editor_property("relative_location", unreal.Vector(
            position[0] - origin.x, position[1] - origin.y, position[2] - origin.z))
    survey = spawn(classes["survey"], (13200, -730, LANDING_Z), "M04 Survey Stakes")

    director = spawn(classes["director"], (100, 680, 0), "Church Hill slice progression")
    for key, value in (("night_shift", night), ("hill_climb", hill), ("survey_stakes", survey),
                       ("playtest_truck_class", pawn_class)):
        director.set_editor_property(key, value)
    for key, values in OUTCOMES.items():
        outcome = unreal.CivicWorkOrderOutcome()
        for field, value in values.items():
            outcome.set_editor_property(field, value)
        director.set_editor_property(key, outcome)


def build(unreal, vehicle_game_mode, target):
    assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    require_new_map(assets, target)
    prerequisites = load_prerequisites(unreal, vehicle_game_mode)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not levels.new_level(target, is_partitioned_world=False):
        raise RuntimeError(f"Could not create the test level at {target}")

    # Save the newly created level after all references and geometry are in place.
    populate(unreal, actors, editor.get_editor_world(), prerequisites)
    if not levels.save_current_level():
        raise RuntimeError(f"The editor did not save the new test level at {target}")
    unreal.log(f"Church Hill test map saved at {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vehicle_game_mode", help="Full Unreal class path of an existing Vehicle GameMode")
    parser.add_argument("--map", default=DEFAULT_MAP, help="New level package path under /Game")
    args = parser.parse_args()
    import unreal
    build(unreal, args.vehicle_game_mode, args.map)


if __name__ == "__main__":
    main()
