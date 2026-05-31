"""
Footprint filters for KiCad .kicad_mod files.

These filters operate on parsed s-expressions and modify footprint data.
"""
import base64
import copy
import io
import logging
import math
from typing import Any, cast

import numpy as np
import trimesh
import trimesh.transformations as tf
import zstandard as zstd
from numpy import sign
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from .kicad_base import find_all_elements, find_element
from .kicad_sexpr import QuotedString

log = logging.getLogger(__name__)


def get_footprint_side(s_expression: list) -> str:
    """
    Detects which side of the PCB a footprint is on based on its layer attribute.

    In KiCad PCB files, embedded footprints have a (layer "F.Cu") or (layer "B.Cu")
    attribute indicating which side of the board they're placed on.

    Args:
        s_expression: The footprint s-expression list

    Returns:
        "front" if on F.Cu (top side) or no layer found
        "back" if on B.Cu (bottom side)
    """
    for item in s_expression:
        if isinstance(item, list) and len(item) >= 2 and item[0] == 'layer':
            layer_name = str(item[1]).strip('"')
            if layer_name == 'B.Cu':
                return "back"
            elif layer_name == 'F.Cu':
                return "front"
    # Default to front side if no layer attribute found (standalone .kicad_mod files)
    return "front"


def get_fab_layer_for_side(side: str) -> str:
    """
    Returns the appropriate fab layer name based on footprint side.

    Args:
        side: "front" or "back"

    Returns:
        "F.Fab" for front side, "B.Fab" for back side
    """
    return "B.Fab" if side == "back" else "F.Fab"


def add_reference_text_to_fab(s_expression: list, center_position: list, hull_shortest_side: float, fab_layer: str | None = None) -> list:
    """
    Common helper function to add a reference text string to the fab layer.

    Args:
        s_expression: The s-expression list to modify
        center_position: [x, y] coordinates for the reference text center
        hull_shortest_side: The shortest side of the bounding box (used for font sizing)
        fab_layer: Layer to add the reference text to (default: auto-detect from footprint side)

    Returns:
        Modified s-expression with reference text added
    """
    # Auto-detect fab layer if not specified
    if fab_layer is None:
        side = get_footprint_side(s_expression)
        fab_layer = get_fab_layer_for_side(side)
    # Find the reference value from the s-expression
    reference = None
    part_center = None

    for p in s_expression:
        if isinstance(p, list) and len(p) > 0:
            # Directly check for property Reference
            if p[0] == 'property' and len(p) >= 3 and p[1] == QuotedString('Reference'):
                reference = p[2]
                # Try to get the center from the 'at' field in this property
                for item in p:
                    if isinstance(item, list) and item[0] == 'at' and len(item) >= 3:
                        part_center = [float(item[1]), float(item[2])]
            # Fallback: global at
            if part_center is None and p[0] == 'at' and len(p) >= 3:
                part_center = [float(p[1]), float(p[2])]

    if reference is not None:
        # Calculate appropriate font size based on bounding box size
        size = min(0.25 * hull_shortest_side, 1.0)
        thickness = min(hull_shortest_side / 10, 0.5)

        ref_string = [
            'fp_text', 'reference', reference,
            ['at', center_position[0], center_position[1]],
            ['layer', QuotedString(fab_layer)],
            ['effects', ['font', ['size', size, size], ['thickness', thickness]]],
        ]

        log.info(f"- Adding reference string (fp_text reference \"{reference}\") at [{center_position[0]:.4f}, {center_position[1]:.4f}] on {fab_layer}")
        log.info("Success: Added reference string.")

        # Add the reference text
        s_expression.append(ref_string)

        # Move the reference text to just after the first pad (if any pads exist)
        for i, p in enumerate(s_expression):
            if isinstance(p, list) and len(p) > 0 and p[0] == 'pad':
                # Move the fp_text reference to the position after the first pad
                s_expression.insert(i, s_expression.pop())
                break
    else:
        log.error("Error: Could not find reference. Skipping reference string addition.")

    return s_expression


