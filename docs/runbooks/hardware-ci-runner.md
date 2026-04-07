# Hardware CI Runner Setup

Self-hosted GitHub Actions runner on a Raspberry Pi 5 for executing
hardware-in-the-loop sensor tests.

---

## 1. Prerequisites

| Requirement | Details |
|---|---|
| Board | Raspberry Pi 5 (4 GB+ RAM) |
| OS | Raspberry Pi OS 64-bit (Bookworm) |
| Python | 3.11+ via system package or pyenv |
| Sensors | BME680, BNO055, INA219 (or whichever sensors the test suite covers) wired and responding on the expected bus |
| Network | Outbound HTTPS to `github.com` and `api.github.com` |

Enable the required buses before continuing:

```bash
sudo raspi-config nonint do_i2c 0   # enable I2C
sudo raspi-config nonint do_spi 0   # enable SPI
sudo raspi-config nonint do_serial_hw 0  # enable UART
```

Verify with:

```bash
i2cdetect -y 1          # should show sensor addresses
ls /dev/spidev0.*       # SPI devices
ls /dev/ttyAMA0         # UART
```

---

## 2. Runner Installation

Create a dedicated user and install the GitHub Actions runner:

```bash
sudo useradd -m -s /bin/bash ghrunner
sudo usermod -aG i2c,spi,dialout,gpio ghrunner
sudo su - ghrunner

mkdir actions-runner && cd actions-runner
curl -o actions-runner-linux-arm64-2.321.0.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.321.0/actions-runner-linux-arm64-2.321.0.tar.gz
tar xzf ./actions-runner-linux-arm64-2.321.0.tar.gz
```

Register the runner (use a scoped PAT or fine-grained token):

```bash
./config.sh \
  --url https://github.com/<org>/<repo> \
  --token <REGISTRATION_TOKEN> \
  --labels rpi5 \
  --name tricorder-hw-runner \
  --work _work
```

---

## 3. Systemd Service

Install and start the runner as a systemd service so it survives reboots:

```bash
sudo ./svc.sh install ghrunner
sudo ./svc.sh start
sudo ./svc.sh status
```

Logs are available via:

```bash
journalctl -u actions.runner.<org>-<repo>.tricorder-hw-runner -f
```

---

## 4. Security

| Concern | Mitigation |
|---|---|
| Privilege | Run as unprivileged `ghrunner` user; grant only `i2c`, `spi`, `dialout`, `gpio` group membership |
| Token scope | Use a fine-grained PAT scoped to the single repository with `actions:write` only |
| Secrets | Never store application secrets on the Pi; use GitHub Actions secrets for anything sensitive |
| Network | Restrict inbound traffic with `ufw`; allow only outbound HTTPS (443) |
| Updates | Keep the runner binary and OS packages up to date (`sudo apt update && sudo apt upgrade`) |

---

## 5. Sensor Wiring Reference

### I2C (Bus 1 — GPIO 2 SDA, GPIO 3 SCL)

| Sensor | Default Address |
|---|---|
| BME680 | 0x76 (or 0x77) |
| BNO055 | 0x28 (or 0x29) |
| INA219 | 0x40 |
| ADS1115 | 0x48 |
| PMSA003I | 0x12 |

### SPI (Bus 0 — GPIO 10 MOSI, GPIO 9 MISO, GPIO 11 SCLK)

| Sensor | CS Pin |
|---|---|
| MCP3008 | CE0 (GPIO 8) |
| MAX31855 | CE1 (GPIO 7) |

### UART (/dev/ttyAMA0 — GPIO 14 TX, GPIO 15 RX)

| Sensor | Baud Rate |
|---|---|
| GPS (NEO-6M / NEO-M8N) | 9600 |

---

## 6. Troubleshooting

### Runner not picking up jobs

1. Confirm the runner service is active: `sudo ./svc.sh status`
2. Check that the workflow uses `runs-on: [self-hosted, rpi5]` and the runner
   has the `rpi5` label.
3. Review runner logs: `journalctl -u actions.runner.* --since "10 min ago"`

### I2C sensor not detected

1. Run `i2cdetect -y 1` and verify the expected address appears.
2. Check wiring — SDA/SCL may be swapped.
3. Ensure the `ghrunner` user is in the `i2c` group: `groups ghrunner`.

### SPI device permission denied

1. Add `ghrunner` to the `spi` group: `sudo usermod -aG spi ghrunner`
2. Log out and back in (or restart the runner service).

### Tests skipped with "bus module not available"

Install the required Python packages in the runner's virtualenv:

```bash
pip install smbus2 spidev pyserial
```

Or install the project with the hardware extra:

```bash
pip install -e ".[hardware]"
```

### High test flakiness / intermittent failures

- Sensor wires may have a loose connection — reseat jumper cables.
- Add pull-up resistors (4.7 kΩ) on I2C SDA/SCL if not already present.
- Increase bus timeout or retry count in the sensor driver configuration.
