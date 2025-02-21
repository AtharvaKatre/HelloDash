"""
This is a pre-processing step that generates Plotly figure templates for standard Bootstrap/Bootswatch themes.
It only needs to run periodically - quarterly? depending on the frequency of changes in the Bootstrap themes.

For now it creates a pickle file - todo - find a better place to store this data

The  file is loaded into dcc.Store in the main layout so it is accessible to all app pages

"""

import pathlib
import pickle
import plotly.graph_objects as go
import copy
import plotly.io as pio
import numpy as np

import util

PATH = pathlib.Path(__file__).parent
DATA_PATH = PATH.joinpath(".../data").resolve()


"""
=====================================================================
_colors.py
"""


try:
    import spectra
    from colormath.density import auto_density
    from colormath.color_objects import LabColor as LabColor
    from colormath.color_diff import delta_e_cie1994
except ImportError:
    msg = (
        "Generating plotly.py figure templates from bootstrap theme files requires\n"
        "the optional spectra package, which can be installed using pip...\n"
        "    $ pip install spectra\n"
        "or conda...\n"
        "    $ conda install -c conda-forge spectra"
    )
    raise ValueError(msg)


white = spectra.lab(100, 0, 0)
black = spectra.lab(0, 0, 0)


def to_colormath(spectra_color):
    lab_values = spectra.html(spectra_color.hexcode).to("lab").values
    return LabColor(*lab_values)


def color_distance(clr1, clr2):
    return delta_e_cie1994(to_colormath(clr1), to_colormath(clr2))


# Distance matric
def color_distance_matrix(colors):
    return np.array(
        [
            [color_distance(c1, c2) for i, c1 in enumerate(colors)]
            for j, c2 in enumerate(colors)
        ],
        dtype="float32",
    )


def get_darkened_colors(colors, darkening_list):
    return [c.darken(d) for c, d in zip(colors, darkening_list)]


def best_darkening(c1, c2, c1_step=(1, 1), c2_step=(1, 1)):
    d = color_distance(c1, c2)
    d1 = color_distance(c1.darken(c1_step[1]), c2)
    dm1 = color_distance(c1.darken(c1_step[0]), c2)
    d2 = color_distance(c1, c2.darken(c2_step[1]))
    dm2 = color_distance(c1, c2.darken(c2_step[0]))

    # Return step with sign that increases distance most
    # Return 0 if either step lower distance
    return sorted(
        [
            (d, (0, 0)),
            (d1, (c1_step[1], 0)),
            (dm1, (c1_step[0], 0)),
            (d2, (0, c2_step[1])),
            (dm2, (0, c2_step[0])),
        ]
    )[-1]


def separate_colorway(html_colors):

    try:
        raw_colors = [
            spectra.rgb(*[c / 255 for c in to_rgb_tuple(clr)]) for clr in html_colors
        ]
    except ValueError:
        # Unable to parse colors as hex or rgb, return as-is
        return html_colors

    test_colors = [white] + raw_colors + [black]

    darkenings = list(np.zeros(len(test_colors)))
    threshold = 36

    max_shift = 16
    max_step = 16
    max_iterations = 4
    max_step_factor = 0.9

    iterations = 0
    distances = np.ones((len(html_colors) + 2, len(html_colors) + 2)) * np.nan

    while iterations < max_iterations:
        for i in range(len(test_colors) - 1):
            c1 = test_colors[i].darken(darkenings[i])
            for j in range(i + 1, len(test_colors)):
                c2 = test_colors[j].darken(darkenings[j])
                distance = color_distance(c1, c2)
                distances[i, j] = distance

                # When comparing to black and white,
                # skip if at least threshold units away
                if distance > threshold:
                    continue

                # Compute max step based on how close colors are
                this_step = max_step * ((100 - distance) / 100) ** 2

                # Clamp max steps based on how close we are to max shift allowances
                c1_step_up = max(0, min(this_step, max_shift - darkenings[i]))
                c2_step_up = max(0, min(this_step, max_shift - darkenings[j]))
                c1_step_down = min(0, max(-this_step, -darkenings[i] - max_shift))
                c2_step_down = min(0, max(-this_step, -darkenings[j] - max_shift))

                # Compute best way to lighten or darken ONE of the colors (not both)
                distance, (delta1, delta2) = best_darkening(
                    c1,
                    c2,
                    c1_step=(c1_step_down, c1_step_up),
                    c2_step=(c2_step_down, c2_step_up),
                )
                distances[i, j] = distance

                darkenings[i] += delta1
                darkenings[j] += delta2

        iterations += 1
        max_step *= max_step_factor

    result = [clr.hexcode for clr in get_darkened_colors(test_colors, darkenings)[1:-1]]

    return result


def hex_to_rgb(clr):
    clr = clr.lstrip("#")
    if len(clr) == 3:
        clr = "".join(c[0] * 2 for c in clr)
    return tuple(int(clr[i : i + 2], 16) for i in (0, 2, 4))


def to_rgb_tuple(color):
    from plotly.colors import unlabel_rgb

    if isinstance(color, tuple):
        pass
    elif color.startswith("#"):
        color = hex_to_rgb(color)
    else:
        color = unlabel_rgb(color)

    return tuple(int(c) for c in color)


def make_grid_color(bg_color, font_color, weight=0.1):
    bg_color = to_rgb_tuple(bg_color)
    font_color = to_rgb_tuple(font_color)

    s_bg_color = spectra.rgb(*[c / 255 for c in bg_color])
    s_font_color = spectra.rgb(*[c / 255 for c in font_color])
    return s_bg_color.blend(s_font_color, weight).hexcode