def fp_filter__clean_layers(unfiltered_s_expression: Any, layers: list[str] | None = None) -> Any:
    """
    Removes all objects on specified layers from a footprint s-expression.

    Args:
        unfiltered_s_expression: The parsed s-expression list
        layers: List of layer names to clean. Supports exact matches and prefix matches.
                Default: ["F.Fab", "B.Fab", "User."]

    Layer matching:
        - Exact match: "F.Fab" matches only "F.Fab"
        - Prefix match (ends with .): "User." matches "User.1", "User.Drawings", etc.
    """
    if layers is None:
        layers = ["F.Fab", "B.Fab", "User.", "Eco1.User", "Eco2.User"]

    log.info(f"\nRunning fp_filter__clean_layers(layers={layers})...\n")

    def layer_matches(layer_name, patterns):
        """Check if layer_name matches any pattern in the list."""
        if layer_name is None:
            return False
        # Normalize: strip quotes if present
        layer_str = str(layer_name).strip('"')
        for pattern in patterns:
            if pattern.endswith('.'):
                # Prefix match
                if layer_str.startswith(pattern[:-1]):
                    return True
            else:
                # Exact match
                if layer_str == pattern:
                    return True
        return False

    layers_removed = 0
    # Walk in reverse so removals don't disturb iteration.
    for i in range(len(unfiltered_s_expression) - 1, -1, -1):
        p = unfiltered_s_expression[i]
        if not isinstance(p, list):
            continue
        layer_elem = find_element(p, 'layer')
        layer_name = layer_elem[1] if (layer_elem is not None and len(layer_elem) >= 2) else None
        if layer_matches(layer_name, layers):
            log.info(f"- Removing object ({p[0]}) on layer {layer_name}")
            unfiltered_s_expression.pop(i)
            layers_removed += 1
            continue
        # Clear property "Value" to empty string (in place).
        if (len(p) >= 3 and p[0] == 'property' and p[1] == QuotedString('Value')):
            log.info(f"- Setting property \"Value\" to empty string for {p[2]}")
            log.info("Success: Cleared property \"Value\".")
            p[2] = QuotedString(' ')

    if layers_removed > 0:
        log.info(f"Success: {layers_removed} objects removed from layers matching {layers}.")
    else:
        log.warning(f"Warning: No objects found on layers matching {layers}.")


    log.info("\nDone! S-expression has been filtered...")
    return unfiltered_s_expression


def fp_filter__clean_fab(unfiltered_s_expression: Any) -> Any:
    """Backward compatible wrapper - cleans F.Fab, B.Fab, User.*, Eco layers."""
    return fp_filter__clean_layers(unfiltered_s_expression)


