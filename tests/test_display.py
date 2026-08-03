import unittest

from PIL import Image

from deepcool_lm_display import (
    DARK_INK,
    DARK_PAPER,
    DARK_RULE,
    DARK_SIGNAL,
    FRAMEBUFFER_SIZE,
    INK,
    PAPER,
    RULE,
    SIGNAL,
    THEME_DARK,
    _format_cpu_model,
    _split_gpu_model,
    framebuffer_to_rgb_image,
    render_monitor_image,
    render_monitor_framebuffer,
    rgb_to_framebuffer,
)
from deepcool_lm_system import SystemSnapshot


class DisplayTests(unittest.TestCase):
    def test_monitor_image_has_protocol_dimensions(self):
        snapshot = SystemSnapshot(
            cpu_brand="AMD",
            cpu_model="Ryzen 9 9950X3D",
            cpu_temp=72,
            cpu_percent=85,
            cpu_freq=5.2,
            gpu_brand="NVIDIA",
            gpu_model="RTX 5090",
            gpu_temp=65,
        )

        image = render_monitor_image(snapshot)

        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.size, (320, 240))

    def test_minimal_ark_palette_uses_light_paper_and_one_signal_color(self):
        image = render_monitor_image(SystemSnapshot())

        self.assertEqual(image.getpixel((319, 239)), PAPER)
        self.assertEqual(image.getpixel((240, 10)), INK)
        self.assertEqual(image.getpixel((1, 10)), SIGNAL)

    def test_dark_theme_inverts_surface_and_text_without_changing_signal(self):
        image = render_monitor_image(SystemSnapshot(), theme=THEME_DARK)

        self.assertEqual(image.getpixel((319, 239)), DARK_PAPER)
        self.assertEqual(image.getpixel((240, 10)), DARK_INK)
        self.assertEqual(image.getpixel((1, 10)), DARK_SIGNAL)

    def test_section_divider_is_a_uniform_rule_in_both_themes(self):
        light = render_monitor_image(SystemSnapshot())
        dark = render_monitor_image(SystemSnapshot(), theme=THEME_DARK)

        for x in (16, 58, 160, 304):
            self.assertEqual(light.getpixel((x, 127)), RULE)
            self.assertEqual(dark.getpixel((x, 127)), DARK_RULE)

    def test_unknown_theme_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "未知主题"):
            render_monitor_image(SystemSnapshot(), theme="unknown")

    def test_missing_metrics_can_be_rendered(self):
        image = render_monitor_image(SystemSnapshot())

        self.assertEqual(image.size, (320, 240))

    def test_rgb565_is_little_endian_and_exact_length(self):
        colors = {
            (255, 0, 0): b"\x00\xf8",
            (0, 255, 0): b"\xe0\x07",
            (0, 0, 255): b"\x1f\x00",
        }
        for color, expected_pixel in colors.items():
            with self.subTest(color=color):
                framebuffer = rgb_to_framebuffer(Image.new("RGB", (320, 240), color))
                self.assertEqual(len(framebuffer), FRAMEBUFFER_SIZE)
                self.assertEqual(framebuffer[:2], expected_pixel)
                self.assertEqual(framebuffer[-2:], expected_pixel)

    def test_framebuffer_resizes_non_rgb_input(self):
        framebuffer = rgb_to_framebuffer(Image.new("L", (10, 10), 255))

        self.assertEqual(len(framebuffer), FRAMEBUFFER_SIZE)

    def test_hardware_models_use_compact_layout_without_ellipsis(self):
        self.assertEqual(_format_cpu_model("Ryzen 9 9900X"), "R9 9900X")
        self.assertEqual(
            _split_gpu_model("RTX 4070 Ti SUPER"),
            ("RTX 4070", "Ti SUPER"),
        )

    def test_preview_decodes_the_exact_usb_framebuffer(self):
        snapshot = SystemSnapshot(
            cpu_brand="AMD",
            cpu_model="Ryzen 9 9900X",
            cpu_temp=62,
            cpu_percent=2,
            cpu_freq=5.12,
            gpu_brand="NVIDIA",
            gpu_model="RTX 4070 Ti SUPER",
            gpu_temp=42,
        )

        framebuffer = render_monitor_framebuffer(snapshot)
        preview = framebuffer_to_rgb_image(framebuffer)

        self.assertEqual(len(framebuffer), FRAMEBUFFER_SIZE)
        self.assertEqual(preview.mode, "RGB")
        self.assertEqual(preview.size, (320, 240))
        self.assertEqual(rgb_to_framebuffer(preview), framebuffer)


if __name__ == "__main__":
    unittest.main()
