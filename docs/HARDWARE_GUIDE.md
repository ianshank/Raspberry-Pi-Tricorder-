# Hardware Wiring Blueprint & Setup Guide

## Bill of Materials

| # | Component | Interface | I2C Addr / Bus | Purpose |
|---|-----------|-----------|----------------|---------|
| 1 | Raspberry Pi 5 (8GB) | - | - | Main compute board |
| 2 | Hailo-10H M.2 NPU | PCIe | - | Neural network acceleration |
| 3 | BME680 | I2C | 0x76 / bus 1 | Temp, humidity, pressure, VOC gas |
| 4 | MLX90640 | I2C | 0x33 / bus 1 | 24x32 thermal camera |
| 5 | AS7265x | I2C | 0x49 / bus 1 | 18-channel spectral sensor (UV/VIS/NIR) |
| 6 | MAX30102 | I2C | 0x57 / bus 1 | SpO2 + heart rate (red/IR LEDs) |
| 7 | ADS1263 | SPI | bus 0, dev 0 | 10-ch 32-bit ADC |
| 8 | HLK-LD2410 | UART | /dev/ttyAMA0 | 24GHz mmWave presence radar |
| 9 | TFmini-S | UART | /dev/ttyUSB0 | LiDAR time-of-flight (12m range) |
| 10 | MQ-2 gas sensor | ADC ch 0-1 | via ADS1263 | Smoke / LPG detection |
| 11 | MQ-7 gas sensor | ADC ch 2-3 | via ADS1263 | Carbon monoxide detection |
| 12 | MQ-135 gas sensor | ADC ch 4-5 | via ADS1263 | Air quality (NH3, NOx, benzene) |
| 13 | K-type thermocouple | ADC ch 6-7 | via ADS1263 | High-temp measurement |
| 14 | GSR sensor | ADC ch 8-9 | via ADS1263 | Galvanic skin response |

## Raspberry Pi 5 GPIO Pinout Reference

```
                    3V3  (1) (2)  5V
          I2C SDA - GP2  (3) (4)  5V
          I2C SCL - GP3  (5) (6)  GND
                    GP4  (7) (8)  GP14 - UART TX (LD2410)
                    GND  (9) (10) GP15 - UART RX (LD2410)
                    GP17 (11)(12) GP18
    ADS1263 DRDY - GP17 (11)(12) GP18
                    GP27 (13)(14) GND
   ADS1263 RESET - GP27 (13)
                    GP22 (15)(16) GP23
                    3V3  (17)(18) GP24
       SPI MOSI - GP10 (19)(20) GND
       SPI MISO -  GP9 (21)(22) GP25
       SPI SCLK - GP11 (23)(24) GP8  - SPI CE0 (ADS1263 CS)
                    GND  (25)(26) GP7
                    GP0  (27)(28) GP1
                    GP5  (29)(30) GND
                    GP6  (31)(32) GP12
                    GP13 (33)(34) GND
                    GP19 (35)(36) GP16
                    GP26 (37)(38) GP20
                    GND  (39)(40) GP21
```

## Wiring Diagram

### I2C Bus 1 (Shared Bus — All 4 Sensors)

```
Pi GPIO Header                    I2C Sensors
--------------                    -----------
Pin 1 (3.3V) ──────┬──────┬──────┬──── BME680 VCC
                    │      │      │
                    │      │      └──── MLX90640 VCC
                    │      │
                    │      └───────────── AS7265x VCC
                    │
                    └──────────────────── MAX30102 VCC

Pin 3 (SDA/GP2) ──────┬──────┬──────┬──── BME680 SDA
                       │      │      │
                       │      │      └──── MLX90640 SDA
                       │      │
                       │      └───────────── AS7265x SDA
                       │
                       └──────────────────── MAX30102 SDA

Pin 5 (SCL/GP3) ──────┬──────┬──────┬──── BME680 SCL
                       │      │      │
                       │      │      └──── MLX90640 SCL
                       │      │
                       │      └───────────── AS7265x SCL
                       │
                       └──────────────────── MAX30102 SCL

Pin 6 (GND) ──────┬──────┬──────┬──── BME680 GND
                   │      │      │
                   │      │      └──── MLX90640 GND
                   │      │
                   │      └───────────── AS7265x GND
                   │
                   └──────────────────── MAX30102 GND
```

