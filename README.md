# OAK-D Pi Recorder

Minimal recording setup for Raspberry Pi with OAK-D camera.

## Quick Setup

```bash
# Clone the repo
git clone https://github.com/YOUR_REPO/asimov.git
cd asimov/pi-recorder

# Clone the hand tracker submodule
git clone https://github.com/geaxgx/depthai_hand_tracker.git hand_tracker

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Manual Recording

```bash
# Activate venv
source venv/bin/activate

# Start recording (runs until Ctrl+C)
python record.py

# Or specify options
python record.py --recordings-dir /path/to/recordings --session-duration 1800
```

## Auto-Start on Boot (systemd)

Create a service file:

```bash
sudo nano /etc/systemd/system/oakd-recorder.service
```

Add this content:

```ini
[Unit]
Description=OAK-D Recorder
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/asimov/pi-recorder
ExecStart=/home/pi/asimov/pi-recorder/venv/bin/python /home/pi/asimov/pi-recorder/record.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable oakd-recorder
sudo systemctl start oakd-recorder

# Check status
sudo systemctl status oakd-recorder

# View logs
journalctl -u oakd-recorder -f
```

## Output Format

Each session creates a folder: `recordings/session_YYYYMMDD_HHMMSS/`

Contents:
- `rgb_frames/` - JPEG frames (frame_000000.jpg, frame_000001.jpg, ...)
- `hand_poses.json` - Hand landmarks (2D pixels + 3D meters) and palm positions
- `camera_info.json` - Camera intrinsics
- `metadata.json` - Recording metadata (duration, FPS, etc.)

## Processing Later

Copy recordings to your main machine:

```bash
# From your main machine
scp -r pi@raspberrypi:~/asimov/pi-recorder/recordings ./

# Then process with the full pipeline
cd oakd-v2-processor
python visualize_rerun.py ../pi-recorder/recordings/session_XXXXXXXX_XXXXXX
```

## Disk Space

- Each frame is ~100-200KB (JPEG quality 85)
- At 15 FPS: ~1.5-3 MB/second, ~5-10 GB/hour
- The recorder automatically stops if disk usage exceeds 90%

## Troubleshooting

**OAK-D not detected:**
```bash
# Check USB connection
lsusb | grep Luxonis

# Try different USB port (use USB 3.0 if available)
```

**Permission denied:**
```bash
# Add udev rules for OAK-D
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' | sudo tee /etc/udev/rules.d/80-movidius.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```
