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

# Number of ASCII characters across the portrait.
COLS = 90

# Brightness levels used to render the portrait.
#
# IMPORTANT:
# The first character is a SPACE.
#
# White pixels map toward the blank end of the ramp.
# Dark pixels map toward the dense characters.
ASCII_RAMP = " .:-=+*#%@MW&"

# Monospace characters are roughly twice as tall as wide.
ROW_ASPECT_CORRECTION = 0.48

# Width of the actual ASCII portrait area.
#
# The final SVG will be slightly wider because we now add
# padding around the portrait for the background card.
PORTRAIT_WIDTH = 460


# ============================================================
# CARD / SVG APPEARANCE
# ============================================================

# Extra space around the ASCII portrait.
CARD_PADDING_X = 20
CARD_PADDING_Y = 18

# Rounded corners.
CARD_RADIUS = 18

# GitHub-style dark background.
CARD_BACKGROUND = "#0d1117"

# Subtle GitHub-style border.
CARD_BORDER = "#30363d"

CARD_BORDER_WIDTH = 1.5

# ASCII portrait color.
ASCII_COLOR = "#f5f3ff"

# Purple typing cursor.
CURSOR_COLOR = "#a78bfa"


# ============================================================
# IMAGE PROCESSING SETTINGS
# ============================================================

BILATERAL_DIAMETER = 7
BILATERAL_SIGMA_COLOR = 55
BILATERAL_SIGMA_SPACE = 55

CLAHE_CLIP_LIMIT = 3.0
CLAHE_TILE_GRID = (8, 8)

# Darkens mid-tones while preserving highlights.
DARKENING_POWER = 1.55


# ============================================================
# ANIMATION SETTINGS
# ============================================================

# Delay between each ASCII row beginning its reveal.
ROW_STAGGER = 0.09

# Duration of each row's left-to-right reveal.
ROW_WIPE_DURATION = 0.72


# ============================================================
# BACKGROUND REMOVAL
# ============================================================

def remove_background(image: Image.Image):
    """
    Remove the image background using rembg.

    Returns:
        subject_rgba:
            PIL image containing the subject with a
            transparent background.

        alpha:
            NumPy alpha mask representing the subject.
    """

    image = image.convert("RGBA")

    result = remove(image)

    # rembg may return either a PIL image or raw bytes
    # depending on the installed version/configuration.
    if isinstance(result, bytes):
        result = Image.open(
            io.BytesIO(result)
        ).convert("RGBA")
    else:
        result = result.convert("RGBA")

    alpha = np.array(
        result.getchannel("A")
    )

    return result, alpha


# ============================================================
# IMAGE PROCESSING
# ============================================================

def prepare_image(image: Image.Image):
    """
    Prepare the source portrait for ASCII conversion.

    Pipeline:

    1. Remove background with rembg.
    2. Composite the subject onto white.
    3. Convert to grayscale.
    4. Apply bilateral filtering.
    5. Apply CLAHE local contrast.
    6. Apply the 1.55 darkening curve.
    7. Force removed-background pixels back to white.
    """

    subject, alpha = remove_background(image)

    # --------------------------------------------------------
    # FORCE BACKGROUND TO WHITE
    # --------------------------------------------------------

    # ASCII conversion treats pure white as blank space.
    #
    # By placing the extracted subject on white, the removed
    # background disappears naturally from the final portrait.
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
    # --------------------------------------------------------
    #
    # Bilateral filtering smooths noisy areas such as skin
    # without destroying important facial edges:
    #
    # - eyebrows
    # - eyes
    # - glasses
    # - nose
    # - lips
    # - beard
    # - jawline
    #
    # This produces cleaner ASCII than a normal blur.
    # --------------------------------------------------------

    gray = cv2.bilateralFilter(
        gray,
        BILATERAL_DIAMETER,
        BILATERAL_SIGMA_COLOR,
        BILATERAL_SIGMA_SPACE
    )

    # --------------------------------------------------------
    # CLAHE
    # --------------------------------------------------------
    #
    # Contrast Limited Adaptive Histogram Equalization
    # enhances local contrast.
    #
    # This is useful for portraits because facial features
    # often contain subtle changes in brightness that would
    # otherwise disappear during downsampling.
    # --------------------------------------------------------

    clahe = cv2.createCLAHE(
        clipLimit=CLAHE_CLIP_LIMIT,
        tileGridSize=CLAHE_TILE_GRID
    )

    gray = clahe.apply(gray)

    # --------------------------------------------------------
    # DARKENING CURVE
    # --------------------------------------------------------
    #
    # Formula:
    #
    #     (brightness / 255) ^ DARKENING_POWER
    #
    # With DARKENING_POWER = 1.55:
    #
    # - bright areas remain relatively bright
    # - middle tones become darker
    # - facial details become more visible
    #
    # This helps eyes, nose, mouth, hair, and shadows survive
    # the aggressive reduction into ASCII.
    # --------------------------------------------------------

    normalized = (
        gray.astype(np.float32)
        / 255.0
    )

    darkened = np.power(
        normalized,
        DARKENING_POWER
    )

    gray = np.clip(
        darkened * 255.0,
        0,
        255
    ).astype(np.uint8)

    # --------------------------------------------------------
    # PRESERVE REMOVED BACKGROUND
    # --------------------------------------------------------
    #
    # Any pixel rembg classified as background should stay
    # completely white so it becomes an ASCII space.
    # --------------------------------------------------------

    gray[alpha < 10] = 255

    return gray