> **Note:** All I2C sensors share a single bus. Each has a unique address
> so there are no conflicts. Use 4.7k pull-up resistors on SDA/SCL if the
> breakout boards do not include them.

### SPI Bus 0 — ADS1263 ADC

```
Pi GPIO Header                    ADS1263
--------------                    -------
Pin 2 (5V)         ──────────────── AVDD (analog supply)
Pin 17 (3.3V)      ──────────────── DVDD (digital supply)
Pin 19 (MOSI/GP10) ──────────────── DIN  (data in)
Pin 21 (MISO/GP9)  ──────────────── DOUT (data out)
Pin 23 (SCLK/GP11) ──────────────── SCLK
Pin 24 (CE0/GP8)   ──────────────── CS   (chip select)
Pin 11 (GP17)      ──────────────── DRDY (data ready interrupt)
Pin 13 (GP27)      ──────────────── RESET
Pin 25 (GND)       ──────────────── DGND + AGND
```

**ADC Channel Wiring:**

```
ADS1263                Gas/Analog Sensors
-------                ------------------
AIN0 (+) ◄──────────── MQ-2 analog out
AIN1 (-) ◄──────────── MQ-2 reference GND
AIN2 (+) ◄──────────── MQ-7 analog out
AIN3 (-) ◄──────────── MQ-7 reference GND
AIN4 (+) ◄──────────── MQ-135 analog out
AIN5 (-) ◄──────────── MQ-135 reference GND
AIN6 (+) ◄──────────── K-type thermocouple +
AIN7 (-) ◄──────────── K-type thermocouple -
AIN8 (+) ◄──────────── GSR sensor output
AIN9 (-) ◄──────────── GSR reference GND
```

> **Note:** MQ-series gas sensors require a heater supply (5V) and a load
> resistor on the analog output. See each sensor datasheet for the specific
> load resistor value.

### UART — Radar & LiDAR

```
Pi GPIO Header                    HLK-LD2410 (Radar)
--------------                    ------------------
Pin 4 (5V)         ──────────────── VCC
Pin 8 (TX/GP14)    ──────────────── RX
Pin 10 (RX/GP15)   ──────────────── TX
Pin 14 (GND)       ──────────────── GND

USB Port                          TFmini-S (LiDAR)
--------                          ----------------
USB-A port         ──── USB-UART adapter ──── TFmini-S
                   (appears as /dev/ttyUSB0)
```

> **Note:** The LD2410 uses the Pi's built-in UART at `/dev/ttyAMA0`.
> The TFmini-S connects via a USB-to-UART adapter (CH340/CP2102).
> On macOS, the TFmini-S appears as `/dev/tty.usbserial-*`.

### Hailo-10H NPU (M.2 HAT)

```
Pi 5 Board                        Hailo M.2 HAT
----------                        -------------
M.2 PCIe slot      ──────────────── Hailo-10H module
(via Raspberry Pi AI HAT+)
```

> Install via: `sudo apt install hailo-all`
> Verify: `hailortcli fw-control identify`

## Power Budget

| Component | Voltage | Typical Current | Notes |
|-----------|---------|-----------------|-------|
| Raspberry Pi 5 | 5V | 3A | Use official 27W PSU |
| Hailo-10H | 5V (via PCIe) | 1.5A peak | Shared with Pi PSU |
| BME680 | 3.3V | 12mA | Low power |
| MLX90640 | 3.3V | 23mA | During read |
| AS7265x | 3.3V | 100mA | LED illumination on |
| MAX30102 | 3.3V | 50mA | LEDs active |
| ADS1263 | 5V + 3.3V | 15mA | |
| HLK-LD2410 | 5V | 150mA | Continuous radar |
| TFmini-S | 5V | 120mA | Continuous ranging |
| MQ-2/7/135 | 5V | 150mA each | Heater element |
| **Total** | | **~4.5A** | **Use 5V 5A PSU** |

