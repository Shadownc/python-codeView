# -*- coding: utf-8 -*-
"""发光 3D 粒子爱心动画渲染器。

这个脚本既可以打开 Tkinter 实时预览窗口，也可以导出 MP4 视频。
整体渲染流程如下：
1. 从参数方程生成爱心外轮廓粒子，并从文字遮罩中采样中心文字粒子；
2. 为每个粒子生成随机起点，再按时间插值聚拢到目标位置；
3. 对 3D 坐标做简单透视投影，得到屏幕上的 2D 坐标；
4. 使用 OpenCV 绘制粒子本体、光晕、闪烁点和环绕火花。
"""

import argparse
import math
import os
import time
from dataclasses import dataclass

import cv2
import numpy as np


# 实时预览为了保持流畅，默认分辨率和粒子数都比导出模式低。
PREVIEW_WIDTH = 900
PREVIEW_HEIGHT = 580
PREVIEW_FPS = 24
PREVIEW_PARTICLES = 1800

# 导出模式使用更高分辨率和更多粒子，画面更细腻，但渲染时间也更长。
EXPORT_WIDTH = 1112
EXPORT_HEIGHT = 720
EXPORT_FPS = 30
EXPORT_PARTICLES = 2400
DURATION = 13.6
# 默认显示在爱心中央的文字，可以通过命令行 --text 覆盖。
HEART_TEXT = "ZY"
# 背景和窗口透明度的默认值，范围会在实际使用时再做 clamp 限制。
BG_ALPHA = 1.0
WINDOW_ALPHA = 1.0


def smoothstep(x):
    """平滑阶跃函数：把 0..1 的线性进度变成起止都更柔和的曲线。"""
    x = float(np.clip(x, 0.0, 1.0))
    return x * x * (3.0 - 2.0 * x)


def clamp(value, low, high):
    """把单个数值限制在 [low, high] 区间内，防止透明度等参数越界。"""
    return max(low, min(high, value))


def ease_out_cubic(x):
    """三次缓出曲线：粒子一开始移动较快，接近目标时逐渐减速。"""
    x = float(np.clip(x, 0.0, 1.0))
    return 1.0 - (1.0 - x) ** 3


def ease_out_back(x):
    """带回弹的缓出曲线，当前主流程未使用，保留给后续尝试更夸张的入场效果。"""
    x = float(np.clip(x, 0.0, 1.0))
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (x - 1.0) ** 3 + c1 * (x - 1.0) ** 2


def heart_xy(t):
    """根据参数 t 计算二维爱心曲线坐标，作为外轮廓粒子的基础形状。"""
    x = 16.0 * np.sin(t) ** 3
    y = 13.0 * np.cos(t) - 5.0 * np.cos(2.0 * t)
    y -= 2.0 * np.cos(3.0 * t) + np.cos(4.0 * t)
    return x, y


def heart_tangent(t):
    """用中心差分估算爱心曲线切线方向，用于控制粒子拖尾的朝向。"""
    dt = 0.002
    x1, y1 = heart_xy(t - dt)
    x2, y2 = heart_xy(t + dt)
    tangent = np.column_stack([x2 - x1, y2 - y1, np.zeros_like(t)])
    length = np.linalg.norm(tangent, axis=1, keepdims=True)
    return tangent / np.maximum(length, 1e-6)


def rotate(points, ax, ay, az):
    """按 X、Y、Z 顺序旋转 Nx3 点数组，让爱心具有轻微 3D 摆动感。"""
    cx, sx = math.cos(ax), math.sin(ax)
    cy, sy = math.cos(ay), math.sin(ay)
    cz, sz = math.cos(az), math.sin(az)

    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    y, z = y * cx - z * sx, y * sx + z * cx
    x, z = x * cy + z * sy, -x * sy + z * cy
    x, y = x * cz - y * sz, x * sz + y * cz
    return np.column_stack([x, y, z])


def project(points, width, height):
    """把 3D 粒子投影到 2D 画布，并返回透视缩放系数。"""
    camera = 48.0
    scale = min(width, height) * 0.0278
    depth = camera - points[:, 2]
    perspective = camera / np.maximum(depth, 1.0)
    sx = width * 0.5 + points[:, 0] * scale * perspective
    sy = height * 0.47 - points[:, 1] * scale * perspective
    return sx, sy, perspective