def fp_filter__add_fab_bounding_orthogonal_convex(unfiltered_s_expression: Any) -> Any:
    """
    - Auto generates a new convex hull bounding box that is 75% larger than the pads on the fab layer.
    - Adds a "REF**" string to the center of the part on the fab layer.
    - Auto-detects if footprint is on front or back side and uses appropriate fab layer (F.Fab or B.Fab).
    """
    def orthogonal_convex_hull(points):
        # Step 1: Calculate center
        center = np.mean(points, axis=0)
        center_x, center_y = center

        # Step 2: Assign to quadrants
        q1, q2, q3, q4 = [], [], [], []
        for p in points:
            x, y = p
            if x >= center_x and y >= center_y:
                q1.append(p)
            elif x < center_x and y >= center_y:
                q2.append(p)
            elif x < center_x and y < center_y:
                q3.append(p)
            else:
                q4.append(p)

        # Step 3: Filter maximal points in each quadrant
        q1 = [p for p in q1 if not any(p_check[0] > p[0] and p_check[1] > p[1] for p_check in points)]
        q2 = [p for p in q2 if not any(p_check[0] < p[0] and p_check[1] > p[1] for p_check in points)]
        q3 = [p for p in q3 if not any(p_check[0] < p[0] and p_check[1] < p[1] for p_check in points)]
        q4 = [p for p in q4 if not any(p_check[0] > p[0] and p_check[1] < p[1] for p_check in points)]

        # Step 4: Merge hull candidates
        hull_points = np.array(q1 + q2 + q3 + q4)

        # Step 5: Sort points in true clockwise order around the center
        center = np.mean(hull_points, axis=0)
        def angle_from_center(p):
            return np.arctan2(p[1] - center[1], p[0] - center[0])
        # Sort by angle, largest to smallest for clockwise
        sorted_hull = np.array(sorted(hull_points, key=angle_from_center, reverse=True))

        # Step 6: Add inward-bend orthogonal segments
        ortho_path = []
        n = len(sorted_hull)

        for i in range(n):
            start = sorted_hull[i]
            end = sorted_hull[(i + 1) % n]

            intersection_p1 = [end[1], start[0]]  # Orthogonal intersection point
            intersection_p2 = [start[1], end[0]]  # Orthogonal intersection point

            distance_p1 = math.sqrt((intersection_p1[0] - start[0])**2 + (intersection_p1[1] - start[1])**2)
            distance_p2 = math.sqrt((intersection_p2[0] - end[0])**2 + (intersection_p2[1] - end[1])**2)

            if (abs(start[0]) < abs(start[1]) and start[0] > center[0] and start[1] > center[1]) or (abs(start[0]) < abs(start[1]) and start[0] < center[0] and start[1] < center[1]):
                horizontal_first = False
            else:
                if sign(start[0]) == sign(start[1]):
                    if distance_p1 < distance_p2:
                        horizontal_first = False
                    else:
                        horizontal_first = True
                else:
                    if distance_p1 > distance_p2:
                        horizontal_first = True
                    else:
                        horizontal_first = False

            if horizontal_first:
                mid = np.array([end[0], start[1]])
            else:
                mid = np.array([start[0], end[1]])

            ortho_path.append(start)
            if not np.array_equal(mid, start):
                ortho_path.append(mid)
            if not np.array_equal(end, mid):
                ortho_path.append(end)

        return np.array(ortho_path)

    log.info("\nRunning fp_filter__add_fab_bounding_orthogonal_convex()...\n")

    # Detect footprint side and determine appropriate fab layer
    side = get_footprint_side(unfiltered_s_expression)
    fab_layer = get_fab_layer_for_side(side)
    log.info(f"- Footprint is on {side} side, using {fab_layer} layer")

    bb_line_width = .127

    # This will auto generate a new bounding box that is 1 line width larger than the pad extends

    point_collection = []
    for p in unfiltered_s_expression:
        # Check if this is a pad object
        if isinstance(p, list) and len(p) > 0 and p[0] == 'pad':
            # Find the pad size and center
            pad_size: list[float] | None = None
            pad_center: list[float] | None = None
            pad_rotation = 0.0
            for item in p:
                if isinstance(item, list) and len(item) >= 3 and item[0] == 'size':
                    pad_size = [float(item[1]), float(item[2])]
                if isinstance(item, list) and len(item) >= 3 and item[0] == 'at':
                    pad_center = [float(item[1]), float(item[2])]
                    pad_rotation = float(item[3]) if len(item) > 3 and isinstance(item[3], (int, float)) else 0.0
            if pad_size is not None and pad_center is not None:
                center = pad_center
                # Calculate the new size, which is increased by 2x the bounding box line width
                new_size = [pad_size[1] + (3*bb_line_width), pad_size[0] + (3*bb_line_width)]

                UL_corner = [float(f"{(center[0] - (new_size[0])/2):.4f}"),
                             float(f"{(center[1] - (new_size[1])/2):.4f}")]
                UR_corner = [float(f"{(center[0] + (new_size[0])/2):.4f}"),
                             float(f"{(center[1] - (new_size[1])/2):.4f}")]
                LL_corner = [float(f"{(center[0] - (new_size[0])/2):.4f}"),
                             float(f"{(center[1] + (new_size[1])/2):.4f}")]
                LR_corner = [float(f"{(center[0] + (new_size[0])/2):.4f}"),
                             float(f"{(center[1] + (new_size[1])/2):.4f}")]

                # Based on the pad rotation, we can rotate the corners
                if pad_rotation != 0:
                    # Convert rotation to radians
                    rotation_rad = np.radians(pad_rotation + 90)
                    cos_theta = np.cos(rotation_rad)
                    sin_theta = np.sin(rotation_rad)

                    # Rotate the corners around the pad center
                    def rotate_point(point):
                        x, y = point
                        x_new = cos_theta * (x - center[0]) - sin_theta * (y - center[1]) + center[0]
                        y_new = sin_theta * (x - center[0]) + cos_theta * (y - center[1]) + center[1]
                        return [float(f"{x_new:.4f}"), float(f"{y_new:.4f}")]

                    UL_corner = rotate_point(UL_corner)
                    UR_corner = rotate_point(UR_corner)
                    LL_corner = rotate_point(LL_corner)
                    LR_corner = rotate_point(LR_corner)

                pad_points = [UL_corner, UR_corner, LR_corner, LL_corner]
                point_collection.extend(pad_points)

        # Now add the points from all F.SilkS layer fp_line objects.
        if isinstance(p, list) and len(p) > 0 and p[0] == 'fp_line':
            for item in p:
                if isinstance(item, list) and len(item) >= 2 and item[0] == 'layer':
                    if item[1] == 'F.SilkS':
                        # Find the start and end points of the line
                        start_point = None
                        end_point = None
                        scaler = 1.1  # Exaggeration factor
                        for sub_item in p:
                            if isinstance(sub_item, list) and len(sub_item) >= 3:
                                if sub_item[0] == 'start':
                                    start_point = [float(sub_item[1])*scaler, float(sub_item[2])*scaler]
                                elif sub_item[0] == 'end':
                                    end_point = [float(sub_item[1])*scaler, float(sub_item[2])*scaler]
                        if start_point is not None and end_point is not None:
                            # Exaggerate the points by 20% in both directions
                            point_collection.append(start_point)
                            point_collection.append(end_point)

    # Using the convex hull to create a bounding box around all pads
    if len(point_collection) > 1:
        points_array = np.array(point_collection)
        hull_points = orthogonal_convex_hull(points_array)

        # Grab the agerage of all the points to find the center of the bounding box
        center_x = np.mean(hull_points[:, 0])
        center_y = np.mean(hull_points[:, 1])
        bounding_box_center = [center_x, center_y]

        # Grab the height and width of the convex hull
        hull_height = np.max(hull_points[:, 1]) - np.min(hull_points[:, 1])
        hull_width = np.max(hull_points[:, 0]) - np.min(hull_points[:, 0])
        hull_shortest_side = min(hull_height, hull_width)

        # Create the bounding box lines
        for p in range(len(hull_points)):
            start_point = hull_points[p]
            end_point = hull_points[(p + 1) % len(hull_points)]

            # Add a bunch of fp_line objects to create a bounding box

            type = 'solid'
            color = [0, 0, 0, 1] # RGBA format, black color

            # Create a line object for the bounding box
            bounding_box_line = [
                'fp_line',
                ['start', start_point[0], start_point[1]],
                ['end', end_point[0], end_point[1]],
                ['stroke', ['width', bb_line_width], ['type', type], ['color'] + color],
                ['layer', QuotedString(fab_layer)],
                ['uuid', QuotedString('')]
            ]
            unfiltered_s_expression.append(bounding_box_line)
    else:
        # There are too few points so defaults will be defined.
        hull_shortest_side = 5
        bounding_box_center = [0, 0]
        log.warning("Warning: Footprint does not have enough points to define a convex hull.\n Placing the reference string in the center.")


    log.info(f"- Adding bounding box around pads with {len(point_collection)} points on {fab_layer}.")
    log.info("Success: Added bounding box around pads.")

    # Use the common function to add reference text to the appropriate fab layer
    add_reference_text_to_fab(unfiltered_s_expression, bounding_box_center, hull_shortest_side, fab_layer)
    log.info("\nDone! S-expression has been filtered...")

    return unfiltered_s_expression