## Software Setup

### 1. Flash Raspberry Pi OS

```bash
# On your PC — write Raspberry Pi OS (64-bit) to SD card
# Use Raspberry Pi Imager: https://www.raspberrypi.com/software/

# Optional: pre-configure WiFi and SSH for headless setup
bash scripts/firstboot/firstboot-setup.sh /path/to/boot/partition
```

### 2. Enable Hardware Interfaces

```bash
# SSH into the Pi, then:
sudo raspi-config nonint do_i2c 0    # Enable I2C
sudo raspi-config nonint do_spi 0    # Enable SPI
sudo raspi-config nonint do_serial_hw 0  # Enable hardware UART
sudo raspi-config nonint do_serial 1     # Disable login shell on UART
sudo reboot
```

### 3. Verify Hardware Detection

```bash
# I2C — should show 0x33, 0x49, 0x57, 0x76
sudo i2cdetect -y 1

# SPI — should list spidev0.0
ls /dev/spidev*

# UART — should exist
ls /dev/ttyAMA0

# Hailo (if installed)
hailortcli fw-control identify
```

### 4. Install Tricorder

```bash
# Option A: Direct install (recommended for development)
git clone https://github.com/ianshank/Raspberry-Pi-Tricorder-.git
cd Raspberry-Pi-Tricorder-
pip install -e ".[hardware]"

# Option B: Automated deployment from remote machine
make deploy PI_HOST=<pi-ip-address>

# Option C: Docker deployment
make docker-build-arm64
make docker-save
# Copy .tar to Pi, then:
bash scripts/pi-load-image.sh /path/to/bundle

# Option D: SD card offline bundle (from Mac/Linux)
bash scripts/bundle-to-drive.sh /Volumes/SDCARD/tricorder-deploy
```

### 5. Run

```bash
# Development mode (simulated sensors, no hardware needed)
PYTHONPATH=src python -m mcp_server.server

# Production mode (real hardware)
TRICORDER__ENVIRONMENT=production PYTHONPATH=src python -m mcp_server.server

# As a systemd service (after make deploy)
sudo systemctl start tricorder-mcp
sudo systemctl status tricorder-mcp
journalctl -u tricorder-mcp -f
```

### 6. Verify

```bash
# Health check
curl http://localhost:8000/health

# Open the LCARS dashboard
open http://localhost:8000/ui/

# Run tests
PYTHONPATH=src python -m pytest tests/ --cov=src --cov-fail-under=85 -v
```

## Configuration

All hardware parameters are configured in `config/base.yaml`. Override per-environment:

```bash
# Mac development
TRICORDER_CONFIG_OVERLAY=config/mac.yaml PYTHONPATH=src python -m mcp_server.server

# Individual overrides via environment variables
TRICORDER__SENSORS__UART_DEVICES__HLK_LD2410__PORT=/dev/ttyUSB1
TRICORDER__LOGGING__LEVEL=DEBUG
```

## Troubleshooting

| Problem | Check |
|---------|-------|
| I2C sensor not detected | `sudo i2cdetect -y 1` — verify address |
| SPI no response | Check CS/DRDY/RESET GPIO wiring |
| UART no data | `sudo minicom -D /dev/ttyAMA0 -b 115200` |
| Hailo not found | `lspci` — verify M.2 HAT seated properly |
| Permission denied | Add user to `i2c,spi,dialout,gpio` groups |
| Sensor reads 0 | Check 3.3V/5V power, verify pull-ups on I2C |
