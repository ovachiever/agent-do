// DPT Layer 5: Coherence
// Design system consistency, token adherence, component drift, animation bounds

function coherence(utils) {

  const MAX_ITEMS = 15;
  const MAX_DRIFT_ELEMENTS = 200;

  const allVisible = utils.queryVisible('*');

  // ─── Shared: Extract CSS Custom Properties ─────────────────────────

  function extractCustomProperties() {
    const colorTokens = new Map();   // name -> {r,g,b,a}
    const spacingTokens = [];        // numeric px values
    const typeTokens = [];           // numeric px values

    // 1. Scan :root computed style for --* properties
    const rootStyle = window.getComputedStyle(document.documentElement);

    // 2. Iterate stylesheets to find declared custom properties
    const declaredProps = new Map(); // prop name -> raw value
    for (const sheet of document.styleSheets) {
      try {
        const rules = sheet.cssRules || sheet.rules;
        if (!rules) continue;
        for (const rule of rules) {
          if (rule.type !== CSSRule.STYLE_RULE) continue;
          // Look at :root, html, body declarations
          if (!rule.selectorText || !rule.selectorText.match(/(:root|html|body)/i)) continue;
          for (let i = 0; i < rule.style.length; i++) {
            const prop = rule.style[i];
            if (prop.startsWith('--')) {
              declaredProps.set(prop, rule.style.getPropertyValue(prop).trim());
            }
          }
        }
      } catch (e) {
        // Cross-origin stylesheet — skip silently
      }
    }

    // Also read from computed style on :root (catches properties set by JS or inline)
    // getComputedStyle doesn't enumerate custom properties directly,
    // so we rely on the stylesheet scan above plus inline style on documentElement
    const inlineStyle = document.documentElement.style;
    for (let i = 0; i < inlineStyle.length; i++) {
      const prop = inlineStyle[i];
      if (prop.startsWith('--')) {
        declaredProps.set(prop, inlineStyle.getPropertyValue(prop).trim());
      }
    }

    // Classify each custom property
    for (const [name, rawValue] of declaredProps) {
      const resolved = rootStyle.getPropertyValue(name).trim() || rawValue;
      const lower = name.toLowerCase();

      // Attempt color parse
      const colorParsed = utils.parseColor(resolved);
      if (colorParsed) {
        colorTokens.set(name, colorParsed);
        continue;
      }

      // Check if it looks like a color token by name heuristic even if parse fails
      // (e.g. references another variable)
      const isColorName = /color|bg|background|border|text|fill|stroke|accent|primary|secondary|success|danger|warning|info|neutral|surface|foreground/i.test(lower);

      // Spacing tokens: numeric px/rem values in spacing/gap/margin/padding named vars
      const isSpacingName = /spacing|space|gap|margin|padding|gutter|indent|size|offset/i.test(lower);
      const pxMatch = resolved.match(/^(-?[\d.]+)\s*px$/);
      const remMatch = resolved.match(/^(-?[\d.]+)\s*rem$/);

      if (isSpacingName && (pxMatch || remMatch)) {
        const px = pxMatch ? parseFloat(pxMatch[1]) : parseFloat(remMatch[1]) * 16;
        spacingTokens.push(px);
        continue;
      }

      // Type scale tokens: font-size related
      const isTypeName = /font-size|type|text-size|heading|body-size|fs-/i.test(lower);
      if (isTypeName && (pxMatch || remMatch)) {
        const px = pxMatch ? parseFloat(pxMatch[1]) : parseFloat(remMatch[1]) * 16;
        typeTokens.push(px);
        continue;
      }

      // If it has a color-like name and we couldn't parse, try evaluating via temp element
      if (isColorName) {
        const temp = document.createElement('div');
        temp.style.color = resolved;
        document.body.appendChild(temp);
        const computed = window.getComputedStyle(temp).color;
        document.body.removeChild(temp);
        const parsed = utils.parseColor(computed);
        if (parsed) {
          colorTokens.set(name, parsed);
        }
      }
    }

    return { colorTokens, spacingTokens, typeTokens };
  }

  const tokens = extractCustomProperties();

  // ─── CO-01: Color Token Consistency ──────────────────────────────

  function co01_colorTokenConsistency() {
    const RGB_TOLERANCE = 2;
    const usedColorMap = new Map(); // hex -> count

    for (const el of allVisible) {
      const style = window.getComputedStyle(el);
      for (const prop of ['color', 'backgroundColor', 'borderColor', 'outlineColor']) {
        const parsed = utils.parseColor(style[prop]);
        if (!parsed || parsed.a < 0.05) continue;
        const hex = utils.rgbToHex(parsed.r, parsed.g, parsed.b);
        usedColorMap.set(hex, (usedColorMap.get(hex) || 0) + 1);
      }
    }

    const tokenColors = Array.from(tokens.colorTokens.values());
    let tokenized = 0;
    let freestyle = 0;
    const freestyleColors = [];

    for (const [hex, count] of usedColorMap) {
      // Parse hex back to RGB for comparison
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);

      let matchesToken = false;
      for (const tc of tokenColors) {
        if (Math.abs(r - tc.r) <= RGB_TOLERANCE &&
            Math.abs(g - tc.g) <= RGB_TOLERANCE &&
            Math.abs(b - tc.b) <= RGB_TOLERANCE) {
          matchesToken = true;
          break;
        }
      }

      if (matchesToken) {
        tokenized++;
      } else {
        freestyle++;
        freestyleColors.push({ hex, count });
      }
    }

    // Sort freestyle by count descending, cap
    freestyleColors.sort((a, b) => b.count - a.count);

    const totalUsed = usedColorMap.size;
    const ratio = totalUsed > 0
      ? Math.round((tokenized / totalUsed) * 1000) / 1000
      : 1;

    return {
      defined_color_tokens: tokens.colorTokens.size,
      used_colors: totalUsed,
      tokenized,
      freestyle,
      freestyle_colors: freestyleColors.slice(0, MAX_ITEMS),
      tokenization_ratio: ratio
    };
  }

  // ─── CO-02: Spacing Token Consistency ────────────────────────────

  function co02_spacingTokenConsistency() {
    const PX_TOLERANCE = 1;
    const spacingValues = new Map(); // px value -> count

    for (const el of allVisible) {
      const style = window.getComputedStyle(el);
      const props = [
        'marginTop', 'marginRight', 'marginBottom', 'marginLeft',
        'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
        'gap', 'rowGap', 'columnGap'
      ];

      for (const prop of props) {
        const raw = style[prop];
        if (!raw || raw === 'normal' || raw === 'auto') continue;
        const px = parseFloat(raw);
        if (isNaN(px) || px === 0) continue;
        const rounded = Math.round(px * 10) / 10;
        spacingValues.set(rounded, (spacingValues.get(rounded) || 0) + 1);
      }
    }

    const definedTokens = tokens.spacingTokens.slice().sort((a, b) => a - b);
    let onToken = 0;
    let offToken = 0;
    const freestyleSpacing = [];

    for (const [value, count] of spacingValues) {
      let matches = false;
      for (const t of definedTokens) {
        if (Math.abs(value - t) <= PX_TOLERANCE) {
          matches = true;
          break;
        }
      }
      if (matches) {
        onToken++;
      } else {
        offToken++;
        freestyleSpacing.push({ value, count });
      }
    }

    freestyleSpacing.sort((a, b) => b.count - a.count);

    const total = onToken + offToken;
    const ratio = total > 0
      ? Math.round((onToken / total) * 1000) / 1000
      : 1;

    return {
      defined_spacing_tokens: definedTokens,
      freestyle_spacing: freestyleSpacing.slice(0, MAX_ITEMS),
      tokenization_ratio: ratio
    };
  }

  // ─── CO-03: Component Consistency (Drift Detection) ──────────────

  function co03_componentConsistency() {
    const MIN_GROUP_SIZE = 3;
    const CHECKED_PROPS = [
      'fontSize', 'fontWeight', 'color', 'backgroundColor',
      'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
      'borderRadius'
    ];

    // Group elements by tag+class pattern
    const groups = new Map(); // pattern -> Element[]

    const sampled = allVisible.slice(0, MAX_DRIFT_ELEMENTS);

    for (const el of sampled) {
      const tag = el.tagName.toLowerCase();
      const classes = (typeof el.className === 'string' && el.className.trim())
        ? el.className.trim().split(/\s+/).sort().join('.')
        : '';
      const pattern = classes ? tag + '.' + classes : tag;

      if (!groups.has(pattern)) {
        groups.set(pattern, []);
      }
      groups.get(pattern).push(el);
    }

    let componentsChecked = 0;
    const driftingComponents = [];

    for (const [pattern, elements] of groups) {
      if (elements.length < MIN_GROUP_SIZE) continue;
      componentsChecked++;

      for (const prop of CHECKED_PROPS) {
        const values = elements.map(el => {
          const val = window.getComputedStyle(el)[prop];
          // Normalize to numeric where possible for stddev
          return val;
        });

        // Check if all values are identical
        const unique = [...new Set(values)];
        if (unique.length > 1) {
          if (driftingComponents.length < MAX_ITEMS) {
            driftingComponents.push({
              pattern,
              property: prop,
              values: unique.slice(0, 5) // cap unique value samples
            });
          }
        }
      }
    }

    // Consistency score: ratio of non-drifting component-property pairs
    const totalPairs = componentsChecked * CHECKED_PROPS.length;
    const driftingPairs = driftingComponents.length;
    const score = totalPairs > 0
      ? Math.round(((totalPairs - driftingPairs) / totalPairs) * 1000) / 1000
      : 0.4; // No reusable components found = low, not perfect

    return {
      components_checked: componentsChecked,
      drifting_components: driftingComponents,
      consistency_score: score
    };
  }

  // ─── CO-04: Shadow Direction Consistency ─────────────────────────

  function co04_shadowDirection() {
    const yOffsets = [];
    const xOffsets = [];

    for (const el of allVisible) {
      const shadow = window.getComputedStyle(el).boxShadow;
      if (!shadow || shadow === 'none') continue;

      // boxShadow can contain multiple shadows separated by commas
      // Each shadow: [inset] <x> <y> [blur] [spread] <color>
      // Computed style returns rgb values, so we parse carefully
      const shadowParts = shadow.split(/,(?![^(]*\))/);

      for (const part of shadowParts) {
        const trimmed = part.trim();
        if (trimmed === 'none') continue;

        // Remove color values (rgb/rgba) and 'inset' to isolate numeric offsets
        const cleaned = trimmed
          .replace(/rgba?\([^)]+\)/g, '')
          .replace(/inset/gi, '')
          .trim();

        // Extract numeric values (px)
        const nums = cleaned.match(/-?[\d.]+/g);
        if (nums && nums.length >= 2) {
          const x = parseFloat(nums[0]);
          const y = parseFloat(nums[1]);
          xOffsets.push(x);
          yOffsets.push(y);
        }
      }
    }

    // Check direction consistency
    let directionConsistent = true;

    if (yOffsets.length > 1) {
      const nonZeroY = yOffsets.filter(y => y !== 0);
      if (nonZeroY.length > 1) {
        const allPositive = nonZeroY.every(y => y > 0);
        const allNegative = nonZeroY.every(y => y < 0);
        if (!allPositive && !allNegative) directionConsistent = false;
      }
    }

    if (xOffsets.length > 1 && directionConsistent) {
      const nonZeroX = xOffsets.filter(x => x !== 0);
      if (nonZeroX.length > 1) {
        const allPositive = nonZeroX.every(x => x > 0);
        const allNegative = nonZeroX.every(x => x < 0);
        const allZero = nonZeroX.length === 0;
        if (!allPositive && !allNegative && !allZero) directionConsistent = false;
      }
    }

    return {
      shadows_found: yOffsets.length,
      y_offsets: [...new Set(yOffsets)].slice(0, MAX_ITEMS),
      x_offsets: [...new Set(xOffsets)].slice(0, MAX_ITEMS),
      direction_consistent: directionConsistent
    };
  }

  // ─── CO-05: Animation Duration Bounds ────────────────────────────

  function co05_animationDurationBounds() {
    const FEEDBACK_MAX_MS = 200;
    const LAYOUT_MAX_MS = 800;

    // Properties that are considered "feedback" (hover, color, opacity)
    const feedbackProps = new Set([
      'color', 'background-color', 'background', 'border-color',
      'opacity', 'box-shadow', 'text-shadow', 'outline-color',
      'fill', 'stroke', 'text-decoration-color'
    ]);

    let transitionCount = 0;
    let withinBounds = 0;
    const tooSlow = [];

    function parseDurationToMs(str) {
      if (!str || str === '0s') return 0;
      const val = parseFloat(str);
      if (isNaN(val)) return 0;
      if (str.includes('ms')) return val;
      return val * 1000; // seconds to ms
    }

    for (const el of allVisible) {
      const style = window.getComputedStyle(el);

      // Check transitions
      const tProp = style.transitionProperty;
      const tDur = style.transitionDuration;
      if (tProp && tProp !== 'none' && tDur && tDur !== '0s') {
        const props = tProp.split(',').map(p => p.trim());
        const durs = tDur.split(',').map(d => d.trim());

        for (let i = 0; i < props.length; i++) {
          const prop = props[i];
          const dur = durs[i] || durs[durs.length - 1]; // CSS repeats last
          const ms = parseDurationToMs(dur);
          if (ms === 0) continue;

          transitionCount++;
          const isFeedback = feedbackProps.has(prop) || prop === 'all';
          const bound = isFeedback ? FEEDBACK_MAX_MS : LAYOUT_MAX_MS;

          if (ms <= bound) {
            withinBounds++;
          } else {
            if (tooSlow.length < MAX_ITEMS) {
              tooSlow.push({
                selector: utils.getSelector(el),
                duration_ms: ms,
                property: prop
              });
            }
          }
        }
      }

      // Check animation durations
      const aDur = style.animationDuration;
      const aName = style.animationName;
      if (aName && aName !== 'none' && aDur && aDur !== '0s') {
        const names = aName.split(',').map(n => n.trim());
        const durs = aDur.split(',').map(d => d.trim());

        for (let i = 0; i < names.length; i++) {
          const dur = durs[i] || durs[durs.length - 1];
          const ms = parseDurationToMs(dur);
          if (ms === 0) continue;

          transitionCount++;
          // Animations: use layout bound as general ceiling
          if (ms <= LAYOUT_MAX_MS) {
            withinBounds++;
          } else {
            if (tooSlow.length < MAX_ITEMS) {
              tooSlow.push({
                selector: utils.getSelector(el),
                duration_ms: ms,
                property: 'animation:' + names[i]
              });
            }
          }
        }
      }
    }

    return {
      transition_count: transitionCount,
      within_bounds: withinBounds,
      too_slow: tooSlow,
      pass: tooSlow.length === 0
    };
  }

  // ─── CO-06: Transition Property Specificity ──────────────────────

  function co06_transitionPropertySpecificity() {
    let transitionAllCount = 0;
    let specificCount = 0;

    for (const el of allVisible) {
      const style = window.getComputedStyle(el);
      const tProp = style.transitionProperty;
      const tDur = style.transitionDuration;

      if (!tProp || tProp === 'none' || !tDur || tDur === '0s') continue;

      const props = tProp.split(',').map(p => p.trim());

      for (const prop of props) {
        if (prop === 'all') {
          transitionAllCount++;
        } else {
          specificCount++;
        }
      }
    }

    return {
      transition_all_count: transitionAllCount,
      specific_count: specificCount,
      pass: transitionAllCount === 0
    };
  }

  // ─── CO-07: Font Size Token Consistency ──────────────────────────

  function co07_fontSizeTokenConsistency() {
    const PX_TOLERANCE = 0.5;
    const sizeMap = new Map(); // px size -> count

    for (const el of allVisible) {
      const style = window.getComputedStyle(el);
      const fs = parseFloat(style.fontSize);
      if (isNaN(fs) || fs === 0) continue;
      const rounded = Math.round(fs * 10) / 10;
      sizeMap.set(rounded, (sizeMap.get(rounded) || 0) + 1);
    }

    const definedTokens = tokens.typeTokens.slice().sort((a, b) => a - b);
    let onToken = 0;
    let offToken = 0;
    const freestyleSizes = [];

    for (const [size, count] of sizeMap) {
      let matches = false;
      for (const t of definedTokens) {
        if (Math.abs(size - t) <= PX_TOLERANCE) {
          matches = true;
          break;
        }
      }
      if (matches) {
        onToken++;
      } else {
        offToken++;
        freestyleSizes.push({ size, count });
      }
    }

    freestyleSizes.sort((a, b) => b.count - a.count);

    const total = onToken + offToken;
    const ratio = total > 0
      ? Math.round((onToken / total) * 1000) / 1000
      : 1;

    return {
      defined_type_tokens: definedTokens,
      used_sizes: Array.from(sizeMap.keys()).sort((a, b) => a - b),
      freestyle_sizes: freestyleSizes.slice(0, MAX_ITEMS),
      tokenization_ratio: ratio
    };
  }

  // ─── CO-08: Overall Coherence Score ──────────────────────────────
  // Structural coherence: measured by value concentration, not token presence.
  // A site that uses 5 colors consistently is coherent regardless of whether
  // those colors are defined as CSS custom properties.

  function co08_overallCoherence(co01, co02, co03, co07) {
    // ── Color structural coherence ──
    // How concentrated is the palette? Fewer unique colors = more coherent.
    // Award full marks if ≤ 15 unique colors, penalize up to 50+.
    const usedColors = co01.used_colors || 0;
    const colorConcentration = usedColors <= 15 ? 1
      : usedColors <= 25 ? 0.8
      : usedColors <= 40 ? 0.5
      : 0.2;
    // Blend with token ratio if tokens exist (bonus for explicit system)
    const hasColorTokens = (co01.defined_color_tokens || 0) > 5;
    const colorCoherence = hasColorTokens
      ? co01.tokenization_ratio * 0.4 + colorConcentration * 0.6
      : colorConcentration;

    // ── Spacing structural coherence ──
    // Does spacing conform to a grid? Compute on-grid ratio directly.
    const spacingVals = [];
    for (const el of allVisible.slice(0, 300)) {
      const style = window.getComputedStyle(el);
      for (const prop of ['marginTop', 'marginBottom', 'paddingTop', 'paddingBottom', 'gap']) {
        const px = parseFloat(style[prop]);
        if (!isNaN(px) && px > 0) spacingVals.push(Math.round(px));
      }
    }
    let spacingGridScore = 0.3; // No data = low score, not perfect
    if (spacingVals.length >= 5) {
      // Test both 4px and 8px grids, pick the better one
      const onGrid4 = spacingVals.filter(v => v % 4 === 0).length / spacingVals.length;
      const onGrid8 = spacingVals.filter(v => v % 8 === 0).length / spacingVals.length;
      spacingGridScore = Math.max(onGrid4, onGrid8);
    }
    // Blend with token ratio if tokens exist
    const hasSpacingTokens = (co02.defined_spacing_tokens || []).length > 5;
    const spacingCoherence = hasSpacingTokens
      ? co02.tokenization_ratio * 0.3 + spacingGridScore * 0.7
      : spacingGridScore;

    // ── Component consistency (keep as-is) ──
    const componentCoherence = co03.consistency_score;

    // ── Type structural coherence ──
    // Fewer distinct sizes = more coherent. Does the scale look intentional?
    const usedSizes = (co07.used_sizes || []).length;
    const typeConcentration = usedSizes <= 5 ? 1
      : usedSizes <= 7 ? 0.85
      : usedSizes <= 10 ? 0.6
      : usedSizes <= 15 ? 0.35
      : 0.15;
    // Check if ratios between adjacent sizes are consistent (scale discipline)
    const sizes = (co07.used_sizes || []).slice().sort((a, b) => a - b);
    let scaleScore = 0;
    if (sizes.length >= 3) {
      const ratios = [];
      for (let i = 1; i < sizes.length; i++) {
        if (sizes[i - 1] > 0) ratios.push(sizes[i] / sizes[i - 1]);
      }
      if (ratios.length > 0) {
        const avg = ratios.reduce((a, b) => a + b, 0) / ratios.length;
        const variance = utils.stddev(ratios) / avg;
        scaleScore = variance < 0.15 ? 1 : variance < 0.3 ? 0.6 : 0.2;
      }
    }
    const hasTypeTokens = (co07.defined_type_tokens || []).length > 3;
    const typeCoherence = hasTypeTokens
      ? co07.tokenization_ratio * 0.3 + typeConcentration * 0.35 + scaleScore * 0.35
      : typeConcentration * 0.5 + scaleScore * 0.5;

    // Type coherence weighted highest — typographic consistency is the most
    // visible coherence signal (Santa Maria, Lupton).
    const overall = Math.round(
      (colorCoherence * 0.25 +
       spacingCoherence * 0.25 +
       componentCoherence * 0.20 +
       typeCoherence * 0.30) * 100
    );

    return {
      color_coherence: Math.round(colorCoherence * 1000) / 1000,
      spacing_coherence: Math.round(spacingCoherence * 1000) / 1000,
      component_coherence: componentCoherence,
      type_coherence: Math.round(typeCoherence * 1000) / 1000,
      overall
    };
  }

  // ─── Execute all checks and assemble result ───────────────────────

  const co01 = co01_colorTokenConsistency();
  const co02 = co02_spacingTokenConsistency();
  const co03 = co03_componentConsistency();
  const co04 = co04_shadowDirection();
  const co05 = co05_animationDurationBounds();
  const co06 = co06_transitionPropertySpecificity();
  const co07 = co07_fontSizeTokenConsistency();
  const co08 = co08_overallCoherence(co01, co02, co03, co07);

  return {
    co01_color_token_consistency: co01,
    co02_spacing_token_consistency: co02,
    co03_component_consistency: co03,
    co04_shadow_direction: co04,
    co05_animation_duration_bounds: co05,
    co06_transition_property_specificity: co06,
    co07_font_size_token_consistency: co07,
    co08_overall_coherence: co08
  };
}