def fp_filter__normalized_embedded_model_naming(unfiltered_s_expression: Any) -> Any:
    """
    This is a filter for an s-expression file that does the following:
    - Looks for the model.
    - Looks for the embedded_files.
    - If there is an embedded_files (i.e. there is an embedded model),
        it will rename the string in the file to match the footprint file name.
    """
    log.info("\nRunning fp_filter__normalized_embedded_model_naming()...\n")

    footprint_name = unfiltered_s_expression[1]

    # For PCB-embedded footprints, the name is "library:footprint"
    # Extract just the footprint name (after the colon)
    if ':' in str(footprint_name):
        footprint_name_only = str(footprint_name).split(':')[-1]
        log.info(f"  - Detected PCB footprint format, using name: {footprint_name_only}")
        footprint_name = footprint_name_only

    embedded_files_section = find_element(unfiltered_s_expression, 'embedded_files')
    model_section = find_element(unfiltered_s_expression, 'model')

    # Check if the "{footprint_name}.STEP" matches the embedded model name
    if embedded_files_section is not None:
        file_name = embedded_files_section[1][1][1] if len(embedded_files_section) > 1 else None
        if file_name != f"{footprint_name}.STEP":
            log.warning("Warning: Embedded file name does not match footprint name.")
            log.info(f"- Renaming embedded model from {file_name} to {footprint_name}.STEP")
            embedded_files_section[1][1][1] = QuotedString(f"{footprint_name}.STEP")
            log.info("Success: Renamed embedded model file name.")
    else:
        log.info("Info: No embedded_files section found (normal for PCB-embedded footprints).")

    # Check if the model section exists and check the model name
    if model_section is not None:
        model_name = model_section[1] if len(model_section) > 1 else None
        log.info(f"- Model name is {model_name}")
        # Only check for kicad-embed if there's an embedded_files section
        if embedded_files_section is not None and model_name != f"kicad-embed://{footprint_name}.STEP":
            log.warning("Warning: Model name does not match footprint name.")
            log.info(f"- Renaming model from {model_name} to kicad-embed://{footprint_name}.STEP")
            model_section[1] = QuotedString(f"kicad-embed://{footprint_name}.STEP")
            log.info("Success: Renamed model name.")
    else:
        log.info("Info: No model section found.")

    log.info("\nDone! S-expression has been filtered...")
    return unfiltered_s_expression


