"""Create and check an isolated station collision map inside Unreal Editor 5.6."""

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic_output import write_json
from station_smoke_contract import MAP_ROOT, digest_file, read_bundle


def vector_list(vector):
    return [vector.x, vector.y, vector.z]


def unreal_winding(unreal):
    # The package follows the mathematical cross product. Query the engine's mesh convention.
    mesh = unreal.DynamicMesh()
    buffers = unreal.GeometryScriptSimpleMeshBuffers(
        vertices=[unreal.Vector(0, 0, 0), unreal.Vector(100, 0, 0), unreal.Vector(0, 100, 0)],
        triangles=[unreal.IntVector(0, 1, 2)])
    unreal.GeometryScript_MeshEdits.append_buffers_to_mesh(mesh, buffers)
    normal, valid = mesh.get_triangle_face_normal(0)
    if not valid or abs(normal.z) < 0.99:
        raise RuntimeError("The Unreal mesh orientation probe did not form a horizontal triangle.")
    return normal.z < 0


def create_mesh(unreal, path, mesh_data, metadata, reverse, collision):
    source = unreal.DynamicMesh()
    triangles = mesh_data["triangles"]
    if reverse:
        triangles = [(a, c, b) for a, b, c in triangles]
    buffers = unreal.GeometryScriptSimpleMeshBuffers(
        vertices=[unreal.Vector(*point) for point in mesh_data["vertices"]],
        triangles=[unreal.IntVector(*face) for face in triangles])
    unreal.GeometryScript_MeshEdits.append_buffers_to_mesh(source, buffers)
    if source.get_triangle_count() != len(triangles):
        raise RuntimeError(f"Unreal dropped geometry from {path}.")
    options = unreal.GeometryScriptCreateNewStaticMeshAssetOptions(
        enable_recompute_normals=True, enable_collision=collision,
        collision_mode=unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    mesh, outcome = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(source, path, options)
    if not mesh or outcome != unreal.GeometryScriptOutcomePins.SUCCESS:
        raise RuntimeError(f"Static Mesh creation failed for {path}.")
    bounds = mesh.get_bounding_box()
    actual = [vector_list(bounds.min), vector_list(bounds.max)]
    if any(abs(a - b) > 0.25 for row, expected in zip(actual, metadata["bounds_cm"])
           for a, b in zip(row, expected)):
        raise RuntimeError(f"The Unreal bounds for {path} differ by more than 2.5 mm from the package.")
    return mesh


def check_collision(unreal, world, placed, probes):
    results = []
    for probe in probes:
        x, y, z = probe["point_cm"]
        expected = placed[probe["mesh"]]
        other_actors = [actor for actor in placed.values() if actor != expected]
        # Isolate the expected layer. A Pawn-profile ray must clear the upper bound and hit by the lower bound.
        start = unreal.Vector(x, y, z + 10)
        hits = [unreal.SystemLibrary.line_trace_single_by_profile(
            world, start, unreal.Vector(x, y, z + offset), "Pawn", False, other_actors,
            unreal.DrawDebugTrace.NONE, False) for offset in (1, -1)]
        if hits[0] is not None or hits[1] is None:
            raise RuntimeError(f"The {probe['mesh']} collision at {probe['name']} is outside the 1 cm tolerance.")
        results.append({"name": probe["name"], "mesh": probe["mesh"], "height_range_cm": [z - 1, z + 1]})
    return results


def build(unreal, bundle, variant, game_mode):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", variant):
        raise ValueError("Use a test-map name beginning with a letter and at most 40 letters, digits or underscores.")
    package, geometry = read_bundle(bundle)
    root = f"{MAP_ROOT}/{variant}"
    target = f"{root}/StationSmoke"
    assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    saving = unreal.EditorLoadingAndSavingUtils
    if levels.is_in_play_in_editor() or saving.get_dirty_map_packages() or saving.get_dirty_content_packages():
        raise RuntimeError("End play and save any pending editor changes before building the station test map.")
    if assets.does_directory_exist(root) or assets.does_asset_exist(target):
        raise RuntimeError(f"The test destination {root} already exists. Use a fresh test-map name.")
    mode = unreal.load_class(None, game_mode) if game_mode else None
    if game_mode and (not mode or not isinstance(unreal.get_default_object(mode), unreal.GameModeBase)):
        raise ValueError("Supply the full class path of an existing GameModeBase, including _C for Blueprints.")
    reverse = unreal_winding(unreal)
    if not levels.new_level(target, is_partitioned_world=False):
        raise RuntimeError(f"Could not create {target}.")
    world = editor.get_editor_world()
    if mode:
        world_settings = unreal.GameplayStatics.get_actor_of_class(world, unreal.WorldSettings)
        world_settings.set_editor_property("default_game_mode", mode)
    for key, row in package["meshes"].items():
        collision = key != "StationSign"
        mesh = create_mesh(unreal, f"{root}/SM_{key}", geometry[key], row, reverse, collision)
        actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator())
        if not actor:
            raise RuntimeError(f"Could not place {key}.")
        actor.set_actor_label("RVA " + key)
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        component.set_static_mesh(mesh)
        component.set_collision_profile_name("BlockAll" if collision else "NoCollision")
        if not assets.save_loaded_asset(mesh):
            raise RuntimeError(f"Failed to save {key}.")
    crosswalk = next(row["point_cm"] for row in package["probes"] if row["name"] == "station_crosswalk")
    x, y, z = crosswalk
    for actor_type, location, rotation, label in (
        (unreal.PlayerStart, (x, y, z + 135), unreal.Rotator(yaw=38), "East Main player start"),
        (unreal.DirectionalLight, (x, y, z + 1600), unreal.Rotator(pitch=-43, yaw=-37), "Station daylight"),
        (unreal.SkyLight, (x, y, z + 1400), unreal.Rotator(), "Station sky fill"),
    ):
        actor = actors.spawn_actor_from_class(actor_type, unreal.Vector(*location), rotation)
        if not actor:
            raise RuntimeError(f"Could not place {label}.")
        actor.set_actor_label(label)
    if not levels.save_current_level() or not levels.load_level(target):
        raise RuntimeError(f"Could not save and reopen {target}.")
    placed = {actor.get_actor_label().removeprefix("RVA "): actor for actor in actors.get_all_level_actors()
              if isinstance(actor, unreal.StaticMeshActor) and actor.get_actor_label().startswith("RVA ")}
    if set(placed) != set(geometry):
        raise RuntimeError("The reopened test map is missing one or more station meshes.")
    results = check_collision(unreal, editor.get_editor_world(), placed, package["probes"])
    return {"map": target, "mesh_count": len(placed), "probes": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--variant", default="Run01")
    parser.add_argument("--game-mode", help="Optional existing GameMode class for a manual driving or walking pass")
    args = parser.parse_args(argv)
    if args.report.exists():
        raise RuntimeError("Choose a fresh filename for the collision report.")
    import unreal

    result = {"status": "FAIL"}
    try:
        result["package_sha256"] = digest_file(args.bundle)
        result.update(build(unreal, args.bundle, args.variant, args.game_mode), status="PASS")
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        write_json(args.report, result)
    unreal.log(f"PASS: Reopened {result['map']} and checked {len(result['probes'])} collision points.")


if __name__ == "__main__":
    main()
