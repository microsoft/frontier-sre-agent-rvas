

# ----------------------------------------------------------------------------- brand (logo, colours, font)
# operation=brand reads the customer's public website (or a logo URL) and proposes the report identity: official logo
# (sanitised, trimmed, embedded as a data URI), primary/accent colours and the closest embedded font. The result is
# cached per site in the thread so scaffold reuses it; the logo never travels through the model.
BRAND_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"}
BRAND_FONT_HINTS = {
    "nunito": ("avenir", "nunito", "montserrat", "gotham", "poppins", "proxima", "futura", "raleway", "quicksand", "museo",
               "circular", "manrope", "outfit", "figtree", "mulish", "dm sans", "jakarta", "lexend", "urbanist", "sofia", "comfortaa", "gilroy"),
    "fira": ("fira", "lato", "source sans", "frutiger", "myriad", "pt sans", "calibri", "ubuntu", "open sans", "noto sans", "segoe",
             "da-vinci", "trebuchet", "verdana", "tahoma", "gill sans", "fs me", "museo sans", "asap"),
}
LOGO_MAX_BYTES = 220_000
# Default colours of CSS frameworks and CMS themes: frequent on many sites but never the customer's brand.
FRAMEWORK_COLORS = {
    "#007bff", "#6610f2", "#6f42c1", "#e83e8c", "#dc3545", "#fd7e14", "#ffc107", "#28a745", "#20c997", "#17a2b8", "#0d6efd",
    "#d63384", "#198754", "#0dcaf0", "#0a58ca", "#0b5ed7", "#146c43", "#b02a37", "#bb2d3b", "#157347", "#31d2f2", "#ffca2c",
    "#0aa2c0", "#3d8bfd", "#6ea8fe", "#9ec5fe", "#0062cc", "#0069d9", "#005cbf", "#1e7e34", "#218838", "#c82333", "#bd2130",
    "#e0a800", "#d39e00", "#138496", "#117a8b", "#212529", "#343a40", "#495057", "#6c757d", "#cf2e2e", "#ff6900", "#fcb900",
    "#7bdcb5", "#00d084", "#8ed1fc", "#0693e3", "#abb8c3", "#9b51e0", "#f78da7", "#219653", "#27ae60", "#2f80ed", "#eb5757",
    "#f2994a", "#f2c94c", "#56ccf2", "#bb6bd9", "#4285f4", "#ea4335", "#fbbc05", "#34a853", "#1877f2", "#1da1f2", "#0a66c2",
    "#25d366", "#ff0000", "#e1306c", "#3b5998", "#00acee", "#0e76a8", "#c4302b", "#bd081c"}
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


def _brand_host(url):
    match = re.match(r"^https://([^/:?#\s]+)", str(url or "").strip(), re.I)
    return match.group(1).lower() if match else None


def _brand_safe_host(host):
    import ipaddress
    import socket
    if not host or "." not in host or host.endswith((".local", ".internal", ".localhost")) or host == "localhost":
        return False
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast:
            return False
    return True


def _brand_get(url, limit=3_000_000):
    import requests
    from urllib.parse import urljoin
    for _ in range(6):
        host = _brand_host(url)
        if not host or not _brand_safe_host(host):
            raise ValueError(f"only public https URLs are allowed ({url})")
        response = requests.get(url, headers=BRAND_UA, timeout=20, stream=True, allow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308) and response.headers.get("Location"):
            url = urljoin(url, response.headers["Location"])
            response.close()
            continue
        break
    else:
        raise ValueError(f"too many redirects for {url}")
    if response.status_code != 200:
        raise ValueError(f"HTTP {response.status_code} for {url}")
    data = b""
    for chunk in response.iter_content(65536):
        data += chunk
        if len(data) > limit:
            raise ValueError(f"{url} is larger than {limit // 1000} KB")
    return data, response.headers.get("Content-Type", ""), url


def _brand_abs(base, ref):
    from urllib.parse import urljoin
    ref = (ref or "").strip()
    if not ref or ref.startswith("data:"):
        return None
    url = urljoin(base, ref.replace("&amp;", "&"))
    return url if url.startswith("https://") else None


