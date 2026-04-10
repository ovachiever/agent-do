// DPT Shared Utilities — Color Math, Geometry, DOM Traversal
// These run in the browser context via page.evaluate()

const DPT_UTILS = {

  // ─── Color Parsing ───────────────────────────────────────────────

  parseColor(str) {
    if (!str || str === 'transparent' || str === 'rgba(0, 0, 0, 0)') return null;
    const rgba = str.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
    if (!rgba) return null;
    return {
      r: parseInt(rgba[1]),
      g: parseInt(rgba[2]),
      b: parseInt(rgba[3]),
      a: rgba[4] !== undefined ? parseFloat(rgba[4]) : 1
    };
  },

  rgbToHex(r, g, b) {
    return '#' + [r, g, b].map(c => c.toString(16).padStart(2, '0')).join('');
  },

  rgbToHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const l = (max + min) / 2;
    if (max === min) return { h: 0, s: 0, l: Math.round(l * 100) };
    const d = max - min;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    let h;
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    else if (max === g) h = ((b - r) / d + 2) / 6;
    else h = ((r - g) / d + 4) / 6;
    return { h: Math.round(h * 360), s: Math.round(s * 100), l: Math.round(l * 100) };
  },

  // Relative luminance per WCAG 2.1
  relativeLuminance(r, g, b) {
    const [rs, gs, bs] = [r, g, b].map(c => {
      c = c / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
  },

  contrastRatio(rgb1, rgb2) {
    const l1 = this.relativeLuminance(rgb1.r, rgb1.g, rgb1.b);
    const l2 = this.relativeLuminance(rgb2.r, rgb2.g, rgb2.b);
    const lighter = Math.max(l1, l2);
    const darker = Math.min(l1, l2);
    return (lighter + 0.05) / (darker + 0.05);
  },

  // CIEDE2000 — perceptual color distance
  // Simplified implementation sufficient for design analysis
  rgbToLab(r, g, b) {
    // RGB -> XYZ (D65)
    let rr = r / 255, gg = g / 255, bb = b / 255;
    rr = rr > 0.04045 ? Math.pow((rr + 0.055) / 1.055, 2.4) : rr / 12.92;
    gg = gg > 0.04045 ? Math.pow((gg + 0.055) / 1.055, 2.4) : gg / 12.92;
    bb = bb > 0.04045 ? Math.pow((bb + 0.055) / 1.055, 2.4) : bb / 12.92;
    let x = (rr * 0.4124564 + gg * 0.3575761 + bb * 0.1804375) / 0.95047;
    let y = (rr * 0.2126729 + gg * 0.7151522 + bb * 0.0721750);
    let z = (rr * 0.0193339 + gg * 0.1191920 + bb * 0.9503041) / 1.08883;
    x = x > 0.008856 ? Math.pow(x, 1/3) : (7.787 * x) + 16/116;
    y = y > 0.008856 ? Math.pow(y, 1/3) : (7.787 * y) + 16/116;
    z = z > 0.008856 ? Math.pow(z, 1/3) : (7.787 * z) + 16/116;
    return { L: (116 * y) - 16, a: 500 * (x - y), b: 200 * (y - z) };
  },

  ciede2000(rgb1, rgb2) {
    const lab1 = this.rgbToLab(rgb1.r, rgb1.g, rgb1.b);
    const lab2 = this.rgbToLab(rgb2.r, rgb2.g, rgb2.b);
    // Simplified: use CIE76 as approximation (sufficient for design thresholds)
    const dL = lab1.L - lab2.L;
    const da = lab1.a - lab2.a;
    const db = lab1.b - lab2.b;
    return Math.sqrt(dL * dL + da * da + db * db);
  },

  isWarm(hue) {
    return (hue >= 0 && hue <= 60) || (hue >= 300 && hue <= 360);
  },

  isCool(hue) {
    return hue > 60 && hue < 300;
  },

  isNeutral(s) {
    return s < 10;
  },

  isStatusColor(h, s) {
    if (s < 20) return false;
    // Red zone: 340-20
    if (h >= 340 || h <= 20) return true;
    // Yellow/amber zone: 35-65
    if (h >= 35 && h <= 65) return true;
    // Green zone: 90-160
    if (h >= 90 && h <= 160) return true;
    return false;
  },

  // ─── DOM Traversal ───────────────────────────────────────────────

  getEffectiveBackground(el) {
    let current = el;
    while (current && current !== document.documentElement) {
      const bg = window.getComputedStyle(current).backgroundColor;
      const parsed = this.parseColor(bg);
      if (parsed && parsed.a > 0.1) {
        if (parsed.a < 1 && current.parentElement) {
          // Semi-transparent — blend with parent
          const parentBg = this.getEffectiveBackground(current.parentElement);
          if (parentBg) {
            return {
              r: Math.round(parsed.r * parsed.a + parentBg.r * (1 - parsed.a)),
              g: Math.round(parsed.g * parsed.a + parentBg.g * (1 - parsed.a)),
              b: Math.round(parsed.b * parsed.a + parentBg.b * (1 - parsed.a)),
              a: 1
            };
          }
        }
        return parsed;
      }
      current = current.parentElement;
    }
    // Default: white
    return { r: 255, g: 255, b: 255, a: 1 };
  },

  isVisible(el) {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  },

  isInViewport(el) {
    const rect = el.getBoundingClientRect();
    return rect.top < window.innerHeight && rect.bottom > 0 &&
           rect.left < window.innerWidth && rect.right > 0;
  },

  isTextElement(el) {
    const textTags = ['P', 'SPAN', 'LI', 'TD', 'TH', 'LABEL', 'A', 'STRONG', 'EM', 'B', 'I',
                      'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE', 'FIGCAPTION', 'CAPTION'];
    return textTags.includes(el.tagName);
  },

  isBodyText(el) {
    return ['P', 'LI', 'TD', 'TH', 'SPAN', 'LABEL'].includes(el.tagName);
  },

  isHeading(el) {
    return /^H[1-6]$/.test(el.tagName);
  },

  isInteractive(el) {
    if (['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)) return true;
    if (el.getAttribute('role') === 'button' || el.getAttribute('role') === 'link') return true;
    if (el.hasAttribute('tabindex') && el.getAttribute('tabindex') !== '-1') return true;
    if (el.getAttribute('onclick') || el.getAttribute('role') === 'checkbox' ||
        el.getAttribute('role') === 'tab' || el.getAttribute('role') === 'menuitem') return true;
    return false;
  },

  isFormField(el) {
    return ['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName) &&
           el.type !== 'hidden' && el.type !== 'submit' && el.type !== 'button';
  },

  getSelector(el, maxLen = 80) {
    if (el.id) return '#' + el.id;
    let sel = el.tagName.toLowerCase();
    if (el.className && typeof el.className === 'string') {
      const cls = el.className.trim().split(/\s+/).slice(0, 2).join('.');
      if (cls) sel += '.' + cls;
    }
    return sel.slice(0, maxLen);
  },

  // Collect all visible elements of specified types
  queryVisible(selector) {
    return Array.from(document.querySelectorAll(selector)).filter(el => this.isVisible(el));
  },

  // ─── Geometry ────────────────────────────────────────────────────

  gap(rect1, rect2) {
    // Vertical gap between two rects
    if (rect1.bottom <= rect2.top) return rect2.top - rect1.bottom;
    if (rect2.bottom <= rect1.top) return rect1.top - rect2.bottom;
    return 0; // overlapping
  },

  areAdjacent(rect1, rect2, threshold = 50) {
    const dx = Math.max(0, Math.max(rect1.left - rect2.right, rect2.left - rect1.right));
    const dy = Math.max(0, Math.max(rect1.top - rect2.bottom, rect2.top - rect1.bottom));
    return Math.sqrt(dx * dx + dy * dy) < threshold;
  },

  // ─── Statistics ──────────────────────────────────────────────────

  median(arr) {
    if (!arr.length) return 0;
    const sorted = [...arr].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  },

  stddev(arr) {
    if (arr.length < 2) return 0;
    const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
    return Math.sqrt(arr.reduce((sum, x) => sum + (x - mean) ** 2, 0) / arr.length);
  },

  mode(arr) {
    const counts = {};
    arr.forEach(v => { counts[v] = (counts[v] || 0) + 1; });
    let maxCount = 0, maxVal = arr[0];
    Object.entries(counts).forEach(([v, c]) => { if (c > maxCount) { maxCount = c; maxVal = v; } });
    return parseFloat(maxVal);
  },

  // Detect the base unit from a set of spacing values
  detectBaseUnit(values) {
    if (!values.length) return { unit: 8, confidence: 0 };
    const candidates = [4, 8];
    let best = { unit: 8, score: 0 };
    for (const unit of candidates) {
      const onGrid = values.filter(v => v > 0 && v % unit === 0).length;
      const score = onGrid / values.length;
      if (score > best.score) best = { unit, score };
    }
    return { unit: best.unit, confidence: Math.round(best.score * 100) / 100 };
  },

  // Detect type scale ratio from sorted font sizes
  detectScaleRatio(sizes) {
    if (sizes.length < 3) return { ratio: null, variance: 1, systematic: false };
    const ratios = [];
    for (let i = 1; i < sizes.length; i++) {
      if (sizes[i - 1] > 0) ratios.push(sizes[i] / sizes[i - 1]);
    }
    if (!ratios.length) return { ratio: null, variance: 1, systematic: false };
    const avgRatio = ratios.reduce((a, b) => a + b, 0) / ratios.length;
    const variance = this.stddev(ratios) / avgRatio;
    // Try to match known scales
    const knownScales = [1.067, 1.125, 1.200, 1.250, 1.333, 1.414, 1.500, 1.618];
    let bestMatch = avgRatio;
    let bestDist = Infinity;
    for (const s of knownScales) {
      const d = Math.abs(avgRatio - s);
      if (d < bestDist) { bestDist = d; bestMatch = s; }
    }
    return {
      ratio: Math.round(avgRatio * 1000) / 1000,
      best_known_match: bestMatch,
      variance: Math.round(variance * 1000) / 1000,
      systematic: variance < 0.15
    };
  }
};
