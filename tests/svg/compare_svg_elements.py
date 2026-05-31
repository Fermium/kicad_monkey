"""Compare SVG elements between Python renderer and KiCad CLI reference output.

This utility compares SVG elements by type and position:
- Geometry: paths, polylines, polygons, rectangles, circles, ellipses, arcs
- Text: content, position, font attributes
- Coordinates: with configurable tolerance (default 0.01px)

Color comparison is deferred (theming will affect colors).

Usage:
    from compare_svg_elements import compare_svgs

    result = compare_svgs(
        reference_svg="symbol_kicad.svg",
        python_svg="symbol_python.svg",
        position_tolerance=0.01
    )

    if result.passed:
        print("All elements match!")
    else:
        for diff in result.differences:
            print(f"  {diff}")
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

log = logging.getLogger(__name__)

# SVG namespace
SVG_NS = "{http://www.w3.org/2000/svg}"


@dataclass
class SvgElement:
    """Parsed SVG element with normalized attributes."""

    tag: str  # line, rect, polyline, path, text, circle, ellipse
    attrs: dict  # Normalized attributes
    text: str = ""  # Text content for <text> elements
    line_num: int = 0  # Approximate line number in SVG for debugging
    is_stroked_text: bool = False  # True if this path is part of stroked text rendering
    is_svg_arc: bool = False  # True if path uses SVG arc command (A/a)

    def __repr__(self):
        pos = ""
        if "x" in self.attrs and "y" in self.attrs:
            pos = f" at ({self.attrs['x']}, {self.attrs['y']})"
        elif "x1" in self.attrs and "y1" in self.attrs:
            pos = f" at ({self.attrs['x1']}, {self.attrs['y1']})"
        return f"SvgElement({self.tag}{pos})"

    def position_key(self) -> tuple:
        """Get a position key for matching elements."""
        if self.tag == "text":
            return (self.tag, round(float(self.attrs.get("x", 0)), 1),
                    round(float(self.attrs.get("y", 0)), 1))
        elif self.tag == "line":
            return (self.tag,
                    round(float(self.attrs.get("x1", 0)), 1),
                    round(float(self.attrs.get("y1", 0)), 1),
                    round(float(self.attrs.get("x2", 0)), 1),
                    round(float(self.attrs.get("y2", 0)), 1))
        elif self.tag == "circle":
            return (self.tag,
                    round(float(self.attrs.get("cx", 0)), 1),
                    round(float(self.attrs.get("cy", 0)), 1))
        elif self.tag == "rect":
            return (self.tag,
                    round(float(self.attrs.get("x", 0)), 1),
                    round(float(self.attrs.get("y", 0)), 1))
        elif self.tag == "path":
            # Use first point in path
            d = self.attrs.get("d", "")
            match = re.search(r'M\s*([\d.-]+)[,\s]*([\d.-]+)', d)
            if match:
                return (self.tag, round(float(match.group(1)), 1),
                        round(float(match.group(2)), 1))
        elif self.tag == "polyline":
            points = self.attrs.get("points", "")
            coords = re.findall(r'[\d.-]+', points)
            if len(coords) >= 2:
                return (self.tag, round(float(coords[0]), 1),
                        round(float(coords[1]), 1))
        return (self.tag,)


@dataclass
class ElementDiff:
    """A difference between two SVG elements."""

    element_type: str
    attribute: str
    reference_value: str
    python_value: str
    position: str = ""  # Position hint for locating the element

    def __str__(self):
        pos = f" at {self.position}" if self.position else ""
        return f"[{self.element_type}]{pos} {self.attribute}: ref='{self.reference_value}' vs python='{self.python_value}'"


@dataclass
class ComparisonResult:
    """Result of comparing two SVG files."""

    passed: bool = True
    differences: list[ElementDiff] = field(default_factory=list)
    reference_only: list[SvgElement] = field(default_factory=list)
    python_only: list[SvgElement] = field(default_factory=list)
    matched_count: int = 0

    # Metrics
    total_reference_elements: int = 0
    total_python_elements: int = 0

    def add_diff(self, diff: ElementDiff):
        self.differences.append(diff)
        self.passed = False

    def summary(self) -> str:
        lines = []
        lines.append(f"Comparison: {'PASSED' if self.passed else 'FAILED'}")
        lines.append(f"  Reference elements: {self.total_reference_elements}")
        lines.append(f"  Python elements: {self.total_python_elements}")
        lines.append(f"  Matched: {self.matched_count}")
        lines.append(f"  Reference only: {len(self.reference_only)}")
        lines.append(f"  Python only: {len(self.python_only)}")
        lines.append(f"  Attribute differences: {len(self.differences)}")
        return "\n".join(lines)


def parse_svg_elements(svg_path: Path) -> list[SvgElement]:
    """Parse SVG file and extract all graphical elements.

    Returns:
        List of SvgElement objects with is_stroked_text flag set for paths
        inside <g class="stroked-text"> groups.
    """
    ET.register_namespace('', 'http://www.w3.org/2000/svg')

    content = svg_path.read_text(encoding='utf-8')
    root = ET.fromstring(content)

    elements = []

    # Tags we care about for geometry comparison
    GEOMETRY_TAGS = {'line', 'rect', 'circle', 'ellipse', 'path',
                     'polyline', 'polygon', 'text'}

    def process_element(elem, depth=0, in_stroked_text=False):
        """Recursively process SVG elements."""
        tag = elem.tag.replace(SVG_NS, '')

        # Check if this is a stroked-text group
        classes = elem.attrib.get("class", "").split()
        is_stroked_text_group = (
            tag == "g" and
            "stroked-text" in classes
        )

        if tag in GEOMETRY_TAGS:
            attrs = normalize_attrs(dict(elem.attrib))
            text_content = ""

            if tag == "text":
                # Get text content (may be in element or child tspan)
                text_content = elem.text or ""
                for child in elem:
                    if child.tag.replace(SVG_NS, '') == "tspan":
                        text_content += child.text or ""

            # Detect SVG arc commands in path data
            is_arc = False
            if tag == "path":
                d = elem.attrib.get("d", "")
                # Check for arc command (A or a)
                if re.search(r'[Aa]\s*[\d.-]+', d):
                    is_arc = True

            elements.append(SvgElement(
                tag=tag,
                attrs=attrs,
                text=text_content.strip(),
                is_stroked_text=in_stroked_text or is_stroked_text_group,
                is_svg_arc=is_arc
            ))

        # Recurse into children, tracking stroked-text context
        for child in elem:
            process_element(
                child,
                depth + 1,
                in_stroked_text=in_stroked_text or is_stroked_text_group
            )

    process_element(root)
    return elements


def normalize_attrs(attrs: dict) -> dict:
    """Normalize SVG attributes for comparison.

    - Skip style/color attributes (theming)
    - Keep geometry attributes
    - Normalize numeric precision
    """
    result = {}

    # Attributes to skip (color/style related - will be compared later)
    SKIP_ATTRS = {'stroke', 'fill', 'stroke-width', 'stroke-linecap',
                  'stroke-linejoin', 'style', 'class', 'id', 'opacity',
                  'fill-opacity', 'stroke-opacity'}

    for key, value in attrs.items():
        if key in SKIP_ATTRS:
            continue

        # Normalize numeric values
        if key in ('x', 'y', 'x1', 'y1', 'x2', 'y2', 'cx', 'cy',
                   'width', 'height', 'r', 'rx', 'ry'):
            try:
                # Keep full precision for comparison
                value = float(value.replace('px', '').replace('mm', ''))
            except (ValueError, AttributeError):
                pass

        # Normalize font-size
        if key == 'font-size':
            try:
                value = float(value.replace('px', '').replace('pt', ''))
            except (ValueError, AttributeError):
                pass

        # Normalize path data
        if key == 'd':
            value = normalize_path(value)

        # Normalize points
        if key == 'points':
            value = normalize_points(value)

        result[key] = value

    return result


def normalize_path(path_str: str) -> str:
    """Normalize SVG path data for comparison."""
    # Remove extra whitespace
    path_str = re.sub(r'\s+', ' ', path_str.strip())
    # Normalize command spacing
    path_str = re.sub(r'([MLHVCSQTAZmlhvcsqtaz])\s*', r'\1 ', path_str)
    return path_str


def normalize_points(points_str: str) -> list[tuple[float, float]]:
    """Normalize polyline/polygon points to list of (x, y) tuples."""
    coords = re.findall(r'[\d.-]+', points_str)
    points = []
    for i in range(0, len(coords) - 1, 2):
        try:
            points.append((float(coords[i]), float(coords[i + 1])))
        except (ValueError, IndexError):
            pass
    return points


def extract_path_coordinates(d: str) -> list[tuple[float, float]]:
    """Extract actual coordinate points from SVG path data.

    Properly handles different SVG path commands:
    - M/m (moveto): 2 coords (x, y)
    - L/l (lineto): 2 coords (x, y)
    - H/h (horizontal): 1 coord (x)
    - V/v (vertical): 1 coord (y)
    - A/a (arc): 7 values (rx, ry, x-rotation, large-arc, sweep, x, y) - only last 2 are coords
    - Z/z (close): no coords

    Returns:
        List of (x, y) coordinate tuples from the path.
    """
    coords = []

    # Tokenize path data
    # Split on commands while keeping the command letter
    tokens = re.split(r'([MLHVCSQTAZmlhvcsqtaz])', d)
    tokens = [t.strip() for t in tokens if t.strip()]

    current_x, current_y = 0.0, 0.0

    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token in 'Mm':
            # Moveto: x y
            if i + 1 < len(tokens):
                nums = re.findall(r'-?[\d.]+', tokens[i + 1])
                for j in range(0, len(nums) - 1, 2):
                    try:
                        x, y = float(nums[j]), float(nums[j + 1])
                        if token == 'm' and coords:  # relative
                            x += current_x
                            y += current_y
                        coords.append((x, y))
                        current_x, current_y = x, y
                    except (ValueError, IndexError):
                        pass
                i += 2
            else:
                i += 1

        elif token in 'Ll':
            # Lineto: x y
            if i + 1 < len(tokens):
                nums = re.findall(r'-?[\d.]+', tokens[i + 1])
                for j in range(0, len(nums) - 1, 2):
                    try:
                        x, y = float(nums[j]), float(nums[j + 1])
                        if token == 'l':  # relative
                            x += current_x
                            y += current_y
                        coords.append((x, y))
                        current_x, current_y = x, y
                    except (ValueError, IndexError):
                        pass
                i += 2
            else:
                i += 1

        elif token in 'Hh':
            # Horizontal: x
            if i + 1 < len(tokens):
                nums = re.findall(r'-?[\d.]+', tokens[i + 1])
                for num in nums:
                    try:
                        x = float(num)
                        if token == 'h':  # relative
                            x += current_x
                        coords.append((x, current_y))
                        current_x = x
                    except ValueError:
                        pass
                i += 2
            else:
                i += 1

        elif token in 'Vv':
            # Vertical: y
            if i + 1 < len(tokens):
                nums = re.findall(r'-?[\d.]+', tokens[i + 1])
                for num in nums:
                    try:
                        y = float(num)
                        if token == 'v':  # relative
                            y += current_y
                        coords.append((current_x, y))
                        current_y = y
                    except ValueError:
                        pass
                i += 2
            else:
                i += 1

        elif token in 'Aa':
            # Arc: rx ry x-rotation large-arc sweep x y
            # Only the last two values (x, y) are actual coordinates
            if i + 1 < len(tokens):
                nums = re.findall(r'-?[\d.]+', tokens[i + 1])
                # Process arcs in groups of 7
                for j in range(0, len(nums) - 6, 7):
                    try:
                        x = float(nums[j + 5])
                        y = float(nums[j + 6])
                        if token == 'a':  # relative
                            x += current_x
                            y += current_y
                        coords.append((x, y))
                        current_x, current_y = x, y
                    except (ValueError, IndexError):
                        pass
                i += 2
            else:
                i += 1

        elif token in 'Zz':
            # Close path: no coordinates
            i += 1

        else:
            # Unknown command or coordinate data - try as coordinate pairs
            nums = re.findall(r'-?[\d.]+', token)
            for j in range(0, len(nums) - 1, 2):
                try:
                    x, y = float(nums[j]), float(nums[j + 1])
                    coords.append((x, y))
                    current_x, current_y = x, y
                except (ValueError, IndexError):
                    pass
            i += 1

    return coords


def coords_match(val1, val2, tolerance: float = 0.01) -> bool:
    """Compare two coordinate values with tolerance."""
    try:
        return abs(float(val1) - float(val2)) <= tolerance
    except (ValueError, TypeError):
        return str(val1) == str(val2)


def paths_match(path1: str, path2: str, tolerance: float = 0.01) -> bool:
    """Compare two SVG paths with coordinate tolerance.

    Properly handles different path formats:
    - Z close command vs explicit return to start
    - Different whitespace/formatting
    """
    # Use extract_path_coordinates for proper handling of SVG path commands
    coords1 = extract_path_coordinates(path1)
    coords2 = extract_path_coordinates(path2)

    # Handle closed paths: if one path uses Z close, the other might have explicit return
    # Check if paths would be equal if we remove the closing point from the longer one
    if len(coords1) != len(coords2):
        # Check if it's a closed path issue (one has explicit return, other uses Z)
        if len(coords1) > len(coords2) and len(coords1) > 0:
            # Check if last point of coords1 matches first point
            if (abs(coords1[-1][0] - coords1[0][0]) <= tolerance and
                abs(coords1[-1][1] - coords1[0][1]) <= tolerance):
                coords1 = coords1[:-1]  # Remove closing point
        elif len(coords2) > len(coords1) and len(coords2) > 0:
            # Check if last point of coords2 matches first point
            if (abs(coords2[-1][0] - coords2[0][0]) <= tolerance and
                abs(coords2[-1][1] - coords2[0][1]) <= tolerance):
                coords2 = coords2[:-1]  # Remove closing point

    if len(coords1) != len(coords2):
        return False

    for (x1, y1), (x2, y2) in zip(coords1, coords2):
        if abs(x1 - x2) > tolerance or abs(y1 - y2) > tolerance:
            return False

    return True


def points_match(points1: list, points2: list, tolerance: float = 0.01) -> bool:
    """Compare two point lists with coordinate tolerance."""
    if len(points1) != len(points2):
        return False

    for (x1, y1), (x2, y2) in zip(points1, points2):
        if abs(x1 - x2) > tolerance or abs(y1 - y2) > tolerance:
            return False

    return True


def find_matching_element(
    target: SvgElement,
    candidates: list[SvgElement],
    tolerance: float = 0.01
) -> SvgElement | None:
    """Find a matching element from candidates based on type and position."""
    for candidate in candidates:
        if candidate.tag != target.tag:
            continue

        # Match by position based on element type
        if target.tag == "line":
            if (coords_match(target.attrs.get("x1"), candidate.attrs.get("x1"), tolerance) and
                coords_match(target.attrs.get("y1"), candidate.attrs.get("y1"), tolerance) and
                coords_match(target.attrs.get("x2"), candidate.attrs.get("x2"), tolerance) and
                coords_match(target.attrs.get("y2"), candidate.attrs.get("y2"), tolerance)):
                return candidate

        elif target.tag == "rect":
            if (coords_match(target.attrs.get("x"), candidate.attrs.get("x"), tolerance) and
                coords_match(target.attrs.get("y"), candidate.attrs.get("y"), tolerance) and
                coords_match(target.attrs.get("width"), candidate.attrs.get("width"), tolerance) and
                coords_match(target.attrs.get("height"), candidate.attrs.get("height"), tolerance)):
                return candidate

        elif target.tag == "circle":
            if (coords_match(target.attrs.get("cx"), candidate.attrs.get("cx"), tolerance) and
                coords_match(target.attrs.get("cy"), candidate.attrs.get("cy"), tolerance) and
                coords_match(target.attrs.get("r"), candidate.attrs.get("r"), tolerance)):
                return candidate

        elif target.tag == "path":
            target_d = target.attrs.get("d", "")
            candidate_d = candidate.attrs.get("d", "")
            if paths_match(target_d, candidate_d, tolerance):
                return candidate

        elif target.tag == "polyline" or target.tag == "polygon":
            target_pts = target.attrs.get("points", [])
            candidate_pts = candidate.attrs.get("points", [])
            if points_match(target_pts, candidate_pts, tolerance):
                return candidate

        elif target.tag == "text":
            # Match text by position and content
            if (coords_match(target.attrs.get("x"), candidate.attrs.get("x"), tolerance) and
                coords_match(target.attrs.get("y"), candidate.attrs.get("y"), tolerance) and
                target.text == candidate.text):
                return candidate

        elif target.tag == "ellipse":
            if (coords_match(target.attrs.get("cx"), candidate.attrs.get("cx"), tolerance) and
                coords_match(target.attrs.get("cy"), candidate.attrs.get("cy"), tolerance) and
                coords_match(target.attrs.get("rx"), candidate.attrs.get("rx"), tolerance) and
                coords_match(target.attrs.get("ry"), candidate.attrs.get("ry"), tolerance)):
                return candidate

    return None


def compare_elements(
    ref_elem: SvgElement,
    py_elem: SvgElement,
    tolerance: float = 0.01
) -> list[ElementDiff]:
    """Compare two matched elements and return differences."""
    diffs = []

    # Compare all geometry attributes
    all_attrs = set(ref_elem.attrs.keys()) | set(py_elem.attrs.keys())

    for attr in all_attrs:
        ref_val = ref_elem.attrs.get(attr)
        py_val = py_elem.attrs.get(attr)

        if ref_val is None or py_val is None:
            if ref_val != py_val:
                diffs.append(ElementDiff(
                    element_type=ref_elem.tag,
                    attribute=attr,
                    reference_value=str(ref_val) if ref_val else "(missing)",
                    python_value=str(py_val) if py_val else "(missing)",
                    position=str(ref_elem.position_key())
                ))
            continue

        # Special handling for paths
        if attr == "d":
            if not paths_match(ref_val, py_val, tolerance):
                diffs.append(ElementDiff(
                    element_type=ref_elem.tag,
                    attribute=attr,
                    reference_value=ref_val[:50] + "..." if len(ref_val) > 50 else ref_val,
                    python_value=py_val[:50] + "..." if len(py_val) > 50 else py_val,
                    position=str(ref_elem.position_key())
                ))
            continue

        # Special handling for points
        if attr == "points":
            if not points_match(ref_val, py_val, tolerance):
                diffs.append(ElementDiff(
                    element_type=ref_elem.tag,
                    attribute=attr,
                    reference_value=str(ref_val)[:50],
                    python_value=str(py_val)[:50],
                    position=str(ref_elem.position_key())
                ))
            continue

        # Numeric comparison
        if isinstance(ref_val, (int, float)) and isinstance(py_val, (int, float)):
            if not coords_match(ref_val, py_val, tolerance):
                diffs.append(ElementDiff(
                    element_type=ref_elem.tag,
                    attribute=attr,
                    reference_value=str(ref_val),
                    python_value=str(py_val),
                    position=str(ref_elem.position_key())
                ))
        elif str(ref_val) != str(py_val):
            diffs.append(ElementDiff(
                element_type=ref_elem.tag,
                attribute=attr,
                reference_value=str(ref_val),
                python_value=str(py_val),
                position=str(ref_elem.position_key())
            ))

    # Compare text content
    if ref_elem.tag == "text" and ref_elem.text != py_elem.text:
        diffs.append(ElementDiff(
            element_type="text",
            attribute="text_content",
            reference_value=ref_elem.text,
            python_value=py_elem.text,
            position=str(ref_elem.position_key())
        ))

    return diffs


def compute_centroid(elements: list[SvgElement], exclude_text: bool = False) -> tuple[float, float]:
    """Compute the centroid of all element positions.

    Args:
        elements: List of SVG elements
        exclude_text: If True, exclude text elements AND stroked text paths from centroid calculation.
                      Useful when text positioning differs between renderers.
    """
    if not elements:
        return (0.0, 0.0)

    all_x = []
    all_y = []

    for elem in elements:
        # Skip text and stroked text paths if requested
        if exclude_text:
            if elem.tag == "text":
                continue
            if elem.is_stroked_text:
                continue

        if elem.tag == "path":
            d = elem.attrs.get("d", "")
            match = re.search(r'M\s*([\d.-]+)[,\s]*([\d.-]+)', d)
            if match:
                all_x.append(float(match.group(1)))
                all_y.append(float(match.group(2)))
        elif elem.tag == "line":
            all_x.append(float(elem.attrs.get("x1", 0)))
            all_y.append(float(elem.attrs.get("y1", 0)))
        elif elem.tag in ("rect", "text"):
            all_x.append(float(elem.attrs.get("x", 0)))
            all_y.append(float(elem.attrs.get("y", 0)))
        elif elem.tag in ("circle", "ellipse"):
            all_x.append(float(elem.attrs.get("cx", 0)))
            all_y.append(float(elem.attrs.get("cy", 0)))

    if not all_x:
        return (0.0, 0.0)

    return (sum(all_x) / len(all_x), sum(all_y) / len(all_y))


def compute_bounds(elements: list[SvgElement], exclude_text: bool = False, exclude_arcs: bool = False) -> tuple[float, float, float, float]:
    """Compute the bounding box (min_x, min_y, max_x, max_y) of all element positions.

    Args:
        elements: List of SVG elements
        exclude_text: If True, exclude text elements AND stroked text paths from bounds calculation.
        exclude_arcs: If True, exclude SVG arc paths from bounds calculation.

    Returns:
        Tuple of (min_x, min_y, max_x, max_y)
    """
    if not elements:
        return (0.0, 0.0, 0.0, 0.0)

    all_x = []
    all_y = []

    for elem in elements:
        # Skip text and stroked text paths if requested
        if exclude_text:
            if elem.tag == "text":
                continue
            if elem.is_stroked_text:
                continue

        # Skip SVG arc paths if requested
        if exclude_arcs and elem.is_svg_arc:
            continue

        if elem.tag == "path":
            d = elem.attrs.get("d", "")
            # Extract coordinates from path, properly handling different commands
            # SVG arc commands (A/a) have format: A rx ry x-rotation large-arc sweep x y
            # We need to skip the arc parameters and only get actual coordinates
            coords = extract_path_coordinates(d)
            for x, y in coords:
                all_x.append(x)
                all_y.append(y)
        elif elem.tag == "line":
            for attr in ("x1", "x2"):
                if attr in elem.attrs:
                    try:
                        all_x.append(float(elem.attrs[attr]))
                    except (ValueError, TypeError):
                        pass
            for attr in ("y1", "y2"):
                if attr in elem.attrs:
                    try:
                        all_y.append(float(elem.attrs[attr]))
                    except (ValueError, TypeError):
                        pass
        elif elem.tag in ("rect", "text"):
            if "x" in elem.attrs:
                try:
                    all_x.append(float(elem.attrs["x"]))
                except (ValueError, TypeError):
                    pass
            if "y" in elem.attrs:
                try:
                    all_y.append(float(elem.attrs["y"]))
                except (ValueError, TypeError):
                    pass
        elif elem.tag in ("circle", "ellipse"):
            if "cx" in elem.attrs:
                try:
                    all_x.append(float(elem.attrs["cx"]))
                except (ValueError, TypeError):
                    pass
            if "cy" in elem.attrs:
                try:
                    all_y.append(float(elem.attrs["cy"]))
                except (ValueError, TypeError):
                    pass

    if not all_x or not all_y:
        return (0.0, 0.0, 0.0, 0.0)

    return (min(all_x), min(all_y), max(all_x), max(all_y))


def normalize_coordinates(
    elements: list[SvgElement],
    offset_x: float,
    offset_y: float
) -> list[SvgElement]:
    """Apply coordinate offset to normalize element positions."""
    normalized = []

    for elem in elements:
        new_attrs = dict(elem.attrs)

        # Normalize based on element type
        if elem.tag == "path":
            d = elem.attrs.get("d", "")
            # Parse path and shift coordinates
            # Extract all numbers from the path
            nums = re.findall(r'-?[\d.]+', d)
            new_nums = []
            for i, n in enumerate(nums):
                try:
                    val = float(n)
                    if i % 2 == 0:  # X coordinate
                        val += offset_x
                    else:  # Y coordinate
                        val += offset_y
                    new_nums.append(val)
                except ValueError:
                    new_nums.append(float(n) if n else 0.0)

            # Rebuild path string - simple M/L format
            if new_nums and len(new_nums) >= 2:
                new_d = f"M {new_nums[0]:.4f} {new_nums[1]:.4f}"
                for i in range(2, len(new_nums), 2):
                    if i + 1 < len(new_nums):
                        new_d += f" L {new_nums[i]:.4f} {new_nums[i+1]:.4f}"
                new_attrs["d"] = new_d
            else:
                new_attrs["d"] = d

        elif elem.tag == "line":
            for attr in ("x1", "x2"):
                if attr in new_attrs:
                    new_attrs[attr] = float(new_attrs[attr]) + offset_x
            for attr in ("y1", "y2"):
                if attr in new_attrs:
                    new_attrs[attr] = float(new_attrs[attr]) + offset_y

        elif elem.tag in ("rect", "text"):
            if "x" in new_attrs:
                new_attrs["x"] = float(new_attrs["x"]) + offset_x
            if "y" in new_attrs:
                new_attrs["y"] = float(new_attrs["y"]) + offset_y

        elif elem.tag in ("circle", "ellipse"):
            if "cx" in new_attrs:
                new_attrs["cx"] = float(new_attrs["cx"]) + offset_x
            if "cy" in new_attrs:
                new_attrs["cy"] = float(new_attrs["cy"]) + offset_y

        elif elem.tag == "polyline":
            points = elem.attrs.get("points", [])
            if isinstance(points, list):
                new_points = [(x + offset_x, y + offset_y) for x, y in points]
                new_attrs["points"] = new_points

        normalized.append(SvgElement(
            tag=elem.tag,
            attrs=new_attrs,
            text=elem.text,
            line_num=elem.line_num,
            is_stroked_text=elem.is_stroked_text,
            is_svg_arc=elem.is_svg_arc
        ))

    return normalized


def compare_svgs(
    reference_svg_path: Path,
    python_svg_path: Path,
    position_tolerance: float = 0.01,
    normalize_positions: bool = True,
    ignore_text: bool = False,
    ignore_arcs: bool = False
) -> ComparisonResult:
    """Compare two SVG files element by element.

    Args:
        reference_svg_path: Path to KiCad CLI reference SVG
        python_svg_path: Path to Python-generated SVG
        position_tolerance: Tolerance for coordinate comparisons (default 0.01px)
        normalize_positions: If True, normalize both SVGs to same centroid before comparison
        ignore_text: If True, exclude text elements and stroked-text paths from pass/fail
                     determination. Text differences are logged but don't fail the comparison.
                     Useful when KiCad CLI has different text positioning than Python.
        ignore_arcs: If True, exclude SVG arc paths (A command) and long polyline paths
                     from pass/fail determination. KiCad CLI uses SVG arc commands while
                     Python approximates arcs with polylines.

    Returns:
        ComparisonResult with matched elements, differences, and pass/fail status
    """
    reference_svg_path = Path(reference_svg_path)
    python_svg_path = Path(python_svg_path)

    if not reference_svg_path.exists():
        raise FileNotFoundError(f"Reference SVG not found: {reference_svg_path}")
    if not python_svg_path.exists():
        raise FileNotFoundError(f"Python SVG not found: {python_svg_path}")

    result = ComparisonResult()

    # Parse both SVGs
    ref_elements = parse_svg_elements(reference_svg_path)
    py_elements = parse_svg_elements(python_svg_path)

    result.total_reference_elements = len(ref_elements)
    result.total_python_elements = len(py_elements)

    log.info(f"Reference SVG: {len(ref_elements)} elements")
    log.info(f"Python SVG: {len(py_elements)} elements")

    # Normalize coordinates using bounding box alignment
    # Shift both SVGs so their min_x and min_y become 0
    # This handles different coordinate origins between renderers
    if normalize_positions and ref_elements and py_elements:
        # Compute bounds excluding text (text positioning may differ)
        # Also exclude arcs when ignore_arcs is True (arc representations differ between renderers)
        ref_bounds = compute_bounds(ref_elements, exclude_text=True, exclude_arcs=ignore_arcs)
        py_bounds = compute_bounds(py_elements, exclude_text=True, exclude_arcs=ignore_arcs)

        # Shift both to origin (0, 0)
        ref_offset_x = -ref_bounds[0]
        ref_offset_y = -ref_bounds[1]
        py_offset_x = -py_bounds[0]
        py_offset_y = -py_bounds[1]

        log.info(f"Reference bounds: min=({ref_bounds[0]:.4f}, {ref_bounds[1]:.4f}), max=({ref_bounds[2]:.4f}, {ref_bounds[3]:.4f})")
        log.info(f"Python bounds: min=({py_bounds[0]:.4f}, {py_bounds[1]:.4f}), max=({py_bounds[2]:.4f}, {py_bounds[3]:.4f})")

        # Normalize both to start at (0, 0)
        ref_elements = normalize_coordinates(ref_elements, ref_offset_x, ref_offset_y)
        py_elements = normalize_coordinates(py_elements, py_offset_x, py_offset_y)

    # Helper to check if element is text-related
    def is_text_element(elem: SvgElement) -> bool:
        return elem.tag == "text" or elem.is_stroked_text

    # Helper to check if element is an arc (SVG arc or polyline approximation)
    def is_arc_element(elem: SvgElement) -> bool:
        if elem.is_svg_arc:
            return True
        # Detect polyline arc approximations (many coordinates, not stroked text)
        if elem.tag == "path" and not elem.is_stroked_text:
            d = elem.attrs.get("d", "")
            nums = re.findall(r'-?[\d.]+', str(d))
            # If path has > 20 numbers and no stroked text, likely an arc approximation
            if len(nums) > 20:
                return True
        return False

    # Track which Python elements have been matched
    matched_py_indices = set()

    # Match reference elements to Python elements
    for ref_elem in ref_elements:
        py_match = find_matching_element(ref_elem, py_elements, position_tolerance)

        if py_match:
            # Found a match - compare attributes
            matched_py_indices.add(py_elements.index(py_match))
            result.matched_count += 1

            diffs = compare_elements(ref_elem, py_match, position_tolerance)
            for diff in diffs:
                result.add_diff(diff)
        else:
            # No match found - element only in reference
            result.reference_only.append(ref_elem)
            # Only fail for non-text elements when ignore_text is True
            # Only fail for non-arc elements when ignore_arcs is True
            should_fail = True
            if ignore_text and is_text_element(ref_elem):
                should_fail = False
            if ignore_arcs and is_arc_element(ref_elem):
                should_fail = False
            if should_fail:
                result.passed = False

    # Find Python-only elements
    for i, py_elem in enumerate(py_elements):
        if i not in matched_py_indices:
            result.python_only.append(py_elem)
            # Only fail for non-text elements when ignore_text is True
            # Only fail for non-arc elements when ignore_arcs is True
            should_fail = True
            if ignore_text and is_text_element(py_elem):
                should_fail = False
            if ignore_arcs and is_arc_element(py_elem):
                should_fail = False
            if should_fail:
                result.passed = False

    return result


def create_overlay_diff(
    reference_svg: Path,
    python_svg: Path,
    output_svg: Path,
    ref_color: str = "#0000FF",  # Blue for reference (KiCad CLI)
    py_color: str = "#FF0000",   # Red for Python
    opacity: float = 0.5,
) -> Path:
    """Create visual overlay diff between reference and Python SVG.

    Uses the same color scheme as Altium L5:
    - Blue (#0000FF) for reference (KiCad CLI)
    - Red (#FF0000) for Python generated
    - Purple/Magenta where they overlap (matching)

    Args:
        reference_svg: Path to KiCad CLI reference SVG
        python_svg: Path to Python generated SVG
        output_svg: Path to write diff SVG
        ref_color: Color for reference elements (default blue)
        py_color: Color for Python elements (default red)
        opacity: Opacity for both layers (0-1)

    Returns:
        Path to generated diff SVG
    """
    reference_svg = Path(reference_svg)
    python_svg = Path(python_svg)
    output_svg = Path(output_svg)

    def load_svg_content(svg_path: Path) -> tuple[str, float, float, float, float]:
        """Load SVG and extract content and viewBox."""
        content = svg_path.read_text(encoding='utf-8')
        root = ET.fromstring(content)

        viewbox = root.get("viewBox")
        if viewbox:
            parts = viewbox.split()
            min_x = float(parts[0])
            min_y = float(parts[1])
            width = float(parts[2])
            height = float(parts[3])
        else:
            min_x = 0
            min_y = 0
            width = float(root.get("width", "100").replace("mm", "").replace("px", ""))
            height = float(root.get("height", "100").replace("mm", "").replace("px", ""))

        # Extract inner content
        match = re.search(r'<svg[^>]*>(.*)</svg>', content, re.DOTALL)
        inner_content = match.group(1) if match else ""

        return inner_content, min_x, min_y, width, height

    def colorize_content(content: str, color: str, opacity: float) -> str:
        """Transform SVG content to use specified color."""
        # Make backgrounds transparent
        def make_bg_transparent(match):
            rect = match.group(0)
            if 'stroke=' in rect:
                return rect
            return re.sub(r'fill="[^"]*"', 'fill="none"', rect)

        content = re.sub(r'<rect[^>]*fill="[^"]*"[^>]*/>', make_bg_transparent, content)

        # Replace stroke colors
        content = re.sub(r'stroke="[^"]*"', f'stroke="{color}"', content)

        # Replace fill colors (preserve "none")
        def replace_fill(match):
            if match.group(1).lower() == "none":
                return match.group(0)
            return f'fill="{color}"'

        content = re.sub(r'fill="([^"]*)"', replace_fill, content)

        # Remove opacity overrides
        content = re.sub(r'\s*fill-opacity="[^"]*"', '', content)
        content = re.sub(r'\s*stroke-opacity="[^"]*"', '', content)

        if opacity < 1.0:
            content = f'<g opacity="{opacity}">{content}</g>'

        return content

    # Load both SVGs
    ref_content, ref_min_x, ref_min_y, ref_w, ref_h = load_svg_content(reference_svg)
    py_content, py_min_x, py_min_y, py_w, py_h = load_svg_content(python_svg)

    # Use combined bounds
    min_x = min(ref_min_x, py_min_x)
    min_y = min(ref_min_y, py_min_y)
    max_x = max(ref_min_x + ref_w, py_min_x + py_w)
    max_y = max(ref_min_y + ref_h, py_min_y + py_h)
    width = max_x - min_x
    height = max_y - min_y

    # Colorize
    ref_colored = colorize_content(ref_content, ref_color, opacity)
    py_colored = colorize_content(py_content, py_color, opacity)

    # Build diff SVG
    diff_svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{width}mm" height="{height}mm"
     viewBox="{min_x} {min_y} {width} {height}"
     stroke-linecap="round" stroke-linejoin="round">
  <title>Overlay Diff: Python vs KiCad CLI</title>
  <desc>Blue=KiCad CLI (reference), Red=Python (generated). Purple=matching.</desc>

  <!-- Background -->
  <rect x="{min_x}" y="{min_y}" width="{width}" height="{height}" fill="white"/>

  <!-- Reference layer (KiCad CLI - blue) -->
  <g id="reference-layer">
    {ref_colored}
  </g>

  <!-- Python layer (red) -->
  <g id="python-layer">
    {py_colored}
  </g>
</svg>'''

    output_svg.parent.mkdir(parents=True, exist_ok=True)
    output_svg.write_text(diff_svg, encoding="utf-8")

    return output_svg


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) == 3:
        ref_path = Path(sys.argv[1])
        py_path = Path(sys.argv[2])

        result = compare_svgs(ref_path, py_path)
        print(result.summary())
        print()

        if result.reference_only:
            print(f"Reference only ({len(result.reference_only)}):")
            for elem in result.reference_only[:5]:
                print(f"  {elem}")

        if result.python_only:
            print(f"Python only ({len(result.python_only)}):")
            for elem in result.python_only[:5]:
                print(f"  {elem}")

        print()
        for diff in result.differences[:10]:
            print(f"  {diff}")

        if len(result.differences) > 10:
            print(f"  ... and {len(result.differences) - 10} more")
    else:
        print("Usage: python compare_svg_elements.py <reference.svg> <python.svg>")
