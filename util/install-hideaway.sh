#!/usr/bin/env bash
set -euo pipefail
set -x

if command -v hideaway >/dev/null 2>&1; then
    echo "Hideaway is already installed. Exiting."
    exit 0
fi

apt install -y interception-tools interception-tools-compat cmake git
git clone https://gitlab.com/interception/linux/plugins/hideaway.git /tmp/hideaway

cd /tmp/hideaway
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
cp ./build/hideaway /usr/local/bin
chmod +x /usr/local/bin/hideaway

cat <<'EOF' >> /etc/interception/udevmon.d/config.yaml
- JOB: intercept $DEVNODE | hideaway 4 10000 10000 -512 -256 | uinput -d $DEVNODE
  DEVICE:
    EVENTS:
      EV_REL: [REL_X, REL_Y]
EOF

systemctl restart udevmon

echo "Installed Hideaway."