def fp_filter__fix_zero_sized_pads(unfiltered_s_expression: Any) -> Any:
    """
    This is a filter for an s-expression file that does the following:
    - Finds pads with (size 0 0) or (size 0.0 0.0)
    - Changes the pad size to 1um (0.001mm) to make them valid
    - Leaves everything else unchanged
    """
    log.info("\nRunning fp_filter__fix_zero_sized_pads()...\n")

    pads_fixed = 0
    for pad in find_all_elements(unfiltered_s_expression, 'pad'):
        pad_name = pad[1] if len(pad) > 1 else "unknown"
        for i, item in enumerate(pad):
            if isinstance(item, list) and len(item) >= 3 and item[0] == 'size':
                if float(item[1]) == 0.0 and float(item[2]) == 0.0:
                    log.warning(f"- Fixing zero-sized pad '{pad_name}': setting size to 0.001mm")
                    pad[i] = ['size', 0.001, 0.001]
                    pads_fixed += 1
                break

    if pads_fixed > 0:
        log.info(f"Success: Fixed {pads_fixed} zero-sized pad(s).")


    log.info("\nDone! S-expression has been filtered...")
    return unfiltered_s_expression


def fp_filter__fix_fp_text_font_to_arial(unfiltered_s_expression: Any) -> Any:
    """
    This is a filter for an s-expression file that does the following:
    - Finds all fp_text objects
    - Ensures they have (face "Arial") in their effects/font section
    - If face doesn't exist, adds it
    - If face exists but is not Arial, changes it to Arial
    """
    log.info("\nRunning fp_filter__fix_fp_text_font_to_arial()...\n")

    texts_fixed = [0]

    def ensure_arial(elem: list, object_desc: str) -> None:
        effects = find_element(elem, 'effects')
        if effects is None:
            log.info(f"- Adding effects section with Arial font to {object_desc}")
            elem.append(['effects', ['font', ['face', QuotedString('Arial')]]])
            texts_fixed[0] += 1
            return
        font = find_element(effects, 'font')
        if font is None:
            log.info(f"- Adding font section with Arial face to {object_desc}")
            effects.append(['font', ['face', QuotedString('Arial')]])
            texts_fixed[0] += 1
            return
        for k, font_item in enumerate(font):
            if isinstance(font_item, list) and len(font_item) >= 2 and font_item[0] == 'face':
                if font_item[1] != QuotedString('Arial'):
                    log.info(f"- Changing font face from {font_item[1]} to Arial for {object_desc}")
                    font[k] = ['face', QuotedString('Arial')]
                    texts_fixed[0] += 1
                return
        log.info(f"- Adding Arial font face to {object_desc}")
        font.append(['face', QuotedString('Arial')])
        texts_fixed[0] += 1

    for elem in unfiltered_s_expression:
        if not (isinstance(elem, list) and len(elem) > 0 and elem[0] in ('fp_text', 'property')):
            continue
        label = elem[1] if len(elem) > 1 else "unknown"
        ensure_arial(elem, f"{elem[0]} {label}")

    if texts_fixed[0] > 0:
        log.info(f"Success: Fixed {texts_fixed[0]} text/property font face(s) to Arial.")
    else:
        log.warning("Warning: No text/property fonts needed fixing.")

    log.info("\nDone! S-expression has been filtered...")
    return unfiltered_s_expression


