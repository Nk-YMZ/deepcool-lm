pkgname=deepcool-lm
pkgver=1.3.0
pkgrel=1
pkgdesc="Linux driver for Deepcool LM series AIO coolers with LCD display (tested on LM360)"
arch=('any')
url="https://github.com/daedlock/deepcool-lm"
license=('MIT')
depends=(
    'python'
    'python-pyusb'
    'python-psutil'
    'python-pillow'
    'lm_sensors'
    'ttf-dejavu'
    'pciutils'
    'usbutils'
)
backup=('etc/systemd/system/deepcool-lm.service')
install=deepcool-lm.install
source=(
    "deepcool-lm"
    "deepcool_lm_display.py"
    "deepcool_lm_system.py"
    "deepcool-lm.service"
)
sha256sums=('SKIP'
            'SKIP'
            'SKIP'
            'SKIP')

package() {
    install -Dm755 "${srcdir}/deepcool-lm" "${pkgdir}/usr/bin/deepcool-lm"
    install -Dm644 "${srcdir}/deepcool_lm_display.py" "${pkgdir}/usr/lib/deepcool-lm/deepcool_lm_display.py"
    install -Dm644 "${srcdir}/deepcool_lm_system.py" "${pkgdir}/usr/lib/deepcool-lm/deepcool_lm_system.py"
    install -Dm644 "${srcdir}/deepcool-lm.service" "${pkgdir}/etc/systemd/system/deepcool-lm.service"
}
