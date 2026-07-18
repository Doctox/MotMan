"""Compile generated transparent motifs into production-shaped APNG loops.

The runtime receives only finished raster animations. Motion is baked here at
build time: no SVG, canvas animation or CSS keyframes are needed in the game.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "output" / "animation-lab" / "seeds-alpha"
SOURCE_V2_DIR = ROOT / "output" / "animation-lab" / "seeds-v2-alpha"
SOURCE_V3_DIR = ROOT / "output" / "animation-lab" / "seeds-v3-alpha"
OUTPUT_DIR = ROOT / "public" / "assets" / "animations" / "lab"
SIZE = 224
CENTER = (SIZE / 2, SIZE / 2)


@dataclass(frozen=True)
class AnimationSpec:
    slug: str
    frames: int
    frame_ms: int
    motion: str


@dataclass
class Component:
    image: Image.Image
    center_x: float
    center_y: float
    area: int


SPECS = (
    AnimationSpec("eclat", 24, 120, "orbit"),
    AnimationSpec("etincelle", 28, 110, "strip_sparkle"),
    AnimationSpec("poussiere-dor", 30, 110, "strip_dust"),
    AnimationSpec("souffle", 30, 110, "strip_breeze"),
    AnimationSpec("halo", 30, 110, "strip_halo"),
    AnimationSpec("lucioles", 30, 110, "fireflies"),
    AnimationSpec("brume-irisee", 34, 110, "strip_mist"),
    AnimationSpec("constellation", 32, 110, "constellation_draw"),
    AnimationSpec("plume", 32, 110, "feather_drift"),
    AnimationSpec("feuille-automne", 38, 110, "strip_leaf"),
    AnimationSpec("lune-vagabonde", 38, 110, "strip_moon"),
    AnimationSpec("rosee", 30, 110, "dew_ripple"),
    AnimationSpec("prisme", 40, 110, "strip_prism"),
    AnimationSpec("ecume", 40, 110, "strip_foam"),
    AnimationSpec("petales", 32, 100, "petal_rain"),
    AnimationSpec("papillons-du-songe", 32, 105, "moth_journey"),
    AnimationSpec("carpes-celestes", 48, 110, "strip_koi"),
    AnimationSpec("oiseau-de-lumiere", 64, 120, "light_bird"),
    AnimationSpec("serpent-emeraude", 64, 120, "strip_serpent"),
    AnimationSpec("dragon-solaire", 64, 120, "strip_dragon"),
)


def load_seed(path: Path) -> Image.Image:
    source = Image.open(path).convert("RGBA")
    return source.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def source_path(slug: str) -> Path:
    if slug == "eclat":
        return SOURCE_DIR / f"{slug}.png"
    return SOURCE_V2_DIR / f"{slug}.png"


def load_horizontal_strip(path: Path, target_width: int, target_height: int) -> list[Image.Image]:
    source = Image.open(path).convert("RGBA")
    slot_width = source.width / 4
    crops: list[Image.Image] = []
    for index in range(4):
        slot = source.crop((round(index * slot_width), 0, round((index + 1) * slot_width), source.height))
        bounds = slot.getchannel("A").getbbox()
        if bounds is None:
            raise RuntimeError(f"Strip frame {index + 1} is empty: {path.name}")
        crops.append(slot.crop(bounds))
    source_width = max(image.width for image in crops)
    source_height = max(image.height for image in crops)
    shared_scale = min(target_width / source_width, target_height / source_height)
    return [
        image.resize(
            (max(1, round(image.width * shared_scale)), max(1, round(image.height * shared_scale))),
            Image.Resampling.LANCZOS,
        )
        for image in crops
    ]


def load_bird_strip() -> list[Image.Image]:
    return load_horizontal_strip(SOURCE_V2_DIR / "oiseau-de-lumiere-strip.png", 82, 74)


def components_from(image: Image.Image, threshold: int = 38) -> list[Component]:
    alpha = image.getchannel("A")
    pixels = alpha.load()
    seen = bytearray(SIZE * SIZE)
    groups: list[list[tuple[int, int]]] = []

    for y in range(SIZE):
        for x in range(SIZE):
            offset = y * SIZE + x
            if seen[offset] or pixels[x, y] <= threshold:
                continue
            seen[offset] = 1
            queue = deque([(x, y)])
            group: list[tuple[int, int]] = []
            while queue:
                current_x, current_y = queue.popleft()
                group.append((current_x, current_y))
                for next_y in range(max(0, current_y - 1), min(SIZE, current_y + 2)):
                    for next_x in range(max(0, current_x - 1), min(SIZE, current_x + 2)):
                        next_offset = next_y * SIZE + next_x
                        if seen[next_offset] or pixels[next_x, next_y] <= threshold:
                            continue
                        seen[next_offset] = 1
                        queue.append((next_x, next_y))
            if len(group) >= 7:
                groups.append(group)

    result: list[Component] = []
    for group in groups:
        left = min(point[0] for point in group)
        top = min(point[1] for point in group)
        right = max(point[0] for point in group) + 1
        bottom = max(point[1] for point in group) + 1
        pad = 2
        box = (max(0, left - pad), max(0, top - pad), min(SIZE, right + pad), min(SIZE, bottom + pad))
        crop = image.crop(box)
        result.append(Component(crop, (box[0] + box[2]) / 2, (box[1] + box[3]) / 2, len(group)))
    return sorted(result, key=lambda component: component.area, reverse=True)


def rotate_point(x: float, y: float, angle_degrees: float) -> tuple[float, float]:
    angle = math.radians(angle_degrees)
    relative_x, relative_y = x - CENTER[0], y - CENTER[1]
    cosine, sine = math.cos(angle), math.sin(angle)
    return (
        CENTER[0] + relative_x * cosine - relative_y * sine,
        CENTER[1] + relative_x * sine + relative_y * cosine,
    )


def transformed(
    component: Component,
    *,
    angle: float = 0,
    scale_x: float = 1,
    scale_y: float = 1,
    opacity: float = 1,
    brightness: float = 1,
    blur: float = 0,
) -> Image.Image:
    image = component.image
    width = max(1, round(image.width * scale_x))
    height = max(1, round(image.height * scale_y))
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    if brightness != 1:
        color = ImageEnhance.Brightness(image.convert("RGB")).enhance(brightness)
        color.putalpha(image.getchannel("A"))
        image = color.convert("RGBA")
    if opacity != 1:
        alpha = image.getchannel("A").point(lambda value: round(value * max(0, min(1, opacity))))
        image.putalpha(alpha)
    if angle:
        image = image.rotate(angle, Image.Resampling.BICUBIC, expand=True)
    if blur > 0:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    return image


def paste_component(
    canvas: Image.Image,
    component: Component,
    *,
    center_x: float | None = None,
    center_y: float | None = None,
    angle: float = 0,
    scale_x: float = 1,
    scale_y: float = 1,
    opacity: float = 1,
    brightness: float = 1,
    blur: float = 0,
) -> None:
    layer = transformed(
        component,
        angle=angle,
        scale_x=scale_x,
        scale_y=scale_y,
        opacity=opacity,
        brightness=brightness,
        blur=blur,
    )
    x = component.center_x if center_x is None else center_x
    y = component.center_y if center_y is None else center_y
    canvas.alpha_composite(layer, (round(x - layer.width / 2), round(y - layer.height / 2)))


def paste_sprite(
    canvas: Image.Image,
    sprite: Image.Image,
    *,
    center_x: float,
    center_y: float,
    scale: float = 1,
    opacity: float = 1,
    angle: float = 0,
    brightness: float = 1,
    blur: float = 0,
) -> None:
    paste_component(
        canvas,
        Component(sprite, 0, 0, sprite.width * sprite.height),
        center_x=center_x,
        center_y=center_y,
        scale_x=scale,
        scale_y=scale,
        opacity=opacity,
        angle=angle,
        brightness=brightness,
        blur=blur,
    )


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def draw_light_particles(
    canvas: Image.Image,
    particles: list[tuple[float, float, float, int]],
    *,
    glow_color: tuple[int, int, int] = (236, 174, 61),
    core_color: tuple[int, int, int] = (255, 229, 150),
) -> None:
    """Bake soft gold motes into a raster frame."""
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    core = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    core_draw = ImageDraw.Draw(core)
    for x, y, radius, alpha in particles:
        if alpha <= 0:
            continue
        glow_radius = radius * 2.8
        glow_draw.ellipse(
            (x - glow_radius, y - glow_radius, x + glow_radius, y + glow_radius),
            fill=(*glow_color, round(alpha * 0.42)),
        )
        core_draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(*core_color, alpha),
        )
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(3.2)))
    canvas.alpha_composite(core)


def paste_pose_transition(
    canvas: Image.Image,
    poses: list[Image.Image],
    progress: float,
    *,
    center_x: float,
    center_y: float,
    scale: float,
    opacity: float,
    angle: float = 0,
    brightness: float = 1,
    blur: float = 0,
    cycles: float = 1,
) -> None:
    """Cross-fade neighbouring generated poses instead of teleporting between them."""
    position = (max(0.0, min(0.9999, progress)) * cycles) % 1 * len(poses)
    current_index = int(position) % len(poses)
    next_index = (current_index + 1) % len(poses)
    blend = smoothstep(position - int(position))
    paste_sprite(
        canvas,
        poses[current_index],
        center_x=center_x,
        center_y=center_y,
        scale=scale,
        opacity=opacity * (1 - blend * 0.78),
        angle=angle,
        brightness=brightness,
        blur=blur,
    )
    if blend > 0.02:
        paste_sprite(
            canvas,
            poses[next_index],
            center_x=center_x,
            center_y=center_y,
            scale=scale,
            opacity=opacity * blend * 0.78,
            angle=angle,
            brightness=brightness,
            blur=blur,
        )


def wave_warp_vertical(sprite: Image.Image, phase: float, amplitude: float = 4.5) -> Image.Image:
    """Undulate one stable serpent pose without generating ghost limbs or tails."""
    padding = math.ceil(amplitude) + 3
    warped = Image.new("RGBA", (sprite.width + padding * 2, sprite.height), (0, 0, 0, 0))
    for y in range(sprite.height):
        normalized_y = y / max(1, sprite.height - 1)
        # The head moves less than the long body and tail.
        body_weight = 0.35 + 0.65 * normalized_y
        offset = round(padding + math.sin(phase + normalized_y * math.pi * 2.7) * amplitude * body_weight)
        warped.alpha_composite(sprite.crop((0, y, sprite.width, y + 1)), (offset, y))
    return warped


def draw_mist_banks(canvas: Image.Image, timeline: float) -> None:
    """Layered opaline haze with no cloud-shaped object."""
    phase = timeline * math.pi * 2
    haze = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(haze)
    palette = ((213, 230, 224), (202, 216, 233), (226, 214, 231))
    for bank in range(3):
        direction = -1 if bank % 2 else 1
        center_x = 112 + direction * (-34 + ((timeline + bank * 0.27) % 1) * 68)
        center_y = 130 + bank * 27 + 4 * math.sin(phase + bank * 1.7)
        color = palette[bank]
        for puff in range(6):
            x = center_x + (puff - 2.5) * 16 + 5 * math.sin(phase * 0.65 + puff + bank)
            y = center_y + 5 * math.cos(phase * 0.55 + puff * 0.8 + bank)
            width = 31 + (puff % 3) * 8
            height = 10 + (puff % 2) * 5
            alpha = 38 + (puff % 3) * 9
            draw.ellipse((x - width / 2, y - height / 2, x + width / 2, y + height / 2), fill=(*color, alpha))
    canvas.alpha_composite(haze.filter(ImageFilter.GaussianBlur(8.5)))

    sheen = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sheen_draw = ImageDraw.Draw(sheen)
    for index in range(3):
        x = 42 + ((timeline + index * 0.34) % 1) * 142
        y = 144 + index * 17 + 3 * math.sin(phase + index)
        sheen_draw.ellipse((x - 24, y - 3, x + 24, y + 3), fill=(228, 241, 237, 42))
    canvas.alpha_composite(sheen.filter(ImageFilter.GaussianBlur(3.6)))


def draw_prismatic_reflections(canvas: Image.Image, timeline: float) -> None:
    """A restrained wash of coloured light: no literal crystal over the portrait."""
    phase = timeline * math.pi * 2
    fade = fade_window(timeline, 0.18)
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    colors = (
        (118, 205, 193),
        (150, 156, 221),
        (232, 174, 175),
        (239, 205, 125),
    )
    for index, color in enumerate(colors):
        inset = 24 + index * 7
        start = 186 + index * 31 + timeline * 105
        sweep = 46 + 8 * math.sin(phase + index)
        draw.arc(
            (inset, inset, SIZE - inset, SIZE - inset),
            start=start,
            end=start + sweep,
            fill=(*color, round((70 - index * 7) * fade)),
            width=3 if index < 2 else 2,
        )

    sweep_x = -48 + smoothstep(timeline) * (SIZE + 96)
    beam = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    beam_draw = ImageDraw.Draw(beam)
    beam_draw.polygon(
        ((sweep_x - 20, 22), (sweep_x + 7, 22), (sweep_x + 58, 204), (sweep_x + 24, 204)),
        fill=(169, 222, 213, round(30 * fade)),
    )
    beam_draw.polygon(
        ((sweep_x - 7, 22), (sweep_x + 13, 22), (sweep_x + 70, 204), (sweep_x + 47, 204)),
        fill=(210, 171, 222, round(24 * fade)),
    )
    canvas.alpha_composite(beam.filter(ImageFilter.GaussianBlur(6.5)))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(1.0)))

    glints: list[tuple[float, float, float, int]] = []
    positions = ((45, 63), (177, 72), (157, 174), (65, 161))
    for index, (x, y) in enumerate(positions):
        pulse = max(0.0, math.sin(phase * 1.5 + index * 1.65))
        glints.append((x, y, 0.7 + 1.1 * pulse, round(155 * pulse * fade)))
    draw_light_particles(canvas, glints, glow_color=(132, 185, 183), core_color=(255, 244, 207))


def draw_foam_bubbles(canvas: Image.Image, timeline: float) -> None:
    """Fine bubbles rise from a quiet ripple instead of covering the avatar."""
    rings = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(rings)
    for index in range(12):
        cycle = (timeline + index * 0.137) % 1
        if cycle > 0.74:
            continue
        progress = cycle / 0.74
        side = -1 if index % 2 == 0 else 1
        x = 112 + side * (24 + (index * 17) % 67) + 7 * math.sin(progress * math.pi * 2 + index)
        y = 203 - progress * (58 + (index * 19) % 104)
        radius = 1.7 + (index % 4) * 0.72
        alpha = round(150 * fade_window(progress, 0.18) * (0.72 + (index % 3) * 0.12))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=(219, 246, 239, alpha), width=1)
        highlight = radius * 0.34
        draw.ellipse(
            (x - radius * 0.45 - highlight, y - radius * 0.45 - highlight,
             x - radius * 0.45 + highlight, y - radius * 0.45 + highlight),
            fill=(255, 255, 246, min(220, alpha + 35)),
        )
    canvas.alpha_composite(rings)

    ripple = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ripple_draw = ImageDraw.Draw(ripple)
    for index in range(3):
        local = (timeline - index * 0.10) % 1
        width = 42 + local * 112
        height = 8 + local * 13
        alpha = round(75 * (1 - local) ** 1.6)
        ripple_draw.ellipse(
            (112 - width / 2, 188 - height / 2, 112 + width / 2, 188 + height / 2),
            outline=(107, 190, 181, alpha),
            width=2,
        )
    canvas.alpha_composite(ripple.filter(ImageFilter.GaussianBlur(0.45)))


def render_strip_scene(
    motion: str,
    poses: list[Image.Image],
    frame: int,
    frame_count: int,
) -> Image.Image:
    """Stage generated four-pose strips as restrained avatar-sized scenes."""
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    timeline = frame / (frame_count - 1)
    phase = timeline * math.pi * 2

    if motion == "strip_sparkle":
        cycle = (timeline * 1.7) % 1
        pose = poses[min(3, int(cycle * 4))]
        x = 112 + math.cos(phase * 0.72 - 0.7) * 71
        y = 111 + math.sin(phase * 0.72 - 0.7) * 65
        paste_sprite(canvas, pose, center_x=x, center_y=y, scale=0.43, opacity=fade_window(cycle, 0.20))

    elif motion == "strip_dust":
        cycle = timeline
        pose = poses[int(cycle * 11) % 4]
        paste_sprite(
            canvas,
            pose,
            center_x=42 + cycle * 142,
            center_y=178 - cycle * 116 + 9 * math.sin(phase * 2),
            scale=0.58,
            opacity=fade_window(cycle, 0.18) * 0.76,
        )

    elif motion == "strip_breeze":
        # Three light breaths cross on separate lanes. Nothing behaves like a
        # rigid banner and the middle of the portrait stays readable.
        for index in range(3):
            cycle = (timeline + index * 0.28) % 1
            if cycle > 0.62:
                continue
            active = cycle / 0.62
            depth = index / 2
            paste_sprite(
                canvas,
                poses[(index + int(active * 4)) % len(poses)],
                center_x=-24 + active * 272,
                center_y=72 + index * 48 + 8 * math.sin(active * math.pi * 2 + index),
                scale=0.27 + depth * 0.07,
                opacity=fade_window(active, 0.20) * (0.32 + depth * 0.07),
                angle=-5 + 10 * math.sin(active * math.pi),
                blur=0.65 if index == 0 else 0.25,
            )

    elif motion == "strip_halo":
        pose = poses[int(timeline * 8) % 4]
        pulse = 0.74 + 0.035 * math.sin(phase)
        opacity = 0.42 + 0.16 * (0.5 + 0.5 * math.sin(phase))
        paste_sprite(canvas, pose, center_x=112, center_y=112, scale=pulse, opacity=opacity)

    elif motion == "strip_mist":
        draw_mist_banks(canvas, timeline)

    elif motion == "strip_leaf":
        # A small autumn shower with one foreground leaf and six quieter ones.
        lanes = (30, 61, 93, 126, 158, 188, 72)
        for index in range(7):
            cycle = (timeline + index * 0.137) % 1
            if cycle > 0.68:
                continue
            active = cycle / 0.68
            foreground = index == 3
            scale = 0.23 if foreground else 0.11 + (index % 3) * 0.025
            x = lanes[index] + 15 * math.sin(active * math.pi * 2 + index * 0.9)
            y = -17 + active * 258
            paste_sprite(
                canvas,
                poses[index % len(poses)],
                center_x=x,
                center_y=y,
                scale=scale,
                opacity=fade_window(active, 0.16) * (0.92 if foreground else 0.58 + (index % 2) * 0.12),
                angle=(-38 + active * 255 + index * 41) * (-1 if index % 2 else 1),
                blur=0 if foreground else 0.28 + (index % 2) * 0.24,
            )

    elif motion == "strip_moon":
        active = timeline / 0.76
        if 0 <= active <= 1:
            pose = poses[int(active * 7) % 4]
            paste_sprite(
                canvas,
                pose,
                center_x=42 + active * 142,
                center_y=62 - 14 * math.sin(active * math.pi),
                scale=0.39,
                opacity=fade_window(active, 0.18) * 0.88,
                angle=-8 + 16 * active,
            )

    elif motion == "strip_prism":
        draw_prismatic_reflections(canvas, timeline)

    elif motion == "strip_foam":
        # The wave stays below the portrait; the living motion belongs to the bubbles.
        wave_opacity = 0.18 + 0.06 * (0.5 + 0.5 * math.sin(phase))
        paste_pose_transition(
            canvas,
            poses,
            timeline,
            center_x=112,
            center_y=211,
            scale=0.88,
            opacity=wave_opacity * 1.18,
            cycles=0.52,
            blur=0.45,
        )
        draw_foam_bubbles(canvas, timeline)

    elif motion == "strip_koi":
        # A true single-fish swim cycle is instanced twice on two offset paths.
        # The tail animation belongs to the source poses; positioning only
        # carries each fish around the outside of the portrait.
        active = timeline / 0.82
        if 0 <= active <= 1:
            stillness = fade_window(active, 0.16)
            for index in range(2):
                theta = active * math.pi * 1.68 + index * (math.pi + 0.24)
                radius_x = 79 - index * 5
                radius_y = 70 - index * 4
                x = 112 + math.cos(theta) * radius_x
                y = 112 + math.sin(theta) * radius_y
                tangent = math.degrees(math.atan2(radius_y * math.cos(theta), -radius_x * math.sin(theta)))
                pose = poses[(int(active * 15) + index * 2) % len(poses)]
                paste_sprite(
                    canvas,
                    pose,
                    center_x=x,
                    center_y=y,
                    scale=0.66 - index * 0.04,
                    opacity=stillness * (0.96 - index * 0.06),
                    angle=tangent + 3 * math.sin(active * math.pi * 4 + index),
                    brightness=1.04,
                )
            motes = []
            for index in range(7):
                local = (active + index * 0.11) % 1
                motes.append((
                    112 + math.cos(local * math.pi * 2 + index) * (62 + index * 2),
                    112 + math.sin(local * math.pi * 2 + index) * (54 + index),
                    0.65 + index % 3 * 0.22,
                    round(90 * stillness * (0.55 + 0.45 * math.sin(local * math.pi) ** 2)),
                ))
            draw_light_particles(canvas, motes, glow_color=(207, 137, 89), core_color=(255, 226, 178))

    elif motion == "strip_serpent":
        # Incarnation, one controlled undulation, then dissolution. The serpent
        # stays in the avatar's orbit instead of sliding across the card.
        active = (timeline - 0.12) / 0.60
        if timeline < 0.20:
            gather: list[tuple[float, float, float, int]] = []
            progress = smoothstep(timeline / 0.20)
            for index in range(18):
                start_x = 18 + (index * 31) % 170
                start_y = 196 - (index * 17) % 80
                gather.append((start_x + (151 - start_x) * progress, start_y + (127 - start_y) * progress, 0.8 + index % 3 * 0.18, round(150 * progress)))
            draw_light_particles(canvas, gather, glow_color=(30, 139, 102), core_color=(180, 244, 202))
        if 0 <= active <= 1:
            body_fade = fade_window(active, 0.16)
            serpent = wave_warp_vertical(poses[0], active * math.pi * 2.2, amplitude=4.8)
            paste_sprite(
                canvas,
                serpent,
                center_x=149 + 4 * math.sin(active * math.pi * 2),
                center_y=115 + 3 * math.cos(active * math.pi * 2),
                scale=0.70 + 0.030 * math.sin(active * math.pi),
                opacity=body_fade * 0.96,
                angle=-4 + 8 * math.sin(active * math.pi),
                brightness=1.06,
            )
        if 0.66 <= timeline < 0.84:
            dissolve = (timeline - 0.66) / 0.18
            dust = []
            for index in range(22):
                angle = index * 2.39996
                distance = smoothstep(dissolve) * (10 + index * 2.0)
                dust.append((151 + math.cos(angle) * distance, 116 + math.sin(angle) * distance, 0.7 + index % 3 * 0.22, round(170 * (1 - dissolve))))
            draw_light_particles(canvas, dust, glow_color=(33, 139, 96), core_color=(184, 240, 195))

    elif motion == "strip_dragon":
        active = (timeline - 0.12) / 0.60
        if timeline < 0.20:
            gather = []
            progress = smoothstep(timeline / 0.20)
            for index in range(18):
                angle = index * 2.39996
                start_x = 112 + math.cos(angle) * (44 + index * 4)
                start_y = 112 + math.sin(angle) * (38 + index * 3)
                gather.append((start_x + (24 - start_x) * progress, start_y + (126 - start_y) * progress, 0.9 + index % 3 * 0.3, round(190 * progress)))
            draw_light_particles(canvas, gather)
        if 0 <= active <= 1:
            pose = poses[int(active * 15) % 4]
            paste_sprite(
                canvas,
                pose,
                center_x=18 + active * 188,
                center_y=126 - 102 * smoothstep(active) - 18 * math.sin(active * math.pi),
                scale=0.58 + 0.08 * math.sin(active * math.pi),
                opacity=fade_window(active, 0.13) * 0.98,
                angle=-14 + 10 * active,
                brightness=1.06,
            )
        if 0.65 <= timeline < 0.82:
            dissolve = (timeline - 0.65) / 0.17
            dust = []
            for index in range(22):
                angle = index * 2.39996 - 0.4
                distance = smoothstep(dissolve) * (14 + index * 2.5)
                dust.append((202 + math.cos(angle) * distance, 24 + math.sin(angle) * distance, 0.8 + index % 4 * 0.3, round(210 * (1 - dissolve))))
            draw_light_particles(canvas, dust)

    return canvas


def render_light_bird_frame(
    frame: int,
    frame_count: int,
    bird_frames: list[Image.Image],
    feathers: list[Component],
) -> Image.Image:
    """A miniature scene: gather, incarnation, flight, dust, silence."""
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    timeline = frame / (frame_count - 1)
    origin = (46.0, 164.0)
    finish = (190.0, 58.0)

    if timeline < 0.255:
        gather = smoothstep(timeline / 0.235)
        particles: list[tuple[float, float, float, int]] = []
        for index in range(24):
            particle_angle = index * 2.39996 + 0.35
            radius = 48 + (index * 19) % 112
            start_x = 112 + math.cos(particle_angle) * radius
            start_y = 112 + math.sin(particle_angle) * radius * 0.82
            curl = math.sin(gather * math.pi * 2 + index * 0.72) * 15 * (1 - gather)
            x = start_x + (origin[0] - start_x) * gather + curl
            y = start_y + (origin[1] - start_y) * gather + math.cos(particle_angle) * curl * 0.35
            pulse = 0.72 + 0.28 * math.sin(index * 1.81 + gather * math.pi * 7)
            particles.append((x, y, 0.8 + (index % 3) * 0.42, round((105 + 120 * gather) * pulse)))
        draw_light_particles(canvas, particles)

    if 0.145 <= timeline < 0.255:
        materialize = smoothstep((timeline - 0.145) / 0.11)
        paste_sprite(
            canvas,
            bird_frames[1],
            center_x=origin[0],
            center_y=origin[1],
            scale=0.32 + 0.42 * materialize,
            opacity=materialize * 0.96,
            angle=-12,
            brightness=1.14,
        )

    if 0.235 <= timeline < 0.675:
        travel = max(0.0, min(1.0, (timeline - 0.235) / 0.44))
        eased = smoothstep(travel)
        x = origin[0] + (finish[0] - origin[0]) * eased
        y = origin[1] + (finish[1] - origin[1]) * eased - 23 * math.sin(travel * math.pi)
        wing = bird_frames[int(travel * 15) % len(bird_frames)]
        fade = 1 if travel < 0.82 else max(0, (1 - travel) / 0.18)
        paste_sprite(
            canvas,
            wing,
            center_x=x,
            center_y=y,
            scale=0.72 + 0.14 * math.sin(travel * math.pi),
            opacity=0.98 * fade,
            angle=-13 + 8 * travel,
            brightness=1.08,
        )
        trail: list[tuple[float, float, float, int]] = []
        for index in range(7):
            past = max(0.0, travel - (index + 1) * 0.028)
            past_eased = smoothstep(past)
            px = origin[0] + (finish[0] - origin[0]) * past_eased
            py = origin[1] + (finish[1] - origin[1]) * past_eased - 23 * math.sin(past * math.pi)
            trail.append((px - index * 1.5, py + index * 0.7, 0.7 + index * 0.10, round(115 * fade * (1 - index / 8))))
        draw_light_particles(canvas, trail)

    if 0.61 <= timeline < 0.79:
        dissolve = max(0.0, min(1.0, (timeline - 0.61) / 0.18))
        particles = []
        for index in range(22):
            particle_angle = index * 2.39996 - 0.5
            distance = smoothstep(dissolve) * (18 + (index * 13) % 48)
            x = finish[0] + math.cos(particle_angle) * distance
            y = finish[1] + math.sin(particle_angle) * distance * 0.72 + dissolve * 13
            opacity = round(230 * (1 - smoothstep(dissolve)) * (0.68 + 0.32 * math.sin(index * 1.7) ** 2))
            particles.append((x, y, 0.8 + (index % 4) * 0.34, opacity))
        draw_light_particles(canvas, particles)
        for index, feather in enumerate(feathers[:2]):
            local = max(0.0, min(1.0, (dissolve - index * 0.12) / 0.88))
            if local <= 0:
                continue
            paste_component(
                canvas,
                feather,
                center_x=finish[0] - 8 + index * 16 + 9 * math.sin(local * math.pi),
                center_y=finish[1] + 5 + local * 42,
                angle=-24 + index * 37 + 42 * math.sin(local * math.pi),
                scale_x=0.25 + index * 0.04,
                scale_y=0.25 + index * 0.04,
                opacity=fade_window(local, 0.24) * 0.72,
                brightness=1.12,
            )

    # The remaining 21% is intentionally empty so the rare effect can breathe.
    return canvas


def fade_window(progress: float, edge: float = 0.14) -> float:
    """Fade a travelling object in and out without a visible loop cut."""
    return max(0.0, min(1.0, progress / edge, (1 - progress) / edge))


def paste_revealed(
    canvas: Image.Image,
    component: Component,
    *,
    progress: float,
    center_x: float,
    center_y: float,
    scale: float,
    opacity: float,
) -> None:
    layer = transformed(component, scale_x=scale, scale_y=scale, opacity=opacity)
    reveal_x = max(0, min(layer.width, round(layer.width * progress)))
    if reveal_x <= 0:
        return
    layer = layer.crop((0, 0, reveal_x, layer.height))
    left = round(center_x - (component.image.width * scale) / 2)
    top = round(center_y - layer.height / 2)
    canvas.alpha_composite(layer, (left, top))


def render_frame(motion: str, components: list[Component], frame: int, frame_count: int) -> Image.Image:
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    phase = 2 * math.pi * frame / frame_count

    if motion == "orbit":
        angle = frame * 360 / frame_count
        for index, component in enumerate(components):
            x, y = rotate_point(component.center_x, component.center_y, angle)
            pulse = 1 + (0.12 if index else 0.018) * math.sin(phase * 2 + index)
            paste_component(canvas, component, center_x=x, center_y=y, angle=angle, scale_x=pulse, scale_y=pulse,
                            opacity=0.76 + 0.24 * (0.5 + 0.5 * math.sin(phase * 2 + index)))

    elif motion == "petal_rain":
        # A sparse, directional shower. Petals cross the portrait instead of
        # forming a decorative wreath around it.
        petals = components[: min(10, len(components))]
        lanes = (26, 52, 81, 111, 141, 171, 198)
        for index, component in enumerate(petals):
            cycle = (frame / frame_count + index / len(petals)) % 1
            if cycle > 0.68:
                continue
            progress = cycle / 0.68
            depth = (index % 3) / 2
            scale = 0.34 + depth * 0.18
            x = lanes[index % len(lanes)] + 12 * math.sin(progress * math.pi * 2 + index * 1.7)
            y = -20 + progress * (SIZE + 40)
            paste_component(
                canvas,
                component,
                center_x=x,
                center_y=y,
                angle=(progress * 250 + index * 47) * (-1 if index % 2 else 1),
                scale_x=scale * (0.86 + 0.14 * abs(math.cos(progress * math.pi * 3))),
                scale_y=scale,
                opacity=fade_window(progress) * (0.62 + depth * 0.30),
                blur=0.55 if depth == 0 else 0,
            )

    elif motion == "fireflies":
        trails = [component for component in components if component.image.width > component.image.height * 3]
        lights = [component for component in components if component not in trails]
        for index, component in enumerate(lights[:7]):
            cycle = (frame / frame_count + index * 0.17) % 1
            if cycle > 0.74:
                continue
            progress = cycle / 0.74
            x = 28 + (index * 31) % 170 + 16 * math.sin(progress * math.pi * 2 + index)
            y = 192 - progress * 154 + 7 * math.sin(progress * math.pi * 3 + index * 0.8)
            pulse = 0.72 + 0.28 * (0.5 + 0.5 * math.sin(progress * math.pi * 8 + index))
            paste_component(
                canvas,
                component,
                center_x=x,
                center_y=y,
                scale_x=(0.68 + 0.10 * (index % 3)) * pulse,
                scale_y=(0.68 + 0.10 * (index % 3)) * pulse,
                opacity=fade_window(progress) * (0.72 + 0.24 * pulse),
                brightness=1.12,
            )
        if trails:
            sweep = (frame / frame_count - 0.50) / 0.34
            if 0 <= sweep <= 1:
                paste_revealed(
                    canvas,
                    trails[0],
                    progress=min(1, sweep * 1.35),
                    center_x=112,
                    center_y=164,
                    scale=0.78,
                    opacity=fade_window(sweep, 0.25) * 0.58,
                )

    elif motion == "feather_drift":
        # One clear subject follows a long S-shaped path. The smaller feathers
        # appear only briefly, like distant echoes, never as a wreath.
        timeline = frame / frame_count
        feathers = components[:3]
        for index, component in enumerate(feathers):
            cycle = (timeline + index * 0.37) % 1
            if cycle > 0.58:
                continue
            progress = cycle / 0.58
            x = 28 + progress * 170 + 20 * math.sin(progress * math.pi * 2 + index)
            y = -22 + progress * 262
            depth = index / max(1, len(feathers) - 1)
            scale = 0.48 + depth * 0.14
            paste_component(
                canvas,
                component,
                center_x=x,
                center_y=y,
                angle=-24 + 48 * math.sin(progress * math.pi * 1.7 + index),
                scale_x=scale * (0.90 + 0.10 * abs(math.sin(progress * math.pi * 2))),
                scale_y=scale,
                opacity=fade_window(progress, 0.16) * (0.80 + depth * 0.18),
                blur=0.20 if index == 0 else 0,
            )

    elif motion == "dew_ripple":
        drops = [component for component in components if component.image.height > component.image.width]
        timeline = frame / (frame_count - 1)
        if drops and timeline < 0.47:
            fall = timeline / 0.47
            ease = fall * fall * (3 - 2 * fall)
            squeeze = max(0, (fall - 0.84) / 0.16)
            paste_component(
                canvas,
                drops[0],
                center_x=112 + 5 * math.sin(fall * math.pi),
                center_y=20 + ease * 132,
                angle=5 * math.sin(fall * math.pi * 2),
                scale_x=0.38 + 0.14 * squeeze,
                scale_y=0.42 - 0.12 * squeeze,
                opacity=fade_window(min(0.99, fall), 0.12) * 0.92,
            )
        ripple_draw = ImageDraw.Draw(canvas)
        for index in range(3):
            local = (timeline - 0.38 - index * 0.075) / 0.48
            if not 0 <= local <= 1:
                continue
            strength = fade_window(local, 0.18) * (0.76 - index * 0.13)
            width = 24 + local * 104
            height = 7 + local * 17
            box = (112 - width / 2, 162 - height / 2 + index * 2, 112 + width / 2, 162 + height / 2 + index * 2)
            ripple_draw.ellipse(box, outline=(73, 145, 141, round(205 * strength)), width=2)

    elif motion == "constellation_draw":
        lines = [component for component in components if component.image.width > component.image.height * 2.1]
        stars = [component for component in components if component not in lines]
        timeline = frame / (frame_count - 1)
        fade = 1 if timeline < 0.78 else max(0, (1 - timeline) / 0.22)
        positions = ((38, 78), (66, 47), (96, 60), (122, 30), (150, 52), (183, 39), (172, 92))
        for index, component in enumerate(stars[:7]):
            appear_at = 0.05 + index * 0.065
            local = max(0, min(1, (timeline - appear_at) / 0.12))
            if local <= 0:
                continue
            pulse = 0.86 + 0.14 * math.sin((timeline - appear_at) * math.pi * 5)
            paste_component(
                canvas,
                component,
                center_x=positions[index][0],
                center_y=positions[index][1],
                scale_x=(0.40 + index * 0.014) * local * pulse,
                scale_y=(0.40 + index * 0.014) * local * pulse,
                opacity=fade * (0.82 + 0.16 * local),
                brightness=1.14,
            )
    elif motion == "ink_reveal":
        strokes = [component for component in components if component.image.width > component.image.height * 3]
        drops = [component for component in components if component not in strokes]
        timeline = frame / (frame_count - 1)
        if strokes:
            reveal = min(1.0, timeline / 0.56)
            fade = 1 if timeline < 0.76 else max(0, (1 - timeline) / 0.24)
            paste_revealed(
                canvas,
                strokes[0],
                progress=reveal,
                center_x=112,
                center_y=171,
                scale=0.88,
                opacity=0.88 * fade,
            )
        if len(strokes) > 1 and 0.22 < timeline < 0.88:
            local = (timeline - 0.22) / 0.66
            paste_revealed(
                canvas,
                strokes[1],
                progress=min(1, local * 1.6),
                center_x=125,
                center_y=184,
                scale=0.72,
                opacity=fade_window(local, 0.22) * 0.68,
            )
        for index, component in enumerate(drops[:3]):
            local = (timeline - 0.42 - index * 0.08) / 0.43
            if not 0 <= local <= 1:
                continue
            paste_component(
                canvas,
                component,
                center_x=148 + index * 14,
                center_y=126 + local * 53,
                scale_x=0.62 + 0.06 * index,
                scale_y=0.70 + 0.06 * index,
                opacity=fade_window(local, 0.20) * 0.82,
            )

    elif motion == "aurora_sweep":
        ribbons = [component for component in components if component.area > 120]
        motes = [component for component in components if component not in ribbons]
        for index, component in enumerate(ribbons[:3]):
            cycle = (frame / frame_count + index * 0.31) % 1
            if cycle > 0.62:
                continue
            progress = cycle / 0.62
            x = -38 + progress * (SIZE + 76)
            y = 52 + index * 43 + 13 * math.sin(progress * math.pi)
            paste_component(
                canvas,
                component,
                center_x=x,
                center_y=y,
                angle=-36 + 7 * math.sin(progress * math.pi * 2 + index),
                scale_x=0.62 + index * 0.06,
                scale_y=0.62 + index * 0.06,
                opacity=fade_window(progress, 0.20) * (0.54 + index * 0.08),
                blur=0.35 if index == 0 else 0,
            )
        for index, component in enumerate(motes[:4]):
            pulse = 0.5 + 0.5 * math.sin(phase * 2 + index * 1.8)
            paste_component(
                canvas,
                component,
                center_x=(42 + index * 47 + 8 * math.sin(phase + index)) % SIZE,
                center_y=51 + (index % 2) * 122 + 5 * math.cos(phase + index),
                scale_x=0.44 + 0.12 * pulse,
                scale_y=0.44 + 0.12 * pulse,
                opacity=0.24 + 0.48 * pulse,
            )

    elif motion == "moth_journey":
        moths = [component for component in components if component.area > 160]
        dust = [component for component in components if component not in moths]
        routes = ((-28, 174, 252, 48), (246, 121, -26, 68), (-22, 82, 142, 28))
        for index, component in enumerate(moths[:3]):
            cycle = (frame / frame_count + index * 0.29) % 1
            if cycle > 0.66:
                continue
            progress = cycle / 0.66
            start_x, start_y, end_x, end_y = routes[index]
            x = start_x + (end_x - start_x) * progress
            y = start_y + (end_y - start_y) * progress - 24 * math.sin(progress * math.pi)
            flap = 0.72 + 0.28 * abs(math.sin(progress * math.pi * 7))
            paste_component(
                canvas,
                component,
                center_x=x,
                center_y=y,
                angle=(-15 + 30 * progress) * (-1 if index == 1 else 1),
                scale_x=(0.58 + index * 0.055) * flap,
                scale_y=0.58 + index * 0.055,
                opacity=fade_window(progress, 0.15) * 0.96,
            )
        for index, component in enumerate(dust[:3]):
            pulse = 0.5 + 0.5 * math.sin(phase * 2.4 + index * 2.1)
            paste_component(
                canvas,
                component,
                center_x=70 + index * 43,
                center_y=56 + index * 55,
                scale_x=0.32 + 0.14 * pulse,
                scale_y=0.32 + 0.14 * pulse,
                opacity=0.16 + 0.50 * pulse,
            )

    return canvas


def build(spec: AnimationSpec) -> None:
    if spec.motion.startswith("strip_"):
        target_sizes = {
            "strip_sparkle": (70, 70),
            "strip_dust": (105, 78),
            "strip_breeze": (165, 72),
            "strip_halo": (178, 178),
            "strip_mist": (158, 92),
            "strip_leaf": (96, 96),
            "strip_moon": (108, 108),
            "strip_prism": (82, 118),
            "strip_foam": (164, 102),
            "strip_koi": (106, 66),
            "strip_serpent": (134, 154),
            "strip_dragon": (164, 126),
        }
        target_width, target_height = target_sizes[spec.motion]
        poses = load_horizontal_strip(
            SOURCE_V3_DIR / f"{spec.slug}-strip.png",
            target_width,
            target_height,
        )
        if spec.motion == "strip_koi":
            for pose in poses:
                alpha = pose.getchannel("A").point(lambda value: min(255, round(value * 1.38)))
                pose.putalpha(alpha)
        frames = [render_strip_scene(spec.motion, poses, index, spec.frames) for index in range(spec.frames)]
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output = OUTPUT_DIR / f"{spec.slug}.png"
        frames[0].save(
            output,
            format="PNG",
            save_all=True,
            append_images=frames[1:],
            duration=spec.frame_ms,
            loop=0,
            disposal=1,
            blend=0,
            optimize=True,
            compress_level=9,
        )
        poster = OUTPUT_DIR / f"{spec.slug}-poster.webp"
        frames[round((spec.frames - 1) * 0.46)].save(poster, format="WEBP", quality=90, method=6)
        print(f"{spec.slug}: 4 generated poses, {len(frames)} frames, {output.stat().st_size} bytes")
        return

    if spec.motion == "light_bird":
        bird_frames = load_bird_strip()
        feather_seed = load_seed(source_path("plume"))
        feather_alpha = feather_seed.getchannel("A").point(lambda value: min(255, round(value * 1.75)))
        feather_seed.putalpha(feather_alpha)
        feathers = components_from(feather_seed)[:2]
        frames = [render_light_bird_frame(index, spec.frames, bird_frames, feathers) for index in range(spec.frames)]
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output = OUTPUT_DIR / f"{spec.slug}.png"
        frames[0].save(
            output,
            format="PNG",
            save_all=True,
            append_images=frames[1:],
            duration=spec.frame_ms,
            loop=0,
            disposal=1,
            blend=0,
            optimize=True,
            compress_level=9,
        )
        poster = OUTPUT_DIR / f"{spec.slug}-poster.webp"
        frames[31].save(poster, format="WEBP", quality=90, method=6)
        print(f"{spec.slug}: 4 bird poses, {len(feathers)} feathers, {len(frames)} frames, {output.stat().st_size} bytes")
        return

    seed = load_seed(source_path(spec.slug))
    if spec.slug == "lucioles":
        # The chroma-key pass correctly preserves the soft glow, but it is too
        # faint once reduced to avatar size. Reinforce only its baked alpha.
        alpha = seed.getchannel("A").point(lambda value: min(255, round(value * 2.25)))
        seed.putalpha(alpha)
    elif spec.slug in {"plume", "rosee"}:
        alpha = seed.getchannel("A").point(lambda value: min(255, round(value * 1.75)))
        seed.putalpha(alpha)
    elif spec.slug == "constellation":
        alpha = seed.getchannel("A").point(lambda value: min(255, round(value * 2.50)))
        seed.putalpha(alpha)
    threshold = 8 if spec.slug == "constellation" else 38
    components = components_from(seed, threshold=threshold)
    if not components:
        raise RuntimeError(f"No visible components found for {spec.slug}")
    frames = [render_frame(spec.motion, components, index, spec.frames) for index in range(spec.frames)]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / f"{spec.slug}.png"
    frames[0].save(
        output,
        format="PNG",
        save_all=True,
        append_images=frames[1:],
        duration=spec.frame_ms,
        loop=0,
        disposal=1,
        blend=0,
        optimize=True,
        compress_level=9,
    )
    poster = OUTPUT_DIR / f"{spec.slug}-poster.webp"
    frames[0].save(poster, format="WEBP", quality=90, method=6)
    print(f"{spec.slug}: {len(components)} components, {len(frames)} frames, {output.stat().st_size} bytes")


if __name__ == "__main__":
    for animation in SPECS:
        build(animation)
