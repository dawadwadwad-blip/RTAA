"""Restored train-shed exterior in the same local coordinate frame as the headhouse."""

from mathutils import Vector


WEST, EAST = -3.80, 33.54
SOUTH, NORTH = 28.70, 177.58
DECK, EAVE, RIDGE = 6.67, 12.62, 16.25
GLASS_TOP = DECK + 3.20
MID = (WEST + EAST) / 2
BAYS = 28


def glass_panel(group, vertices):
    group.shape(vertices, [tuple(range(len(vertices)))], "shed_glass")


def train_shed(group):
    from math import pi
    from mathutils import Matrix
    from station_headhouse import opening

    y_values = [SOUTH + (NORTH - SOUTH) * i / BAYS for i in range(BAYS + 1)]
    group.box(WEST - 0.36, EAST + 0.36, SOUTH, NORTH, DECK - 0.69, DECK, "pavement")
    group.box(WEST + 0.88, EAST - 0.88, SOUTH, NORTH, -2.75, -0.32, "pavement")
    # The headhouse meets the elevated shed through a lower brick connector.
    group.box(0.25, 32.80, 22.28, SOUTH + 0.12, 3.58, 11.02, "brick")
    group.box(30.92, 32.81, 22.28, SOUTH + 0.12, -2.75, 3.59, "stone")
    group.box(0.10, 33.03, 22.24, SOUTH + 0.26, 10.89, 11.19, "trim_dark")
    group.box(4.60, 30.18, 23.17, 27.90, 11.06, 12.05, "shed_glass")
    group.box(4.49, 30.29, 23.05, 28.02, 12.02, 12.18, "shed_roof")
    start = len(group.vertices)
    for center in (24.7, 27.1):
        opening(group, center, 1.64, 5.1, 7.1, 0.77, 0.12, -0.29, 0.21, "trim_dark", "glass_dark")
    group.transform(Matrix.Translation((32.8, 0, 0)) @ Matrix.Rotation(pi / 2, 4, "Z"), start)
    for x, inward in ((WEST, 1), (EAST, -1)):
        group.box(x - 0.24, x + 0.24, SOUTH, NORTH, DECK - 0.93, DECK - 0.58, "trestle")
        group.box(x - 0.31, x + 0.31, SOUTH, NORTH, DECK - 0.91, DECK - 0.84, "trestle")
        group.box(x - 0.135, x + 0.135, SOUTH, NORTH, EAVE - 0.21, EAVE + 0.11, "steel")
        group.box(x - 0.093, x + 0.093, SOUTH, NORTH, GLASS_TOP - 0.06, GLASS_TOP + 0.028, "steel")
        support_x = x + 0.50 * inward
        for index, y in enumerate(y_values):
            group.box(x - 0.115, x + 0.115, y - 0.13, y + 0.13, DECK, EAVE + 0.03, "steel")
            if index % 2 == 0:
                group.box(support_x - 0.48, support_x + 0.48, y - 0.60, y + 0.60, -2.61, -0.52, "stone")
                group.box(support_x - 0.16, support_x + 0.16, y - 0.23, y + 0.23,
                          -0.53, DECK - 0.74, "trestle")
                if index + 2 <= BAYS:
                    y_end = y_values[index + 2]
                    group.rod((support_x, y, 0.12), (support_x, y_end, DECK - 0.98), 0.13, "trestle", 4)
                    group.rod((support_x, y_end, 0.12), (support_x, y, DECK - 0.98), 0.13, "trestle", 4)
            if index == BAYS:
                continue
            y_next = y_values[index + 1]
            for fraction in (0.33, 0.67):
                mullion = y + (y_next - y) * fraction
                group.box(x - 0.060, x + 0.060, mullion - 0.053, mullion + 0.053, DECK, GLASS_TOP, "steel")
            glass_panel(group, [(x, y, DECK), (x, y_next, DECK), (x, y_next, GLASS_TOP), (x, y, GLASS_TOP)])
            inset = x + 0.48 * inward
            lower = [Vector((inset, val, GLASS_TOP - 0.14)) for val in (y, y_next)]
            upper = [Vector((inset, val, EAVE - 0.32)) for val in (y, y_next)]
            group.rod(lower[0], upper[1], 0.064, "steel", 4)
            group.rod(lower[1], upper[0], 0.064, "steel", 4)
        z = DECK + 1.66
        group.box(x - 0.06, x + 0.06, SOUTH, NORTH, z, z + 0.072, "steel")

    for side in (-1, 1):
        wall_x = WEST if side == -1 else EAST
        monitor = MID + side * 2.88
        roof_edge = wall_x + side * 1.95
        roof_drop = 0.24
        roof_z = RIDGE - 1.02
        front = [(roof_edge, SOUTH - 0.46, EAVE - roof_drop), (monitor, SOUTH - 0.46, roof_z),
                 (monitor, NORTH + 0.46, roof_z), (roof_edge, NORTH + 0.46, EAVE - roof_drop)]
        group.prism([(x, y, z - 0.14) for x, y, z in front], front, "shed_roof")
        glass_panel(group, [(monitor, SOUTH, roof_z), (monitor, NORTH, roof_z), (monitor, NORTH, RIDGE),
                            (monitor, SOUTH, RIDGE)])
        for y in y_values:
            group.box(monitor - 0.065, monitor + 0.065, y - 0.062, y + 0.062, roof_z, RIDGE, "steel")
            group.rod((roof_edge, y, EAVE - roof_drop + 0.018), (monitor, y, roof_z + 0.018), 0.031, "steel", 4)
    group.loft([
        [(MID - 3.16, SOUTH - 0.56, RIDGE - 0.02), (MID + 3.16, SOUTH - 0.56, RIDGE - 0.02),
         (MID + 3.16, NORTH + 0.56, RIDGE - 0.02), (MID - 3.16, NORTH + 0.56, RIDGE - 0.02)],
        [(MID - 0.10, SOUTH - 0.56, RIDGE + 0.51), (MID + 0.10, SOUTH - 0.56, RIDGE + 0.51),
         (MID + 0.10, NORTH + 0.56, RIDGE + 0.51), (MID - 0.10, NORTH + 0.56, RIDGE + 0.51)],
    ], "shed_roof")
    # The exterior photograph reads through the glazing to the repeated
    # crosswise trusses. Keep the frame distinct from the glazing material.
    for y in y_values:
        chord_z = EAVE - 0.68
        group.rod((WEST, y, chord_z), (EAST, y, chord_z), 0.11, "steel", 4)
        for side in (-1, 1):
            wall = WEST if side == -1 else EAST
            monitor = MID + side * 2.88
            group.rod((wall, y, EAVE), (monitor, y, RIDGE - 1.14), 0.14, "steel", 4)
            for index in range(4):
                a, b = index / 4, (index + 1) / 4
                x0, x1 = wall + (monitor - wall) * a, wall + (monitor - wall) * b
                upper = (x1, y, EAVE + (RIDGE - 1.14 - EAVE) * b)
                lower = (x0, y, chord_z)
                group.rod(lower, upper, 0.064, "steel", 4)
                group.rod((x1, y, chord_z), upper, 0.075, "steel", 4)
    for y, inset in ((SOUTH + 0.03, 1), (NORTH - 0.03, -1)):
        glass_panel(group, [(WEST, y, DECK), (EAST, y, DECK), (EAST, y, EAVE), (WEST, y, EAVE)])
        glass_panel(group, [(WEST, y, EAVE), (EAST, y, EAVE), (MID + 2.88, y, RIDGE - 1.02), (MID - 2.88, y, RIDGE - 1.02)])
        for index in range(13):
            x = WEST + (EAST - WEST) * index / 12
            group.box(x - 0.067, x + 0.067, min(y, y + 0.11 * inset), max(y, y + 0.11 * inset), DECK, EAVE, "steel")