# ============================================================
# ASCII CONVERSION
# ============================================================

def image_to_ascii(gray):
    """
    Convert the processed grayscale portrait into ASCII.

    The image is resized to COLS characters wide while its
    height is corrected for the proportions of monospace
    characters.
    """

    original_height, original_width = gray.shape

    aspect_ratio = (
        original_height
        / original_width
    )

    # --------------------------------------------------------
    # CALCULATE ASCII HEIGHT
    # --------------------------------------------------------
    #
    # Formula:
    #
    # rows =
    #     columns
    #     * image aspect ratio
    #     * character aspect correction
    #
    # Characters are taller than they are wide, so without
    # ROW_ASPECT_CORRECTION the portrait would appear stretched.
    # --------------------------------------------------------

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

    ramp_length = len(
        ASCII_RAMP
    )

    lines = []

    # --------------------------------------------------------
    # MAP EACH PIXEL TO ASCII
    # --------------------------------------------------------

    for row in resized:

        chars = []

        for value in row:

            # Pixel brightness:
            #
            # 255 = pure white
            #   0 = pure black
            #
            # We convert brightness to darkness because the
            # ASCII ramp begins with the lightest character
            # and ends with the densest.
            #
            # White -> " "
            # Black -> "&"

            darkness = (
                1.0
                - (float(value) / 255.0)
            )

            index = round(
                darkness
                * (ramp_length - 1)
            )

            index = max(
                0,
                min(
                    index,
                    ramp_length - 1
                )
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
    Generate the animated ASCII portrait SVG.

    Features:

    - Dark GitHub-style card background
    - Rounded corners
    - Subtle border
    - Light ASCII text
    - Purple animated cursor
    - Row-by-row typing animation
    - Works in GitHub light and dark mode

    Each ASCII row reveals from left to right using its own
    animated clipPath.

    The animation plays once and freezes in its completed state.
    """

    # --------------------------------------------------------
    # FONT SIZE
    # --------------------------------------------------------
    #
    # Approximate monospace character width is around 60%
    # of the selected font size.
    #
    # Therefore:
    #
    # font size =
    #     desired portrait width
    #     / character count
    #     / approximate glyph-width ratio
    # --------------------------------------------------------

    font_size = (
        PORTRAIT_WIDTH
        / (COLS * 0.60)
    )

    line_height = (
        font_size * 1.02
    )

    # --------------------------------------------------------
    # SVG DIMENSIONS
    # --------------------------------------------------------

    svg_width = (
        PORTRAIT_WIDTH
        + (CARD_PADDING_X * 2)
    )

    top_padding = (
        CARD_PADDING_Y
        + font_size
    )

    svg_height = (
        top_padding
        + len(lines) * line_height
        + CARD_PADDING_Y
        + font_size * 0.35
    )

    # --------------------------------------------------------
    # SVG COMPONENT COLLECTIONS
    # --------------------------------------------------------

    clip_defs = []
    text_rows = []
    cursors = []

    # --------------------------------------------------------
    # CREATE EACH ASCII ROW
    # --------------------------------------------------------

    for i, line in enumerate(lines):

        y = (
            top_padding
            + ((i + 1) * line_height)
        )

        begin = (
            i * ROW_STAGGER
        )

        end = (
            begin
            + ROW_WIPE_DURATION
        )

        clip_id = (
            f"rowClip{i}"
        )

        # ----------------------------------------------------
        # ROW CLIP PATH
        # ----------------------------------------------------
        #
        # Each line starts completely hidden.
        #
        # The clipping rectangle expands from:
        #
        # width = 0
        #
        # to:
        #
        # width = PORTRAIT_WIDTH
        #
        # producing the typing/reveal effect.
        # ----------------------------------------------------

        clip_defs.append(
            f"""
<clipPath id="{clip_id}">
    <rect
        x="{CARD_PADDING_X}"
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

        # Escape characters that SVG/XML could interpret
        # as markup.
        safe_line = html.escape(line)

        # ----------------------------------------------------
        # ASCII TEXT ROW
        # ----------------------------------------------------

        text_rows.append(
            f"""
<text
    x="{CARD_PADDING_X}"
    y="{y}"
    xml:space="preserve"
    clip-path="url(#{clip_id})"
    fill="{ASCII_COLOR}"
    font-family="SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace"
    font-size="{font_size:.2f}"
>{safe_line}</text>
"""
        )

        # ----------------------------------------------------
        # TYPING CURSOR
        # ----------------------------------------------------
        #
        # A small purple block follows the leading edge of the
        # row reveal.
        # ----------------------------------------------------

        cursor_width = max(
            2,
            font_size * 0.40
        )

        cursor_end_x = (
            CARD_PADDING_X
            + PORTRAIT_WIDTH
            - cursor_width
        )

        cursors.append(
            f"""
<rect
    x="{CARD_PADDING_X}"
    y="{y - font_size + 1}"
    width="{cursor_width:.2f}"
    height="{font_size + 1:.2f}"
    fill="{CURSOR_COLOR}"
    opacity="0"
>
    <set
        attributeName="opacity"
        to="1"
        begin="{begin:.2f}s"
    />

    <animate
        attributeName="x"
        from="{CARD_PADDING_X}"
        to="{cursor_end_x:.2f}"
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

    # --------------------------------------------------------
    # FINAL SVG
    # --------------------------------------------------------

    svg = f"""<svg
    xmlns="http://www.w3.org/2000/svg"
    width="{svg_width}"
    height="{svg_height:.0f}"
    viewBox="0 0 {svg_width} {svg_height:.0f}"
>

<defs>
{''.join(clip_defs)}
</defs>

<!-- ======================================================
     BACKGROUND CARD
     ====================================================== -->

<rect
    x="{CARD_BORDER_WIDTH / 2}"
    y="{CARD_BORDER_WIDTH / 2}"
    width="{svg_width - CARD_BORDER_WIDTH}"
    height="{svg_height - CARD_BORDER_WIDTH}"
    rx="{CARD_RADIUS}"
    ry="{CARD_RADIUS}"
    fill="{CARD_BACKGROUND}"
    stroke="{CARD_BORDER}"
    stroke-width="{CARD_BORDER_WIDTH}"
/>

<!-- ======================================================
     ASCII PORTRAIT
     ====================================================== -->

{''.join(text_rows)}

<!-- ======================================================
     TYPING CURSORS
     ====================================================== -->

{''.join(cursors)}

</svg>
"""

    return svg


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Generate an animated ASCII portrait SVG "
            "for a GitHub profile README"
        )
    )

    # --------------------------------------------------------
    # INPUT
    # --------------------------------------------------------
    #
    # The input argument is optional.
    #
    # Running:
    #
    #     python3 scripts/generate_portrait.py
    #
    # automatically uses:
    #
    #     assets/portrait-source.png
    # --------------------------------------------------------

    parser.add_argument(
        "input",
        nargs="?",
        default="assets/portrait-source.png",
        help=(
            "Path to source portrait "
            "(default: assets/portrait-source.png)"
        )
    )

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

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

    input_path = Path(
        args.input
    )

    output_path = Path(
        args.output
    )

    # --------------------------------------------------------
    # VERIFY INPUT
    # --------------------------------------------------------

    if not input_path.exists():
        raise FileNotFoundError(
            f"Could not find source image: {input_path}"
        )

    # --------------------------------------------------------
    # LOAD SOURCE IMAGE
    # --------------------------------------------------------

    print("Loading portrait...")

    image = Image.open(
        input_path
    ).convert("RGB")

    print(
        f"Source image: "
        f"{image.width}x{image.height}"
    )

    # --------------------------------------------------------
    # SOURCE QUALITY WARNING
    # --------------------------------------------------------
    #
    # A higher-resolution source preserves significantly more
    # facial detail after downsampling to 90 ASCII columns.
    # --------------------------------------------------------

    if max(
        image.width,
        image.height
    ) < 1200:

        print(
            "WARNING: Source image is below 1200px. "
            "A high-resolution, tightly cropped portrait "
            "will produce better facial detail."
        )

    # --------------------------------------------------------
    # PROCESS IMAGE
    # --------------------------------------------------------

    print(
        "Removing background..."
    )

    gray = prepare_image(
        image
    )

    print(
        "Applied bilateral filtering, "
        "CLAHE, and darkening curve."
    )

    # --------------------------------------------------------
    # GENERATE ASCII
    # --------------------------------------------------------

    print(
        "Generating ASCII..."
    )

    lines = image_to_ascii(
        gray
    )

    print(
        f"ASCII dimensions: "
        f"{COLS} columns x {len(lines)} rows"
    )

    # --------------------------------------------------------
    # GENERATE SVG
    # --------------------------------------------------------

    print(
        "Generating animated SVG..."
    )

    svg = generate_svg(
        lines
    )

    # --------------------------------------------------------
    # WRITE OUTPUT
    # --------------------------------------------------------

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