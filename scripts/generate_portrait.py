from pathlib import Path
import argparse
import html
import io

import cv2
import numpy as np
from PIL import Image
from rembg import remove


# ============================================================
# SETTINGS
# ============================================================

# Recommended by the portrait guide.
COLS = 90

# 13 brightness levels.
# IMPORTANT: the first character is a SPACE.
# White pixels map to the blank end of the ramp.
ASCII_RAMP = " .:-=+*#%@MW&"

# Monospace characters are roughly twice as tall as wide.
ROW_ASPECT_CORRECTION = 0.48

# Intended display width on the GitHub README.
PORTRAIT_WIDTH = 460

# Image processing settings.
BILATERAL_DIAMETER = 7
BILATERAL_SIGMA_COLOR = 55
BILATERAL_SIGMA_SPACE = 55

CLAHE_CLIP_LIMIT = 3.0
CLAHE_TILE_GRID = (8, 8)

# Important darkening curve from the guide.
DARKENING_POWER = 1.55

# Typing animation settings.
ROW_STAGGER = 0.09
ROW_WIPE_DURATION = 0.72


# ============================================================
# BACKGROUND REMOVAL
# ============================================================

def remove_background(image: Image.Image):
    """
    Remove the image background using rembg.

    Returns:
        subject_rgba: PIL image with transparent background
        alpha: NumPy alpha mask
    """

    image = image.convert("RGBA")

    result = remove(image)

    # rembg may return either a PIL image or bytes,
    # depending on version/configuration.
    if isinstance(result, bytes):
        result = Image.open(io.BytesIO(result)).convert("RGBA")
    else:
        result = result.convert("RGBA")

    alpha = np.array(result.getchannel("A"))

    return result, alpha


# ============================================================
# IMAGE PROCESSING
# ============================================================

def prepare_image(image: Image.Image):
    """
    Portrait processing pipeline:

    1. Remove background with rembg
    2. Force background to white
    3. Convert to grayscale
    4. Apply bilateral filtering
    5. Apply CLAHE local contrast
    6. Apply the ^1.7 darkening curve
    """

    subject, alpha = remove_background(image)

    # --------------------------------------------------------
    # FORCE BACKGROUND TO WHITE
    # --------------------------------------------------------

    white_background = Image.new(
        "RGBA",
        subject.size,
        (255, 255, 255, 255)
    )

    composite = Image.alpha_composite(
        white_background,
        subject
    ).convert("RGB")

    rgb = np.array(composite)

    # --------------------------------------------------------
    # GRAYSCALE
    # --------------------------------------------------------

    gray = cv2.cvtColor(
        rgb,
        cv2.COLOR_RGB2GRAY
    )

    # --------------------------------------------------------
    # BILATERAL FILTER
    #
    # Smooths skin while preserving important edges such as:
    # - glasses
    # - eyebrows
    # - eyes
    # - nose
    # - lips
    # - jawline
    # --------------------------------------------------------

    gray = cv2.bilateralFilter(
        gray,
        BILATERAL_DIAMETER,
        BILATERAL_SIGMA_COLOR,
        BILATERAL_SIGMA_SPACE
    )

    # --------------------------------------------------------
    # CLAHE
    #
    # Improves local contrast instead of applying one global
    # contrast adjustment to the entire photograph.
    # --------------------------------------------------------

    clahe = cv2.createCLAHE(
        clipLimit=CLAHE_CLIP_LIMIT,
        tileGridSize=CLAHE_TILE_GRID
    )

    gray = clahe.apply(gray)

    # --------------------------------------------------------
    # DARKENING CURVE
    #
    # (v / 255) ^ 1.7
    #
    # This pushes mid-tones darker while preserving highlights.
    # It helps facial features survive ASCII conversion.
    # --------------------------------------------------------

    normalized = gray.astype(np.float32) / 255.0

    darkened = np.power(
        normalized,
        DARKENING_POWER
    )

    gray = np.clip(
        darkened * 255.0,
        0,
        255
    ).astype(np.uint8)

    # Ensure everything rembg identified as background
    # remains pure white.
    gray[alpha < 10] = 255

    return gray


# ============================================================
# ASCII CONVERSION
# ============================================================

def image_to_ascii(gray):
    """
    Resize the processed portrait to ASCII dimensions and
    convert each brightness value into an ASCII character.
    """

    original_height, original_width = gray.shape

    aspect_ratio = original_height / original_width

    # Guide formula:
    #
    # rows = cols * (height / width) * 0.48
    #
    rows = max(
        1,
        round(
            COLS
            * aspect_ratio
            * ROW_ASPECT_CORRECTION
        )
    )

    resized = cv2.resize(
        gray,
        (COLS, rows),
        interpolation=cv2.INTER_AREA
    )

    ramp_length = len(ASCII_RAMP)

    lines = []

    for row in resized:

        chars = []

        for value in row:

            # Pixel brightness:
            #
            # 255 = white
            #   0 = black
            #
            # ASCII_RAMP begins with a space, so we convert
            # brightness into darkness.
            #
            # White -> " "
            # Black -> densest character

            darkness = 1.0 - (float(value) / 255.0)

            index = round(
                darkness
                * (ramp_length - 1)
            )

            index = max(
                0,
                min(index, ramp_length - 1)
            )

            chars.append(
                ASCII_RAMP[index]
            )

        lines.append(
            "".join(chars)
        )

    return lines


