"""Generate forge.ico from brain.png at multiple sizes.

Run: python -m forge.ui.gen_icon
"""

from pathlib import Path

try:
    from PIL import Image, ImageEnhance
except ImportError:
    print("Requires: pip install Pillow")
    raise SystemExit(1)

BRAIN_PATH = Path(__file__).parent / "assets" / "brain.png"
ICO_PATH = Path(__file__).parent / "assets" / "forge.ico"
SIZES = [16, 32, 48, 64, 128, 256]


def generate_icon():
    if not BRAIN_PATH.exists():
        print(f"Brain image not found: {BRAIN_PATH}")
        return False

    img = Image.open(str(BRAIN_PATH)).convert("RGBA")

    # Pillow ICO: save the largest size, pass all desired sizes
    # Pillow will auto-resize to each requested size
    largest = img.resize((256, 256), Image.LANCZOS)

    # Boost contrast slightly for icon clarity
    enhancer = ImageEnhance.Contrast(largest)
    largest = enhancer.enhance(1.15)

    largest.save(
        str(ICO_PATH),
        format="ICO",
        sizes=[(s, s) for s in SIZES],
    )

    actual_size = ICO_PATH.stat().st_size
    print(f"Generated: {ICO_PATH} ({actual_size:,} bytes)")
    print(f"  Sizes: {', '.join(f'{s}x{s}' for s in SIZES)}")
    return True


if __name__ == "__main__":
    generate_icon()
