"""Small dependency-free Canvas icons for the EQ Cosplay interface.

``draw_icon`` returns a list of Tk Canvas item ids. All icons are drawn from
Canvas primitives in a 24-unit coordinate system and scaled to ``size``. Pass
``tag`` to assign a common Canvas tag to every item, which makes later updates
or deletion straightforward.
"""

from __future__ import annotations

from tkinter import Canvas


def draw_icon(
    canvas: Canvas,
    name: str,
    x: float,
    y: float,
    size: float,
    color: str,
    tag: str | None = None,
) -> list[int]:
    """Draw a named outline icon and return its Canvas item ids.

    Supported names: ``search``, ``close``, ``refresh``, ``play``, ``stop``,
    ``trash``, ``expand``, ``settings``, ``data``, ``library``, ``motion``, and
    ``arrow``. Coordinates describe the top-left corner and square extent.
    """
    name = name.lower().replace("-", "_")
    aliases = {"delete": "trash", "search_icon": "search", "left_right": "motion"}
    name = aliases.get(name, name)
    supported = {
        "search", "close", "refresh", "play", "stop", "trash", "expand",
        "settings", "data", "library", "motion", "arrow",
    }
    if name not in supported:
        raise ValueError(f"unknown icon {name!r}; expected one of {sorted(supported)}")

    scale = size / 24.0
    width = max(1.15, size * 0.075)
    ids: list[int] = []
    tags = (tag,) if tag else ()

    def xy(points: tuple[float, ...]) -> tuple[float, ...]:
        return tuple((v * scale + (x if i % 2 == 0 else y)) for i, v in enumerate(points))

    def line(points: tuple[float, ...], smooth: bool = False) -> None:
        ids.append(canvas.create_line(*xy(points), fill=color, width=width,
                                      capstyle="butt", joinstyle="miter",
                                      smooth=smooth, splinesteps=20, tags=tags))

    def oval(bounds: tuple[float, float, float, float], outline: str = color,
             fill: str = "", stroke: float = width) -> None:
        ids.append(canvas.create_oval(*xy(bounds), outline=outline, fill=fill,
                                      width=stroke, tags=tags))

    def rect(bounds: tuple[float, float, float, float], outline: str = color,
             fill: str = "", stroke: float = width) -> None:
        ids.append(canvas.create_rectangle(*xy(bounds), outline=outline, fill=fill,
                                           width=stroke, tags=tags))

    if name == "search":
        oval((3, 3, 15, 15))
        line((13.5, 13.5, 21, 21))
    elif name == "close":
        line((5, 5, 19, 19))
        line((19, 5, 5, 19))
    elif name == "refresh":
        # Two open arcs and arrowheads make the cycle legible at small sizes.
        ids.append(canvas.create_arc(*xy((4, 4, 20, 20)), start=42, extent=150,
                                     style="arc", outline=color, width=width,
                                     tags=tags))
        ids.append(canvas.create_arc(*xy((4, 4, 20, 20)), start=222, extent=150,
                                     style="arc", outline=color, width=width,
                                     tags=tags))
        line((17, 3.5, 20, 4, 19.5, 7))
        line((7, 20.5, 4, 20, 4.5, 17))
    elif name == "play":
        ids.append(canvas.create_polygon(*xy((7, 4, 20, 12, 7, 20)), fill=color,
                                         outline=color, tags=tags))
    elif name == "stop":
        rect((5, 5, 19, 19), outline=color, fill=color, stroke=1)
    elif name == "trash":
        line((4, 6, 20, 6))
        line((9, 4, 15, 4))
        line((7, 7, 8, 20, 16, 20, 17, 7))
        line((10, 10, 10, 17))
        line((14, 10, 14, 17))
    elif name == "expand":
        line((9, 4, 4, 4, 4, 9))
        line((15, 4, 20, 4, 20, 9))
        line((4, 15, 4, 20, 9, 20))
        line((20, 15, 20, 20, 15, 20))
    elif name == "settings":
        # A clean radial control glyph stays crisp at tiny toolbar sizes.
        oval((8, 8, 16, 16))
        for a, b in (((12, 2, 12, 6), (12, 18, 12, 22)),
                     ((2, 12, 6, 12), (18, 12, 22, 12)),
                     ((5, 5, 7.5, 7.5), (16.5, 16.5, 19, 19)),
                     ((17, 5, 19, 7), (5, 17, 7, 19))):
            line(a)
            line(b)
    elif name == "data":
        line((4, 6, 20, 6))
        line((4, 12, 20, 12))
        line((4, 18, 20, 18))
        oval((7, 4.5, 10, 7.5), fill=color, stroke=1)
        oval((14, 10.5, 17, 13.5), fill=color, stroke=1)
        oval((9, 16.5, 12, 19.5), fill=color, stroke=1)
    elif name == "library":
        rect((4, 5, 9, 19))
        rect((10, 4, 15, 20))
        rect((16, 6, 20, 19))
        line((5.5, 8, 7.5, 8))
        line((11.5, 7, 13.5, 7))
        line((17, 9, 19, 9))
    elif name == "motion":
        line((3, 12, 6, 12, 8, 7, 11, 17, 14, 8, 16, 12, 21, 12), smooth=True)
    elif name == "arrow":
        line((3, 12, 20, 12))
        line((14, 6, 20, 12, 14, 18))
    return ids


def draw_brand_mark(
    canvas: Canvas,
    x: float,
    y: float,
    size: float,
    color: str,
    secondary: str,
    tag: str | None = None,
) -> list[int]:
    """Draw a sound transformation emblem with two semantic response colors.

    The mark combines an incoming short waveform with a longer shaped output
    curve and a fine directional bridge. It uses only vector Canvas items.
    """
    s = size / 32.0
    t = (tag,) if tag else ()
    ids: list[int] = []

    def xy(points: tuple[float, ...]) -> tuple[float, ...]:
        return tuple((v * s + (x if i % 2 == 0 else y)) for i, v in enumerate(points))

    def line(points: tuple[float, ...], stroke: str, width: float,
             smooth: bool = False) -> None:
        ids.append(canvas.create_line(*xy(points), fill=stroke, width=max(1, width * s),
                                      capstyle="butt", joinstyle="miter",
                                      smooth=smooth, splinesteps=20, tags=t))

    # A restrained outer frame gives the emblem a stable silhouette.
    ids.append(canvas.create_rectangle(x + 0.5, y + 0.5, x + size - 0.5, y + size - 0.5,
                                       outline="#72808a", width=max(1, s), tags=t))
    # Input pulse enters from the left; the cool secondary curve is transformed sound.
    line((4, 16, 7, 16, 9, 11, 11, 21, 13, 13, 15, 16), color, 1.55)
    line((15, 16, 18, 16, 20, 11, 23, 20, 25, 13, 28, 13), secondary, 1.65, smooth=True)
    line((22, 7, 27, 7, 27, 11), secondary, 1.2)
    return ids