def maybe_blend(base_color, overlay_color):
    """
    Try to blend semi transparent overlay color on opaque
    base color. Return None if not successful
    """
    import re

    try:
        bc = spectra.html(base_color).to("rgb")
    except ValueError:
        return None

    try:
        # If overlay color is hex code or named color, it's
        # opaque, return as is
        return spectra.html(overlay_color).hexcode
    except ValueError:
        # Otherwise, it might be rgba
        pass

    rgba_match = re.match(r"rgba\(([^,]+),([^,]+),([^,]+),([^,]+)\)", overlay_color)
    if rgba_match is None:
        return None

    r, g, b, a = [float(n) for n in rgba_match.groups()]
    overlay_rgb = spectra.rgb(r / 255, g / 255, b / 255)
    blended = overlay_rgb.blend(bc, 1 - a)
    return blended.hexcode


"""
=====================================================================
From /templates/dbc.py
"""


def parse_rules_from_bootstrap_css(css_text):
    import tinycss2

    tinycss_parsed = tinycss2.parse_stylesheet(css_text)

    # Build dict from css selectors to dict of css prop-values
    rule_props = {}
    for token in tinycss_parsed:
        if token.type != "qualified-rule":
            continue
        rule = token
        selector_str = "".join([t.serialize() for t in rule.prelude])
        selectors = tuple(s.strip() for s in selector_str.split(","))
        property_strings = [
            entry
            for entry in "".join([c.serialize().strip() for c in rule.content]).split(
                ";"
            )
            if entry
        ]

        property_pairs = [prop_str.split(":") for prop_str in property_strings]
        for selector in selectors:
            for prop_pair in property_pairs:
                if len(prop_pair) != 2:
                    continue
                rule_props.setdefault(selector, {})
                prop_key = prop_pair[0]
                prop_value = prop_pair[1].replace("!important", "").strip()
                rule_props[selector][prop_key] = prop_value

    return rule_props


# Get title font color
def get_font(rule_props):
    color = "#000"
    family = "sans-serif"

    for el in ["html", "body", "h1"]:
        color = rule_props.get(el, {}).get("color", color)
        family = rule_props.get(el, {}).get("font-family", family)

    return color, family


def get_role_colors(rule_props):
    # Initialize role_colors with default values
    role_colors = {
        "primary": "#007bff",
        "secondary": "#6c757d",
        "success": "#28a745",
        "info": "#17a2b8",
        "warning": "#ffc107",
        "danger": "#dc3545",
        "light": "#f8f9fa",
        "dark": "#343a40",
    }

    # Override with role colors for current theme
    for prop, val in rule_props[":root"].items():
        if prop.startswith("--"):
            maybe_color = prop.lstrip("-")
            if maybe_color in role_colors:
                role_colors[maybe_color] = val

    return role_colors


def build_plotly_template_from_bootstrap_css_text(css_text):

    # Parse css text
    rule_props = parse_rules_from_bootstrap_css(css_text)

    # Initialize role_colors with default values
    role_colors = get_role_colors(rule_props)

    # Get font info
    font_color, font_family = get_font(rule_props)

    # Get background color
    plot_bgcolor = rule_props["body"].get("background-color", "#fff")
    paper_bgcolor = rule_props[".card"].get("background-color", plot_bgcolor)

    blended = maybe_blend(plot_bgcolor, paper_bgcolor)
    if blended is None:
        # Can't blend, use background color for everything
        paper_bgcolor = plot_bgcolor
    else:
        paper_bgcolor = blended

    # Build colorway
    colorway_roles = [
        "primary",
        "danger",
        "success",
        "warning",
        "info",
    ]
    colorway = [role_colors[r] for r in colorway_roles]
    colorway = separate_colorway(colorway)
    print("colorway", colorway)

    # Build grid color
    gridcolor = make_grid_color(plot_bgcolor, font_color, 0.08)

    # Make template
    template = copy.deepcopy(pio.templates["plotly_dark"])

    layout = template.layout
    layout.colorway = colorway
    layout.piecolorway = colorway
    layout.paper_bgcolor = paper_bgcolor
    layout.plot_bgcolor = plot_bgcolor
    layout.font.color = font_color
    layout.font.family = font_family
    layout.xaxis.gridcolor = gridcolor
    layout.yaxis.gridcolor = gridcolor
    layout.xaxis.gridwidth = 0.5
    layout.yaxis.gridwidth = 0.5
    layout.xaxis.zerolinecolor = gridcolor
    layout.yaxis.zerolinecolor = gridcolor
    layout.margin = dict(l=0, r=0, b=0)

    template.data.scatter = (go.Scatter(marker_line_color=plot_bgcolor),)
    template.data.scattergl = (go.Scattergl(marker_line_color=plot_bgcolor),)

    return template


def try_build_plotly_template_from_bootstrap_css_path(css_url):
    import requests
    from urllib.parse import urlparse

    parse_result = urlparse(css_url)
    if parse_result.scheme:
        # URL
        response = requests.get(css_url)
        if response.status_code != 200:
            return None
        css_text = response.content.decode("utf8")
    elif parse_result.path:
        # Local file
        with open(parse_result.path, "rt") as f:
            css_text = f.read()

    return build_plotly_template_from_bootstrap_css_text(css_text)


"""
==========================================================
Generate Templates
"""


def generate_template(theme):
    return try_build_plotly_template_from_bootstrap_css_path(theme)


dbc_templates = {}
for theme in util.dbc_themes_url.values():
    dbc_templates[theme] = generate_template(theme)


with open(DATA_PATH.joinpath("dbc_graph_templates"), "wb") as handle:
    pickle.dump(dbc_templates, handle, protocol=pickle.HIGHEST_PROTOCOL)

print("templates saved to /data/dbc_graph_templates")