@dataclass
class ParticleSet:
    """保存所有粒子的静态属性。

    这些数组只在初始化时生成一次，之后每一帧只根据时间计算动态位置。
    target 表示最终目标坐标，start 表示初始散开坐标，tangent 用于绘制拖尾方向。
    """

    target: np.ndarray
    start: np.ndarray
    tangent: np.ndarray
    size: np.ndarray
    length: np.ndarray
    twinkle: np.ndarray
    color_mix: np.ndarray
    is_letter: np.ndarray
    is_cjk_text: bool
    text: str


def has_cjk(text):
    """判断文本中是否包含中文、日文假名或韩文字符。"""
    return any(
        "\u3400" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        or "\u3040" <= char <= "\u30ff"
        or "\uac00" <= char <= "\ud7af"
        for char in text
    )


def load_text_font(size, text=""):
    """根据文本内容加载合适字体，优先保证中文等 CJK 字符能正确显示。"""
    from PIL import ImageFont

    # 先列出常见 Windows 中文字体，再列出英文字体；如果用户机器缺少某个字体，
    # 下面的循环会自动尝试下一个候选项。
    cjk_fonts = [
        "C:/Windows/Fonts/Noto Sans SC Bold (TrueType).otf",
        "C:/Windows/Fonts/SourceHanSansCN-Normal.ttf",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/Dengb.ttf",
        "C:/Windows/Fonts/Deng.ttf",
    ]
    latin_fonts = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    # CJK 文本优先使用中文字体；纯英文文本优先使用 Arial，避免字形过于拥挤。
    font_candidates = cjk_fonts + latin_fonts if has_cjk(text) else latin_fonts + cjk_fonts
    for font_path in font_candidates:
        try:
            return ImageFont.truetype(font_path, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def text_units(text):
    """把多字符 CJK 文本拆成单字绘制，方便手动加入字间距。"""
    compact = text.replace(" ", "")
    return list(compact) if has_cjk(text) and len(compact) > 1 else [text]


def sample_text_points(count, rng, text):
    """把文字先栅格化为灰度遮罩，再从遮罩亮部采样文字粒子坐标。"""
    from PIL import Image, ImageDraw

    text = (text or HEART_TEXT).strip() or HEART_TEXT
    # 使用比最终文字区域更大的离屏画布，先清晰画出文字，再缩放到爱心坐标系。
    canvas_w, canvas_h = 900, 360
    image = Image.new("L", (canvas_w, canvas_h), 0)
    draw = ImageDraw.Draw(image)

    font_size = 220
    font = load_text_font(font_size, text)
    units = text_units(text)
    gap = int(font_size * 0.16) if len(units) > 1 else 0
    boxes = [draw.textbbox((0, 0), unit, font=font) for unit in units]
    text_w = sum(box[2] - box[0] for box in boxes) + gap * max(0, len(units) - 1)
    text_h = max(box[3] - box[1] for box in boxes)
    # 不同文字长度差异很大，这里循环缩小字号，直到整体文字能放进采样画布。
    while (text_w > canvas_w * 0.82 or text_h > canvas_h * 0.72) and font_size > 24:
        font_size = int(font_size * 0.9)
        font = load_text_font(font_size, text)
        gap = int(font_size * 0.16) if len(units) > 1 else 0
        boxes = [draw.textbbox((0, 0), unit, font=font) for unit in units]
        text_w = sum(box[2] - box[0] for box in boxes) + gap * max(0, len(units) - 1)
        text_h = max(box[3] - box[1] for box in boxes)

    x_cursor = (canvas_w - text_w) * 0.5
    baseline_y = (canvas_h - text_h) * 0.5
    for unit, bbox in zip(units, boxes):
        # textbbox 的左上角可能不是 (0, 0)，绘制时要扣掉 bbox 偏移才能真正居中。
        unit_w = bbox[2] - bbox[0]
        y = baseline_y - bbox[1] + (text_h - (bbox[3] - bbox[1])) * 0.5
        draw.text((x_cursor - bbox[0], y), unit, fill=255, font=font)
        x_cursor += unit_w + gap

    mask = np.array(image)
    text_mask = mask > 30
    if has_cjk(text):
        # CJK 字形笔画密度高，如果所有内部像素都均匀采样，文字会变成一团亮块。
        # 这里先腐蚀得到内部区域，再用“原始文字 - 腐蚀结果”取出边缘，
        # 最后混入少量高亮内部像素，让文字既有轮廓又不显得空心。
        kernel = np.ones((3, 3), dtype=np.uint8)
        eroded = cv2.erode(text_mask.astype(np.uint8), kernel, iterations=1).astype(bool)
        edge_mask = text_mask & ~eroded
        edge_mask = cv2.dilate(edge_mask.astype(np.uint8), kernel, iterations=1).astype(bool)
        sample_mask = edge_mask | ((mask > 190) & (rng.random(mask.shape) < 0.04))
    else:
        sample_mask = text_mask

    ys, xs = np.nonzero(sample_mask)
    if len(xs) == 0:
        return sample_text_points(count, rng, HEART_TEXT)

    # 遮罩越亮的位置采样权重越高，粒子更容易落在清晰的笔画中心。
    weights = mask[ys, xs].astype(np.float32)
    if has_cjk(text):
        # 对 CJK 使用平方根降低亮度差异，避免笔画中心过密、边缘过稀。
        weights = np.sqrt(weights)
    weights /= weights.sum()
    pick = rng.choice(len(xs), size=count, replace=True, p=weights)
    px = xs[pick].astype(np.float32) + rng.normal(0.0, 0.45, count)
    py = ys[pick].astype(np.float32) + rng.normal(0.0, 0.45, count)

    # 把离屏画布上的像素坐标归一化到爱心使用的数学坐标系。
    # 注意屏幕坐标 y 轴向下，而数学坐标 y 轴向上，所以后面会对 y 取负。
    min_x, max_x = xs.min(), xs.max()
    min_y, max_y = ys.min(), ys.max()
    box_w = max(1.0, float(max_x - min_x + 1))
    box_h = max(1.0, float(max_y - min_y + 1))
    is_cjk_text = has_cjk(text)
    if is_cjk_text:
        # CJK 单字通常更接近方形，多字会横向展开，因此宽高上限分开处理。
        compact_len = len(text.replace(" ", ""))
        max_w = 7.2 if compact_len <= 1 else 13.2
        max_h = 7.0 if compact_len <= 1 else 5.9
        y_offset = -1.05 if compact_len <= 1 else -0.85
        scale = min(max_w / box_w, max_h / box_h)
    else:
        y_offset = -0.35
        scale = min(14.8 / box_w, 7.2 / box_h)
    cx = (min_x + max_x) * 0.5
    cy = (min_y + max_y) * 0.5

    points = np.column_stack(
        [
            (px - cx) * scale,
            -(py - cy) * scale + y_offset,
            rng.normal(0.0, 0.28, count),
        ]
    ).astype(np.float32)

    angles = rng.uniform(0.0, math.tau, count)
    # 文字粒子没有天然切线，随机方向能让拖尾分布更自然。
    tangents = np.column_stack([np.cos(angles), np.sin(angles), np.zeros(count)]).astype(np.float32)
    return points, tangents


def make_particles(count, seed=2026, text=HEART_TEXT):
    """生成粒子系统：包括爱心目标点、文字目标点、随机起点和绘制属性。"""
    rng = np.random.default_rng(seed)
    target = np.zeros((count, 3), dtype=np.float32)
    tangent = np.zeros((count, 3), dtype=np.float32)

    text = (text or HEART_TEXT).strip() or HEART_TEXT
    # 根据文字类型和长度动态分配文字粒子比例。
    # CJK 字形笔画更复杂，需要更多粒子才能看清；英文通常可以少一些。
    if has_cjk(text):
        compact_len = len(text.replace(" ", ""))
        text_fraction = min(0.54, max(0.36, 0.30 + compact_len * 0.07))
    else:
        text_fraction = min(0.36, max(0.22, 0.16 + len(text) * 0.035))
    letter_count = max(80, int(count * text_fraction))
    outline_count = count - letter_count

    # 爱心轮廓不是一根无限细的线，而是在法线和切线方向加入少量随机偏移，
    # 形成略带厚度的“粒子管”，这样光晕叠加后会更饱满。
    t = rng.random(outline_count) * math.tau
    x, y = heart_xy(t)
    tan = heart_tangent(t)
    normal = np.column_stack([-tan[:, 1], tan[:, 0], np.zeros(outline_count)])

    tube = rng.normal(0.0, 0.28, (outline_count, 1))
    side = rng.normal(0.0, 0.22, (outline_count, 1))
    z = rng.normal(0.0, 1.25, outline_count)
    target[:outline_count] = np.column_stack([x, y, z])
    target[:outline_count] += normal * tube + tan * side
    tangent[:outline_count] = tan

    # 中央文字单独采样，目标点会被放到同一个 3D 坐标空间中。
    letters, letter_tangent = sample_text_points(letter_count, rng, text)
    target[outline_count:] = letters
    tangent[outline_count:] = letter_tangent

    # 粒子起点集中在画面下方并带随机散布，因此动画开始时像从下方升起后聚拢。
    start = np.column_stack(
        [
            rng.uniform(-22.0, 22.0, count),
            rng.uniform(-23.0, -12.5, count),
            rng.uniform(-9.0, 9.0, count),
        ]
    ).astype(np.float32)
    start[:, 0] += rng.normal(0.0, 4.0, count)
    start[:, 1] += rng.normal(0.0, 2.0, count)

    size = rng.uniform(1.0, 2.6, count).astype(np.float32)
    length = rng.uniform(6.0, 15.0, count).astype(np.float32)
    is_letter = np.zeros(count, dtype=bool)
    is_letter[outline_count:] = True
    # 文字粒子需要和轮廓粒子区分：CJK 用较短拖尾避免糊成块，英文可以略长更闪亮。
    if has_cjk(text):
        size[is_letter] = rng.uniform(0.85, 1.45, letter_count).astype(np.float32)
        length[is_letter] = rng.uniform(1.2, 3.0, letter_count).astype(np.float32)
    else:
        size[is_letter] = rng.uniform(1.45, 2.9, letter_count).astype(np.float32)
        length[is_letter] = rng.uniform(4.5, 9.0, letter_count).astype(np.float32)

    return ParticleSet(
        target=target.astype(np.float32),
        start=start.astype(np.float32),
        tangent=tangent.astype(np.float32),
        size=size,
        length=length,
        twinkle=(rng.random(count) * math.tau).astype(np.float32),
        color_mix=rng.random(count).astype(np.float32),
        is_letter=is_letter,
        is_cjk_text=has_cjk(text),
        text=text,
    )


def make_background(width, height, alpha=1.0):
    """生成暗色径向渐变背景，中心略亮、四周压暗，突出粒子光效。"""
    alpha = clamp(float(alpha), 0.0, 1.0)
    yy, xx = np.mgrid[0:height, 0:width]
    cx, cy = width * 0.5, height * 0.48
    radius = np.sqrt(((xx - cx) / width) ** 2 + ((yy - cy) / height) ** 2)
    vignette = np.clip(1.0 - radius * 1.75, 0.0, 1.0)
    bg = np.zeros((height, width, 3), dtype=np.uint8)
    bg[..., 0] = ((7 + vignette * 12) * alpha).astype(np.uint8)
    bg[..., 1] = ((5 + vignette * 7) * alpha).astype(np.uint8)
    bg[..., 2] = ((10 + vignette * 18) * alpha).astype(np.uint8)
    return bg


def camera_angles(now, gather):
    """计算当前帧的相机旋转角度，聚拢完成后逐渐减弱镜头摆动。"""
    # gather 接近 1 时表示爱心已经成形，镜头摆动会收敛，避免最终画面太晃。
    swing = max(0.0, 1.0 - smoothstep((gather - 0.82) / 0.18))
    ax = 0.18 * math.sin(now * 0.42) * swing
    ay = (-0.22 + 0.34 * math.sin(now * 0.52)) * swing
    az = 0.055 * math.sin(now * 0.68) * swing
    return ax, ay, az


def particle_motion(particles, now):
    """根据当前时间计算一帧中的粒子位置、切线和聚拢进度。"""
    gather = ease_out_cubic(smoothstep(now / 5.8))
    pulse = 1.0 + 0.055 * max(0.0, math.sin(now * math.tau * 1.18)) ** 8
    breathe = 1.0 + 0.025 * math.sin(now * 1.7)

    # 在目标点上加入心跳和呼吸缩放：x/y 控制整体大小，z 控制前后轻微起伏。
    target = particles.target.copy()
    target[:, :2] *= pulse * breathe
    target[:, 2] *= 1.0 + 0.12 * math.sin(now * 1.1)

    # 从随机起点线性混合到目标点；聚拢早期额外叠加上升漂移和细小抖动。
    wobble = np.sin(now * 3.7 + particles.twinkle)[:, None]
    points = particles.start * (1.0 - gather) + target * gather
    points[:, 1] += (1.0 - gather) * np.sin(now * 4.8 + points[:, 0] * 0.6) * 1.8
    points[:, 1] += (1.0 - gather) * now * 1.4
    points += wobble * (1.0 - gather) * np.array([0.14, 0.2, 0.11], dtype=np.float32)

    ax, ay, az = camera_angles(now, gather)
    return rotate(points, ax, ay, az), rotate(particles.tangent, ax, ay, az), gather


def draw_particles(frame, particles, now, width, height, quality="preview"):
    """绘制粒子；导出模式会使用更慢但更精细的线段拖尾和多层光晕。"""
    if quality == "preview":
        return draw_particles_fast(frame, particles, now, width, height)

    points, tangents, gather = particle_motion(particles, now)
    sx, sy, perspective = project(points, width, height)

    glow = np.zeros_like(frame)
    core = np.zeros_like(frame)
    # 按 z 深度从远到近绘制，使靠近镜头的粒子能自然覆盖远处粒子。
    order = np.argsort(points[:, 2])

    rose = np.array([185, 35, 255], dtype=np.float32)
    pink = np.array([210, 88, 255], dtype=np.float32)
    white = np.array([245, 225, 255], dtype=np.float32)

    for i in order:
        x, y = sx[i], sy[i]
        if x < -60 or x > width + 60 or y < -60 or y > height + 60:
            continue

        # depth 由透视系数得到，越靠近镜头的粒子越大、越亮。
        depth = float(np.clip(perspective[i], 0.55, 1.55))
        flash = 0.72 + 0.28 * math.sin(now * 6.3 + float(particles.twinkle[i]))
        mix = float(particles.color_mix[i])
        color = rose * (1.0 - mix) + pink * mix
        color = color * (0.78 + 0.28 * depth) + white * (0.10 + 0.12 * flash)
        if particles.is_letter[i]:
            # 文字粒子使用更接近白色的颜色，保证中心文字可读。
            if particles.is_cjk_text:
                color = white * (0.50 + 0.12 * flash) + pink * 0.24
            else:
                color = white * (0.68 + 0.18 * flash) + pink * 0.32
        color = np.clip(color, 0, 255).astype(np.uint8)
        dim_strength = 0.30 if particles.is_letter[i] and particles.is_cjk_text else 0.52 if particles.is_letter[i] else 0.35
        dim = np.clip(color.astype(np.float32) * dim_strength, 0, 255).astype(np.uint8)

        # 切线决定拖尾方向；投影到屏幕坐标时 y 方向要取反。
        tx, ty = tangents[i, 0], -tangents[i, 1]
        norm = math.hypot(float(tx), float(ty))
        if norm < 1e-5:
            tx, ty, norm = 0.0, -1.0, 1.0
        tx, ty = tx / norm, ty / norm

        length = float(particles.length[i] * (0.56 + 0.58 * depth))
        if gather < 0.93:
            # 形状未完全稳定前，拖尾统一偏向上方，制造“向上飞入”的火花感。
            tx = 0.22 * math.sin(now * 5.0 + float(particles.twinkle[i]))
            ty = -1.0
            length *= 1.35 - 0.5 * gather

        dx, dy = tx * length * 0.5, ty * length * 0.5
        p1 = (int(x - dx), int(y - dy))
        p2 = (int(x + dx), int(y + dy))
        line_width = max(1, int(float(particles.size[i]) * depth))
        if particles.is_letter[i] and not particles.is_cjk_text:
            line_width += 1

        if particles.is_letter[i] and particles.is_cjk_text:
            # CJK 文字笔画复杂，导出模式中用圆点而不是长线，降低笔画粘连。
            center = (int(x), int(y))
            radius = max(1, int(float(particles.size[i]) * depth))
            cv2.circle(glow, center, radius + 2, tuple(int(v) for v in dim), -1, cv2.LINE_AA)
            cv2.circle(core, center, radius, tuple(int(v) for v in color), -1, cv2.LINE_AA)
            continue

        if particles.is_letter[i] and particles.is_cjk_text:
            glow_width = line_width + (2 if quality == "preview" else 3)
        else:
            glow_width = line_width + (4 if quality == "preview" else 7)
        cv2.line(glow, p1, p2, tuple(int(v) for v in dim), glow_width, cv2.LINE_AA)
        cv2.line(core, p1, p2, tuple(int(v) for v in color), line_width, cv2.LINE_AA)

        if mix > 0.91:
            # 少量粒子额外绘制亮点，形成随机闪烁的星点。
            r = max(1, int(1.6 * depth))
            cv2.circle(core, (int(x), int(y)), r, (255, 240, 255), -1, cv2.LINE_AA)

    # glow 先模糊成外发光，再和 core 粒子本体叠加到背景上。
    if quality == "preview":
        bloom = cv2.GaussianBlur(glow, (0, 0), 5)
        frame[:] = cv2.addWeighted(frame, 1.0, bloom, 1.15, 0)
    else:
        bloom = cv2.GaussianBlur(glow, (0, 0), 8)
        bloom2 = cv2.GaussianBlur(glow, (0, 0), 20)
        frame[:] = cv2.addWeighted(frame, 1.0, bloom2, 0.62, 0)
        frame[:] = cv2.addWeighted(frame, 1.0, bloom, 1.18, 0)
    frame[:] = cv2.addWeighted(frame, 1.0, core, 1.0, 0)

    draw_orbit_sparks(frame, now, width, height, quality)
    return frame


def draw_particles_fast(frame, particles, now, width, height):
    """实时预览专用的快速绘制器，用点精灵替代逐粒子线段。"""
    points, _tangents, _gather = particle_motion(particles, now)
    sx, sy, perspective = project(points, width, height)

    xi = sx.astype(np.int32)
    yi = sy.astype(np.int32)
    visible = (xi >= 2) & (xi < width - 2) & (yi >= 2) & (yi < height - 2)
    if not np.any(visible):
        return frame

    # 只保留画面内粒子，减少后续颜色计算和数组索引开销。
    xi = xi[visible]
    yi = yi[visible]
    depth = np.clip(perspective[visible], 0.55, 1.55).astype(np.float32)
    twinkle = particles.twinkle[visible]
    mix = particles.color_mix[visible]
    is_letter = particles.is_letter[visible]

    flash = 0.76 + 0.24 * np.sin(now * 6.0 + twinkle)
    rose = np.array([185, 35, 255], dtype=np.float32)
    pink = np.array([210, 95, 255], dtype=np.float32)
    white = np.array([245, 225, 255], dtype=np.float32)
    # 颜色计算尽量使用 NumPy 批量完成，比逐粒子调用 cv2 画线更适合实时预览。
    color = rose[None, :] * (1.0 - mix[:, None]) + pink[None, :] * mix[:, None]
    color = color * (0.92 + 0.38 * depth[:, None]) + white[None, :] * (0.12 + 0.18 * flash[:, None])
    if np.any(is_letter):
        if particles.is_cjk_text:
            color[is_letter] = white[None, :] * (0.54 + 0.10 * flash[is_letter, None]) + pink[None, :] * 0.24
        else:
            color[is_letter] = white[None, :] * (0.78 + 0.16 * flash[is_letter, None]) + pink[None, :] * 0.30
    color = np.clip(color, 0, 255).astype(np.uint8)
    if particles.is_cjk_text:
        dim_strength = np.where(is_letter, 0.36, 0.46).astype(np.float32)
    else:
        dim_strength = np.where(is_letter, 0.72, 0.46).astype(np.float32)
    dim = np.clip(color.astype(np.float32) * dim_strength[:, None], 0, 255).astype(np.uint8)

    glow = np.zeros_like(frame)
    core = np.zeros_like(frame)

    # 给每个粒子盖一个固定小核，模拟近似的光晕；这样避免在预览中逐粒子画线。
    for ox, oy, strength in (
        (0, 0, 1.0),
        (1, 0, 0.82),
        (-1, 0, 0.82),
        (0, 1, 0.82),
        (0, -1, 0.82),
        (1, 1, 0.56),
        (-1, 1, 0.56),
        (1, -1, 0.56),
        (-1, -1, 0.56),
        (2, 0, 0.32),
        (-2, 0, 0.32),
        (0, 2, 0.32),
        (0, -2, 0.32),
    ):
        target = np.clip(dim.astype(np.float32) * strength, 0, 255).astype(np.uint8)
        gx = xi + ox
        gy = yi + oy
        glow[gy, gx] = np.maximum(glow[gy, gx], target)

    for ox, oy, strength in (
        (0, 0, 1.0),
        (1, 0, 0.72),
        (-1, 0, 0.72),
        (0, 1, 0.72),
        (0, -1, 0.72),
    ):
        target = np.clip(color.astype(np.float32) * strength, 0, 255).astype(np.uint8)
        core[yi + oy, xi + ox] = np.maximum(core[yi + oy, xi + ox], target)

    bright = (mix > 0.92) | is_letter
    if np.any(bright):
        core[yi[bright], xi[bright]] = (255, 238, 255)

    # CJK 文字更容易被光晕糊掉，因此使用较小 sigma 和较低叠加强度。
    bloom_sigma = 5 if particles.is_cjk_text else 7
    bloom_weight = 1.25 if particles.is_cjk_text else 1.85
    core_weight = 1.25 if particles.is_cjk_text else 1.55
    bloom = cv2.GaussianBlur(glow, (0, 0), bloom_sigma)
    frame[:] = cv2.addWeighted(frame, 1.0, bloom, bloom_weight, 0)
    frame[:] = cv2.addWeighted(frame, 1.0, core, core_weight, 0)
    draw_orbit_sparks(frame, now, width, height, "preview")
    return frame


def draw_orbit_sparks(frame, now, width, height, quality="preview"):
    """沿爱心外侧绘制一圈缓慢旋转的小火花，增强空间层次。"""
    count = 34 if quality == "preview" else 58
    t = np.linspace(0, math.tau, count, endpoint=False) + now * 0.72
    x, y = heart_xy(t)
    orbit = np.column_stack([x * 1.08, y * 1.08, np.sin(t * 2.0 + now * 1.4) * 4.2])
    gather = ease_out_cubic(smoothstep(now / 5.8))
    ax, ay, az = camera_angles(now, gather)
    orbit = rotate(orbit, ax * 0.65, ay, az * 0.5)
    sx, sy, perspective = project(orbit, width, height)

    for i in range(count):
        # 每个火花的亮度随时间错相变化，避免整圈同时明暗变化太机械。
        fade = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(now * 4.0 + i * 0.7))
        r = max(1, int(1.7 * perspective[i] * fade))
        color = (255, int(160 + 70 * fade), 255)
        cv2.circle(frame, (int(sx[i]), int(sy[i])), r, color, -1, cv2.LINE_AA)


