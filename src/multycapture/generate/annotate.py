"""Screenshot preparation for documents: highlight the action point and shrink.

Uses the mouse position stored on each event to draw a highlight ring where the
user clicked/scrolled, then downscales and re-encodes so embedded images stay a
sensible size in the output document.
"""

from __future__ import annotations

import io
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image


def highlight_point(image: "Image", x: int, y: int) -> "Image":
    """Draw a translucent highlight ring centred on (x, y) in image pixels."""
    from PIL import Image, ImageDraw

    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    r_outer = max(18, min(base.size) // 30)   # scale ring to image size
    r_inner = int(r_outer * 0.62)

    # soft glow + solid ring, in an attention-grabbing red-orange
    draw.ellipse(
        [x - r_outer, y - r_outer, x + r_outer, y + r_outer],
        fill=(255, 64, 32, 60),
    )
    for width, alpha in ((6, 255), (10, 90)):
        draw.ellipse(
            [x - r_inner, y - r_inner, x + r_inner, y + r_inner],
            outline=(255, 48, 24, alpha), width=width,
        )

    return Image.alpha_composite(base, overlay).convert("RGB")


def prepare_for_doc(
    image: "Image",
    point: Optional[tuple[int, int]] = None,
    max_width: int = 1200,
    jpeg_quality: int = 82,
) -> io.BytesIO:
    """Annotate (optional), downscale to ``max_width``, encode to JPEG bytes.

    Returns a rewound BytesIO suitable for ``python-docx``'s ``add_picture``.
    """
    from PIL import Image

    img = image
    if point is not None:
        img = highlight_point(img, point[0], point[1])

    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize(
            (max_width, max(1, round(img.height * ratio))),
            Image.LANCZOS,
        )

    if img.mode != "RGB":
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    buf.seek(0)
    return buf
