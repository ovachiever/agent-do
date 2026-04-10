// DPT Layer 2: Typographic Skeleton
// Type scale, weight hierarchy, measure, line-height, typographic craft

function typographicSkeleton(utils) {

  const MAX_ITEMS = 15;
  const GENERIC_FAMILIES = new Set(['sans-serif', 'serif', 'monospace', 'cursive', 'fantasy', 'system-ui', 'ui-sans-serif', 'ui-serif', 'ui-monospace', 'ui-rounded']);

  // ── Helpers ──────────────────────────────────────────────────────

  function px(el, prop) {
    return parseFloat(window.getComputedStyle(el)[prop]) || 0;
  }

  function fontSize(el) {
    return parseFloat(window.getComputedStyle(el).fontSize) || 0;
  }

  function lineHeight(el) {
    const style = window.getComputedStyle(el);
    const lh = style.lineHeight;
    if (lh === 'normal') return fontSize(el) * 1.2; // browser default ~1.2
    return parseFloat(lh) || 0;
  }

  function primaryFamily(el) {
    const raw = window.getComputedStyle(el).fontFamily;
    if (!raw) return null;
    // First font in the comma-separated list, stripped of quotes
    const first = raw.split(',')[0].trim().replace(/^["']|["']$/g, '');
    return first || null;
  }

  function collectVisible(selector) {
    return utils.queryVisible(selector).filter(el => utils.isInViewport(el));
  }

  // Gather body-text elements visible in viewport
  const bodyTextEls = collectVisible('p, li, td, th, span')
    .filter(el => utils.isBodyText(el) && el.textContent.trim().length > 0);

  const paragraphs = collectVisible('p')
    .filter(el => el.textContent.trim().length > 0);

  const headings = collectVisible('h1, h2, h3, h4, h5, h6')
    .filter(el => el.textContent.trim().length > 0);

  const allTextEls = collectVisible('p, span, li, td, th, label, a, strong, em, b, i, h1, h2, h3, h4, h5, h6, blockquote, figcaption, caption')
    .filter(el => utils.isTextElement(el) && el.textContent.trim().length > 0);


  // ── TS-01: Body Text Minimum Size ───────────────────────────────

  function ts01() {
    let minSize = Infinity;
    let violations = 0;
    const violationSelectors = [];

    for (const el of bodyTextEls) {
      const size = fontSize(el);
      if (size > 0 && size < minSize) minSize = size;
      if (size < 16) {
        violations++;
        if (violationSelectors.length < MAX_ITEMS) {
          violationSelectors.push(utils.getSelector(el));
        }
      }
    }

    return {
      min_size: minSize === Infinity ? 0 : Math.round(minSize * 100) / 100,
      violations,
      violation_selectors: violationSelectors,
      pass: violations === 0
    };
  }


  // ── TS-02: Absolute Floor (12px) ────────────────────────────────

  function ts02() {
    let count = 0;
    const elements = [];

    for (const el of allTextEls) {
      const size = fontSize(el);
      if (size > 0 && size < 12) {
        count++;
        if (elements.length < MAX_ITEMS) {
          elements.push(utils.getSelector(el));
        }
      }
    }

    return {
      sub_12px_count: count,
      elements,
      pass: count === 0
    };
  }


  // ── TS-03: Line Length (Measure) ────────────────────────────────

  function ts03() {
    const checks = [];
    let violations = 0;

    for (const el of paragraphs) {
      const rect = el.getBoundingClientRect();
      const size = fontSize(el);
      if (size <= 0 || rect.width <= 0) continue;

      const charsPerLine = Math.round(rect.width / (size * 0.48));
      const pass = charsPerLine >= 45 && charsPerLine <= 75;
      if (!pass) violations++;

      if (checks.length < MAX_ITEMS) {
        checks.push({
          selector: utils.getSelector(el),
          chars_per_line: charsPerLine,
          pass
        });
      }
    }

    return { checks, violations };
  }


  // ── TS-04: Body Line Height ─────────────────────────────────────

  function ts04() {
    const ratios = [];

    for (const el of bodyTextEls) {
      const size = fontSize(el);
      if (size <= 0) continue;
      const lh = lineHeight(el);
      const ratio = Math.round((lh / size) * 100) / 100;

      if (ratios.length < MAX_ITEMS) {
        ratios.push({
          selector: utils.getSelector(el),
          ratio,
          pass: ratio >= 1.4 && ratio <= 1.6
        });
      }
    }

    const allRatios = bodyTextEls
      .map(el => { const s = fontSize(el); return s > 0 ? lineHeight(el) / s : null; })
      .filter(r => r !== null);

    const med = utils.median(allRatios);
    const medRounded = Math.round(med * 100) / 100;

    return {
      ratios,
      median_ratio: medRounded,
      pass: medRounded >= 1.4 && medRounded <= 1.6
    };
  }


  // ── TS-05: Headline Line Height ─────────────────────────────────

  function ts05() {
    const ratios = [];
    let allPass = true;

    for (const el of headings) {
      const size = fontSize(el);
      if (size <= 0) continue;
      const lh = lineHeight(el);
      const ratio = Math.round((lh / size) * 100) / 100;
      const pass = ratio >= 1.1 && ratio <= 1.25;
      if (!pass) allPass = false;

      if (ratios.length < MAX_ITEMS) {
        ratios.push({
          tag: el.tagName.toLowerCase(),
          ratio,
          pass
        });
      }
    }

    return {
      ratios,
      pass: allPass
    };
  }


  // ── TS-06: Typeface Family Count ────────────────────────────────

  function ts06() {
    const familySet = new Set();

    for (const el of allTextEls) {
      const fam = primaryFamily(el);
      if (fam && !GENERIC_FAMILIES.has(fam.toLowerCase())) {
        familySet.add(fam);
      }
    }

    const families = Array.from(familySet).sort();

    return {
      families: families.slice(0, MAX_ITEMS),
      count: families.length,
      pass: families.length <= 3
    };
  }


  // ── TS-07: Font Weight Count ────────────────────────────────────

  function ts07() {
    const weightSet = new Set();

    for (const el of allTextEls) {
      const w = parseInt(window.getComputedStyle(el).fontWeight) || 400;
      weightSet.add(w);
    }

    const weights = Array.from(weightSet).sort((a, b) => a - b);

    // Group into bands of 100 (300-399, 400-499, etc.)
    const bandSet = new Set();
    for (const w of weights) {
      bandSet.add(Math.floor(w / 100) * 100);
    }

    return {
      weights_used: weights,
      band_count: bandSet.size,
      pass: bandSet.size <= 2
    };
  }


  // ── TS-08: Type Scale Systematicity ─────────────────────────────

  function ts08() {
    const sizeSet = new Set();

    for (const el of allTextEls) {
      const size = fontSize(el);
      if (size > 0) sizeSet.add(Math.round(size * 10) / 10);
    }

    const sizes = Array.from(sizeSet).sort((a, b) => a - b);
    const detection = utils.detectScaleRatio(sizes);

    return {
      sizes,
      detected_ratio: detection.ratio,
      best_known_match: detection.best_known_match || null,
      variance: detection.variance,
      systematic: detection.systematic
    };
  }


  // ── TS-09: Headline Size Jump ───────────────────────────────────

  function ts09() {
    const h1Els = collectVisible('h1').filter(el => el.textContent.trim().length > 0);
    const h1Size = h1Els.length > 0 ? fontSize(h1Els[0]) : 0;

    // Body text size: median of paragraph font sizes
    const pSizes = paragraphs.map(el => fontSize(el)).filter(s => s > 0);
    const bodySize = pSizes.length > 0 ? utils.median(pSizes) : 16;

    const ratio = bodySize > 0 ? Math.round((h1Size / bodySize) * 100) / 100 : 0;

    return {
      h1_size: Math.round(h1Size * 100) / 100,
      body_size: Math.round(bodySize * 100) / 100,
      ratio,
      pass: ratio >= 2.0 && ratio <= 3.0
    };
  }


  // ── TS-10: ALL CAPS Letter-Spacing ──────────────────────────────

  function ts10() {
    const uppercaseEls = allTextEls.filter(el =>
      window.getComputedStyle(el).textTransform === 'uppercase'
    );

    let properlySpaced = 0;
    const violations = [];

    for (const el of uppercaseEls) {
      const style = window.getComputedStyle(el);
      const ls = parseFloat(style.letterSpacing) || 0;
      const size = fontSize(el);
      const minSpacing = size * 0.05;
      const maxSpacing = size * 0.1;

      if (ls >= minSpacing && ls <= maxSpacing) {
        properlySpaced++;
      } else {
        if (violations.length < MAX_ITEMS) {
          violations.push(utils.getSelector(el));
        }
      }
    }

    return {
      uppercase_elements: uppercaseEls.length,
      properly_spaced: properlySpaced,
      violations,
      pass: uppercaseEls.length === 0 || violations.length === 0
    };
  }


  // ── TS-11: ALL CAPS Word Count ──────────────────────────────────

  function ts11() {
    const uppercaseEls = allTextEls.filter(el =>
      window.getComputedStyle(el).textTransform === 'uppercase'
    );

    const longUppercase = [];

    for (const el of uppercaseEls) {
      const text = el.textContent.trim();
      const words = text.split(/\s+/).filter(w => w.length > 0);
      if (words.length > 3) {
        if (longUppercase.length < MAX_ITEMS) {
          longUppercase.push({
            selector: utils.getSelector(el),
            word_count: words.length,
            text: text.slice(0, 80)
          });
        }
      }
    }

    return {
      long_uppercase: longUppercase,
      pass: longUppercase.length === 0
    };
  }


  // ── TS-12: Centered Body Text ───────────────────────────────────

  function ts12() {
    const centered = [];

    for (const el of paragraphs) {
      const style = window.getComputedStyle(el);
      if (style.textAlign !== 'center') continue;

      const rect = el.getBoundingClientRect();
      const lh = lineHeight(el);
      if (lh <= 0) continue;

      const lines = Math.round(rect.height / lh);
      if (lines > 3) {
        if (centered.length < MAX_ITEMS) {
          centered.push({
            selector: utils.getSelector(el),
            lines
          });
        }
      }
    }

    return {
      centered_paragraphs: centered,
      pass: centered.length === 0
    };
  }


  // ── TS-13: Heading Semantic/Visual Alignment ────────────────────

  function ts13() {
    // Query all headings in document order (not just viewport)
    const allHeadings = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'))
      .filter(el => utils.isVisible(el) && el.textContent.trim().length > 0);

    const sequence = [];
    const levelsUsed = new Set();

    for (const el of allHeadings) {
      const tag = el.tagName.toLowerCase();
      const level = parseInt(tag.charAt(1));
      const size = fontSize(el);
      levelsUsed.add(level);

      if (sequence.length < MAX_ITEMS) {
        sequence.push({
          tag,
          size: Math.round(size * 100) / 100
        });
      }
    }

    // Check for skipped levels
    const skippedLevels = [];
    const sortedLevels = Array.from(levelsUsed).sort((a, b) => a - b);
    for (let i = 1; i < sortedLevels.length; i++) {
      const gap = sortedLevels[i] - sortedLevels[i - 1];
      if (gap > 1) {
        for (let skipped = sortedLevels[i - 1] + 1; skipped < sortedLevels[i]; skipped++) {
          skippedLevels.push('h' + skipped);
        }
      }
    }

    // Check visual size monotonicity: for each heading level used,
    // the average size should decrease as level increases
    const sizeByLevel = {};
    for (const el of allHeadings) {
      const level = parseInt(el.tagName.charAt(1));
      const size = fontSize(el);
      if (!sizeByLevel[level]) sizeByLevel[level] = [];
      sizeByLevel[level].push(size);
    }

    const avgByLevel = {};
    for (const [level, sizes] of Object.entries(sizeByLevel)) {
      avgByLevel[level] = sizes.reduce((a, b) => a + b, 0) / sizes.length;
    }

    let visualMonotonic = true;
    const levelKeys = Object.keys(avgByLevel).map(Number).sort((a, b) => a - b);
    for (let i = 1; i < levelKeys.length; i++) {
      if (avgByLevel[levelKeys[i]] >= avgByLevel[levelKeys[i - 1]]) {
        visualMonotonic = false;
        break;
      }
    }

    return {
      sequence,
      skipped_levels: skippedLevels,
      visual_monotonic: visualMonotonic,
      pass: skippedLevels.length === 0 && visualMonotonic
    };
  }


  // ── TS-14: Heading Space Asymmetry ──────────────────────────────

  function ts14() {
    const results = [];
    let violationCount = 0;

    for (const el of headings) {
      const style = window.getComputedStyle(el);
      const mt = parseFloat(style.marginTop) || 0;
      const mb = parseFloat(style.marginBottom) || 0;
      const pass = mt > mb;
      if (!pass) violationCount++;

      if (results.length < MAX_ITEMS) {
        results.push({
          tag: el.tagName.toLowerCase(),
          margin_top: Math.round(mt * 100) / 100,
          margin_bottom: Math.round(mb * 100) / 100,
          pass
        });
      }
    }

    return {
      headings: results,
      violation_count: violationCount
    };
  }


  // ── TS-15: Straight Quotes Detection ────────────────────────────

  function ts15() {
    let count = 0;
    const samples = [];

    // Walk text nodes, skip code/pre/kbd
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent) return NodeFilter.FILTER_REJECT;
          const tag = parent.tagName;
          if (tag === 'CODE' || tag === 'PRE' || tag === 'KBD') {
            return NodeFilter.FILTER_REJECT;
          }
          if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT') {
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        }
      }
    );

    let node;
    while ((node = walker.nextNode())) {
      const text = node.textContent;
      // Match straight double quotes (") and straight single quotes/apostrophes (')
      // but not within empty content
      const straightDoubles = (text.match(/"/g) || []).length;
      const straightSingles = (text.match(/'/g) || []).length;
      const found = straightDoubles + straightSingles;

      if (found > 0) {
        count += found;
        if (samples.length < MAX_ITEMS) {
          const trimmed = text.trim();
          if (trimmed.length > 0) {
            samples.push(trimmed.slice(0, 80));
          }
        }
      }
    }

    return {
      straight_quote_count: count,
      sample_texts: samples,
      pass: count === 0
    };
  }


  // ── TS-16: Double Hyphen Detection ──────────────────────────────

  function ts16() {
    let count = 0;

    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent) return NodeFilter.FILTER_REJECT;
          const tag = parent.tagName;
          if (tag === 'CODE' || tag === 'PRE' || tag === 'KBD' ||
              tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT') {
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        }
      }
    );

    let node;
    while ((node = walker.nextNode())) {
      const matches = node.textContent.match(/--/g);
      if (matches) count += matches.length;
    }

    return {
      double_hyphen_count: count,
      pass: count === 0
    };
  }


  // ── TS-17: Faux Bold/Italic Detection ───────────────────────────

  function ts17() {
    let fauxBold = 0;
    let fauxItalic = 0;
    const elements = [];

    for (const el of allTextEls) {
      const style = window.getComputedStyle(el);
      const weight = parseInt(style.fontWeight) || 400;
      const isItalic = style.fontStyle === 'italic';

      if (weight < 700 && !isItalic) continue;

      const synthesis = style.fontSynthesis || '';
      const family = style.fontFamily || '';

      // Check document.fonts for a real matching FontFace
      let hasMatchingFace = false;
      if (document.fonts && typeof document.fonts.forEach === 'function') {
        document.fonts.forEach(face => {
          if (!family.includes(face.family.replace(/^["']|["']$/g, ''))) return;
          const faceWeight = parseInt(face.weight) || 400;
          const faceStyle = face.style || 'normal';
          if (weight >= 700 && faceWeight >= 700 && faceStyle === style.fontStyle) {
            hasMatchingFace = true;
          }
          if (isItalic && faceStyle === 'italic' && faceWeight === weight) {
            hasMatchingFace = true;
          }
        });
      }

      const synthesisingWeight = synthesis !== 'none' && synthesis.includes('weight');
      const synthesisingStyle = synthesis !== 'none' && synthesis.includes('style');
      const isFauxBold = weight >= 700 && (synthesisingWeight || !hasMatchingFace);
      const isFauxItalic = isItalic && (synthesisingStyle || !hasMatchingFace);

      if (isFauxBold) fauxBold++;
      if (isFauxItalic) fauxItalic++;

      if ((isFauxBold || isFauxItalic) && elements.length < MAX_ITEMS) {
        elements.push({
          selector: utils.getSelector(el),
          issue: isFauxBold && isFauxItalic ? 'faux bold+italic'
            : isFauxBold ? 'faux bold' : 'faux italic'
        });
      }
    }

    return {
      faux_bold: fauxBold,
      faux_italic: fauxItalic,
      elements,
      pass: fauxBold === 0 && fauxItalic === 0
    };
  }


  // ── TS-18: Tabular Numerals in Data Tables ────────────────────

  function ts18() {
    const cells = collectVisible('td, th')
      .filter(el => /\d/.test(el.textContent));

    let withTabularNums = 0;
    const violations = [];

    for (const el of cells) {
      const style = window.getComputedStyle(el);
      const variantNumeric = style.fontVariantNumeric || '';
      const featureSettings = style.fontFeatureSettings || '';

      if (variantNumeric.includes('tabular-nums') ||
          featureSettings.includes('"tnum"')) {
        withTabularNums++;
      } else {
        if (violations.length < MAX_ITEMS) {
          violations.push({ selector: utils.getSelector(el) });
        }
      }
    }

    return {
      numeric_cells: cells.length,
      with_tabular_nums: withTabularNums,
      violations,
      pass: cells.length === 0 || violations.length === 0
    };
  }


  // ── TS-19: Justified Text Without Hyphenation ─────────────────

  function ts19() {
    const justified = allTextEls.filter(el =>
      window.getComputedStyle(el).textAlign === 'justify'
    );

    let withoutHyphens = 0;
    const violations = [];

    for (const el of justified) {
      let hasHyphens = false;
      let current = el;

      while (current && current !== document.body) {
        if (window.getComputedStyle(current).hyphens === 'auto') {
          hasHyphens = true;
          break;
        }
        current = current.parentElement;
      }

      if (!hasHyphens) {
        withoutHyphens++;
        if (violations.length < MAX_ITEMS) {
          violations.push({ selector: utils.getSelector(el) });
        }
      }
    }

    return {
      justified_elements: justified.length,
      without_hyphens: withoutHyphens,
      violations,
      pass: justified.length === 0 || withoutHyphens === 0
    };
  }


  // ── TS-20: Paragraph Separation Consistency ───────────────────

  function ts20() {
    let indentCount = 0;
    let spaceCount = 0;

    for (const el of paragraphs) {
      const style = window.getComputedStyle(el);
      const textIndent = parseFloat(style.textIndent) || 0;
      const mt = parseFloat(style.marginTop) || 0;
      const mb = parseFloat(style.marginBottom) || 0;
      const totalMargin = mt + mb;

      if (textIndent > 0 && totalMargin < 4) {
        indentCount++;
      } else if (totalMargin > 0 && textIndent === 0) {
        spaceCount++;
      }
    }

    const mixed = indentCount > 0 && spaceCount > 0;

    return {
      indent_count: indentCount,
      space_count: spaceCount,
      mixed,
      pass: !mixed
    };
  }


  // ── TS-21: Typeface Distortion Detection ──────────────────────

  function ts21() {
    let distortedElements = 0;
    const elements = [];

    for (const el of allTextEls) {
      const transform = window.getComputedStyle(el).transform;
      if (!transform || transform === 'none') continue;

      // Parse matrix(a, b, c, d, tx, ty) or matrix3d(...)
      const matrixMatch = transform.match(/^matrix\((.+)\)$/);
      if (!matrixMatch) continue;

      const values = matrixMatch[1].split(',').map(v => parseFloat(v.trim()));
      if (values.length < 6) continue;

      const scaleX = Math.round(values[0] * 1000) / 1000;
      const scaleY = Math.round(values[3] * 1000) / 1000;

      if (Math.abs(scaleX - scaleY) > 0.01) {
        distortedElements++;
        if (elements.length < MAX_ITEMS) {
          elements.push({
            selector: utils.getSelector(el),
            scaleX,
            scaleY
          });
        }
      }
    }

    return {
      distorted_elements: distortedElements,
      elements,
      pass: distortedElements === 0
    };
  }


  // ── TS-22: Heading Letter-Spacing ──────────────────────────────

  function ts22() {
    let largeHeadings = 0;
    let positiveTracking = 0;
    const violations = [];

    for (const el of headings) {
      const size = fontSize(el);
      if (size <= 30) continue;

      largeHeadings++;
      const style = window.getComputedStyle(el);
      const ls = parseFloat(style.letterSpacing) || 0;

      if (ls > 0) {
        positiveTracking++;
        if (violations.length < MAX_ITEMS) {
          violations.push({
            selector: utils.getSelector(el),
            size: Math.round(size * 100) / 100,
            letter_spacing: Math.round(ls * 100) / 100
          });
        }
      }
    }

    return {
      large_headings: largeHeadings,
      positive_tracking: positiveTracking,
      violations,
      pass: positiveTracking === 0
    };
  }


  // ── Assemble ────────────────────────────────────────────────────

  return {
    ts01_body_text_min_size:        ts01(),
    ts02_absolute_floor:            ts02(),
    ts03_line_length:               ts03(),
    ts04_body_line_height:          ts04(),
    ts05_headline_line_height:      ts05(),
    ts06_typeface_family_count:     ts06(),
    ts07_font_weight_count:         ts07(),
    ts08_type_scale:                ts08(),
    ts09_headline_size_jump:        ts09(),
    ts10_caps_letter_spacing:       ts10(),
    ts11_caps_word_count:           ts11(),
    ts12_centered_body_text:        ts12(),
    ts13_heading_semantic_visual:   ts13(),
    ts14_heading_space_asymmetry:   ts14(),
    ts15_straight_quotes:           ts15(),
    ts16_double_hyphens:            ts16(),
    ts17_faux_bold_italic:          ts17(),
    ts18_tabular_numerals:          ts18(),
    ts19_justified_hyphenation:     ts19(),
    ts20_paragraph_separation:      ts20(),
    ts21_typeface_distortion:       ts21(),
    ts22_heading_letter_spacing:    ts22()
  };
}