def render_frame(particles, background, now, width, height, quality="preview"):
    """渲染完整一帧：复制背景，再把粒子和火花绘制上去。"""
    frame = background.copy()
    draw_particles(frame, particles, now, width, height, quality)
    return frame


def render_video(args):
    """按命令行参数逐帧渲染动画，并写入 MP4 文件。"""
    output = os.path.abspath(args.output)
    particles = make_particles(args.particles, text=args.text)
    background = make_background(args.width, args.height, args.bg_alpha)
    writer = cv2.VideoWriter(
        output,
        cv2.VideoWriter_fourcc(*"mp4v"),
        args.fps,
        (args.width, args.height),
    )
    if not writer.isOpened():
        raise RuntimeError(f"Cannot write video: {output}")

    # 总帧数 = 时长 * 帧率；now 用帧号反推，保证导出视频的时间轴稳定。
    total = max(1, int(args.duration * args.fps))
    for index in range(total):
        now = index / args.fps
        writer.write(render_frame(particles, background, now, args.width, args.height, "export"))
        if index % args.fps == 0:
            print(f"rendering {index + 1}/{total}")
    writer.release()
    print(f"saved {output}")


def play_live(args):
    """打开可拖动的实时预览窗口。"""
    import tkinter as tk
    from PIL import Image, ImageTk

    particles = make_particles(args.particles, text=args.text)
    background = make_background(args.width, args.height, args.bg_alpha)
    start = time.perf_counter()
    delay = max(1, int(1000 / args.fps))

    root = tk.Tk()
    root.title("3D Heart Particles")
    root.resizable(False, False)
    root.configure(bg="black")
    # 默认无边框显示，更像桌面挂件；--windowed 可恢复系统标题栏。
    if not args.windowed:
        root.overrideredirect(True)
    if args.window_alpha < 1.0:
        root.attributes("-alpha", clamp(float(args.window_alpha), 0.15, 1.0))

    label = tk.Label(root, bd=0, highlightthickness=0, bg="black")
    label.pack()

    # 记录鼠标按下时相对窗口左上角的位置，用于拖动无边框窗口。
    drag = {"x": 0, "y": 0}

    def start_drag(event):
        drag["x"] = event.x
        drag["y"] = event.y

    def move_window(event):
        root.geometry(f"+{event.x_root - drag['x']}+{event.y_root - drag['y']}")

    def draw():
        """渲染一帧预览图，并根据耗时安排下一帧。"""
        frame_started = time.perf_counter()
        now = time.perf_counter() - start
        frame = render_frame(particles, background, now, args.width, args.height, "preview")
        # OpenCV 使用 BGR，Tkinter/Pillow 使用 RGB，显示前需要转换颜色通道。
        image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        photo = ImageTk.PhotoImage(Image.fromarray(image))
        label.configure(image=photo)
        # 保存引用，防止 PhotoImage 被 Python 垃圾回收后窗口变成空白。
        label.image = photo
        render_ms = int((time.perf_counter() - frame_started) * 1000)
        root.after(max(1, delay - render_ms), draw)

    # 绑定退出和拖动事件：Esc/q 退出，鼠标左键拖动窗口。
    root.bind("<Escape>", lambda _event: root.destroy())
    root.bind("q", lambda _event: root.destroy())
    root.bind("<ButtonPress-1>", start_drag)
    root.bind("<B1-Motion>", move_window)
    draw()
    root.mainloop()


