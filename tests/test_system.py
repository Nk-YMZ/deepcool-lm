from types import SimpleNamespace
import unittest

from deepcool_lm_system import (
    _normalize_cpu_identity,
    _normalize_gpu_model,
    _normalize_frequency,
    _normalize_temperature,
    _parse_pci_gpu_identities,
    _read_cpu_temperature,
    _read_gpu_temperature,
)


def sensor(label, current):
    return SimpleNamespace(label=label, current=current)


class SystemTests(unittest.TestCase):
    def test_cpu_identity_normalizes_current_and_legacy_models(self):
        cases = {
            "AMD Ryzen 9 9900X 12-Core Processor": ("AMD", "Ryzen 9 9900X"),
            "AMD Ryzen 7 PRO 8840U w/ Radeon 780M Graphics": (
                "AMD",
                "Ryzen 7 PRO 8840U",
            ),
            "13th Gen Intel(R) Core(TM) i9-13900K": (
                "Intel",
                "Core i9-13900K",
            ),
            "Intel(R) Xeon(R) CPU E5-2690 0 @ 2.90GHz": (
                "Intel",
                "Xeon E5-2690 0",
            ),
            "Intel(R) Pentium(R) CPU N3520 @ 2.16GHz": (
                "Intel",
                "Pentium N3520",
            ),
        }
        for raw_name, expected in cases.items():
            with self.subTest(raw_name=raw_name):
                self.assertEqual(_normalize_cpu_identity(raw_name), expected)

    def test_machine_readable_pci_output_detects_common_gpu_classes(self):
        output = "\n".join(
            (
                '0000:01:00.0 "VGA compatible controller" "NVIDIA Corporation" '
                '"AD102 [GeForce RTX 4070 Ti SUPER]"',
                '0000:03:00.0 "Display controller" '
                '"Advanced Micro Devices, Inc. [AMD/ATI]" '
                '"Navi 31 [Radeon RX 7900 XTX]"',
                '0000:04:00.0 "3D controller" "Intel Corporation" '
                '"DG2 [Arc A770]"',
            )
        )

        self.assertEqual(
            _parse_pci_gpu_identities(output),
            [
                ("NVIDIA", "RTX 4070 Ti SUPER"),
                ("AMD", "RX 7900 XTX"),
                ("Intel", "Arc A770"),
            ],
        )

    def test_ambiguous_amd_device_is_reduced_to_its_product_series(self):
        self.assertEqual(
            _normalize_gpu_model(
                "Navi 31 [Radeon RX 7900 XT/7900 XTX/7900M]", "AMD"
            ),
            "RX 7900 SERIES",
        )

    def test_cpu_temperature_prefers_die_and_package_sensors(self):
        self.assertEqual(
            _read_cpu_temperature(
                {
                    "k10temp": [
                        sensor("Tctl", 95),
                        sensor("Tdie", 75),
                    ]
                }
            ),
            75,
        )
        self.assertEqual(
            _read_cpu_temperature(
                {
                    "coretemp": [
                        sensor("Core 0", 45),
                        sensor("Package id 0", 70),
                    ]
                }
            ),
            70,
        )

    def test_gpu_temperature_uses_the_selected_brand(self):
        temperatures = {
            "amdgpu": [sensor("edge", 0)],
            "nouveau": [sensor("GPU core", 56)],
            "xe": [sensor("GPU", 41)],
        }

        self.assertEqual(_read_gpu_temperature(temperatures, "AMD"), 0)
        self.assertEqual(_read_gpu_temperature(temperatures, "NVIDIA"), 56)
        self.assertEqual(_read_gpu_temperature(temperatures, "Intel"), 41)

        temperatures["nouveau"] = [sensor("", 54)]
        self.assertEqual(_read_gpu_temperature(temperatures, "NVIDIA"), 54)

    def test_invalid_temperatures_are_rejected(self):
        for value in (None, "N/A", float("nan"), float("inf"), -101, 201):
            with self.subTest(value=value):
                self.assertIsNone(_normalize_temperature(value))

    def test_invalid_cpu_frequencies_are_rejected(self):
        for value in (None, "N/A", float("nan"), -1, 100_001):
            with self.subTest(value=value):
                self.assertIsNone(_normalize_frequency(value))


if __name__ == "__main__":
    unittest.main()
