"""Original, tileable surface maps for the station's Blender and glTF materials."""

from math import tau

import bpy
import numpy as np


def image_from_pixels(name, pixels, color_space):
    height, width = pixels.shape[:2]
    image = bpy.data.images.new(name, width=width, height=height, alpha=False)
    image.colorspace_settings.name = color_space
    rgba = np.ones((height, width, 4), dtype=np.float32)
    rgba[:, :, :3] = pixels
    image.pixels.foreach_set(rgba.ravel())
    image.pack()
    return image


def tiled_surface(name, count_x, count_y, colors, grout, gap, relief, seed, stagger=True, rough_face=False):
    """Return base color and tangent normal maps with wrapped texel gradients."""
    size = 512
    rng = np.random.default_rng(seed)
    y, x = np.indices((size, size), dtype=np.float32) / size
    row = np.floor(y * count_y).astype(int)
    shifted = x * count_x + (0.5 * (row % 2) if stagger else 0)
    col = np.floor(shifted).astype(int) % count_x
    fx, fy = shifted % 1, (y * count_y) % 1
    if rough_face:
        fx = (fx + 0.008 * np.sin(tau * (17 * y + 3 * x))) % 1
        fy = (fy + 0.035 * np.sin(tau * (19 * x + 2 * y))) % 1
    edge = np.minimum(np.minimum(fx, 1 - fx) / gap[0], np.minimum(fy, 1 - fy) / gap[1])
    bevel = np.clip((edge - 0.66) / 0.72, 0, 1)
    weather = 0.023 * np.cos(tau * (3 * x + y + 0.20 * np.sin(tau * 2 * y)))
    weather += 0.018 * np.sin(tau * (x - 5 * y))
    grit = rng.random((size, size), dtype=np.float32) - 0.5
    variation = rng.random((count_y, count_x), dtype=np.float32)[row, col, None]
    palette = np.asarray(colors, dtype=np.float32) / 255
    body = palette[0] + variation * (palette[1] - palette[0])
    color = np.asarray(grout, dtype=np.float32) / 255
    color = color + (body - color) * bevel[:, :, None]
    color = np.clip(color + (weather + grit * 0.045)[:, :, None], 0, 1)

    height_field = bevel + 0.16 * weather + 0.024 * grit
    if rough_face:
        facets = (
            0.40 * np.sin(tau * (x * 23 + y * 17))
            + 0.36 * np.cos(tau * (x * 29 - y * 37 + 0.55 * np.sin(tau * x * 13)))
            + 0.24 * np.sin(tau * (x * 57 + y * 51))
        )
        height_field += bevel * facets * 0.30
        color += (0.074 * bevel * facets)[:, :, None]
    if not stagger:
        # Crown the clay tiles across their width and shadow the overlapping lap.
        height_field *= 0.65 + 0.35 * np.sin(np.pi * fx) + 0.13 * fy
        color *= (0.86 + 0.15 * np.sin(np.pi * fx) + 0.09 * fy)[:, :, None]
    dx = np.roll(height_field, 1, axis=1) - np.roll(height_field, -1, axis=1)
    dy = np.roll(height_field, 1, axis=0) - np.roll(height_field, -1, axis=0)
    normal = np.stack((relief * dx, relief * dy, np.ones_like(dx)), axis=-1)
    normal = 0.5 + 0.5 * normal / np.linalg.norm(normal, axis=-1, keepdims=True)
    return (image_from_pixels(name + " Base Color", color.clip(0, 1), "sRGB"),
            image_from_pixels(name + " Normal", normal, "Non-Color"))


def material(name, color, roughness=0.65, metal=0.0, maps=None, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, alpha)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metal
    shader.inputs["Alpha"].default_value = alpha
    if alpha < 1.0:
        mat.surface_render_method = "BLENDED"
    if maps:
        base = nodes.new("ShaderNodeTexImage")
        base.image = maps[0]
        base.location = (-550, 180)
        links.new(base.outputs["Color"], shader.inputs["Base Color"])
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = maps[1]
        texture.location = (-550, -160)
        normal = nodes.new("ShaderNodeNormalMap")
        normal.location = (-220, -120)
        links.new(texture.outputs["Color"], normal.inputs["Color"])
        links.new(normal.outputs["Normal"], shader.inputs["Normal"])
    return mat


def station_materials():
    def masonry(name, counts, palette, grout, gaps, relief, seed, **texture_options):
        maps = tiled_surface(name, *counts, palette, grout, gaps, relief, seed, **texture_options)
        return material(name, (0.27, 0.14, 0.08), maps=maps)

    return {
        "brick": masonry("MSS Roman brick", (7, 32), ((174, 104, 70), (198, 132, 94)),
                         (158, 110, 83), (0.025, 0.053), 0.80, 44),
        "stone": masonry("MSS Rusticated foundation stone", (3, 6), ((165, 155, 134), (222, 213, 190)),
                         (151, 139, 120), (0.023, 0.046), 1.60, 50, rough_face=True),
        "clay": masonry("MSS Red clay roof tile", (8, 10), ((137, 55, 39), (190, 91, 61)),
                        (104, 57, 42), (0.041, 0.053), 0.95, 61, stagger=False),
        "pavers": masonry("MSS Plaza brick", (8, 14), ((100, 65, 55), (155, 100, 81)),
                          (88, 80, 72), (0.050, 0.066), 0.8, 72),
        "trim": material("MSS Terra cotta", (0.33, 0.155, 0.091), 0.73),
        "trim_light": material("MSS Buff terra cotta", (0.50, 0.272, 0.161), 0.76),
        "trim_dark": material("MSS Deep terra cotta", (0.198, 0.091, 0.059), 0.77),
        "highlight": material("MSS Pale cut stone", (0.63, 0.55, 0.40), 0.72),
        "glass": material("MSS Cool sash glazing", (0.155, 0.245, 0.296), 0.23, 0.34),
        "glass_dark": material("MSS Dim glazing", (0.088, 0.107, 0.111), 0.23, 0.20),
        "shed_glass": material("MSS Train shed glazing", (0.22, 0.34, 0.36), 0.20, 0.03, alpha=0.23),
        "steel": material("MSS Dark shed ironwork", (0.055, 0.067, 0.063), 0.56, 0.23),
        "shed_roof": material("MSS Train shed standing seam", (0.133, 0.151, 0.151), 0.44, 0.38),
        "wood": material("MSS Dark painted joinery", (0.036, 0.051, 0.039), 0.49),
        "metal": material("MSS Painted iron", (0.042, 0.060, 0.047), 0.48, 0.38),
        "bronze": material("MSS Patinated finial bronze", (0.105, 0.22, 0.164), 0.49, 0.46),
        "clock": material("MSS Opal blue clock glass", (0.52, 0.77, 0.80), 0.34),
        "cream": material("MSS Painted lettering", (0.84, 0.79, 0.62), 0.61),
        "pavement": material("MSS Stone tread", (0.265, 0.243, 0.219), 0.83),
        "leaves": material("MSS Dark boxwood", (0.064, 0.122, 0.035), 0.88),
        "leaves_light": material("MSS Sunlit boxwood", (0.105, 0.174, 0.044), 0.86),
        "soil": material("MSS Mulch", (0.091, 0.058, 0.033), 0.95),
    }
