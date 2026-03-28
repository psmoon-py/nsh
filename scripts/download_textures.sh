#!/bin/bash
# Download Earth textures for the 3D globe visualization
# Run this once: bash scripts/download_textures.sh

TEXTURE_DIR="frontend/public/textures"
mkdir -p "$TEXTURE_DIR"

echo "Downloading Earth textures..."

# Day map (Blue Marble)
if [ ! -f "$TEXTURE_DIR/earth_daymap.jpg" ]; then
  curl -L -o "$TEXTURE_DIR/earth_daymap.jpg" \
    "https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
  echo "  ✓ earth_daymap.jpg"
else
  echo "  ✓ earth_daymap.jpg (already exists)"
fi

# Night map (city lights)
if [ ! -f "$TEXTURE_DIR/earth_nightmap.jpg" ]; then
  curl -L -o "$TEXTURE_DIR/earth_nightmap.jpg" \
    "https://unpkg.com/three-globe/example/img/earth-night.jpg"
  echo "  ✓ earth_nightmap.jpg"
else
  echo "  ✓ earth_nightmap.jpg (already exists)"
fi

# Clouds
if [ ! -f "$TEXTURE_DIR/earth_clouds.png" ]; then
  curl -L -o "$TEXTURE_DIR/earth_clouds.png" \
    "https://unpkg.com/three-globe/example/img/earth-water.png"
  echo "  ✓ earth_clouds.png"
else
  echo "  ✓ earth_clouds.png (already exists)"
fi

echo "Done! Textures saved to $TEXTURE_DIR"