def parse_args():
    """解析命令行参数；预览和导出模式共用同一套参数。"""
    parser = argparse.ArgumentParser(description="渲染发光 3D 粒子爱心动画。")
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--fps", type=int, default=None)
    parser.add_argument("--duration", type=float, default=DURATION)
    parser.add_argument("--particles", type=int, default=None)
    parser.add_argument("--text", default=HEART_TEXT, help="爱心内部显示的文字。")
    parser.add_argument("--bg-alpha", type=float, default=BG_ALPHA, help="黑色背景强度，范围 0.0 到 1.0。")
    parser.add_argument("--window-alpha", type=float, default=WINDOW_ALPHA, help="实时预览窗口透明度，范围 0.15 到 1.0。")
    parser.add_argument("--windowed", action="store_true", help="实时预览时显示正常窗口标题栏。")
    parser.add_argument("--output", default="", help="指定 MP4 输出路径；不传则打开实时预览。")
    return parser.parse_args()


def main():
    """程序入口：根据是否传入 --output 决定导出视频还是打开预览。"""
    args = parse_args()
    if args.output:
        # 导出模式使用导出默认值；用户显式传入的宽高、帧率和粒子数会被保留。
        args.width = args.width or EXPORT_WIDTH
        args.height = args.height or EXPORT_HEIGHT
        args.fps = args.fps or EXPORT_FPS
        args.particles = args.particles or EXPORT_PARTICLES
        render_video(args)
    else:
        # 预览模式使用较轻量的默认值，确保普通机器上也能尽量保持流畅。
        args.width = args.width or PREVIEW_WIDTH
        args.height = args.height or PREVIEW_HEIGHT
        args.fps = args.fps or PREVIEW_FPS
        args.particles = args.particles or PREVIEW_PARTICLES
        play_live(args)


if __name__ == "__main__":
    main()
