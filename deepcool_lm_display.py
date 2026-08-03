"""Deepcool LM 屏幕的纯 PIL 绘制和 RGB565 编码。"""

from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont


WIDTH = 320
HEIGHT = 240
FRAMEBUFFER_SIZE = WIDTH * HEIGHT * 2

_REGULAR_FONT_PATHS = (
    "/usr/share/fonts/TTF/DejaVuSansCondensed.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
_BOLD_FONT_PATHS = (
    "/usr/share/fonts/TTF/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)

INK = (8, 10, 11)
PAPER = (244, 246, 246)
SIGNAL = (24, 209, 255)
MUTED = (92, 101, 105)
RULE = (199, 205, 207)


def load_fonts():
    regular = _find_font(_REGULAR_FONT_PATHS)
    bold = _find_font(_BOLD_FONT_PATHS)
    if regular and bold:
        return {
            "temperature": ImageFont.truetype(bold, 44),
            "model": ImageFont.truetype(bold, 24),
            "data": ImageFont.truetype(bold, 16),
            "label": ImageFont.truetype(regular, 11),
            "micro": ImageFont.truetype(bold, 10),
        }

    default = ImageFont.load_default()
    return {
        key: default
        for key in ("temperature", "model", "data", "label", "micro")
    }


def render_monitor_image(snapshot, fonts=None):
    """根据完整系统快照生成固定 320x240 RGB 图像。"""
    fonts = fonts or load_fonts()
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, WIDTH - 1, 27), fill=INK)
    draw.rectangle((0, 0, 3, 27), fill=SIGNAL)
    draw.text((16, 8), "SYSTEM / MONITOR", fill=PAPER, font=fonts["micro"])
    draw.rectangle((264, 11, 269, 16), fill=SIGNAL)
    draw.text((276, 8), "LIVE", fill=PAPER, font=fonts["micro"])

    draw.text((16, 39), "01 / CPU", fill=MUTED, font=fonts["micro"])
    cpu_model = _format_cpu_model(snapshot.cpu_model)
    cpu_temp = _format_temperature(snapshot.cpu_temp)
    cpu_temp_width = _text_width(draw, cpu_temp, fonts["temperature"])
    cpu_temp_x = WIDTH - 16 - cpu_temp_width
    cpu_font = _fit_font(
        draw, cpu_model, fonts["model"], cpu_temp_x - 28, minimum_size=15
    )
    draw.text((16, 57), cpu_model, fill=INK, font=cpu_font)
    _draw_right_text(
        draw,
        cpu_temp,
        WIDTH - 16,
        42,
        INK,
        fonts["temperature"],
    )

    draw.text((16, 101), "LOAD", fill=MUTED, font=fonts["micro"])
    draw.text(
        (51, 96),
        _format_percent(snapshot.cpu_percent),
        fill=INK,
        font=fonts["data"],
    )
    draw.line((91, 96, 91, 114), fill=RULE)
    draw.text((104, 101), "CLOCK", fill=MUTED, font=fonts["micro"])
    draw.text(
        (151, 96),
        _format_frequency(snapshot.cpu_freq),
        fill=INK,
        font=fonts["data"],
    )
    draw.line((16, 127, WIDTH - 16, 127), fill=RULE)
    draw.line((16, 127, 58, 127), fill=SIGNAL, width=2)

    draw.text((16, 141), "02 / GPU", fill=MUTED, font=fonts["micro"])
    gpu_temp_text = _format_temperature(snapshot.gpu_temp)
    gpu_temp_width = _text_width(draw, gpu_temp_text, fonts["temperature"])
    gpu_temp_x = WIDTH - 16 - gpu_temp_width
    gpu_model_width = gpu_temp_x - 28
    gpu_model, gpu_suffix = _split_gpu_model(snapshot.gpu_model)
    gpu_model_font = _fit_font(
        draw, gpu_model, fonts["model"], gpu_model_width, minimum_size=15
    )
    draw.text((16, 159), gpu_model, fill=INK, font=gpu_model_font)
    if gpu_suffix:
        suffix_font = _fit_font(
            draw, gpu_suffix, fonts["data"], gpu_model_width, minimum_size=11
        )
        draw.text(
            (16, 188),
            gpu_suffix,
            fill=MUTED,
            font=suffix_font,
        )
    _draw_right_text(
        draw,
        gpu_temp_text,
        WIDTH - 16,
        151,
        INK,
        fonts["temperature"],
    )

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


def _find_font(paths):
    return next((path for path in paths if Path(path).is_file()), None)


def _fit_font(draw, text, font, max_width, minimum_size):
    """缩小字体以保留完整型号，不通过截断换取空间。"""
    if _text_width(draw, text, font) <= max_width or not hasattr(font, "font_variant"):
        return font
    for size in range(font.size - 1, minimum_size - 1, -1):
        candidate = font.font_variant(size=size)
        if _text_width(draw, text, candidate) <= max_width:
            return candidate
    return font.font_variant(size=minimum_size)


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


def _format_temperature(value):
    return "N/A" if value is None else f"{value:.0f}°"


def _format_percent(value):
    return "N/A" if value is None else f"{value:.0f}%"


def _format_frequency(value):
    return "N/A" if value is None else f"{value:.2f} GHz"
