#!/usr/bin/env python3
"""Generate the RARNinja app icon with zero dependencies.

Draws a rounded-rectangle gradient badge with a white ninja throwing-star
(shuriken) and writes assets/icon_1024.png. On macOS it also packs a full
.icns via sips + iconutil. Run: python3 scripts/make_icon.py
"""
import math
import os
import struct
import subprocess
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
SIZE = 1024
SS = 2                      # supersample factor for smooth edges
R = SIZE * SS

TOP = (79, 70, 229)        # indigo  #4f46e5
BOT = (37, 99, 235)        # blue    #2563eb
STAR = (250, 250, 252)


def _star_vertices(cx, cy, ro, ri, spikes=4):
    verts = []
    for k in range(spikes * 2):
        ang = math.pi * k / spikes            # 0,45,90,... degrees
        r = ro if k % 2 == 0 else ri
        verts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return verts


def _in_poly(x, y, verts):
    inside = False
    n = len(verts)
    j = n - 1
    for i in range(n):
        xi, yi = verts[i]
        xj, yj = verts[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def render():
    rad = 0.225 * R
    cx = cy = R / 2.0
    ro, ri, hole = 0.40 * R, 0.16 * R, 0.085 * R
    verts = _star_vertices(cx, cy, ro, ri)
    bbox = ro + 2                      # star lives within +/- ro of centre

    # internal RGBA buffer as list of [r,g,b,a]
    buf = bytearray(R * R * 4)
    for y in range(R):
        t = y / (R - 1)
        gr = (int(TOP[0] + (BOT[0] - TOP[0]) * t),
              int(TOP[1] + (BOT[1] - TOP[1]) * t),
              int(TOP[2] + (BOT[2] - TOP[2]) * t))
        row = y * R * 4
        for x in range(R):
            # rounded-rect membership
            dx = max(rad - x, x - (R - rad), 0)
            dy = max(rad - y, y - (R - rad), 0)
            inside = (dx * dx + dy * dy) <= rad * rad
            o = row + x * 4
            if not inside:
                buf[o + 3] = 0
                continue
            r_, g_, b_ = gr
            if abs(x - cx) < bbox and abs(y - cy) < bbox:
                d2 = (x - cx) ** 2 + (y - cy) ** 2
                if d2 > hole * hole and _in_poly(x, y, verts):
                    r_, g_, b_ = STAR
            buf[o] = r_; buf[o + 1] = g_; buf[o + 2] = b_; buf[o + 3] = 255
    return buf


def downsample(buf):
    out = bytearray(SIZE * SIZE * 4)
    for y in range(SIZE):
        for x in range(SIZE):
            r = g = b = a = 0
            for sy in range(SS):
                for sx in range(SS):
                    o = ((y * SS + sy) * R + (x * SS + sx)) * 4
                    r += buf[o]; g += buf[o + 1]; b += buf[o + 2]; a += buf[o + 3]
            n = SS * SS
            oo = (y * SIZE + x) * 4
            out[oo] = r // n; out[oo + 1] = g // n; out[oo + 2] = b // n; out[oo + 3] = a // n
    return out


def write_png(path, rgba, size):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    raw = bytearray()
    for y in range(size):
        raw.append(0)                               # filter type 0
        raw += rgba[y * size * 4:(y + 1) * size * 4]
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def make_icns(png):
    """macOS-only: build assets/RARNinja.icns from the 1024 master."""
    if sys.platform != "darwin":
        return
    iconset = os.path.join(ASSETS, "RARNinja.iconset")
    os.makedirs(iconset, exist_ok=True)
    for sz in (16, 32, 64, 128, 256, 512, 1024):
        subprocess.run(["sips", "-z", str(sz), str(sz), png,
                        "--out", os.path.join(iconset, f"icon_{sz}x{sz}.png")],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if sz <= 512:  # @2x variants
            subprocess.run(["sips", "-z", str(sz * 2), str(sz * 2), png,
                            "--out", os.path.join(iconset, f"icon_{sz}x{sz}@2x.png")],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["iconutil", "-c", "icns", iconset,
                    "-o", os.path.join(ASSETS, "RARNinja.icns")], check=True)


def main():
    os.makedirs(ASSETS, exist_ok=True)
    png = os.path.join(ASSETS, "icon_1024.png")
    print("Rendering icon…")
    write_png(png, downsample(render()), SIZE)
    print("Wrote", png)
    make_icns(png)
    icns = os.path.join(ASSETS, "RARNinja.icns")
    if os.path.isfile(icns):
        print("Wrote", icns)


if __name__ == "__main__":
    main()
