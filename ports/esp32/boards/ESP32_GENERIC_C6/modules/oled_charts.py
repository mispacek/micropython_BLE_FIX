
# MicroPython port of moonbench/oled-charts (SSD1306 charts)
# Optimized for low RAM/flash; uses framebuf drawing primitives.

import math

WHITE = 1
BLACK = 0

_FB = None
_FB_W = None
_FB_H = None


def set_framebuffer(fbuf):
    global _FB, _FB_W, _FB_H
    _FB = fbuf
    try:
        _FB_W = int(getattr(fbuf, "width"))
        _FB_H = int(getattr(fbuf, "height"))
    except Exception:
        _FB_W = None
        _FB_H = None


def _get_fb(fbuf):
    return fbuf if fbuf is not None else _FB


def _get_wh(fb):
    if fb is None:
        return None, None
    if _FB_W is not None and _FB_H is not None and fb is _FB:
        return _FB_W, _FB_H
    try:
        return int(getattr(fb, "width")), int(getattr(fb, "height"))
    except Exception:
        return None, None


def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _map(v, in_min, in_max, out_min, out_max):
    if in_max == in_min:
        return out_min
    return int((v - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)


def _iround(v):
    # Deterministic rounding for symmetric shapes
    return int(v + 0.5) if v >= 0 else int(v - 0.5)


def _pixel(fb, x, y, c=WHITE):
    w, h = _get_wh(fb)
    if w is None or h is None:
        fb.pixel(int(x), int(y), c)
        return
    xi = int(x); yi = int(y)
    if 0 <= xi < w and 0 <= yi < h:
        fb.pixel(xi, yi, c)


def _hline(fb, x, y, w, c=WHITE):
    if w <= 0:
        return
    w_fb, h_fb = _get_wh(fb)
    xi = int(x); yi = int(y); wi = int(w)
    if w_fb is None or h_fb is None:
        fb.hline(xi, yi, wi, c)
        return
    if yi < 0 or yi >= h_fb:
        return
    if xi < 0:
        wi += xi
        xi = 0
    if xi + wi > w_fb:
        wi = w_fb - xi
    if wi > 0:
        fb.hline(xi, yi, wi, c)


def _vline(fb, x, y, h, c=WHITE):
    if h <= 0:
        return
    w_fb, h_fb = _get_wh(fb)
    xi = int(x); yi = int(y); hi = int(h)
    if w_fb is None or h_fb is None:
        fb.vline(xi, yi, hi, c)
        return
    if xi < 0 or xi >= w_fb:
        return
    if yi < 0:
        hi += yi
        yi = 0
    if yi + hi > h_fb:
        hi = h_fb - yi
    if hi > 0:
        fb.vline(xi, yi, hi, c)


def draw_circle(fbuf, x0, y0, r, c=WHITE):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    x0 = int(x0); y0 = int(y0); r = int(r)
    if r <= 0:
        return
    # Angle-stepped outline for smoother small-radius circles
    steps = max(24, int(2 * math.pi * r * 2))
    step = (2 * math.pi) / steps
    px = _iround(x0 + r)
    py = _iround(y0)
    for i in range(1, steps + 1):
        a = i * step
        x = _iround(x0 + math.cos(a) * r)
        y = _iround(y0 + math.sin(a) * r)
        fb.line(px, py, x, y, c)
        px, py = x, y


def fill_circle(fbuf, x0, y0, r, c=WHITE):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    x0 = int(x0); y0 = int(y0); r = int(r)
    if r <= 0:
        return
    r2 = r * r
    for dy in range(-r, r + 1):
        dx = int((r2 - dy * dy) ** 0.5)
        _hline(fb, x0 - dx, y0 + dy, 2 * dx + 1, c)


def draw_triangle(fbuf, x0, y0, x1, y1, x2, y2, c=WHITE):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    fb.line(int(x0), int(y0), int(x1), int(y1), c)
    fb.line(int(x1), int(y1), int(x2), int(y2), c)
    fb.line(int(x2), int(y2), int(x0), int(y0), c)


def fill_triangle(fbuf, x0, y0, x1, y1, x2, y2, c=WHITE):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    x0 = int(x0); y0 = int(y0)
    x1 = int(x1); y1 = int(y1)
    x2 = int(x2); y2 = int(y2)

    # sort by y
    if y0 > y1:
        x0, x1 = x1, x0
        y0, y1 = y1, y0
    if y1 > y2:
        x1, x2 = x2, x1
        y1, y2 = y2, y1
    if y0 > y1:
        x0, x1 = x1, x0
        y0, y1 = y1, y0

    if y0 == y2:
        a = min(x0, x1, x2)
        b = max(x0, x1, x2)
        _hline(fb, a, y0, b - a + 1, c)
        return

    def _interp(xa, ya, xb, yb, y):
        if yb == ya:
            return xa
        return xa + (xb - xa) * (y - ya) / (yb - ya)

    y = y0
    while y <= y2:
        if y < y1:
            xa = _interp(x0, y0, x1, y1, y)
            xb = _interp(x0, y0, x2, y2, y)
        else:
            xa = _interp(x1, y1, x2, y2, y)
            xb = _interp(x0, y0, x2, y2, y)
        if xa > xb:
            xa, xb = xb, xa
        _hline(fb, int(xa), y, int(xb - xa + 1), c)
        y += 1


def draw_round_rect(fbuf, x, y, w, h, r, c=WHITE):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    x = int(x); y = int(y); w = int(w); h = int(h); r = int(r)
    if w <= 0 or h <= 0:
        return
    r = _clamp(r, 0, min(w, h) // 2)
    fb.rect(x + r, y, w - 2 * r, h, c)
    fb.rect(x, y + r, w, h - 2 * r, c)
    draw_circle(fb, x + r, y + r, r, c)
    draw_circle(fb, x + w - r - 1, y + r, r, c)
    draw_circle(fb, x + r, y + h - r - 1, r, c)
    draw_circle(fb, x + w - r - 1, y + h - r - 1, r, c)


def fill_round_rect(fbuf, x, y, w, h, r, c=WHITE):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    x = int(x); y = int(y); w = int(w); h = int(h); r = int(r)
    if w <= 0 or h <= 0:
        return
    r = _clamp(r, 0, min(w, h) // 2)
    fb.fill_rect(x + r, y, w - 2 * r, h, c)
    fb.fill_rect(x, y + r, w, h - 2 * r, c)
    fill_circle(fb, x + r, y + r, r, c)
    fill_circle(fb, x + w - r - 1, y + r, r, c)
    fill_circle(fb, x + r, y + h - r - 1, r, c)
    fill_circle(fb, x + w - r - 1, y + h - r - 1, r, c)


# Shared scales

def draw_vertical_scale(fbuf, x, y, height, spacing, divisions):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    bottom = y + height - 1
    steps = height // spacing
    for i in range(steps + 1):
        tick_y = bottom - i * spacing
        fb.pixel(x, tick_y, WHITE)
        if divisions and (i % divisions == 0):
            fb.pixel(x + 1, tick_y, WHITE)


def draw_horizontal_scale(fbuf, x, y, width, spacing, divisions):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    steps = width // spacing
    for i in range(steps):
        tick_x = x + i * spacing
        fb.pixel(tick_x, y, WHITE)
        if divisions and (i % divisions == 0):
            fb.pixel(tick_x, y - 1, WHITE)


# Graphs

def draw_line_graph(fbuf, x, y, width, height, data, data_count=None, line=True, fill=False):
    fb = _get_fb(fbuf)
    if fb is None or data is None:
        return
    if data_count is None:
        data_count = len(data)
    bottom = y + height - 1
    count = min(data_count, width)
    for i in range(count):
        v = data[i]
        bar_y = bottom - _clamp(_map(v, 0, 100, 0, height - 1), 0, height - 1)
        if fill:
            fb.line(x + i, bar_y, x + i, bottom, WHITE)
        elif line and i > 0:
            last_v = data[i - 1]
            last_y = bottom - _clamp(_map(last_v, 0, 100, 0, height - 1), 0, height - 1)
            fb.line(x + i - 1, last_y, x + i, bar_y, WHITE)
        else:
            fb.pixel(x + i, bar_y, WHITE)

    draw_vertical_scale(fb, x, y, height, 3, 5)
    draw_horizontal_scale(fb, x, bottom, width, 3, 5)


def draw_line_graph_simple(fbuf, x, y, width, height, data, data_count=None):
    draw_line_graph(fbuf, x, y, width, height, data, data_count, True, False)


def draw_area_graph(fbuf, x, y, width, height, data, data_count=None):
    draw_line_graph(fbuf, x, y, width, height, data, data_count, False, True)


def draw_dot_graph(fbuf, x, y, width, height, data, data_count=None):
    draw_line_graph(fbuf, x, y, width, height, data, data_count, False, False)


def draw_bar_graph(fbuf, x, y, width, height, data, data_count=None, bar_width=3, bar_padding=2):
    fb = _get_fb(fbuf)
    if fb is None or data is None:
        return
    if data_count is None:
        data_count = len(data)
    bottom = y + height - 1
    step = bar_width + bar_padding
    if step <= 0:
        return
    bar_start_x = x + 2
    bar_count = min(data_count, width // step)
    for i in range(bar_count):
        bar_height = _clamp(_map(data[i], 0, 100, 0, height - 1), 0, height - 1)
        offset_x = bar_start_x + (i * step)
        fb.fill_rect(offset_x, bottom - bar_height, bar_width, bar_height, WHITE)

    draw_vertical_scale(fb, x, y, height, 3, 5)
    _hline(fb, x, bottom, width, WHITE)


def draw_bar_graph_simple(fbuf, x, y, width, height, data, data_count=None):
    draw_bar_graph(fbuf, x, y, width, height, data, data_count, 3, 2)


def draw_autoscale_bar_graph(fbuf, x, y, width, height, data, data_count=None):
    if data_count is None:
        data_count = len(data) if data is not None else 0
    bar_padding = 3
    if data_count > 4:
        bar_padding = 2
    if data_count > 8:
        bar_padding = 1
    if data_count <= 0:
        return
    bar_width = max(1, (width - (data_count * bar_padding)) // data_count)
    draw_bar_graph(fbuf, x, y, width, height, data, data_count, bar_width, bar_padding)


# Gauges

def draw_linear_gauge(fbuf, x, y, width, height, value):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    needle_x = _map(value, 0, 100, x, x + width)
    needle_height = 3 * height // 5
    needle_y = y + (height - needle_height)
    draw_horizontal_scale(fb, x, needle_y, width, 2, 10)
    fb.line(x, needle_y + 2, x + width - 1, needle_y + 2, WHITE)
    fb.line(x, y, x, needle_y + 4, WHITE)
    fb.line(x + width - 1, y, x + width - 1, needle_y + 4, WHITE)
    # Symmetric triangle filled row-by-row to avoid 1px skew
    tri_h = (y + height) - needle_y
    if tri_h > 0:
        base_half = 4
        for i in range(tri_h + 1):
            half = _iround(base_half * i / tri_h)
            _hline(fb, needle_x - half, needle_y + i, 2 * half + 1, WHITE)
    fb.line(needle_x, needle_y, needle_x, y + height, BLACK)


def draw_needle_meter(fbuf, x, y=None, width=None, value=None):
    # Allow calling without explicit framebuffer: draw_needle_meter(x, y, width, value)
    if y is None:
        # called as (x, y, width, value) but missing fbuf
        x, y, width, value = fbuf, x, y, width
        fbuf = None
    fb = _get_fb(fbuf)
    if fb is None:
        return
    if width is None or value is None:
        return
    radius = width
    circle_x = x + width // 2
    circle_y = y + radius
    needle_length = radius - 4
    needle_taper = radius - 15

    for i in range(21):
        mapped = (( _clamp(i * 5, 0, 100) - 50) * 0.01) - (math.pi / 2)
        xoff = math.cos(mapped)
        yoff = math.sin(mapped)
        length = 10 if (i % 5 == 0) else 4
        fb.line(_iround(circle_x + xoff * radius),
                _iround(circle_y + yoff * radius),
                _iround(circle_x + xoff * (radius - length)),
                _iround(circle_y + yoff * (radius - length)), WHITE)

    mapped = (( _clamp(value, 0, 100) - 50) * 0.01) - (math.pi / 2)
    xoff = math.cos(mapped)
    yoff = math.sin(mapped)
    fb.line(circle_x, circle_y, _iround(circle_x + xoff * needle_length), _iround(circle_y + yoff * needle_length), WHITE)
    fb.line(circle_x + 1, circle_y, _iround(circle_x + 1 + xoff * needle_taper), _iround(circle_y + yoff * needle_taper), WHITE)
    fb.line(circle_x - 1, circle_y, _iround(circle_x - 1 + xoff * needle_taper), _iround(circle_y + yoff * needle_taper), WHITE)


def draw_signal_strength(fbuf, x, y, width, height, value, bar_width=1):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    highest = _map(value, 0, 100, 0, width // (1 + bar_width))
    for i in range(highest):
        bar_height = _map(i * (1 + bar_width), 0, width, 0, height)
        fb.fill_rect(x + i * (1 + bar_width), y + height - bar_height, bar_width, bar_height, WHITE)


def draw_thermometer(fbuf, x, y, width, height, value):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    thickness = 2
    if width > 20 and height > 20:
        thickness = 3
    if width < 8:
        thickness = 1
    if width < 6 or height < 10:
        return

    corner_radius = max(1, thickness * 2)
    bulb_radius = max(2, (width // 2) - thickness * 2)
    bulb_x = x + (width // 2)
    bulb_y = y + height - bulb_radius - thickness * 2 - 1
    bar_width = max(1, width // 2 - thickness * 3)
    bar_x = bulb_x - bar_width // 2
    bar_y = y + thickness * 2
    bar_bottom_y = bulb_y - bulb_radius - thickness * 2
    bar_max_height = max(1, abs(bar_y - bar_bottom_y))
    bar_height = _clamp(_map(value, 0, 100, 0, bar_max_height), 0, bar_max_height)

    # outline
    fill_round_rect(fb, bar_x - thickness * 2, y, bar_width + thickness * 4, height - bulb_radius, corner_radius, WHITE)
    fill_circle(fb, bulb_x, bulb_y, bulb_radius + thickness * 2, WHITE)

    fill_round_rect(fb, bar_x - thickness, y + thickness, bar_width + thickness * 2,
                    height - bulb_radius - thickness * 2, corner_radius, BLACK)
    fill_circle(fb, bulb_x, bulb_y, bulb_radius + thickness, BLACK)

    # inner
    fb.fill_rect(bar_x, bar_bottom_y + 1, bar_width, bulb_radius, WHITE)
    fill_circle(fb, bulb_x, bulb_y, bulb_radius, WHITE)
    if bar_height > 0:
        fill_round_rect(fb, bar_x, bar_bottom_y - bar_height + corner_radius,
                        bar_width, bar_height, corner_radius, WHITE)


def draw_segmented_gauge(fbuf, x, y, width, height, value, segments):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    segments = _clamp(segments, 1, max(1, width // 5))
    margin = 2
    segment_width = (width // segments) - margin
    highlight_to_x = _map(value, 0, 100, 0, width)
    for i in range(segments):
        offset = (segment_width + margin) * i
        if offset < highlight_to_x:
            fb.fill_rect(x + offset, y, segment_width, height, WHITE)
        else:
            fb.rect(x + offset, y, segment_width, height, WHITE)


def draw_dot_gauge(fbuf, x, y, width, height, value):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    margin = 2
    segment_radius = height // 2
    segments = width // (segment_radius * 2 + margin)
    highlight_to_x = _map(value, 0, 100, 0, width)
    for i in range(segments):
        offset = (segment_radius * 2 + margin) * i + segment_radius
        if offset < highlight_to_x:
            fill_circle(fb, x + offset, y + segment_radius, segment_radius, WHITE)
        else:
            draw_circle(fb, x + offset, y + segment_radius, segment_radius, WHITE)


def draw_radial_gauge(fbuf, x, y, radius, value, padding=2, outer_border=True, inner_border=True, draw_line=True, start_offset=-math.pi/2):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    segments = 32
    inner_radius = int(radius * 0.6)
    meter_radius = radius - padding
    segment_arc = (2 * math.pi) / segments
    half_arc = segment_arc / 2
    fill_up_to = _clamp(_map(value, 0, 100, 0, segments), 0, segments)

    for i in range(fill_up_to):
        segment_theta = i * segment_arc + start_offset
        a0 = segment_theta - half_arc
        a1 = segment_theta + half_arc
        # ring segment between inner_radius and outer (meter_radius)
        x0o = _iround(x + math.cos(a0) * meter_radius)
        y0o = _iround(y + math.sin(a0) * meter_radius)
        x1o = _iround(x + math.cos(a1) * meter_radius)
        y1o = _iround(y + math.sin(a1) * meter_radius)
        x0i = _iround(x + math.cos(a0) * inner_radius)
        y0i = _iround(y + math.sin(a0) * inner_radius)
        x1i = _iround(x + math.cos(a1) * inner_radius)
        y1i = _iround(y + math.sin(a1) * inner_radius)
        fill_triangle(fb, x0o, y0o, x1o, y1o, x1i, y1i, WHITE)
        fill_triangle(fb, x0o, y0o, x1i, y1i, x0i, y0i, WHITE)

    if outer_border:
        draw_circle(fb, x, y, radius, WHITE)
    if inner_border:
        draw_circle(fb, x, y, inner_radius, WHITE)

    if draw_line:
        theta = (value / 100.0) * (2 * math.pi) + start_offset
        x1 = math.cos(theta)
        y1 = math.sin(theta)
        fb.line(_iround(x + x1 * radius), _iround(y + y1 * radius),
                _iround(x + x1 * radius * 0.4), _iround(y + y1 * radius * 0.4), WHITE)


def draw_radial_dot_gauge(fbuf, x, y, radius, dot_radius, value, segments=8, empty_dot_radius=1, start_offset=-math.pi/2):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    segment_arc = (2 * math.pi) / segments
    fill_up_to = _clamp(_map(value, 0, 100, 0, segments), 0, segments)
    for i in range(segments):
        segment_theta = i * segment_arc + start_offset
        if i <= fill_up_to:
            fill_circle(fb, _iround(x + math.cos(segment_theta) * radius), _iround(y + math.sin(segment_theta) * radius), dot_radius, WHITE)
        else:
            draw_circle(fb, _iround(x + math.cos(segment_theta) * radius), _iround(y + math.sin(segment_theta) * radius), empty_dot_radius, WHITE)


def draw_radial_segment_gauge(fbuf, x, y, radius, segments, value, padding=2, outer_border=True, inner_border=True, start_offset=-math.pi/2):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    segment_arc = (2 * math.pi) / segments
    half_arc = segment_arc / (math.sqrt(radius) - 1)
    fill_up_to = _clamp(_map(value, 0, 100, 0, segments), 0, segments)

    for i in range(fill_up_to):
        segment_theta = i * segment_arc + start_offset
        fill_triangle(fb,
                      _iround(x + math.cos(segment_theta) * (radius / 3 - padding)),
                      _iround(y + math.sin(segment_theta) * (radius / 3 - padding)),
                      _iround(x + math.cos(segment_theta - half_arc) * (radius - padding)),
                      _iround(y + math.sin(segment_theta - half_arc) * (radius - padding)),
                      _iround(x + math.cos(segment_theta + half_arc) * (radius - padding)),
                      _iround(y + math.sin(segment_theta + half_arc) * (radius - padding)),
                      WHITE)

    if outer_border:
        draw_circle(fb, x, y, radius, WHITE)
    if inner_border:
        draw_circle(fb, x, y, int(radius * 0.6), WHITE)


def draw_radial_line_gauge(fbuf, x, y, radius, lines, value, outer_border=True, inner_border=True, start_offset=-math.pi/2):
    fb = _get_fb(fbuf)
    if fb is None:
        return
    segment_arc = (2 * math.pi) / lines
    half_arc = segment_arc / 4
    fill_up_to = _clamp(_map(value, 0, 100, 0, lines), 0, lines)

    for i in range(fill_up_to):
        segment_theta = i * segment_arc + start_offset
        x1 = math.cos(segment_theta - half_arc)
        y1 = math.sin(segment_theta - half_arc)
        x2 = math.cos(segment_theta + half_arc)
        y2 = math.sin(segment_theta + half_arc)
        fb.line(_iround(x + x1 * radius), _iround(y + y1 * radius), _iround(x + x1 * radius * 0.4), _iround(y + y1 * radius * 0.4), WHITE)
        fb.line(_iround(x + x2 * radius), _iround(y + y2 * radius), _iround(x + x2 * radius * 0.4), _iround(y + y2 * radius * 0.4), WHITE)

    if outer_border:
        draw_circle(fb, x, y, radius, WHITE)
    if inner_border:
        draw_circle(fb, x, y, int(radius * 0.6), WHITE)

