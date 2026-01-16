from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple

try:
    from PIL import Image
except Exception as exc:  # noqa: BLE001
    raise RuntimeError("Pillow is required for experimental image deltas") from exc


@dataclass(frozen=True)
class BrightnessDeltaResult:
    ok: bool
    reason: str
    k: Optional[int] = None
    k_range: Optional[Tuple[int, int]] = None
    ambiguous: bool = False
    clamped: bool = False
    pixels: int = 0
    size: Optional[Tuple[int, int]] = None


def _iter_rgba_pixels(image: Image.Image) -> Iterable[Tuple[int, int, int, int]]:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    return image.getdata()


def _compute_k_range(
    base_pixels: Iterable[Tuple[int, int, int, int]],
    target_pixels: Iterable[Tuple[int, int, int, int]],
) -> Tuple[bool, str, Optional[Tuple[int, int]], int]:
    lower = -255
    upper = 255
    count = 0
    for base_px, target_px in zip(base_pixels, target_pixels):
        if base_px[3] != target_px[3]:
            return False, "alpha mismatch", None, count
        for c1, c2 in zip(base_px[:3], target_px[:3]):
            if c2 == 0:
                upper = min(upper, -c1)
            elif c2 == 255:
                lower = max(lower, 255 - c1)
            else:
                k = c2 - c1
                lower = max(lower, k)
                upper = min(upper, k)
            if lower > upper:
                return False, "no single brightness shift fits all pixels", None, count
        count += 1
    return True, "", (lower, upper), count


def _apply_brightness(value: int, k: int) -> Tuple[int, bool]:
    out = value + k
    if out < 0:
        return 0, True
    if out > 255:
        return 255, True
    return out, False


def _verify_brightness(
    base_pixels: Iterable[Tuple[int, int, int, int]],
    target_pixels: Iterable[Tuple[int, int, int, int]],
    k: int,
) -> Tuple[bool, bool]:
    clamped = False
    for base_px, target_px in zip(base_pixels, target_pixels):
        if base_px[3] != target_px[3]:
            return False, clamped
        for c1, c2 in zip(base_px[:3], target_px[:3]):
            out, did_clamp = _apply_brightness(c1, k)
            clamped = clamped or did_clamp
            if out != c2:
                return False, clamped
    return True, clamped


def detect_brightness_delta(base_path: Path, target_path: Path) -> BrightnessDeltaResult:
    base_img = Image.open(base_path)
    target_img = Image.open(target_path)
    if base_img.size != target_img.size:
        return BrightnessDeltaResult(
            ok=False,
            reason="size mismatch",
            size=base_img.size,
        )

    ok, reason, k_range, pixels = _compute_k_range(
        _iter_rgba_pixels(base_img),
        _iter_rgba_pixels(target_img),
    )
    if not ok or k_range is None:
        return BrightnessDeltaResult(
            ok=False,
            reason=reason,
            pixels=pixels,
            size=base_img.size,
        )

    lower, upper = k_range
    k = lower
    verified, clamped = _verify_brightness(
        _iter_rgba_pixels(base_img),
        _iter_rgba_pixels(target_img),
        k,
    )
    if not verified and upper != lower:
        k = upper
        verified, clamped = _verify_brightness(
            _iter_rgba_pixels(base_img),
            _iter_rgba_pixels(target_img),
            k,
        )

    if not verified:
        return BrightnessDeltaResult(
            ok=False,
            reason="verification failed for candidate k",
            k_range=k_range,
            ambiguous=lower != upper,
            pixels=pixels,
            size=base_img.size,
        )

    return BrightnessDeltaResult(
        ok=True,
        reason="ok",
        k=k,
        k_range=k_range,
        ambiguous=lower != upper,
        clamped=clamped,
        pixels=pixels,
        size=base_img.size,
    )


def apply_brightness_delta(base_path: Path, out_path: Path, k: int) -> None:
    base_img = Image.open(base_path).convert("RGBA")
    out = Image.new("RGBA", base_img.size)
    out_pixels = []
    for r, g, b, a in base_img.getdata():
        r2, _ = _apply_brightness(r, k)
        g2, _ = _apply_brightness(g, k)
        b2, _ = _apply_brightness(b, k)
        out_pixels.append((r2, g2, b2, a))
    out.putdata(out_pixels)
    out.save(out_path)


def _main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: python -m storage_core.experimental BASE.png TARGET.png", file=sys.stderr)
        return 2
    base = Path(argv[1])
    target = Path(argv[2])
    result = detect_brightness_delta(base, target)
    print(json.dumps(asdict(result), indent=2, ensure_ascii=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
