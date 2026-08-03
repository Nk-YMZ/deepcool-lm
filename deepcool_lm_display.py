"""Deepcool LM 屏幕的纯 PIL 绘制和 RGB565 编码。"""

from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont


WIDTH = 320
HEIGHT = 240
FRAMEBUFFER_SIZE = WIDTH * HEIGHT * 2

_REGULAR_FONT_PATHS = (
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
_BOLD_FONT_PATHS = (
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def load_fonts():
    regular = _find_font(_REGULAR_FONT_PATHS)
    bold = _find_font(_BOLD_FONT_PATHS)
    if regular and bold:
        return {
            "large": ImageFont.truetype(bold, 40),
            "normal": ImageFont.truetype(regular, 26),
            "small": ImageFont.truetype(regular, 20),
        }

    default = ImageFont.load_default()
    return {"large": default, "normal": default, "small": default}


def render_monitor_image(snapshot, fonts=None):
    """根据完整系统快照生成固定 320x240 RGB 图像。"""
    fonts = fonts or load_fonts()
    image = Image.new("RGB", (WIDTH, HEIGHT), (14, 14, 18))
    draw = ImageDraw.Draw(image)

    cpu_brand_color = get_brand_color(snapshot.cpu_brand)
    cpu_temp_color = get_temp_color(snapshot.cpu_temp)
    usage_color = get_usage_color(snapshot.cpu_percent)
    frequency_color = get_frequency_color(snapshot.cpu_freq)
    gpu_brand_color = get_brand_color(snapshot.gpu_brand)
    gpu_temp_color = get_temp_color(snapshot.gpu_temp)

    draw.rounded_rectangle(
        (12, 10, 308, 125), radius=8, outline=(40, 40, 50), width=2
    )
    cpu_model = _format_cpu_model(snapshot.cpu_model)
    cpu_label = _fit_text(draw, f"⚙ {cpu_model}", fonts["normal"], 200, ellipsis=False)
    draw.text((20, 22), cpu_label, fill=cpu_brand_color, font=fonts["normal"])
    _draw_right_text(
        draw,
        _format_temperature(snapshot.cpu_temp),
        300,
        20,
        cpu_temp_color,
        fonts["large"],
    )

    usage_label = "Usage:"
    draw.text((20, 68), usage_label, fill=_dim(cpu_brand_color, 30), font=fonts["small"])
    usage_x = 20 + _text_width(draw, usage_label, fonts["small"]) + 6
    usage_text = _format_percent(snapshot.cpu_percent)
    draw.text((usage_x, 68), usage_text, fill=usage_color, font=fonts["small"])
    separator_x = usage_x + _text_width(draw, usage_text, fonts["small"]) + 6
    draw.text((separator_x, 68), "•", fill=(130, 130, 150), font=fonts["small"])
    frequency_x = separator_x + _text_width(draw, "•", fonts["small"]) + 6
    draw.text(
        (frequency_x, 68),
        _format_frequency(snapshot.cpu_freq),
        fill=frequency_color,
        font=fonts["small"],
    )
    _draw_progress_bar(draw, 23, 93, 274, 18, snapshot.cpu_temp, cpu_temp_color)

    draw.rounded_rectangle(
        (12, 135, 308, 230), radius=8, outline=(40, 40, 50), width=2
    )
    gpu_temp_text = _format_temperature(snapshot.gpu_temp)
    gpu_temp_width = _text_width(draw, gpu_temp_text, fonts["large"])
    gpu_model_width = max(40, WIDTH - 40 - gpu_temp_width - 12)
    gpu_model, gpu_suffix = _split_gpu_model(snapshot.gpu_model)
    gpu_label = _fit_text(
        draw, f"▣ {gpu_model}", fonts["normal"], gpu_model_width, ellipsis=False
    )
    draw.text((20, 145), gpu_label, fill=gpu_brand_color, font=fonts["normal"])
    if gpu_suffix:
        icon_width = _text_width(draw, "▣ ", fonts["normal"])
        draw.text(
            (20 + icon_width, 171),
            gpu_suffix,
            fill=gpu_brand_color,
            font=fonts["small"],
        )
    _draw_right_text(
        draw,
        gpu_temp_text,
        300,
        145,
        gpu_temp_color,
        fonts["large"],
    )
    _draw_progress_bar(draw, 23, 200, 274, 18, snapshot.gpu_temp, gpu_temp_color)

    return image


def render_monitor_framebuffer(snapshot, fonts=None):
    """生成正式 USB 传输使用的最终 RGB565 framebuffer。"""
    return rgb_to_framebuffer(render_monitor_image(snapshot, fonts))


def render_solid_image(color):
    return Image.new("RGB", (WIDTH, HEIGHT), color=tuple(color))


def rgb_to_framebuffer(image):
    """转换为设备要求的 320x240 小端 RGB565 数据。"""
    if image.mode != "RGB":
        image = image.convert("RGB")
    if image.size != (WIDTH, HEIGHT):
        image = image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)

    framebuffer = bytearray(FRAMEBUFFER_SIZE)
    pixels = image.tobytes()
    for pixel_offset in range(0, len(pixels), 3):
        red, green, blue = pixels[pixel_offset : pixel_offset + 3]
        rgb565 = ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
        offset = pixel_offset // 3 * 2
        framebuffer[offset] = rgb565 & 0xFF
        framebuffer[offset + 1] = rgb565 >> 8
    return bytes(framebuffer)


def framebuffer_to_rgb_image(framebuffer):
    """把设备 framebuffer 解码为预览图，不重新执行任何布局逻辑。"""
    if len(framebuffer) != FRAMEBUFFER_SIZE:
        raise ValueError(
            f"帧缓冲区长度错误: {len(framebuffer)}，应为 {FRAMEBUFFER_SIZE}"
        )

    pixels = bytearray(WIDTH * HEIGHT * 3)
    for source_offset in range(0, FRAMEBUFFER_SIZE, 2):
        rgb565 = framebuffer[source_offset] | (framebuffer[source_offset + 1] << 8)
        red5 = (rgb565 >> 11) & 0x1F
        green6 = (rgb565 >> 5) & 0x3F
        blue5 = rgb565 & 0x1F
        target_offset = source_offset // 2 * 3
        pixels[target_offset] = (red5 << 3) | (red5 >> 2)
        pixels[target_offset + 1] = (green6 << 2) | (green6 >> 4)
        pixels[target_offset + 2] = (blue5 << 3) | (blue5 >> 2)
    return Image.frombytes("RGB", (WIDTH, HEIGHT), bytes(pixels))


def get_brand_color(brand):
    return {
        "AMD": (255, 50, 50),
        "Intel": (100, 150, 255),
        "NVIDIA": (100, 255, 100),
    }.get(brand, (150, 150, 150))


def get_temp_color(value):
    if value is None:
        return (130, 130, 150)
    if value < 40:
        return (100, 200, 255)
    if value < 60:
        return (100, 255, 100)
    if value < 75:
        return (255, 220, 50)
    if value < 85:
        return (255, 140, 0)
    return (255, 50, 50)


def get_usage_color(value):
    if value is None:
        return (130, 130, 150)
    if value < 30:
        return (100, 200, 255)
    if value < 60:
        return (100, 255, 100)
    if value < 85:
        return (255, 220, 50)
    return (255, 50, 50)


def get_frequency_color(value):
    if value is None:
        return (130, 130, 150)
    if value < 3.5:
        return (100, 200, 255)
    if value < 4.5:
        return (100, 255, 100)
    if value < 5.2:
        return (255, 220, 50)
    return (255, 50, 50)


def _find_font(paths):
    return next((path for path in paths if Path(path).is_file()), None)


def _fit_text(draw, text, font, max_width, ellipsis=True):
    if _text_width(draw, text, font) <= max_width:
        return text
    shortened = text
    suffix = "..." if ellipsis else ""
    while shortened and _text_width(draw, f"{shortened}{suffix}", font) > max_width:
        shortened = shortened[:-1]
    return f"{shortened.rstrip()}{suffix}" if shortened else suffix


def _format_cpu_model(model):
    model = (model or "Unknown").strip()
    model = re.sub(r"^Ryzen\s+(\d)\s+", r"R\1 ", model)
    model = re.sub(r"^Core\s+", "", model)
    return model


def _split_gpu_model(model):
    model = (model or "Unknown").strip()
    model = re.sub(r"^(?:NVIDIA\s+)?(?:GeForce\s+)?", "", model)
    match = re.match(r"^(.*?\d)\s+(Ti(?:\s+SUPER)?|SUPER|XTX|XT|GRE)$", model, re.I)
    if not match:
        return model, ""
    return match.group(1), match.group(2)


def _text_width(draw, text, font):
    bounds = draw.textbbox((0, 0), text, font=font)
    return bounds[2] - bounds[0]


def _draw_right_text(draw, text, right, y, color, font):
    draw.text((right - _text_width(draw, text, font), y), text, fill=color, font=font)


def _draw_progress_bar(draw, x, y, width, height, value, color):
    radius = height // 2
    draw.rounded_rectangle(
        (x, y, x + width, y + height), radius=radius, fill=(30, 30, 38)
    )
    if value is None:
        return
    fill_width = int(width * min(max(value, 0.0), 100.0) / 100.0)
    if fill_width >= radius * 2:
        draw.rounded_rectangle(
            (x, y, x + fill_width, y + height), radius=radius, fill=color
        )


def _format_temperature(value):
    return "N/A" if value is None else f"{value:.0f}°"


def _format_percent(value):
    return "N/A" if value is None else f"{value:.0f}%"


def _format_frequency(value):
    return "N/A" if value is None else f"{value:.2f} GHz"


def _dim(color, amount):
    return tuple(max(0, channel - amount) for channel in color)