def fp_filter__orthographic_projection_outline(unfiltered_s_expression: Any) -> Any:
    """
    This is a filter for an s-expression file that does the following:
    - Extracts the embedded STEP file data.
    - Decodes the BASE64 and decompresses with ZSTD.
    - Assembles the STEP file and applies STEP file node graph requests and KiCad requested transformations.
    - Flattens the STEP model using Trimesh along the Z-Axis and finds an outline.
    - Applies the outline as an assortment of fp_lines on the appropriate fab layer to the s-expression file.
    - Adds a "REF**" string to the center of the part on the appropriate fab layer.
    - Auto-detects if footprint is on front or back side and uses appropriate fab layer (F.Fab or B.Fab).
    - If no embedded STEP model is found, falls back to fp_filter__add_fab_bounding_orthogonal_convex.
    """

    def get_model_transform(s_expr):
        """
        Extracts (offset), (scale), (rotate) from the (model ...) section of the s-expression.
        Returns a 4x4 transformation matrix.
        """
        for item in s_expr:
            if isinstance(item, list) and item and item[0] == 'model':
                offset = [0, 0, 0]
                scale = [1, 1, 1]
                rotate = [0, 0, 0]
                for sub in item[1:]:
                    if isinstance(sub, list) and sub and sub[0] == 'offset':
                        for xyz in sub[1:]:
                            if isinstance(xyz, list) and xyz[0] == 'xyz':
                                offset = [float(x) for x in xyz[1:]]
                    if isinstance(sub, list) and sub and sub[0] == 'scale':
                        for xyz in sub[1:]:
                            if isinstance(xyz, list) and xyz[0] == 'xyz':
                                scale = [float(x) for x in xyz[1:]]
                    if isinstance(sub, list) and sub and sub[0] == 'rotate':
                        for xyz in sub[1:]:
                            if isinstance(xyz, list) and xyz[0] == 'xyz':
                                rotate = [float(x) for x in xyz[1:]]
                # KiCad transform order (from create_scene.cpp lines 1306-1322):
                # modelMatrix = translate(modelMatrix, offset)
                # modelMatrix = rotate(modelMatrix, -rot_z, Z)
                # modelMatrix = rotate(modelMatrix, -rot_y, Y)
                # modelMatrix = rotate(modelMatrix, -rot_x, X)
                # modelMatrix = scale(modelMatrix, scale)
                #
                # This builds: T * Rz * Ry * Rx * S
                # Applied to point p: Scale -> RotX -> RotY -> RotZ -> Translate
                m_scale = tf.scale_matrix(scale[0], [0, 0, 0])
                m_scale[1, 1] = scale[1]
                m_scale[2, 2] = scale[2]
                m_rot_x = tf.rotation_matrix(np.deg2rad(-rotate[0]), [1, 0, 0])
                m_rot_y = tf.rotation_matrix(np.deg2rad(-rotate[1]), [0, 1, 0])
                m_rot_z = tf.rotation_matrix(np.deg2rad(-rotate[2]), [0, 0, 1])
                m_trans = tf.translation_matrix([offset[0], offset[1], offset[2]])
                # Match KiCad order: T * Rz * Ry * Rx * S
                m = tf.concatenate_matrices(m_trans, m_rot_z, m_rot_y, m_rot_x, m_scale)
                log.info(f"[........   ] Created transformation matrix (offset={offset}, rotate={rotate}).")
                return m
        log.error("[.......x   ] Error: Could not create transformation matrix.")
        return np.eye(4)

    def polygon_to_fp_lines(polygon, layer="Eco1.User", width=0.12):
        """
        Converts a shapely Polygon or MultiPolygon to a list of fp_line s-expr lists.
        """
        fp_lines = []
        def add_ring(ring):
            coords = list(ring.coords)
            for i in range(len(coords) - 1):
                start = coords[i]
                end = coords[i + 1]
                fp_lines.append([
                    'fp_line',
                    ['start', float(start[0]), float(start[1])],
                    ['end', float(end[0]), float(end[1])],
                    ['stroke', ['width', width], ['type', 'default']],
                    ['layer', QuotedString(layer)]
                ])
        if isinstance(polygon, Polygon):
            add_ring(polygon.exterior)
            for interior in polygon.interiors:
                add_ring(interior)
        elif isinstance(polygon, MultiPolygon):
            for poly in polygon.geoms:
                add_ring(poly.exterior)
                for interior in poly.interiors:
                    add_ring(interior)
        log.info("[...........] Generated KiCad S-Expression fp_lines from projected polygon.")
        return fp_lines

    def find_embedded_step_data(sexp, step_exts=(".stp", ".step")):
        """
        Traverses the parsed s-expression to find the embedded STEP data.
        Returns the base64 string if found, else None.
        """
        def walk(node):
            if isinstance(node, list):
                # Look for embedded_files
                if node and node[0] == 'embedded_files':
                    for file_node in node[1:]:
                        if isinstance(file_node, list) and file_node and file_node[0] == 'file':
                            name = None
                            data = None
                            for item in file_node[1:]:
                                if isinstance(item, list) and item and item[0] == 'name':
                                    name = item[1]
                                if isinstance(item, list) and item and item[0] == 'data':
                                    # Join all data parts, remove newlines, strip KiCad's |...| wrapper
                                    data = ''.join(item[1:]).replace('\n', '').replace('\r', '').strip('|')
                            if name and any(str(name).lower().endswith(ext) for ext in step_exts) and data:
                                log.info(f"[..         ] Success: Found step data for {str(name)}")
                                return data
                # Recurse into children
                for child in node:
                    result = walk(child)
                    if result:
                        return result
            return None
        return walk(sexp)

    log.info("\nRunning fp_filter__orthographic_projection_outline()...\n")

    # Detect footprint side and determine appropriate fab layer
    side = get_footprint_side(unfiltered_s_expression)
    fab_layer = get_fab_layer_for_side(side)
    log.info(f"- Footprint is on {side} side, using {fab_layer} layer")

    unfiltered_s_expr_list = unfiltered_s_expression

    file_name = None
    for item in unfiltered_s_expr_list:
        if isinstance(item, list) and item and item[0] == 'model':
            if len(item) > 1 and isinstance(item[1], str):
                model_str = item[1]
                if model_str.startswith("kicad-embed://"):
                   file_name = model_str[len("kicad-embed://"):]

    b64_data = find_embedded_step_data(unfiltered_s_expr_list)
    if not b64_data:
        log.warning(f"Warning: No embedded STEP data found in {file_name}.")
        log.info("Falling back to fp_filter__add_fab_bounding_orthogonal_convex()...")
        return fp_filter__add_fab_bounding_orthogonal_convex(unfiltered_s_expr_list)

    compressed_data = base64.b64decode(b64_data)
    log.info("[...        ] Base64 decoded.")

    try:
        data = zstd.decompress(compressed_data)
        log.info("[....       ] Success: ZSTD decompressed successfully.")
    except Exception as e:
        log.error(f"[...x       ] Error: ZSTD decompression failed: {e}")
        return fp_filter__add_fab_bounding_orthogonal_convex(unfiltered_s_expr_list)

    step_io = io.BytesIO(data)

    try:
        # merge_primitives=False is required because some STEP files have primitives
        # without materials, which causes trimesh's merge logic to fail with KeyError: 'visual'
        # This is a trimesh bug where it assumes all primitives have a 'visual' key when merging.
        mesh_dict = cast(Any, trimesh).exchange.cascade.load_step(
            step_io, file_type="step", merge_primitives=False
        )
    except Exception as e:
        log.warning(f"STEP loading failed for {file_name}: {e}")
        log.warning("Falling back to convex hull from pads...")
        return fp_filter__add_fab_bounding_orthogonal_convex(unfiltered_s_expr_list)

    log.info("[.....      ] STEP model data set up for Trimesh.")

    # Grab all the geometry from the file.
    geometry = mesh_dict['geometry']
    # Grab all the nodes from graph in the file to assemble the parts.
    # The graph is a scene hierarchy - we need to compute full transforms by walking the tree
    nodes = mesh_dict['graph']

    # Build frame transform lookup: frame_to -> (frame_from, matrix)
    frame_transforms = {}
    geometry_frames = {}  # geometry_name -> frame_to
    for node in nodes:
        frame_to = node.get('frame_to')
        frame_from = node.get('frame_from')
        matrix = node.get('matrix', np.eye(4))
        if frame_to:
            frame_transforms[frame_to] = (frame_from, np.array(matrix).reshape(4, 4))
        if 'geometry' in node and frame_to:
            geometry_frames[node['geometry']] = frame_to

    def get_full_transform(frame):
        """Walk up the frame hierarchy to compute full world transform."""
        if frame == 'world' or frame not in frame_transforms:
            return np.eye(4)
        parent_frame, local_matrix = frame_transforms[frame]
        parent_transform = get_full_transform(parent_frame)
        return parent_transform @ local_matrix

    # Compute full transform for each geometry
    node_map = {}
    for geom_name, frame in geometry_frames.items():
        node_map[geom_name] = get_full_transform(frame)

    # Also check for geometries not in geometry_frames (direct mapping)
    for node in nodes:
        if 'geometry' in node and node['geometry'] not in node_map:
            frame_to = node.get('frame_to', 'world')
            node_map[node['geometry']] = get_full_transform(frame_to)

    meshes = []
    for name, part in geometry.items():
        # Skip geometries without faces (e.g., COMPOUND entities with only 'entities' key)
        if 'faces' not in part:
            continue

        transform = node_map.get(name, np.eye(4))

        verts = part['vertices']
        # Only process if verts are 2D or 3D points
        if verts.shape[1] == 2:
            verts = np.hstack([verts, np.zeros((verts.shape[0], 1))])
        elif verts.shape[1] == 3:
            pass  # OK
        else:
            log.warning(f"Skipping geometry '{name}' with unexpected vertex shape: {verts.shape}")
            continue

        verts_hom = np.hstack([verts, np.ones((verts.shape[0], 1))])  # (N, 4)
        verts_trans = (transform @ verts_hom.T).T[:, :3]

        meshes.append(trimesh.Trimesh(vertices=verts_trans, faces=part['faces']))
    log.info("[......     ] Constructed STEP model from node map.")

    for _i, part in enumerate(meshes):
        if not part.is_winding_consistent:
            part.invert()

    mesh = trimesh.util.concatenate(meshes)
    log.info("[.......    ] Mesh concatenated for global transformations.")

    # Apply scale: STEP is in meters, KiCad footprints are in mm
    mesh.apply_scale(1000)

    # Get and apply KiCad model transform (offset, scale, rotate)
    model_transform = get_model_transform(unfiltered_s_expr_list)
    mesh.apply_transform(model_transform)
    log.info("[.........  ] Applied KiCad model transformations.")

    polys = []
    for face in mesh.faces:
        pts_3d = mesh.vertices[face]
        pts_2d = pts_3d[:, :2] # Drop Z
        #pts_2d[:, 0] *= -1  # Invert X
        pts_2d[:, 1] *= -1  # Invert Y
        #pts_2d = pts_3d[:, [0, 2]]  # Drop Y, keep X and Z
        poly = Polygon(pts_2d)
        if poly.is_valid and poly.area > 1e-12:
            polys.append(poly)

    shadow_2d = unary_union(polys)
    log.info("[.......... ] Created 2D projection.")

    fab_fp_lines = polygon_to_fp_lines(shadow_2d, layer=fab_layer, width=0.12)
    filtered_s_expr = copy.deepcopy(unfiltered_s_expr_list)

    # Calculate bounding box dimensions and center from the 2D projection
    bounds = shadow_2d.bounds  # (minx, miny, maxx, maxy)
    projection_width = bounds[2] - bounds[0]
    projection_height = bounds[3] - bounds[1]
    projection_center = [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2]
    hull_shortest_side = min(projection_width, projection_height)

    DRAW_PRIMITIVES = {'fp_line', 'fp_arc', 'fp_circle', 'fp_poly', 'fp_text', 'fp_rect'}

    last_draw_idx = -1
    last_embedded_idx = -1
    for idx, item in enumerate(filtered_s_expr):
        if isinstance(item, list) and item:
            if item[0] in DRAW_PRIMITIVES:
                last_draw_idx = idx
            elif item[0] in ('embedded_files', 'model'):
                last_embedded_idx = idx

    if last_draw_idx != -1:
        insert_idx = last_draw_idx + 1
    elif last_embedded_idx != -1:
        insert_idx = last_embedded_idx + 1
    else:
        insert_idx = len(filtered_s_expr)  # Insert at end if nothing else

    for fp_line in fab_fp_lines:
        filtered_s_expr.insert(insert_idx, fp_line)
        insert_idx += 1

    # Add reference text to the appropriate fab layer at the center of the projection
    log.info(f"[........... ] Adding reference text to {fab_layer} layer.")
    filtered_s_expr = add_reference_text_to_fab(filtered_s_expr, projection_center, hull_shortest_side, fab_layer)

    log.info("[ooooooooooo] Done!")
    return filtered_s_expr
