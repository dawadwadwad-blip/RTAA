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


def tiled_surface(name, count_x, count_y, colors, grout, gap, relief, seed, stagger=True):
    """Return base color and tangent normal maps with wrapped texel gradients."""
    size = 512
    rng = np.random.default_rng(seed)
    y, x = np.indices((size, size), dtype=np.float32) / size
    row = np.floor(y * count_y).astype(int)
    shifted = x * count_x + (0.5 * (row % 2) if stagger else 0)
    col = np.floor(shifted).astype(int) % count_x
    fx, fy = shifted % 1, (y * count_y) % 1
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


def material(name, color, roughness=0.65, metal=0.0, maps=None):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metal
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
    def masonry(name, counts, palette, grout, gaps, relief, seed, stagger=True):
        maps = tiled_surface(name, *counts, palette, grout, gaps, relief, seed, stagger)
        return material(name, (0.27, 0.14, 0.08), maps=maps)

    return {
        "brick": masonry("MSS Roman brick", (6, 28), ((137, 73, 43), (201, 133, 85)),
                         (138, 113, 91), (0.035, 0.076), 1.35, 44),
        "stone": masonry("MSS Rusticated granite", (3, 6), ((103, 100, 91), (170, 163, 149)),
                         (76, 73, 66), (0.030, 0.065), 1.45, 50),
        "clay": masonry("MSS Red clay roof tile", (8, 10), ((116, 47, 34), (172, 83, 53)),
                        (79, 46, 36), (0.045, 0.058), 0.95, 61, False),
        "pavers": masonry("MSS Plaza brick", (8, 14), ((100, 65, 55), (155, 100, 81)),
                          (88, 80, 72), (0.050, 0.066), 0.8, 72),
        "trim": material("MSS Buff terra cotta", (0.48, 0.29, 0.16), 0.73),
        "highlight": material("MSS Cut limestone", (0.55, 0.48, 0.36), 0.72),
        "shadow": material("MSS Recess", (0.028, 0.019, 0.014), 0.84),
        "glass": material("MSS Blue-green glass", (0.055, 0.096, 0.093), 0.21, 0.22),
        "glass_dark": material("MSS Dim glazing", (0.027, 0.052, 0.054), 0.29, 0.05),
        "wood": material("MSS Dark painted joinery", (0.036, 0.051, 0.039), 0.49),
        "metal": material("MSS Painted iron", (0.042, 0.060, 0.047), 0.48, 0.38),
        "bronze": material("MSS Oxidized bronze", (0.18, 0.17, 0.10), 0.48, 0.48),
        "dome": material("MSS Bronze gray tower roof", (0.136, 0.146, 0.126), 0.55, 0.30),
        "clock": material("MSS Ivory clock enamel", (0.82, 0.77, 0.62), 0.42),
        "cream": material("MSS Painted lettering", (0.84, 0.79, 0.62), 0.61),
        "pavement": material("MSS Stone tread", (0.265, 0.243, 0.219), 0.83),
        "leaves": material("MSS Dark boxwood", (0.064, 0.122, 0.035), 0.88),
        "leaves_light": material("MSS Sunlit boxwood", (0.105, 0.174, 0.044), 0.86),
        "soil": material("MSS Mulch", (0.091, 0.058, 0.033), 0.95),
    }
