#!/bin/bash
# Setup script for OAK-D Pi Recorder

set -e

echo "==================================="
echo "OAK-D Pi Recorder Setup"
echo "==================================="

# Check if running on Raspberry Pi
if [[ ! -f /proc/device-tree/model ]] || ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    echo "Warning: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Clone hand tracker if not present
if [ ! -d "hand_tracker" ]; then
    echo "Cloning hand tracker..."
    git clone https://github.com/geaxgx/depthai_hand_tracker.git hand_tracker
else
    echo "Hand tracker already present"
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
else
    echo "Virtual environment already exists"
fi

# Activate and install dependencies
echo "Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create recordings directory
mkdir -p recordings

# Setup udev rules for OAK-D
echo "Setting up OAK-D udev rules..."
if [ ! -f /etc/udev/rules.d/80-movidius.rules ]; then
    echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' | sudo tee /etc/udev/rules.d/80-movidius.rules
    sudo udevadm control --reload-rules && sudo udevadm trigger
    echo "Udev rules installed. You may need to reconnect OAK-D."
else
    echo "Udev rules already present"
fi

echo ""
echo "==================================="
echo "Setup complete!"
echo "==================================="
echo ""
echo "To start recording:"
echo "  source venv/bin/activate"
echo "  python record.py"
echo ""
echo "To install as a service (auto-start on boot):"
echo "  sudo cp oakd-recorder.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable oakd-recorder"
echo "  sudo systemctl start oakd-recorder"