def _brand_attr(tag, name):
    match = re.search(rf"\b{name}\s*=\s*([\"'])(.*?)\1", tag, re.I | re.S)
    return match.group(2) if match else ""


def _brand_hex(value):
    value = value.lower()
    return "#" + "".join(ch * 2 for ch in value) if len(value) == 3 else "#" + value


def _brand_colors(text):
    from collections import Counter
    found = Counter()
    for m in re.finditer(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-zA-Z])", text):
        found[_brand_hex(m.group(1))] += 1
    for m in re.finditer(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})", text):
        r, g, b = (min(255, int(v)) for v in m.groups())
        found["#%02x%02x%02x" % (r, g, b)] += 1
    return found


def _brand_hls(color):
    import colorsys
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)


def _brand_lum(color):
    def channel(v):
        v = int(v, 16) / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(color[1:3]) + 0.7152 * channel(color[3:5]) + 0.0722 * channel(color[5:7])


def _brand_contrast(a, b):
    hi, lo = sorted((_brand_lum(a), _brand_lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _brandish(color):
    h, light, s = _brand_hls(color)
    return s >= 0.35 and 0.08 <= light <= 0.9


def _hue_gap(a, b):
    gap = abs(_brand_hls(a)[0] - _brand_hls(b)[0]) * 360
    return min(gap, 360 - gap)


def _brand_palette(site, logo, theme_color=None):
    """Pick primary (hero/headings), accent (highlights, buttons) and an optional dark neutral from colour counts."""
    logo_set = set(logo)
    site_list = [(c, n) for c, n in site.most_common(80) if _brandish(c) and (c not in FRAMEWORK_COLORS or c in logo_set)]
    if theme_color and _brandish(theme_color):
        site_list.insert(0, (theme_color, max([n for _, n in site_list] + [1])))
    logo_list = [c for c, _ in logo.most_common(8) if _brandish(c)]
    anchor = logo_list[0] if logo_list else (site_list[0][0] if site_list else None)
    if not anchor:
        return None
    family = sorted([(c, n) for c, n in site_list if _hue_gap(c, anchor) <= 25] or [(anchor, 1)], key=lambda x: -x[1])
    base, base_n = family[0]
    deep = [(c, n) for c, n in family if _brand_lum(c) < _brand_lum(base) and _brand_contrast(c, "#ffffff") >= 4.5 and n >= 0.35 * base_n]
    primary = max(deep, key=lambda x: x[1])[0] if deep else base
    others = [c for c in logo_list if _hue_gap(c, primary) >= 40] + [c for c, n in site_list if _hue_gap(c, primary) >= 40 and n >= 0.3 * base_n]
    accent = others[0] if others else (base if base != primary else primary)
    darks = [(c, n) for c, n in site.most_common(80) if 0.002 < _brand_lum(c) < 0.035 and c not in FRAMEWORK_COLORS and n >= 0.5 * base_n]
    dark = darks[0][0] if darks and _brand_contrast(accent, darks[0][0]) >= 4.5 else None
    return {"primary": primary, "accent": accent, "dark": dark,
            "palette": [c for c, _ in site_list[:6]], "logo_colors": logo_list[:4]}


def _brand_font(css):
    from collections import Counter
    declared, used = Counter(), Counter()
    skip = r"icon|awesome|material|glyph|symbol|emoji|slick|fontello|dashicons|monospace|^sans-serif$|^serif$|\d{2,}"
    for m in re.finditer(r"@font-face\s*\{[^}]*?font-family\s*:\s*([^;}{]+)", css, re.I):
        name = m.group(1).split(",")[0].strip().strip("'\"").lower()
        if name and not re.search(skip, name):
            declared[name] += 1
    for m in re.finditer(r"font-family\s*:\s*([^;}{]+)", css, re.I):
        first = m.group(1).split(",")[0].strip().strip("'\"").lower()
        if first and not first.startswith(("var(", "inherit", "initial")) and not re.search(skip, first):
            used[first] += 1
    detected = (declared.most_common(1) or used.most_common(1) or [("", 0)])[0][0]
    preset = next((p for p, hints in BRAND_FONT_HINTS.items() if any(h in detected for h in hints)), "plex")
    return detected, preset


def _svg_clean(data):
    import xml.etree.ElementTree as ET
    text = data.decode("utf-8", "ignore") if isinstance(data, bytes) else data
    if re.search(r"<!ENTITY", text, re.I):
        return None
    text = re.sub(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>|<!--.*?-->", "", text, flags=re.S | re.I).strip()
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    if root.tag.rsplit("}", 1)[-1].lower() != "svg":
        return None
    banned = {"script", "foreignobject", "iframe", "object", "embed", "audio", "video", "animate", "set", "animatetransform", "animatemotion"}

    def keep_ns(tag):
        return not tag.startswith("{") or tag.startswith("{" + SVG_NS + "}")

    for parent in list(root.iter()):
        for child in list(parent):
            local = child.tag.rsplit("}", 1)[-1].lower() if isinstance(child.tag, str) else ""
            href = child.get("href") or child.get("{" + XLINK_NS + "}href") or ""
            if (not isinstance(child.tag, str) or local in banned or not keep_ns(child.tag)
                    or (local in ("image", "use") and href and not href.startswith("#"))
                    or (local == "style" and re.search(r"url\(\s*['\"]?(?!#)|@import", child.text or "", re.I))):
                parent.remove(child)
    for element in root.iter():
        for name in list(element.attrib):
            local = name.rsplit("}", 1)[-1].lower()
            value = element.attrib[name]
            if (local.startswith("on") or (name.startswith("{") and not name.startswith("{" + XLINK_NS + "}"))
                    or (local == "href" and not value.startswith("#"))
                    or re.search(r"url\(\s*['\"]?(?!#)|javascript:", value, re.I)):
                del element.attrib[name]
    if not root.get("viewBox"):
        try:
            w, h = (float(re.sub(r"[^0-9.]", "", root.get(k, "")) or 0) for k in ("width", "height"))
        except ValueError:
            w = h = 0
        if not (w and h):
            return None
        root.set("viewBox", f"0 0 {w:g} {h:g}")
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    out = ET.tostring(root, encoding="unicode")
    return out if len(out.encode()) <= LOGO_MAX_BYTES else None


def _svg_render(svg, width=800):
    import cairosvg
    from PIL import Image
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=width)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def _svg_trim(svg):
    """Crop the viewBox to the drawn content (many site logos ship with large padding)."""
    try:
        box = [float(v) for v in re.findall(r"-?\d*\.?\d+(?:e-?\d+)?", re.search(r'viewBox="([^"]+)"', svg).group(1))]
        vx, vy, vw, vh = box
        sized = re.sub(r'(<svg\b[^>]*?)\s(width|height)="[^"]*"', r"\1", svg, count=2)
        sized = re.sub(r"<svg\b", f'<svg width="{vw:g}" height="{vh:g}"', sized, count=1)
        image = _svg_render(sized)
        bbox = image.getchannel("A").getbbox()
        if not bbox:
            return svg, None
        scale = vw / image.width
        pad = max(vw, vh) * 0.01
        nx, ny = vx + bbox[0] * scale - pad, vy + bbox[1] * scale - pad
        nw, nh = (bbox[2] - bbox[0]) * scale + 2 * pad, (bbox[3] - bbox[1]) * scale + 2 * pad
        trimmed = re.sub(r'viewBox="[^"]+"', f'viewBox="{nx:.2f} {ny:.2f} {nw:.2f} {nh:.2f}"', sized, count=1)
        trimmed = re.sub(r'(<svg\b[^>]*?)width="[^"]*"\s*height="[^"]*"', rf'\1width="{nw:.2f}" height="{nh:.2f}"', trimmed, count=1)
        return (trimmed if nw * nh < 0.97 * vw * vh else sized), image
    except Exception:  # noqa: BLE001 - trimming is cosmetic; keep the clean logo
        return svg, None


def _logo_tone(image):
    """Average luminance of opaque logo pixels: > 0.82 means a light logo that needs a dark header."""
    try:
        small = image.resize((max(1, image.width // 4), max(1, image.height // 4)))
        pixels = [p for p in small.getdata() if p[3] > 200]
        if not pixels:
            return None
        return sum(0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b, _ in pixels) / (255 * len(pixels))
    except Exception:  # noqa: BLE001
        return None


def _logo_from_bytes(data, ctype, url):
    """Return (data_uri, format, light_logo, colour Counter) or raise ValueError."""
    from collections import Counter
    is_svg = "svg" in ctype or url.lower().split("?")[0].endswith(".svg") or data.lstrip()[:5] in (b"<svg ", b"<?xml") or b"<svg" in data[:400]
    if is_svg:
        svg = _svg_clean(data)
        if not svg:
            raise ValueError("SVG logo rejected (not a static vector image)")
        svg, image = _svg_trim(svg)
        tone = _logo_tone(image) if image is not None else None
        colors = _brand_colors(svg)
        return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode(), "svg", bool(tone and tone > 0.82), colors
    try:
        from PIL import Image
        image = Image.open(io.BytesIO(data))
        image.load()
        if image.format not in ("PNG", "JPEG", "WEBP", "GIF", "ICO"):
            raise ValueError(f"unsupported logo format {image.format}")
        image = image.convert("RGBA")
        bbox = image.getchannel("A").getbbox()
        if bbox:
            image = image.crop(bbox)
        if image.height > 200:
            image = image.resize((max(1, round(image.width * 200 / image.height)), 200))
        buf = io.BytesIO()
        image.save(buf, "PNG", optimize=True)
        quant = image.convert("RGB").quantize(colors=6)
        palette = quant.getpalette()
        colors = Counter()
        for count, index in quant.getcolors() or []:
            colors["#%02x%02x%02x" % tuple(palette[index * 3:index * 3 + 3])] += count
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), "png", bool((_logo_tone(image) or 0) > 0.82), colors
    except ImportError:
        if len(data) > LOGO_MAX_BYTES or not ctype.startswith("image/"):
            raise ValueError("logo too large or not an image")
        return f"data:{ctype.split(';')[0]};base64," + base64.b64encode(data).decode(), ctype, False, Counter()


def _logo_candidates(page, base):
    cands = []
    head_end = (re.search(r"</header>", page, re.I) or re.search(r"<main\b", page, re.I))
    limit = head_end.end() if head_end else len(page) // 3
    for m in re.finditer(r"<img\b[^>]*>", page, re.I):
        tag = m.group(0)
        src = _brand_attr(tag, "src") or _brand_attr(tag, "data-src")
        url = _brand_abs(base, src)
        if not url:
            continue
        hint = (src + " " + _brand_attr(tag, "alt") + " " + _brand_attr(tag, "class") + " " + _brand_attr(tag, "id")).lower()
        around = page[max(0, m.start() - 300):m.start()].lower()
        score = (6 if "logo" in hint else 3 if "logo" in around or "brand" in hint else 0) + (3 if ".svg" in url.lower() else 0) + (2 if m.start() < limit else 0)
        if score >= 5:
            cands.append((score, url))
    for m in re.finditer(r"<link\b[^>]*>", page, re.I):
        tag = m.group(0)
        rel, href = _brand_attr(tag, "rel").lower(), _brand_abs(base, _brand_attr(tag, "href"))
        if href and ("apple-touch-icon" in rel or ("icon" in rel and ".svg" in href.lower())):
            cands.append((1, "icon:" + href))
    for m in re.finditer(r"<svg\b[^>]*>.*?</svg>", page, re.I | re.S):
        opening = m.group(0)[:300].lower() + page[max(0, m.start() - 200):m.start()].lower()
        if "logo" in opening and len(m.group(0)) > 400:
            cands.append((7 if m.start() < limit else 4, "inline:" + str(m.start())))
    seen, ordered = set(), []
    for score, url in sorted(cands, key=lambda x: -x[0]):
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered[:6]


def _brand_discover(website=None, logo_url=None):
    """Fetch the site, its CSS and the logo; return a brand dict (with data URI) and a list of notes."""
    from collections import Counter
    notes, site_colors, css_text, name, theme_color, page, base = [], Counter(), "", "", None, "", website
    if website:
        try:
            raw, _, base = _brand_get(website)
            page = raw.decode("utf-8", "ignore")
            site_colors.update(_brand_colors(page))
            meta = re.search(r"<meta[^>]+(?:property|name)=[\"']og:site_name[\"'][^>]*>", page, re.I)
            name = _brand_attr(meta.group(0), "content") if meta else ""
            title = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
            label = (_brand_host(base) or "").split(".")[-2] if (_brand_host(base) or "").count(".") >= 1 else ""
            words = re.findall(r"[\w&'-]+", html_unescape(title.group(1))) if title else []
            match_word = next((w for w in words if label and w.lower() == label.lower()), "")
            if match_word and (not name or len(name) > len(match_word) + 12):
                name = match_word
            if not name:
                name = re.split(r"\s[|\-–—:·]\s", html_unescape(title.group(1)).strip())[0] if title else ""
            theme = re.search(r"<meta[^>]+name=[\"']theme-color[\"'][^>]*>", page, re.I)
            hexes = _brand_colors(_brand_attr(theme.group(0), "content")) if theme else {}
            theme_color = next(iter(hexes), None) if hexes else None
            sheets = [s for s in (_brand_abs(base, _brand_attr(m.group(0), "href")) for m in re.finditer(r"<link\b[^>]*rel=[\"'][^\"']*stylesheet[^>]*>", page, re.I)) if s]
            ranked = sorted(enumerate(sheets), key=lambda x: -((3 if re.search(r"theme|main|style|global|/app|site|brand|custom|base", x[1], re.I)
                                                                      and not re.search(r"contrib|vendor|cookie|slick|module", x[1], re.I) else 0) + x[0] / max(1, len(sheets))))
            for _, href in ranked[:8]:
                try:
                    css = _brand_get(href, 2_000_000)[0].decode("utf-8", "ignore")
                    css_text += css
                    site_colors.update(_brand_colors(css))
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"stylesheet skipped: {str(exc)[:80]}")
            css_text += "".join(re.findall(r"<style[^>]*>(.*?)</style>", page, re.I | re.S))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"website not readable: {str(exc)[:140]}")
    logo, logo_fmt, light, logo_colors, logo_source = "", "", False, Counter(), ""
    candidates = ([logo_url] if logo_url else []) + (_logo_candidates(page, base) if page else [])
    for cand in candidates:
        try:
            if cand.startswith("inline:"):
                start = int(cand.split(":")[1])
                svg_text = re.match(r"<svg\b[^>]*>.*?</svg>", page[start:], re.I | re.S).group(0)
                data, ctype, src = svg_text.encode(), "image/svg+xml", website + " (inline SVG)"
            else:
                data, ctype, src = _brand_get(cand.split("icon:", 1)[-1], 1_500_000)
            logo, logo_fmt, light, logo_colors = _logo_from_bytes(data, ctype, cand)
            logo_source = src
            if cand.startswith("icon:"):
                logo_fmt += " (site icon)"
                notes.append("only the site icon was found, not the full logo: ask for a direct logo URL (brand.logo_url)")
            break
        except Exception as exc:  # noqa: BLE001
            notes.append(f"logo candidate skipped: {str(exc)[:100]}")
    if not logo:
        notes.append("no logo found: the report will show the name as a wordmark (pass brand.logo_url to fix)")
    palette = _brand_palette(site_colors, logo_colors, theme_color) or {}
    detected_font, preset = _brand_font(css_text)
    return {"name": html_unescape(name)[:60].strip(), "primary": palette.get("primary"), "accent": palette.get("accent"),
            "dark": palette.get("dark"), "font": preset, "font_detected": detected_font, "logo": logo, "logo_format": logo_fmt,
            "logo_on_dark": light, "logo_source": logo_source, "palette": palette.get("palette", []),
            "logo_colors": palette.get("logo_colors", [])}, notes


def html_unescape(text):
    import html as _html
    return _html.unescape(text or "")


def _brand_cache_path(key):
    folder = Path.cwd() / "sre-usecase-builder" / "_brand"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (re.sub(r"[^a-z0-9.-]", "_", key.lower())[:80] + ".json")


def _brand_resolve(spec_brand, config, warnings):
    """Fill config['brand'] from cache/discovery (website, logo_url) and return the logo data URI."""
    source = spec_brand if isinstance(spec_brand, dict) else {}
    website, logo_url = source.get("website"), source.get("logo_url")
    if not (website or logo_url):
        return ""
    key = _brand_host(website) or _brand_host(logo_url) or "brand"
    path = _brand_cache_path(key)
    found = None
    if path.exists():
        found = json.loads(path.read_text(encoding="utf-8"))
        if logo_url and found.get("logo_request") != logo_url:
            found = None
    if found is None:
        found, notes = _brand_discover(website, logo_url)
        found["logo_request"] = logo_url
        path.write_text(json.dumps(found, ensure_ascii=False), encoding="utf-8")
        warnings.extend("brand: " + n for n in notes[:3])
    brand = config["brand"]
    for k in ("name", "primary", "accent", "dark", "font"):
        if not brand.get(k) and found.get(k):
            brand[k] = found[k]
    if "logo_on_dark" not in source:
        brand["logo_on_dark"] = bool(found.get("logo_on_dark"))
    if not config.get("client") and brand.get("name"):
        config["client"] = brand["name"]
    return found.get("logo", "")


def _font_css(preset):
    data = FONT_PRESETS.get(preset) or FONT_PRESETS["plex"]
    return "".join(f"@font-face{{font-family:'{data['family']}';font-style:normal;font-weight:{w};font-display:swap;"
                   f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}" for w, b64 in data["faces"].items())


def _brand_op(spec_json):
    """operation=brand: discover and preview the report identity for a customer website or logo URL."""
    try:
        spec = json.loads(spec_json) if (spec_json or "").strip().startswith("{") else {"website": (spec_json or "").strip()}
    except ValueError:
        return {"status": "INVALID", "message": "spec_json must be {\"website\": \"https://...\"} (optionally logo_url, name, primary, accent, font)"}
    for key in ("website", "logo_url"):
        if spec.get(key) and not str(spec[key]).startswith("https://"):
            spec[key] = "https://" + str(spec[key]).split("://")[-1]
    if not (spec.get("website") or spec.get("logo_url")):
        return {"status": "INVALID", "message": "give website (https://...) or logo_url"}
    warnings = []
    config = {"brand": {k: spec[k] for k in ("name", "primary", "accent", "font", "hero") if spec.get(k)}, "client": ""}
    path = _brand_cache_path(_brand_host(spec.get("website")) or _brand_host(spec.get("logo_url")) or "brand")
    if path.exists():
        path.unlink()
    logo = _brand_resolve(spec, config, warnings)
    brand = config["brand"]
    preview = {}
    try:
        recipe = json.loads(json.dumps(next(r["spec"] for r in RECIPES if r["name"] == "entra-app-secrets-expiry")))
        recipe.update(name="brand-preview", title=spec.get("preview_title") or ("Caducidad de secretos de aplicaciones" if spec.get("language", "es") == "es" else "App secrets expiring"),
                      language=spec.get("language", "es"), brand=dict(brand, website=None, logo_url=None))
        pconfig, pmeta, errors, _ = _validate(recipe)
        if not errors:
            pconfig["brand"] = dict(brand)
            ns, result, _ = _run(_build_code(pconfig, pmeta, logo), "self_test")
            preview = {k: v for k, v in (result.get("files") or {}).items() if k.endswith((".html", ".pdf"))}
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"preview not generated: {type(exc).__name__}: {str(exc)[:120]}")
    cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {"status": "OK" if logo else "PARTIAL",
            "brand": {k: brand.get(k) for k in ("name", "primary", "accent", "dark", "font", "logo_on_dark") if brand.get(k) is not None},
            "logo": {"found": bool(logo), "format": cached.get("logo_format"), "source": cached.get("logo_source"),
                     "bytes": len(logo)}, "font_detected": cached.get("font_detected"), "site_palette": cached.get("palette"),
            "preview": preview, "warnings": warnings,
            "next": "Show the preview link to the user. Then put in the spec: brand = {name, website, primary, accent, font} "
                    "(values above; the user may override colours). scaffold reuses the cached logo for this website."}
