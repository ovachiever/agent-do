// DPT Layer 1: Chromatic Field
// Color perception, palette structure, contrast, emotional mapping

function chromaticField(utils) {

  const MAX_VIOLATIONS = 20;
  const MAX_TEXT_SAMPLE = 500;

  // ─── Shared collection: gather all visible elements once ──────────

  const allVisible = utils.queryVisible('*');
  const textElements = allVisible.filter(el => utils.isTextElement(el));
  const interactiveElements = allVisible.filter(el => utils.isInteractive(el));
  const viewportElements = allVisible.filter(el => utils.isInViewport(el));

  // ─── CF-01: WCAG Text Contrast ────────────────────────────────────

  function cf01_textContrast() {
    const sampled = textElements.slice(0, MAX_TEXT_SAMPLE);
    const violations = [];
    let checkedCount = 0;
    let hardFailCount = 0;
    let softFailCount = 0;

    // Detect dominant text color to identify secondary text
    const colorCounts = new Map();
    for (const el of sampled) {
      const style = window.getComputedStyle(el);
      const fg = utils.parseColor(style.color);
      if (!fg || fg.a < 0.1) continue;
      const hex = utils.rgbToHex(fg.r, fg.g, fg.b);
      colorCounts.set(hex, (colorCounts.get(hex) || 0) + 1);
    }
    let dominantTextHex = null;
    let maxCount = 0;
    for (const [hex, count] of colorCounts) {
      if (count > maxCount) { maxCount = count; dominantTextHex = hex; }
    }

    for (const el of sampled) {
      const style = window.getComputedStyle(el);
      const fg = utils.parseColor(style.color);
      if (!fg || fg.a < 0.1) continue;

      const bg = utils.getEffectiveBackground(el);
      if (!bg) continue;

      checkedCount++;
      const ratio = utils.contrastRatio(fg, bg);
      const fontSize = parseFloat(style.fontSize);
      const fontWeight = parseInt(style.fontWeight, 10) || 400;
      const isBold = fontWeight >= 700;
      const isLarge = fontSize >= 18 || (fontSize >= 14 && isBold);

      // Detect text role: secondary text is dimmer than dominant
      const fgHex = utils.rgbToHex(fg.r, fg.g, fg.b);
      let textRole = 'primary';
      if (dominantTextHex && fgHex !== dominantTextHex) {
        const domR = parseInt(dominantTextHex.slice(1, 3), 16);
        const domG = parseInt(dominantTextHex.slice(3, 5), 16);
        const domB = parseInt(dominantTextHex.slice(5, 7), 16);
        const fgLum = utils.relativeLuminance(fg.r, fg.g, fg.b);
        const domLum = utils.relativeLuminance(domR, domG, domB);
        const bgLum = utils.relativeLuminance(bg.r, bg.g, bg.b);
        // Secondary: closer to bg luminance than dominant text is
        const fgDist = Math.abs(fgLum - bgLum);
        const domDist = Math.abs(domLum - bgLum);
        if (fgDist < domDist * 0.7) {
          textRole = 'secondary';
        }
      }

      let level;
      if (ratio >= 7) {
        level = 'AAA';
      } else if (ratio >= 4.5) {
        level = 'AA';
      } else if (ratio >= 3 && (isLarge || textRole === 'secondary')) {
        // 3:1 passes for large text AND intentional secondary text
        level = textRole === 'secondary' ? 'AA_secondary' : 'AA_large';
      } else {
        level = 'fail';
      }

      if (level === 'fail') {
        // Hard fail: below 3:1 — genuinely unreadable
        // Soft fail: 3-4.5:1 on primary text — below AA but visible
        if (ratio < 3) {
          hardFailCount++;
        } else {
          softFailCount++;
        }
        if (violations.length < MAX_VIOLATIONS) {
          violations.push({
            selector: utils.getSelector(el),
            contrast: Math.round(ratio * 100) / 100,
            fg: utils.rgbToHex(fg.r, fg.g, fg.b),
            bg: utils.rgbToHex(bg.r, bg.g, bg.b),
            text_role: textRole,
            level,
            severity: ratio < 3 ? 'hard' : 'soft'
          });
        }
      }
    }

    const totalFails = hardFailCount + softFailCount;
    const passRate = checkedCount > 0
      ? Math.round(((checkedCount - totalFails) / checkedCount) * 1000) / 1000
      : 1;
    // Adjusted: only hard fails (< 3:1) count against the rate
    const adjustedPassRate = checkedCount > 0
      ? Math.round(((checkedCount - hardFailCount) / checkedCount) * 1000) / 1000
      : 1;

    const result = {
      pairs_checked: checkedCount,
      violations,
      pass_rate: passRate,
      adjusted_pass_rate: adjustedPassRate,
      hard_failures: hardFailCount,
      soft_failures: softFailCount
    };

    if (totalFails > MAX_VIOLATIONS) {
      result.violations_note = `Showing ${MAX_VIOLATIONS} of ${totalFails} violations`;
    }

    return result;
  }

  // ─── CF-02: Palette Analysis ──────────────────────────────────────

  function cf02_palette() {
    const colorMap = new Map(); // hex -> { hsl, count, role }
    const HUE_BUCKET_SIZE = 30;

    for (const el of allVisible) {
      const style = window.getComputedStyle(el);
      const props = ['color', 'backgroundColor', 'borderColor'];

      for (const prop of props) {
        const raw = style[prop];
        const parsed = utils.parseColor(raw);
        if (!parsed || parsed.a < 0.1) continue;

        const hex = utils.rgbToHex(parsed.r, parsed.g, parsed.b);
        const hsl = utils.rgbToHsl(parsed.r, parsed.g, parsed.b);

        if (colorMap.has(hex)) {
          colorMap.get(hex).area_count++;
        } else {
          let role;
          if (utils.isNeutral(hsl.s)) {
            role = 'neutral';
          } else if (utils.isStatusColor(hsl.h, hsl.s)) {
            role = 'status';
          } else {
            role = 'chromatic';
          }
          colorMap.set(hex, { hex, hsl, role, area_count: 1 });
        }
      }
    }

    // Cluster chromatic hues by 30-degree buckets
    const hueBuckets = new Set();
    let neutralCount = 0;
    let statusCount = 0;

    for (const entry of colorMap.values()) {
      if (entry.role === 'neutral') {
        neutralCount++;
      } else if (entry.role === 'status') {
        statusCount++;
      }
      if (entry.role === 'chromatic' || entry.role === 'status') {
        hueBuckets.add(Math.floor(entry.hsl.h / HUE_BUCKET_SIZE));
      }
    }

    // Sort palette by usage count descending
    const palette = Array.from(colorMap.values())
      .sort((a, b) => b.area_count - a.area_count);

    return {
      total_colors: colorMap.size,
      chromatic_hues: hueBuckets.size,
      neutrals: neutralCount,
      status_colors: statusCount,
      palette
    };
  }

  // ─── CF-03: Grey Saturation Check ─────────────────────────────────

  function cf03_greySaturation() {
    const greys = [];

    for (const el of allVisible) {
      const style = window.getComputedStyle(el);
      for (const prop of ['color', 'backgroundColor', 'borderColor']) {
        const parsed = utils.parseColor(style[prop]);
        if (!parsed || parsed.a < 0.1) continue;
        const hsl = utils.rgbToHsl(parsed.r, parsed.g, parsed.b);
        // Neutral range: saturation < 15%, lightness 15-95%
        if (hsl.s < 15 && hsl.l >= 15 && hsl.l <= 95) {
          greys.push(hsl);
        }
      }
    }

    let untinted = 0;
    let tinted = 0;
    const tintedHues = [];

    for (const g of greys) {
      if (g.s === 0) {
        untinted++;
      } else if (g.s >= 3 && g.s <= 10) {
        tinted++;
        tintedHues.push(g.h);
      }
      // s between 1-2 or 11-14 are in a middle ground; count neither
    }

    // Determine dominant grey hue and consistency
    let dominantGreyHue = null;
    let hueConsistent = true;

    if (tintedHues.length > 0) {
      // Find mode of hue buckets (30-degree granularity)
      const hueCounts = {};
      for (const h of tintedHues) {
        const bucket = Math.round(h / 30) * 30;
        hueCounts[bucket] = (hueCounts[bucket] || 0) + 1;
      }
      let maxCount = 0;
      for (const [hue, count] of Object.entries(hueCounts)) {
        if (count > maxCount) {
          maxCount = count;
          dominantGreyHue = parseInt(hue);
        }
      }

      // Consistent if >= 70% of tinted greys share the dominant bucket
      const dominantShare = maxCount / tintedHues.length;
      hueConsistent = dominantShare >= 0.7;
    }

    return {
      untinted_greys: untinted,
      tinted_greys: tinted,
      dominant_grey_hue: dominantGreyHue,
      hue_consistent: hueConsistent
    };
  }

  // ─── CF-04: Interactive-Only Primary Hue ──────────────────────────

  function cf04_interactivePrimary() {
    const HUE_TOLERANCE = 15;
    const hueUsage = {}; // hue bucket -> count

    // Collect saturated hues from interactive elements
    for (const el of interactiveElements) {
      const style = window.getComputedStyle(el);
      for (const prop of ['color', 'backgroundColor', 'borderColor']) {
        const parsed = utils.parseColor(style[prop]);
        if (!parsed || parsed.a < 0.1) continue;
        const hsl = utils.rgbToHsl(parsed.r, parsed.g, parsed.b);
        if (hsl.s >= 20) { // must be chromatic
          const bucket = Math.round(hsl.h / 10) * 10; // 10-degree buckets
          hueUsage[bucket] = (hueUsage[bucket] || 0) + 1;
        }
      }
    }

    // Find primary hue (most used saturated hue on interactive elements)
    let primaryHue = null;
    let maxInteractive = 0;
    for (const [hue, count] of Object.entries(hueUsage)) {
      if (count > maxInteractive) {
        maxInteractive = count;
        primaryHue = parseInt(hue);
      }
    }

    if (primaryHue === null) {
      return {
        primary_hue: null,
        interactive_uses: 0,
        non_interactive_leaks: 0,
        leaked_selectors: [],
        pass: true
      };
    }

    // Check non-interactive elements for leaks of the primary hue
    const nonInteractive = allVisible.filter(el =>
      !utils.isInteractive(el) &&
      (el.tagName.match(/^H[1-6]$/) || el.tagName === 'P' || el.tagName === 'DIV' ||
       el.tagName === 'SPAN' || el.tagName === 'SECTION')
    );

    let leakCount = 0;
    const leakedSelectors = [];

    for (const el of nonInteractive) {
      const style = window.getComputedStyle(el);
      for (const prop of ['color', 'backgroundColor', 'borderColor']) {
        const parsed = utils.parseColor(style[prop]);
        if (!parsed || parsed.a < 0.1) continue;
        const hsl = utils.rgbToHsl(parsed.r, parsed.g, parsed.b);
        if (hsl.s < 20) continue;

        const hueDist = Math.min(
          Math.abs(hsl.h - primaryHue),
          360 - Math.abs(hsl.h - primaryHue)
        );

        if (hueDist <= HUE_TOLERANCE) {
          leakCount++;
          if (leakedSelectors.length < MAX_VIOLATIONS) {
            leakedSelectors.push(utils.getSelector(el));
          }
          break; // count element once
        }
      }
    }

    return {
      primary_hue: primaryHue,
      interactive_uses: maxInteractive,
      non_interactive_leaks: leakCount,
      leaked_selectors: leakedSelectors,
      pass: leakCount === 0
    };
  }

  // ─── CF-05: Warm/Cool Balance ─────────────────────────────────────

  function cf05_warmCoolBalance() {
    let warmCount = 0;
    let coolCount = 0;

    for (const el of allVisible) {
      const style = window.getComputedStyle(el);
      for (const prop of ['color', 'backgroundColor', 'borderColor']) {
        const parsed = utils.parseColor(style[prop]);
        if (!parsed || parsed.a < 0.1) continue;
        const hsl = utils.rgbToHsl(parsed.r, parsed.g, parsed.b);
        if (utils.isNeutral(hsl.s)) continue; // skip neutrals

        if (utils.isWarm(hsl.h)) warmCount++;
        else if (utils.isCool(hsl.h)) coolCount++;
      }
    }

    const total = warmCount + coolCount;
    const warmPct = total > 0 ? Math.round((warmCount / total) * 1000) / 10 : 0;
    const coolPct = total > 0 ? Math.round((coolCount / total) * 1000) / 10 : 0;

    // Monotony: one side exceeds 90%
    const monotony = total > 0 && (warmPct > 90 || coolPct > 90);

    return {
      warm_pct: warmPct,
      cool_pct: coolPct,
      monotony
    };
  }

  // ─── CF-06: Dark Mode Checks ──────────────────────────────────────

  function cf06_darkMode() {
    let pureBlackBgs = 0;
    let pureWhiteText = 0;

    for (const el of allVisible) {
      const style = window.getComputedStyle(el);

      // Check background for pure black
      const bgParsed = utils.parseColor(style.backgroundColor);
      if (bgParsed && bgParsed.a > 0.1 &&
          bgParsed.r === 0 && bgParsed.g === 0 && bgParsed.b === 0) {
        pureBlackBgs++;
      }

      // Check text color for pure white
      if (utils.isTextElement(el)) {
        const fgParsed = utils.parseColor(style.color);
        if (fgParsed && fgParsed.r === 255 && fgParsed.g === 255 && fgParsed.b === 255) {
          pureWhiteText++;
        }
      }
    }

    // Halation risk: pure white text on pure black background exists
    let halationRisk = false;
    if (pureBlackBgs > 0 && pureWhiteText > 0) {
      // Verify at least one element actually combines both
      for (const el of allVisible) {
        if (!utils.isTextElement(el)) continue;
        const style = window.getComputedStyle(el);
        const fg = utils.parseColor(style.color);
        if (!fg || fg.r !== 255 || fg.g !== 255 || fg.b !== 255) continue;

        const bg = utils.getEffectiveBackground(el);
        if (bg && bg.r === 0 && bg.g === 0 && bg.b === 0) {
          halationRisk = true;
          break;
        }
      }
    }

    return {
      pure_black_backgrounds: pureBlackBgs,
      pure_white_text: pureWhiteText,
      halation_risk: halationRisk
    };
  }

  // ─── CF-07: Red-Blue Adjacency (Chromostereopsis) ─────────────────

  function cf07_redBlueAdjacency() {
    // Collect elements with strong red or blue backgrounds/colors
    const redEls = [];
    const blueEls = [];

    function isStrongRed(h, s) {
      return s > 40 && (h >= 340 || h <= 20);
    }

    function isStrongBlue(h, s) {
      return s > 40 && h >= 210 && h <= 260;
    }

    for (const el of viewportElements) {
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;

      // Check background and text color
      for (const prop of ['color', 'backgroundColor']) {
        const parsed = utils.parseColor(style[prop]);
        if (!parsed || parsed.a < 0.1) continue;
        const hsl = utils.rgbToHsl(parsed.r, parsed.g, parsed.b);

        if (isStrongRed(hsl.h, hsl.s)) {
          redEls.push({ el, rect });
          break;
        }
        if (isStrongBlue(hsl.h, hsl.s)) {
          blueEls.push({ el, rect });
          break;
        }
      }
    }

    let pairCount = 0;

    // Check adjacency between red and blue elements
    for (const red of redEls) {
      for (const blue of blueEls) {
        if (red.el === blue.el) continue;
        if (utils.areAdjacent(red.rect, blue.rect)) {
          pairCount++;
        }
      }
    }

    return {
      chromostereopsis_pairs: pairCount,
      risk: pairCount > 0
    };
  }

  // ─── CF-08: Full Saturation Overuse ───────────────────────────────

  function cf08_saturationOveruse() {
    const SAT_THRESHOLD = 85;
    let fullSatElements = 0;
    const fullSatHues = new Set(); // 30-degree buckets

    for (const el of viewportElements) {
      const style = window.getComputedStyle(el);
      let found = false;

      for (const prop of ['color', 'backgroundColor', 'borderColor']) {
        const parsed = utils.parseColor(style[prop]);
        if (!parsed || parsed.a < 0.1) continue;
        const hsl = utils.rgbToHsl(parsed.r, parsed.g, parsed.b);

        if (hsl.s > SAT_THRESHOLD && hsl.l > 10 && hsl.l < 90) {
          fullSatHues.add(Math.floor(hsl.h / 30));
          if (!found) {
            fullSatElements++;
            found = true;
          }
        }
      }
    }

    return {
      full_saturation_elements: fullSatElements,
      full_saturation_hues: fullSatHues.size,
      pass: fullSatHues.size <= 1
    };
  }

  // ─── CF-09: Body Text Color Softness ──────────────────────────────

  function cf09_bodyTextSoftness() {
    const bodyTextEls = allVisible.filter(el =>
      el.tagName === 'P' || el.tagName === 'LI'
    );

    let pureBlackCount = 0;

    for (const el of bodyTextEls) {
      const style = window.getComputedStyle(el);
      const fg = utils.parseColor(style.color);
      if (!fg) continue;

      // Pure black text
      if (fg.r === 0 && fg.g === 0 && fg.b === 0) {
        // On white or near-white background
        const bg = utils.getEffectiveBackground(el);
        if (bg) {
          const bgHsl = utils.rgbToHsl(bg.r, bg.g, bg.b);
          if (bgHsl.l >= 90) {
            pureBlackCount++;
          }
        }
      }
    }

    return {
      pure_black_body_text: pureBlackCount,
      pass: pureBlackCount === 0
    };
  }

  // ─── CF-10: Complementary Adjacency Detection ────────────────────

  function cf10_complementaryAdjacency() {
    const MAX_ELEMENTS = 200;
    const MAX_PAIRS = 10;

    // Collect viewport elements with chromatic colors (S > 40%)
    const chromaticEls = [];

    for (const el of viewportElements) {
      if (chromaticEls.length >= MAX_ELEMENTS) break;
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;

      for (const prop of ['color', 'backgroundColor']) {
        const parsed = utils.parseColor(style[prop]);
        if (!parsed || parsed.a < 0.1) continue;
        const hsl = utils.rgbToHsl(parsed.r, parsed.g, parsed.b);

        if (hsl.s > 40) {
          chromaticEls.push({ el, rect, hue: hsl.h, selector: utils.getSelector(el) });
          break;
        }
      }
    }

    let pairCount = 0;
    const pairs = [];

    for (let i = 0; i < chromaticEls.length; i++) {
      for (let j = i + 1; j < chromaticEls.length; j++) {
        const a = chromaticEls[i];
        const b = chromaticEls[j];
        if (a.el === b.el) continue;

        const hueDist = Math.min(
          Math.abs(a.hue - b.hue),
          360 - Math.abs(a.hue - b.hue)
        );

        if (hueDist >= 150 && hueDist <= 210 && utils.areAdjacent(a.rect, b.rect)) {
          pairCount++;
          if (pairs.length < MAX_PAIRS) {
            pairs.push({
              sel1: a.selector,
              sel2: b.selector,
              hue1: Math.round(a.hue),
              hue2: Math.round(b.hue),
              hue_distance: Math.round(hueDist)
            });
          }
        }
      }
    }

    return {
      complementary_pairs: pairCount,
      risk: pairCount > 0,
      pairs
    };
  }

  // ─── CF-11: Saturated Color Area Overuse ────────────────────────

  function cf11_saturatedArea() {
    const SAT_THRESHOLD = 70;
    const AREA_THRESHOLD = 25; // percent
    const HUE_BUCKET_SIZE = 30;
    const bucketAreas = {}; // bucket -> total pixel area

    const viewportArea = window.innerWidth * window.innerHeight;

    for (const el of viewportElements) {
      const style = window.getComputedStyle(el);
      const bgParsed = utils.parseColor(style.backgroundColor);
      if (!bgParsed || bgParsed.a < 0.1) continue;

      const hsl = utils.rgbToHsl(bgParsed.r, bgParsed.g, bgParsed.b);
      if (hsl.s <= SAT_THRESHOLD) continue;

      const rect = el.getBoundingClientRect();
      const area = rect.width * rect.height;
      if (area === 0) continue;

      const bucket = Math.floor(hsl.h / HUE_BUCKET_SIZE) * HUE_BUCKET_SIZE;
      bucketAreas[bucket] = (bucketAreas[bucket] || 0) + area;
    }

    const hueAreas = [];
    let overuseCount = 0;

    for (const [bucket, area] of Object.entries(bucketAreas)) {
      const areaPct = Math.round((area / viewportArea) * 1000) / 10;
      hueAreas.push({ hue_bucket: parseInt(bucket), area_pct: areaPct });
      if (areaPct > AREA_THRESHOLD) {
        overuseCount++;
      }
    }

    // Sort by area descending
    hueAreas.sort((a, b) => b.area_pct - a.area_pct);

    return {
      hue_areas: hueAreas,
      overuse_hues: overuseCount,
      pass: overuseCount === 0
    };
  }

  // ─── CF-12: Perceived Brightness Consistency ───────────────────────

  function cf12_perceivedBrightness(paletteResult) {
    const SAT_THRESHOLD = 30;
    const DELTA_THRESHOLD = 0.15;

    // Group chromatic colors by semantic role
    const roleGroups = new Map(); // role -> [{r,g,b,brightness}]

    for (const entry of paletteResult.palette) {
      if (entry.hsl.s <= SAT_THRESHOLD) continue; // skip low-saturation

      const role = entry.role; // 'status' or 'chromatic'
      if (role !== 'status' && role !== 'chromatic') continue;

      // Parse hex back to RGB for brightness calc
      const r = parseInt(entry.hex.slice(1, 3), 16);
      const g = parseInt(entry.hex.slice(3, 5), 16);
      const b = parseInt(entry.hex.slice(5, 7), 16);

      const brightness = Math.sqrt(0.299 * r * r + 0.587 * g * g + 0.114 * b * b) / 255;

      if (!roleGroups.has(role)) {
        roleGroups.set(role, []);
      }
      roleGroups.get(role).push({ hex: entry.hex, brightness });
    }

    let roleGroupsChecked = 0;
    let inconsistentGroups = 0;
    let maxDelta = 0;

    for (const [role, colors] of roleGroups) {
      if (colors.length < 2) continue;
      roleGroupsChecked++;

      // Compute max brightness delta within this role group
      let groupMin = Infinity;
      let groupMax = -Infinity;

      for (const c of colors) {
        if (c.brightness < groupMin) groupMin = c.brightness;
        if (c.brightness > groupMax) groupMax = c.brightness;
      }

      const delta = groupMax - groupMin;
      if (delta > maxDelta) maxDelta = delta;

      if (delta > DELTA_THRESHOLD) {
        inconsistentGroups++;
      }
    }

    return {
      role_groups_checked: roleGroupsChecked,
      inconsistent_groups: inconsistentGroups,
      max_delta: Math.round(maxDelta * 1000) / 1000,
      pass: inconsistentGroups === 0
    };
  }

  // ─── Execute all checks and assemble result ───────────────────────

  const cf02 = cf02_palette();

  return {
    cf01_text_contrast: cf01_textContrast(),
    cf02_palette: cf02,
    cf03_grey_saturation: cf03_greySaturation(),
    cf04_interactive_primary: cf04_interactivePrimary(),
    cf05_warm_cool_balance: cf05_warmCoolBalance(),
    cf06_dark_mode: cf06_darkMode(),
    cf07_red_blue_adjacency: cf07_redBlueAdjacency(),
    cf08_saturation_overuse: cf08_saturationOveruse(),
    cf09_body_text_softness: cf09_bodyTextSoftness(),
    cf10_complementary_adjacency: cf10_complementaryAdjacency(),
    cf11_saturated_area: cf11_saturatedArea(),
    cf12_perceived_brightness: cf12_perceivedBrightness(cf02)
  };
}
