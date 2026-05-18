"""One-shot generator for the Todo TUI placeholder icon PNGs.

Runs Pillow to render a stylized "T" mark on a rounded teal background at
the canonical Windows-icon sizes. Re-run this whenever the placeholder
artwork should be regenerated; the produced PNGs are checked into source
alongside this script and consumed by app/todo/build.sem via the
`iconImagePath` declarations.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent

BACKGROUND_COLOR = (38, 116, 142, 255)   # muted teal
FOREGROUND_COLOR = (240, 240, 240, 255)  # warm off-white
SIZES = (16, 32, 48, 256)


def render_icon(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # Rounded-square background tile.
    radius = max(2, size // 5)
    draw.rounded_rectangle(
        [(0, 0), (size - 1, size - 1)],
        radius=radius,
        fill=BACKGROUND_COLOR,
    )
    # Two-stroke "T" sized to the icon. Stroke width scales with size so
    # small icons stay legible without antialiasing destroying the shape.
    stroke = max(1, size // 8)
    horizontal_y_top = size // 4
    horizontal_y_bottom = horizontal_y_top + stroke
    horizontal_x_left = size // 5
    horizontal_x_right = size - size // 5
    vertical_x_left = (size // 2) - (stroke // 2)
    vertical_x_right = vertical_x_left + stroke
    vertical_y_top = horizontal_y_bottom
    vertical_y_bottom = size - size // 5
    draw.rectangle(
        [(horizontal_x_left, horizontal_y_top),
         (horizontal_x_right, horizontal_y_bottom)],
        fill=FOREGROUND_COLOR,
    )
    draw.rectangle(
        [(vertical_x_left, vertical_y_top),
         (vertical_x_right, vertical_y_bottom)],
        fill=FOREGROUND_COLOR,
    )
    return image


def main() -> None:
    for size in SIZES:
        output_path = HERE / f"icon-{size}.png"
        render_icon(size).save(output_path, format="PNG", optimize=True)
        print(f"wrote {output_path} ({size}x{size})")


if __name__ == "__main__":
    main()
