// DPT Layer 3: Spatial Rhythm
// Spacing scale, touch targets, proximity, elevation, alignment, whitespace
function spatialRhythm(utils) {

  const MAX_VIOLATIONS = 15;
  const MAX_SAMPLE = 300;

  // ─── Helpers ─────────────────────────────────────────────────────

  function parsePx(val) {
    if (!val || val === 'normal' || val === 'auto' || val === 'none') return null;
    const n = parseFloat(val);
    return isNaN(n) ? null : n;
  }

  function roundTo(n, decimals) {
    const f = Math.pow(10, decimals);
    return Math.round(n * f) / f;
  }

  function clusterValues(values, tolerance) {
    // Sort and merge values within tolerance into clusters
    if (!values.length) return [];
    const sorted = [...values].sort((a, b) => a - b);
    const clusters = [];
    let current = { value: sorted[0], sum: sorted[0], count: 1 };

    for (let i = 1; i < sorted.length; i++) {
      if (sorted[i] - (current.sum / current.count) <= tolerance) {
        current.sum += sorted[i];
        current.count++;
      } else {
        clusters.push({ value: roundTo(current.sum / current.count, 1), count: current.count });
        current = { value: sorted[i], sum: sorted[i], count: 1 };
      }
    }
    clusters.push({ value: roundTo(current.sum / current.count, 1), count: current.count });
    return clusters;
  }

  // ─── SR-01: Spacing Scale Systematicity ──────────────────────────

  function sr01_spacingScale() {
    const allElements = utils.queryVisible('*');
    const sample = allElements.slice(0, MAX_SAMPLE);
    const spacingValues = [];

    for (const el of sample) {
      const cs = window.getComputedStyle(el);
      const props = [
        cs.marginTop, cs.marginRight, cs.marginBottom, cs.marginLeft,
        cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft,
        cs.gap, cs.rowGap, cs.columnGap
      ];
      for (const val of props) {
        const px = parsePx(val);
        if (px !== null && px > 0) {
          spacingValues.push(Math.round(px));
        }
      }
    }

    const detected = utils.detectBaseUnit(spacingValues);
    const baseUnit = detected.unit;
    const onGrid = spacingValues.filter(v => v % baseUnit === 0).length;
    const offGrid = spacingValues.length - onGrid;

    // Collect the actual off-grid values (deduplicated, sorted)
    const offGridSet = new Set();
    for (const v of spacingValues) {
      if (v % baseUnit !== 0) offGridSet.add(v);
    }
    const offGridValues = [...offGridSet].sort((a, b) => a - b).slice(0, 30);

    const consistency = spacingValues.length > 0
      ? roundTo(onGrid / spacingValues.length, 3)
      : 1;

    return {
      base_unit: baseUnit,
      confidence: detected.confidence,
      total_values: spacingValues.length,
      on_grid: onGrid,
      off_grid: offGrid,
      off_grid_values: offGridValues,
      consistency: consistency
    };
  }

  // ─── SR-02: Touch Target Size ────────────────────────────────────

  function sr02_touchTargets() {
    const allElements = utils.queryVisible('*');
    const interactive = allElements.filter(el => utils.isInteractive(el) && utils.isInViewport(el));
    const violations = [];

    for (const el of interactive) {
      const rect = el.getBoundingClientRect();
      const w = Math.round(rect.width);
      const h = Math.round(rect.height);

      if (w < 44 || h < 44) {
        if (violations.length < MAX_VIOLATIONS) {
          violations.push({
            selector: utils.getSelector(el),
            width: w,
            height: h
          });
        }
      }
    }

    const undersized = interactive.filter(el => {
      const r = el.getBoundingClientRect();
      return r.width < 44 || r.height < 44;
    }).length;

    return {
      total_interactive: interactive.length,
      undersized: undersized,
      violations: violations,
      pass: undersized === 0
    };
  }

  // ─── SR-03: Proximity Grouping (Label-Input) ────────────────────

  function sr03_proximityGrouping() {
    const labels = utils.queryVisible('label[for]');
    const pairs = [];
    const violations = [];

    for (const label of labels) {
      const forId = label.getAttribute('for');
      if (!forId) continue;
      const input = document.getElementById(forId);
      if (!input || !utils.isVisible(input)) continue;

      const labelRect = label.getBoundingClientRect();
      const inputRect = input.getBoundingClientRect();
      const gapToInput = utils.gap(labelRect, inputRect);

      // Find the previous visible element before the label
      let gapToPrevious = Infinity;
      let prev = label.previousElementSibling;

      // Walk backwards to find a visible previous sibling
      while (prev && !utils.isVisible(prev)) {
        prev = prev.previousElementSibling;
      }

      // If no previous sibling, try parent's previous sibling
      if (!prev && label.parentElement) {
        prev = label.parentElement.previousElementSibling;
        while (prev && !utils.isVisible(prev)) {
          prev = prev.previousElementSibling;
        }
      }

      if (prev) {
        const prevRect = prev.getBoundingClientRect();
        gapToPrevious = utils.gap(prevRect, labelRect);
      }

      const properlyGrouped = gapToInput <= gapToPrevious;
      pairs.push({ label: forId, properlyGrouped });

      if (!properlyGrouped && violations.length < MAX_VIOLATIONS) {
        violations.push({
          label: utils.getSelector(label),
          input: utils.getSelector(input),
          gap_to_input: Math.round(gapToInput),
          gap_to_previous: gapToPrevious === Infinity ? 'none' : Math.round(gapToPrevious)
        });
      }
    }

    const properlyGrouped = pairs.filter(p => p.properlyGrouped).length;

    return {
      pairs_checked: pairs.length,
      properly_grouped: properlyGrouped,
      violations: violations
    };
  }

  // ─── SR-04: Border Radius Consistency ────────────────────────────

  function sr04_borderRadius() {
    const allElements = utils.queryVisible('*');
    const sample = allElements.slice(0, MAX_SAMPLE);
    const radiiSet = new Set();

    for (const el of sample) {
      const cs = window.getComputedStyle(el);
      const br = cs.borderRadius;
      if (!br || br === '0px') continue;

      // borderRadius can be shorthand: "4px 4px 4px 4px" or "4px"
      // Take the first value as the representative token
      const first = br.split(/\s+/)[0];
      const px = parsePx(first);
      if (px !== null && px > 0) {
        radiiSet.add(Math.round(px));
      }
    }

    const distinctRadii = [...radiiSet].sort((a, b) => a - b);

    return {
      distinct_radii: distinctRadii,
      token_count: distinctRadii.length,
      pass: distinctRadii.length <= 4
    };
  }

  // ─── SR-05: Shadow Elevation System ──────────────────────────────

  function sr05_shadowElevation() {
    const allElements = utils.queryVisible('*');
    const sample = allElements.slice(0, MAX_SAMPLE);
    const shadows = [];

    for (const el of sample) {
      const cs = window.getComputedStyle(el);
      const bs = cs.boxShadow;
      if (!bs || bs === 'none') continue;

      // A single element can have multiple comma-separated shadows.
      // Split carefully: commas inside rgb()/rgba() should not split.
      // getComputedStyle normalizes to "rgb(r, g, b) Xpx Ypx Bpx Spx"
      const shadowParts = [];
      let depth = 0;
      let current = '';
      for (let i = 0; i < bs.length; i++) {
        const ch = bs[i];
        if (ch === '(') depth++;
        else if (ch === ')') depth--;
        else if (ch === ',' && depth === 0) {
          shadowParts.push(current.trim());
          current = '';
          continue;
        }
        current += ch;
      }
      if (current.trim()) shadowParts.push(current.trim());

      for (const part of shadowParts) {
        // Extract numeric px values from the shadow string.
        // Computed form: "rgb(r, g, b) Xpx Ypx Bpx [Spx]"
        // Or with inset:  "inset rgb(r, g, b) Xpx Ypx Bpx [Spx]"
        // Strip color function and "inset", then grab px values.
        const stripped = part
          .replace(/rgba?\([^)]*\)/g, '')
          .replace(/inset/g, '')
          .trim();
        const pxValues = stripped.match(/-?[\d.]+px/g);
        if (!pxValues || pxValues.length < 2) continue;

        const xOffset = parseFloat(pxValues[0]);
        const yOffset = parseFloat(pxValues[1]);
        const blur = pxValues.length >= 3 ? parseFloat(pxValues[2]) : 0;

        shadows.push({ y_offset: yOffset, blur: blur });
      }
    }

    if (shadows.length === 0) {
      return {
        shadow_count: 0,
        elevation_levels: 0,
        direction_consistent: true,
        levels: [],
        pass: true
      };
    }

    // Check directional consistency: all y-offsets should be same sign (or zero)
    const nonZeroY = shadows.filter(s => s.y_offset !== 0);
    let directionConsistent = true;
    if (nonZeroY.length > 0) {
      const positive = nonZeroY.filter(s => s.y_offset > 0).length;
      const negative = nonZeroY.filter(s => s.y_offset < 0).length;
      directionConsistent = positive === 0 || negative === 0;
    }

    // Cluster by (y_offset, blur) to find elevation levels
    // Use combined metric: group shadows with similar y+blur signatures
    const signatures = shadows.map(s => ({
      y_offset: Math.round(s.y_offset),
      blur: Math.round(s.blur)
    }));

    // Deduplicate into level buckets
    const levelMap = new Map();
    for (const sig of signatures) {
      const key = `${sig.y_offset}|${sig.blur}`;
      if (!levelMap.has(key)) {
        levelMap.set(key, { y_offset: sig.y_offset, blur: sig.blur, count: 0 });
      }
      levelMap.get(key).count++;
    }

    const levels = [...levelMap.values()]
      .sort((a, b) => a.y_offset - b.y_offset || a.blur - b.blur);

    return {
      shadow_count: shadows.length,
      elevation_levels: levels.length,
      direction_consistent: directionConsistent,
      levels: levels,
      pass: directionConsistent && levels.length <= 5
    };
  }

  // ─── SR-06: Content Container Max-Width ──────────────────────────

  function sr06_containerMaxWidth() {
    const paragraphs = utils.queryVisible('p');
    const blowoutRisk = [];

    for (const p of paragraphs) {
      const text = p.textContent || '';
      if (text.trim().length < 20) continue; // skip trivially short paragraphs

      const rect = p.getBoundingClientRect();
      const cs = window.getComputedStyle(p);
      const fontSize = parseFloat(cs.fontSize) || 16;

      // Approximate ch width as ~0.5em for most proportional fonts
      const chWidth = fontSize * 0.5;
      const estimatedChars = Math.round(rect.width / chWidth);

      if (estimatedChars > 75) {
        // Check if the paragraph or any ancestor has a max-width constraint
        let constrained = false;
        let current = p;
        while (current && current !== document.body) {
          const style = window.getComputedStyle(current);
          const mw = style.maxWidth;
          if (mw && mw !== 'none' && mw !== '0px') {
            const mwPx = parsePx(mw);
            // Percentage max-widths still count as constrained
            if (mwPx !== null || mw.includes('%') || mw.includes('ch') || mw.includes('em')) {
              constrained = true;
              break;
            }
          }
          current = current.parentElement;
        }

        if (!constrained && blowoutRisk.length < MAX_VIOLATIONS) {
          blowoutRisk.push({
            selector: utils.getSelector(p),
            width: Math.round(rect.width),
            estimated_chars: estimatedChars
          });
        }
      }
    }

    return {
      unconstrained_containers: blowoutRisk.length,
      blowout_risk: blowoutRisk,
      pass: blowoutRisk.length === 0
    };
  }

  // ─── SR-07: Alignment Vector Detection ───────────────────────────

  function sr07_alignmentVectors() {
    const allElements = utils.queryVisible('*');
    const inViewport = allElements.filter(el => utils.isInViewport(el));
    const sample = inViewport.slice(0, MAX_SAMPLE);
    const TOLERANCE = 2;

    // Collect left and right edges
    const leftEdges = [];
    const rightEdges = [];
    const elementEdges = []; // track per-element for unaligned counting

    for (const el of sample) {
      const rect = el.getBoundingClientRect();
      const left = Math.round(rect.left);
      const right = Math.round(rect.right);
      leftEdges.push(left);
      rightEdges.push(right);
      elementEdges.push({ left, right });
    }

    const allEdges = [...leftEdges, ...rightEdges];
    const clusters = clusterValues(allEdges, TOLERANCE);

    // Only keep guides with multiple elements aligned
    const guides = clusters
      .filter(c => c.count >= 3)
      .sort((a, b) => b.count - a.count)
      .map(c => ({ x: c.value, element_count: c.count }));

    // Count elements that don't align with any guide
    let unalignedCount = 0;
    for (const edge of elementEdges) {
      const leftAligned = guides.some(g => Math.abs(edge.left - g.x) <= TOLERANCE);
      const rightAligned = guides.some(g => Math.abs(edge.right - g.x) <= TOLERANCE);
      if (!leftAligned && !rightAligned) {
        unalignedCount++;
      }
    }

    const alignmentScore = sample.length > 0
      ? roundTo(1 - (unalignedCount / sample.length), 3)
      : 1;

    return {
      alignment_guides: guides.slice(0, 20),
      unaligned_count: unalignedCount,
      alignment_score: alignmentScore
    };
  }

  // ─── SR-08: Whitespace Density Map ───────────────────────────────

  function sr08_whitespaceDensity() {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const cellW = vw / 4;
    const cellH = vh / 4;

    // Initialize 4x4 grid of zeros (occupied pixels)
    const occupied = Array.from({ length: 4 }, () => Array(4).fill(0));
    const cellArea = cellW * cellH;

    const allElements = utils.queryVisible('*');
    const inViewport = allElements.filter(el => utils.isInViewport(el));

    // For each element, add its overlap with each grid cell
    for (const el of inViewport) {
      const rect = el.getBoundingClientRect();
      // Skip elements that are the full viewport (body, html, wrappers)
      if (rect.width >= vw * 0.98 && rect.height >= vh * 0.98) continue;

      for (let row = 0; row < 4; row++) {
        for (let col = 0; col < 4; col++) {
          const cellLeft = col * cellW;
          const cellTop = row * cellH;
          const cellRight = cellLeft + cellW;
          const cellBottom = cellTop + cellH;

          // Compute intersection area
          const overlapLeft = Math.max(rect.left, cellLeft);
          const overlapTop = Math.max(rect.top, cellTop);
          const overlapRight = Math.min(rect.right, cellRight);
          const overlapBottom = Math.min(rect.bottom, cellBottom);

          if (overlapRight > overlapLeft && overlapBottom > overlapTop) {
            const area = (overlapRight - overlapLeft) * (overlapBottom - overlapTop);
            occupied[row][col] += area;
          }
        }
      }
    }

    // Compute density per cell (capped at 1.0 since elements can overlap)
    const grid = occupied.map(row =>
      row.map(val => roundTo(Math.min(val / cellArea, 1), 3))
    );

    const flat = grid.flat();
    const minDensity = roundTo(Math.min(...flat), 3);
    const maxDensity = roundTo(Math.max(...flat), 3);

    // Balance score: 1.0 means perfectly uniform, drops as variance grows
    const mean = flat.reduce((a, b) => a + b, 0) / flat.length;
    const variance = flat.reduce((sum, v) => sum + (v - mean) ** 2, 0) / flat.length;
    // Normalize: stddev of 0 = perfect balance (1.0), stddev of 0.5 = poor (0.0)
    const balanceScore = roundTo(Math.max(0, 1 - Math.sqrt(variance) * 2), 3);

    return {
      grid: grid,
      min_density: minDensity,
      max_density: maxDensity,
      balance_score: balanceScore
    };
  }

  // ─── SR-09: Body Text Margin Adequacy ────────────────────────────

  function sr09_bodyTextMarginAdequacy() {
    const paragraphs = utils.queryVisible('p');
    const inViewport = paragraphs.filter(el => utils.isInViewport(el));
    const violations = [];
    let inadequateMargin = 0;

    for (const p of inViewport) {
      const cs = window.getComputedStyle(p);
      const fontSize = parseFloat(cs.fontSize) || 16;
      const parent = p.parentElement;
      if (!parent) continue;

      const parentCs = window.getComputedStyle(parent);
      const paddingLeft = parseFloat(parentCs.paddingLeft) || 0;
      const paddingRight = parseFloat(parentCs.paddingRight) || 0;

      // Minimum adequate margin is 1em (the paragraph's own font-size)
      if (paddingLeft < fontSize || paddingRight < fontSize) {
        inadequateMargin++;
        if (violations.length < MAX_VIOLATIONS) {
          violations.push({
            selector: utils.getSelector(p),
            parent_padding_left: roundTo(paddingLeft, 1),
            parent_padding_right: roundTo(paddingRight, 1),
            font_size: roundTo(fontSize, 1)
          });
        }
      }
    }

    return {
      paragraphs_checked: inViewport.length,
      inadequate_margin: inadequateMargin,
      violations: violations,
      pass: inadequateMargin === 0
    };
  }

  // ─── SR-10: Shadow Color Temperature ────────────────────────────

  function sr10_shadowColorTemperature() {
    const allElements = utils.queryVisible('*');
    const sample = allElements.slice(0, MAX_SAMPLE);
    let shadowsFound = 0;
    let achromaticShadows = 0;
    let tintedShadows = 0;

    for (const el of sample) {
      const cs = window.getComputedStyle(el);
      const bs = cs.boxShadow;
      if (!bs || bs === 'none') continue;

      // Split comma-separated shadows (respecting parentheses)
      const shadowParts = [];
      let depth = 0;
      let current = '';
      for (let i = 0; i < bs.length; i++) {
        const ch = bs[i];
        if (ch === '(') depth++;
        else if (ch === ')') depth--;
        else if (ch === ',' && depth === 0) {
          shadowParts.push(current.trim());
          current = '';
          continue;
        }
        current += ch;
      }
      if (current.trim()) shadowParts.push(current.trim());

      for (const part of shadowParts) {
        // Extract the color function from the shadow string
        const colorMatch = part.match(/rgba?\([^)]*\)/);
        if (!colorMatch) continue;

        const parsed = utils.parseColor(colorMatch[0]);
        if (!parsed || parsed.a === 0) continue;

        shadowsFound++;
        const hsl = utils.rgbToHsl(parsed.r, parsed.g, parsed.b);

        if (hsl.s < 5) {
          achromaticShadows++;
        } else {
          tintedShadows++;
        }
      }
    }

    return {
      shadows_found: shadowsFound,
      achromatic_shadows: achromaticShadows,
      tinted_shadows: tintedShadows,
      pass: shadowsFound === 0 || tintedShadows > achromaticShadows
    };
  }

  // ─── Assemble and Return ─────────────────────────────────────────

  return {
    sr01_spacing_scale: sr01_spacingScale(),
    sr02_touch_targets: sr02_touchTargets(),
    sr03_proximity_grouping: sr03_proximityGrouping(),
    sr04_border_radius: sr04_borderRadius(),
    sr05_shadow_elevation: sr05_shadowElevation(),
    sr06_container_max_width: sr06_containerMaxWidth(),
    sr07_alignment_vectors: sr07_alignmentVectors(),
    sr08_whitespace_density: sr08_whitespaceDensity(),
    sr09_body_text_margin: sr09_bodyTextMarginAdequacy(),
    sr10_shadow_color_temperature: sr10_shadowColorTemperature()
  };
}