# ============================================================
# SVG GENERATION
# ============================================================

def generate_svg(lines):
    """
    Generate an SVG portrait.

    Each ASCII row reveals from left to right using its own
    clipPath.

    Rows begin 0.09 seconds apart.

    The animation plays once and freezes in its completed state.
    """

    # Approximate monospace character width is about 60%
    # of the font size.
    font_size = PORTRAIT_WIDTH / (COLS * 0.60)

    line_height = font_size * 1.02

    top_padding = font_size

    svg_height = (
        top_padding
        + len(lines) * line_height
        + font_size
    )

    clip_defs = []
    text_rows = []
    cursors = []

    for i, line in enumerate(lines):

        y = (
            top_padding
            + ((i + 1) * line_height)
        )

        begin = i * ROW_STAGGER
        end = begin + ROW_WIPE_DURATION

        clip_id = f"rowClip{i}"

        # ----------------------------------------------------
        # ROW CLIP PATH
        #
        # The clip rectangle expands from width 0 to the
        # full portrait width.
        # ----------------------------------------------------

        clip_defs.append(
            f"""
<clipPath id="{clip_id}">
    <rect
        x="0"
        y="{y - font_size}"
        width="0"
        height="{line_height + 3}"
    >
        <animate
            attributeName="width"
            from="0"
            to="{PORTRAIT_WIDTH}"
            dur="{ROW_WIPE_DURATION}s"
            begin="{begin:.2f}s"
            fill="freeze"
        />
    </rect>
</clipPath>
"""
        )

        safe_line = html.escape(line)

        # ----------------------------------------------------
        # ASCII TEXT ROW
        # ----------------------------------------------------

        text_rows.append(
            f"""
<text
    x="0"
    y="{y}"
    xml:space="preserve"
    clip-path="url(#{clip_id})"
    fill="#f5f3ff"
    font-family="SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace"
    font-size="{font_size:.2f}"
>{safe_line}</text>
"""
        )

        # ----------------------------------------------------
        # TYPING CURSOR
        #
        # A small block travels along the leading edge
        # of each row's reveal.
        # ----------------------------------------------------

        cursor_width = max(
            2,
            font_size * 0.40
        )

        cursors.append(
            f"""
<rect
    x="0"
    y="{y - font_size + 1}"
    width="{cursor_width:.2f}"
    height="{font_size + 1:.2f}"
    fill="#a78bfa"
    opacity="0"
>
    <set
        attributeName="opacity"
        to="1"
        begin="{begin:.2f}s"
    />

    <animate
        attributeName="x"
        from="0"
        to="{PORTRAIT_WIDTH - cursor_width:.2f}"
        dur="{ROW_WIPE_DURATION}s"
        begin="{begin:.2f}s"
        fill="freeze"
    />

    <set
        attributeName="opacity"
        to="0"
        begin="{end:.2f}s"
    />
</rect>
"""
        )

    svg = f"""<svg
    xmlns="http://www.w3.org/2000/svg"
    width="{PORTRAIT_WIDTH}"
    height="{svg_height:.0f}"
    viewBox="0 0 {PORTRAIT_WIDTH} {svg_height:.0f}"
>

<defs>
{''.join(clip_defs)}
</defs>

{''.join(text_rows)}

{''.join(cursors)}

</svg>
"""

    return svg


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Generate animated ASCII portrait SVG"
    )

    # Input is optional.
    #
    # Running:
    #
    # python3 scripts/generate_portrait.py
    #
    # automatically uses:
    #
    # assets/portrait-source.png
    #
    parser.add_argument(
        "input",
        nargs="?",
        default="assets/portrait-source.png",
        help=(
            "Path to source portrait "
            "(default: assets/portrait-source.png)"
        )
    )

    parser.add_argument(
        "-o",
        "--output",
        default="assets/portrait.svg",
        help=(
            "Output SVG path "
            "(default: assets/portrait.svg)"
        )
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Could not find source image: {input_path}"
        )

    print("Loading portrait...")

    image = Image.open(
        input_path
    ).convert("RGB")

    print(
        f"Source image: "
        f"{image.width}x{image.height}"
    )

    # The guide strongly recommends a high-resolution,
    # tightly cropped source portrait.
    if max(image.width, image.height) < 1200:
        print(
            "WARNING: Source image is below 1200px. "
            "A high-resolution, tightly cropped portrait "
            "will produce better facial detail."
        )

    print("Removing background...")

    gray = prepare_image(image)

    print("Applying bilateral filter, CLAHE, and darkening curve...")

    print("Generating ASCII...")

    lines = image_to_ascii(gray)

    print(
        f"ASCII dimensions: "
        f"{COLS} columns x {len(lines)} rows"
    )

    print("Generating animated SVG...")

    svg = generate_svg(lines)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path.write_text(
        svg,
        encoding="utf-8"
    )

    print(
        f"Done: {output_path}"
    )


if __name__ == "__main__":
    main()