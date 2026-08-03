import importlib.machinery
import importlib.util
from pathlib import Path
import socket
import unittest


def load_driver():
    path = Path(__file__).resolve().parents[1] / "deepcool-lm"
    loader = importlib.machinery.SourceFileLoader("deepcool_lm_driver", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FakeUSBDevice:
    def __init__(self):
        self.writes = []

    def write(self, endpoint, data, timeout):
        self.writes.append((endpoint, data, timeout))
        return len(data)


class DriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = load_driver()

    def test_frame_protocol_and_order_are_unchanged(self):
        usb_device = FakeUSBDevice()
        display = self.driver.LMDisplay()
        display.device = usb_device
        framebuffer = bytes(self.driver.FRAMEBUFFER_SIZE)

        display.send_frame(framebuffer)

        self.assertEqual(
            self.driver.FRAME_HEADER,
            bytes.fromhex("aa08000001005802002c01bc11"),
        )
        self.assertEqual(
            usb_device.writes,
            [
                (0x01, self.driver.FRAME_HEADER, 5000),
                (0x01, framebuffer, 5000),
            ],
        )

    def test_brightness_commands_are_unchanged(self):
        usb_device = FakeUSBDevice()
        display = self.driver.LMDisplay()
        display.device = usb_device

        display.brightness_up()
        display.brightness_down()

        self.assertEqual(usb_device.writes[0][1], bytes.fromhex("aa040006036100d246"))
        self.assertEqual(usb_device.writes[1][1], bytes.fromhex("aa040006031d00e60b"))

    def test_image_ipc_action_is_rejected(self):
        server_connection, client_connection = socket.socketpair()
        client_connection.sendall(b'{"action":"image"}')
        client_connection.shutdown(socket.SHUT_WR)

        server = self.driver.IPCServer(FakeUSBDevice(), self.driver.DisplayState())
        server._handle(server_connection)
        response = client_connection.recv(4096)
        client_connection.close()

        self.assertIn(b'"status": "error"', response)

    def test_disconnected_ipc_client_does_not_raise(self):
        server_connection, client_connection = socket.socketpair()
        client_connection.close()

        server = self.driver.IPCServer(FakeUSBDevice(), self.driver.DisplayState())
        server._handle(server_connection)


if __name__ == "__main__":
    unittest.main()
