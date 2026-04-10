// DPT Layer 4: Attention Architecture
// Visual hierarchy, affordances, interaction patterns, navigation

function attentionArchitecture(utils) {

  const MAX_ITEMS = 15;

  // ─── Shared collection: gather visible elements once ──────────────

  const allVisible = utils.queryVisible('*');
  const viewportElements = allVisible.filter(el => utils.isInViewport(el));
  const interactiveElements = allVisible.filter(el => utils.isInteractive(el));
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  // ─── AA-01: Visual Weight Ranking ─────────────────────────────────

  function aa01_visualWeightRanking() {
    const rects = new Map();
    const scored = [];

    // Pre-compute rects for all viewport elements
    for (const el of viewportElements) {
      rects.set(el, el.getBoundingClientRect());
    }

    for (const el of viewportElements) {
      const rect = rects.get(el);
      if (rect.width < 2 || rect.height < 2) continue;

      const style = window.getComputedStyle(el);

      // Size weight: fraction of viewport area
      const sizeWeight = (rect.width * rect.height) / (vw * vh);

      // Contrast weight: element foreground or background vs effective bg
      const fg = utils.parseColor(style.color);
      const bg = utils.getEffectiveBackground(el);
      let contrastWeight = 0;
      if (fg && bg) {
        contrastWeight = utils.contrastRatio(fg, bg) / 21;
      }

      // Saturation weight: from the element's most prominent color
      let saturationWeight = 0;
      for (const prop of ['color', 'backgroundColor', 'borderColor']) {
        const parsed = utils.parseColor(style[prop]);
        if (parsed && parsed.a > 0.1) {
          const hsl = utils.rgbToHsl(parsed.r, parsed.g, parsed.b);
          saturationWeight = Math.max(saturationWeight, hsl.s / 100);
        }
      }

      // Isolation weight: 1 / (1 + nearby count within 50px)
      let nearbyCount = 0;
      for (const other of viewportElements) {
        if (other === el) continue;
        const otherRect = rects.get(other);
        if (utils.areAdjacent(rect, otherRect, 50)) {
          nearbyCount++;
        }
      }
      const isolationWeight = 1 / (1 + nearbyCount);

      const weight = (
        sizeWeight * 0.3 +
        contrastWeight * 0.3 +
        saturationWeight * 0.2 +
        isolationWeight * 0.2
      );

      scored.push({
        el,
        selector: utils.getSelector(el),
        text: (el.textContent || '').trim().slice(0, 60),
        weight: Math.round(weight * 10000) / 10000
      });
    }

    // Rank by weight descending, take top 10
    scored.sort((a, b) => b.weight - a.weight);
    const top10 = scored.slice(0, 10);
    const rankings = top10.map((item, i) => ({
      selector: item.selector,
      text: item.text,
      weight: item.weight,
      rank: i + 1
    }));

    const weights = rankings.map(r => r.weight);
    const weightSpread = weights.length >= 2
      ? Math.round((weights[0] - weights[weights.length - 1]) * 10000) / 10000
      : 0;

    return {
      rankings,
      dominant_element: rankings.length > 0 ? rankings[0].selector : null,
      weight_spread: weightSpread
    };
  }

  // ─── AA-02: Button Hierarchy ──────────────────────────────────────

  function aa02_buttonHierarchy() {
    // Detect page theme: dark if body/html bg luminance < 0.2
    const pageBg = utils.getEffectiveBackground(document.body);
    const pageLum = pageBg
      ? utils.relativeLuminance(pageBg.r, pageBg.g, pageBg.b)
      : 0.95;
    const isDarkMode = pageLum < 0.2;

    // Collect all button-like elements
    const buttons = [];

    // <button> and [role="button"]
    const btnEls = utils.queryVisible('button, [role="button"]');
    for (const el of btnEls) {
      if (utils.isInViewport(el)) buttons.push(el);
    }

    // <a> styled as buttons: must have a visible background or border
    const links = utils.queryVisible('a');
    for (const el of links) {
      if (!utils.isInViewport(el)) continue;
      const style = window.getComputedStyle(el);
      const bg = utils.parseColor(style.backgroundColor);
      const border = parseFloat(style.borderWidth) || 0;
      if ((bg && bg.a > 0.1) || border >= 1) {
        if (!el.hasAttribute('role') || el.getAttribute('role') !== 'button') {
          buttons.push(el);
        }
      }
    }

    let primary = 0;
    let secondary = 0;
    let tertiary = 0;
    let unclassified = 0;
    const primaryButtons = [];

    for (const el of buttons) {
      const style = window.getComputedStyle(el);
      const bg = utils.parseColor(style.backgroundColor);
      const borderWidth = parseFloat(style.borderWidth) || 0;
      const borderColor = utils.parseColor(style.borderColor);

      const hasVisibleBg = bg && bg.a > 0.1;
      const hasVisibleBorder = borderWidth >= 1 &&
        borderColor && borderColor.a > 0.1;

      // Theme-aware classification
      let isPrimary = false;

      if (hasVisibleBg) {
        const bgLum = utils.relativeLuminance(bg.r, bg.g, bg.b);
        const bgHsl = utils.rgbToHsl(bg.r, bg.g, bg.b);

        if (isDarkMode) {
          // Dark mode: primary = high contrast against page bg
          // A button that stands out (light fill on dark page, or saturated fill)
          const contrastVsPage = pageBg
            ? utils.contrastRatio(bg, pageBg)
            : 1;
          isPrimary = contrastVsPage >= 3 && (bgLum > pageLum + 0.1 || bgHsl.s > 30);
        } else {
          // Light mode: primary = saturated, non-white fill
          const isWhiteBg = bg.r > 240 && bg.g > 240 && bg.b > 240;
          isPrimary = !isWhiteBg && bgHsl.s > 30;
        }
      }

      if (isPrimary) {
        primary++;
        if (primaryButtons.length < MAX_ITEMS) {
          primaryButtons.push({
            selector: utils.getSelector(el),
            text: (el.textContent || '').trim().slice(0, 60)
          });
        }
        continue;
      }

      // Secondary: outlined/bordered without strong fill
      const isTransparentBg = !hasVisibleBg;
      const isSubtleBg = hasVisibleBg && (() => {
        const contrast = pageBg ? utils.contrastRatio(bg, pageBg) : 1;
        return contrast < 1.5;
      })();

      if (hasVisibleBorder && (isTransparentBg || isSubtleBg)) {
        secondary++;
        continue;
      }

      // Tertiary: ghost button — no visible bg distinction, no border
      if ((isTransparentBg || isSubtleBg) && !hasVisibleBorder) {
        tertiary++;
        continue;
      }

      unclassified++;
    }

    return {
      primary,
      secondary,
      tertiary,
      unclassified,
      primary_buttons: primaryButtons,
      pass: primary === 1
    };
  }

  // ─── AA-03: Interactive Affordance ────────────────────────────────

  function aa03_interactiveAffordance() {
    const viewportInteractive = interactiveElements.filter(el =>
      utils.isInViewport(el)
    );

    let withAffordance = 0;
    const weakAffordance = [];

    for (const el of viewportInteractive) {
      const style = window.getComputedStyle(el);
      const issues = [];

      // Check cursor: pointer
      const hasCursorPointer = style.cursor === 'pointer';

      // Check distinct color from parent text
      let hasDistinctColor = false;
      if (el.parentElement) {
        const parentStyle = window.getComputedStyle(el.parentElement);
        const elColor = utils.parseColor(style.color);
        const parentColor = utils.parseColor(parentStyle.color);
        if (elColor && parentColor) {
          const dist = utils.ciede2000(elColor, parentColor);
          hasDistinctColor = dist > 10;
        }
      }

      // Check underline (for links in text)
      const hasUnderline = style.textDecorationLine.includes('underline') ||
        style.textDecoration.includes('underline');

      // Check background/border distinguishing it
      const bg = utils.parseColor(style.backgroundColor);
      const hasVisibleBg = bg && bg.a > 0.1 &&
        !(bg.r > 245 && bg.g > 245 && bg.b > 245);
      const borderWidth = parseFloat(style.borderWidth) || 0;
      const borderColor = utils.parseColor(style.borderColor);
      const hasVisibleBorder = borderWidth >= 1 &&
        borderColor && borderColor.a > 0.1;

      const affordanceSignals = [
        hasCursorPointer,
        hasDistinctColor,
        hasUnderline,
        hasVisibleBg,
        hasVisibleBorder
      ];

      const signalCount = affordanceSignals.filter(Boolean).length;

      if (signalCount >= 1) {
        withAffordance++;
      } else {
        if (!hasCursorPointer) issues.push('no cursor:pointer');
        if (!hasDistinctColor) issues.push('color same as parent');
        if (!hasUnderline) issues.push('no underline');
        if (!hasVisibleBg && !hasVisibleBorder) issues.push('no bg/border distinction');

        if (weakAffordance.length < MAX_ITEMS) {
          weakAffordance.push({
            selector: utils.getSelector(el),
            tag: el.tagName.toLowerCase(),
            issues
          });
        }
      }
    }

    return {
      total: viewportInteractive.length,
      with_affordance: withAffordance,
      weak_affordance: weakAffordance,
      pass: weakAffordance.length === 0
    };
  }

  // ─── AA-04: Icon Text Labels ──────────────────────────────────────

  function aa04_iconTextLabels() {
    let iconsFound = 0;
    let withLabels = 0;
    const withoutLabels = [];

    // Find SVGs and small images inside interactive elements
    for (const interactive of interactiveElements) {
      if (!utils.isInViewport(interactive)) continue;

      const icons = interactive.querySelectorAll('svg, img');
      for (const icon of icons) {
        // For img, check if it's small (icon-sized)
        if (icon.tagName === 'IMG') {
          const rect = icon.getBoundingClientRect();
          if (rect.width >= 40) continue;
        }

        iconsFound++;

        // Check for labeling mechanisms
        let hasLabel = false;

        // 1. Adjacent visible text sibling
        const parent = icon.parentElement;
        if (parent) {
          const siblings = Array.from(parent.childNodes);
          for (const sib of siblings) {
            if (sib === icon) continue;
            if (sib.nodeType === Node.TEXT_NODE) {
              const text = sib.textContent.trim();
              if (text.length > 0) { hasLabel = true; break; }
            }
            if (sib.nodeType === Node.ELEMENT_NODE) {
              const sibEl = /** @type {Element} */ (sib);
              if (sibEl.textContent && sibEl.textContent.trim().length > 0) {
                const sibStyle = window.getComputedStyle(sibEl);
                if (sibStyle.display !== 'none' && sibStyle.visibility !== 'hidden') {
                  hasLabel = true;
                  break;
                }
              }
            }
          }
        }

        // 2. aria-label on icon or parent interactive element
        if (!hasLabel) {
          if (icon.getAttribute('aria-label') ||
              interactive.getAttribute('aria-label') ||
              interactive.getAttribute('aria-labelledby')) {
            hasLabel = true;
          }
        }

        // 3. title attribute on the icon
        if (!hasLabel) {
          if (icon.getAttribute('title')) {
            hasLabel = true;
          }
        }

        if (hasLabel) {
          withLabels++;
        } else {
          if (withoutLabels.length < MAX_ITEMS) {
            withoutLabels.push({
              selector: utils.getSelector(icon),
              parent_text: (interactive.textContent || '').trim().slice(0, 60)
            });
          }
        }
      }
    }

    return {
      icons_found: iconsFound,
      with_labels: withLabels,
      without_labels: withoutLabels,
      pass: withoutLabels.length === 0
    };
  }

  // ─── AA-05: Link Affordance in Body Text ──────────────────────────

  function aa05_linkAffordanceInBody() {
    // Find <a> elements inside prose containers
    const proseContainers = utils.queryVisible('p, li, td');
    let inlineLinks = 0;
    let withUnderline = 0;
    let withDistinctColor = 0;
    let bareLinks = 0;

    for (const container of proseContainers) {
      const links = container.querySelectorAll('a');
      for (const link of links) {
        if (!utils.isVisible(link)) continue;
        inlineLinks++;

        const linkStyle = window.getComputedStyle(link);
        const containerStyle = window.getComputedStyle(container);

        // Check underline
        const hasUnderline = linkStyle.textDecorationLine.includes('underline') ||
          linkStyle.textDecoration.includes('underline');

        // Check distinct color from surrounding text
        const linkColor = utils.parseColor(linkStyle.color);
        const containerColor = utils.parseColor(containerStyle.color);
        let hasDistinct = false;
        if (linkColor && containerColor) {
          const dist = utils.ciede2000(linkColor, containerColor);
          hasDistinct = dist > 10;
        }

        if (hasUnderline) withUnderline++;
        if (hasDistinct) withDistinctColor++;

        if (!hasUnderline && !hasDistinct) {
          bareLinks++;
        }
      }
    }

    return {
      inline_links: inlineLinks,
      with_underline: withUnderline,
      with_distinct_color: withDistinctColor,
      bare_links: bareLinks,
      pass: bareLinks === 0
    };
  }

  // ─── AA-06: Form Label Presence ───────────────────────────────────

  function aa06_formLabelPresence() {
    const fields = allVisible.filter(el => utils.isFormField(el));
    let withVisibleLabel = 0;
    let placeholderOnly = 0;
    let noLabel = 0;
    const violations = [];

    for (const field of fields) {
      const id = field.id;
      const placeholder = field.getAttribute('placeholder');
      let hasVisibleLabel = false;

      // 1. Check for <label for="id"> matching this field
      if (id) {
        const label = document.querySelector(`label[for="${CSS.escape(id)}"]`);
        if (label && utils.isVisible(label)) {
          hasVisibleLabel = true;
        }
      }

      // 2. Check for wrapping <label>
      if (!hasVisibleLabel) {
        let parent = field.parentElement;
        while (parent && parent !== document.body) {
          if (parent.tagName === 'LABEL') {
            // Verify the label has text beyond just the field itself
            const labelText = parent.textContent.replace(field.textContent || '', '').trim();
            if (labelText.length > 0 && utils.isVisible(parent)) {
              hasVisibleLabel = true;
            }
            break;
          }
          parent = parent.parentElement;
        }
      }

      // 3. Check aria-label / aria-labelledby as visible label proxy
      if (!hasVisibleLabel) {
        const ariaLabelledBy = field.getAttribute('aria-labelledby');
        if (ariaLabelledBy) {
          const labelEl = document.getElementById(ariaLabelledBy);
          if (labelEl && utils.isVisible(labelEl)) {
            hasVisibleLabel = true;
          }
        }
      }

      if (hasVisibleLabel) {
        withVisibleLabel++;
      } else if (placeholder) {
        placeholderOnly++;
        if (violations.length < MAX_ITEMS) {
          violations.push({
            selector: utils.getSelector(field),
            type: field.type || field.tagName.toLowerCase(),
            issue: 'placeholder_only'
          });
        }
      } else {
        noLabel++;
        if (violations.length < MAX_ITEMS) {
          violations.push({
            selector: utils.getSelector(field),
            type: field.type || field.tagName.toLowerCase(),
            issue: 'no_label'
          });
        }
      }
    }

    return {
      fields: fields.length,
      with_visible_label: withVisibleLabel,
      placeholder_only: placeholderOnly,
      no_label: noLabel,
      violations,
      pass: placeholderOnly === 0 && noLabel === 0
    };
  }

  // ─── AA-07: Disabled Button Count ─────────────────────────────────

  function aa07_disabledButtons() {
    const disabledBtns = utils.queryVisible(
      'button[disabled], button[aria-disabled="true"], ' +
      '[role="button"][disabled], [role="button"][aria-disabled="true"]'
    );

    const elements = [];
    for (const el of disabledBtns) {
      if (elements.length >= MAX_ITEMS) break;
      elements.push({
        selector: utils.getSelector(el),
        text: (el.textContent || '').trim().slice(0, 60)
      });
    }

    return {
      disabled_count: disabledBtns.length,
      elements
    };
  }

  // ─── AA-08: Generic Link Text ─────────────────────────────────────

  function aa08_genericLinkText() {
    const BLOCKLIST = [
      'learn more', 'read more', 'click here', 'more',
      'here', 'link', 'info', 'details',
      'view all', 'see more', 'explore', 'view details', 'find out more'
    ];

    const allLinks = utils.queryVisible('a');
    const samples = [];

    for (const el of allLinks) {
      const text = (el.textContent || '').trim();
      const normalized = text.toLowerCase();

      if (BLOCKLIST.includes(normalized)) {
        if (samples.length < MAX_ITEMS) {
          samples.push({
            selector: utils.getSelector(el),
            text
          });
        }
      }
    }

    return {
      generic_links: samples.length,
      samples,
      pass: samples.length === 0
    };
  }

  // ─── AA-09: Navigation Item Count ─────────────────────────────────

  function aa09_navigationItemCount() {
    const navElements = utils.queryVisible('nav, [role="navigation"]');
    const itemsPerNav = [];
    let allPass = true;

    function isNavItem(el) {
      if (!utils.isVisible(el)) return false;
      const tag = el.tagName;
      // Direct interactive elements
      if (tag === 'A' || tag === 'BUTTON') return true;
      // Radix/headless UI triggers and menu items
      const role = el.getAttribute('role');
      if (role === 'menuitem' || role === 'tab' || role === 'link' || role === 'button') return true;
      return false;
    }

    function collectNavItems(container) {
      // Resilient approach: query all interactive elements within the nav,
      // filter to visible ones with text. Works regardless of nesting depth
      // (handles Radix, Headless UI, and other framework-generated markup).
      const selector = 'a, button, [role="menuitem"], [role="tab"], [role="link"]';
      const all = container.querySelectorAll(selector);
      const items = [];
      const seenText = new Set();

      for (const el of all) {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        if (!utils.isVisible(el)) continue;
        const text = (el.textContent || '').trim();
        if (!text) continue;
        // Deduplicate by text content (dropdown trigger + link often share text)
        if (seenText.has(text)) continue;
        seenText.add(text);
        items.push(el);
      }

      return items;
    }

    for (const nav of navElements) {
      const items = collectNavItems(nav);
      const count = items.length;
      const navPass = count <= 7;
      if (!navPass) allPass = false;

      if (itemsPerNav.length < MAX_ITEMS) {
        itemsPerNav.push({
          selector: utils.getSelector(nav),
          count,
          pass: navPass
        });
      }
    }

    return {
      nav_elements: navElements.length,
      items_per_nav: itemsPerNav,
      pass: allPass
    };
  }

  // ─── AA-10: Tab Order vs Visual Order ─────────────────────────────

  function aa10_tabOrderVisualOrder() {
    // Collect all focusable elements in DOM (tab) order
    const focusableSelector = [
      'a[href]', 'button:not([disabled])', 'input:not([disabled]):not([type="hidden"])',
      'select:not([disabled])', 'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])', '[role="button"]:not([aria-disabled="true"])'
    ].join(', ');

    const allFocusable = Array.from(document.querySelectorAll(focusableSelector))
      .filter(el => utils.isVisible(el) && utils.isInViewport(el));

    // Separate elements with explicit tabindex > 0 from natural order
    const withTabindex = [];
    const naturalOrder = [];

    for (const el of allFocusable) {
      const ti = parseInt(el.getAttribute('tabindex'), 10);
      if (ti > 0) {
        withTabindex.push({ el, tabindex: ti });
      } else {
        naturalOrder.push(el);
      }
    }

    // Tab order: explicit tabindex first (sorted ascending), then natural DOM order
    withTabindex.sort((a, b) => a.tabindex - b.tabindex);
    const tabOrder = [...withTabindex.map(w => w.el), ...naturalOrder];

    // Compare: check if next tab-stop is visually before current
    let mismatches = 0;

    for (let i = 1; i < tabOrder.length; i++) {
      const prevRect = tabOrder[i - 1].getBoundingClientRect();
      const currRect = tabOrder[i].getBoundingClientRect();

      // Reading order: top-to-bottom, left-to-right
      // A mismatch occurs when the next focusable element is visually
      // above the previous one (more than a row-height tolerance)
      const rowTolerance = 10; // px — elements on the same visual row
      if (currRect.top < prevRect.top - rowTolerance) {
        mismatches++;
      } else if (
        Math.abs(currRect.top - prevRect.top) <= rowTolerance &&
        currRect.left < prevRect.left - rowTolerance
      ) {
        // Same row but goes backward (right-to-left in LTR layout)
        mismatches++;
      }
    }

    return {
      focusable_count: tabOrder.length,
      order_mismatches: mismatches,
      pass: mismatches === 0
    };
  }

  // ─── AA-11: Form Field Border Contrast ──────────────────────────

  function aa11_formFieldBorderContrast() {
    const fieldSelector = 'input, select, textarea';
    const skipTypes = ['hidden', 'submit', 'button'];
    const fields = utils.queryVisible(fieldSelector).filter(el => {
      if (!utils.isInViewport(el)) return false;
      const type = (el.getAttribute('type') || '').toLowerCase();
      return !skipTypes.includes(type);
    });

    let adequateContrast = 0;
    const violations = [];

    for (const el of fields) {
      const style = window.getComputedStyle(el);
      const borderColor = utils.parseColor(style.borderColor);
      if (!borderColor || borderColor.a < 0.05) continue;

      const bg = utils.getEffectiveBackground(el);
      if (!bg) continue;

      const contrast = utils.contrastRatio(borderColor, bg);

      if (contrast >= 3) {
        adequateContrast++;
      } else {
        if (violations.length < MAX_ITEMS) {
          violations.push({
            selector: utils.getSelector(el),
            contrast: Math.round(contrast * 100) / 100,
            border_color: `rgb(${borderColor.r},${borderColor.g},${borderColor.b})`,
            background: `rgb(${bg.r},${bg.g},${bg.b})`
          });
        }
      }
    }

    return {
      fields_checked: fields.length,
      adequate_contrast: adequateContrast,
      violations: violations,
      pass: violations.length === 0
    };
  }

  // ─── AA-12: Generic Button Text ──────────────────────────────────

  function aa12_genericButtonText() {
    const BLOCKLIST = [
      'submit', 'ok', 'yes', 'no', 'cancel', 'click here',
      'learn more', 'read more', 'continue', 'next', 'back', 'go', 'send'
    ];

    // Collect all button-like elements
    const buttons = [];

    const btnEls = utils.queryVisible('button, [role="button"]');
    for (const el of btnEls) {
      if (utils.isInViewport(el)) buttons.push(el);
    }

    const links = utils.queryVisible('a');
    for (const el of links) {
      if (!utils.isInViewport(el)) continue;
      const style = window.getComputedStyle(el);
      const bg = utils.parseColor(style.backgroundColor);
      const border = parseFloat(style.borderWidth) || 0;
      if ((bg && bg.a > 0.1) || border >= 1) {
        if (!el.hasAttribute('role') || el.getAttribute('role') !== 'button') {
          buttons.push(el);
        }
      }
    }

    let genericLabels = 0;
    const samples = [];

    for (const el of buttons) {
      const text = (el.textContent || '').trim();
      const normalized = text.toLowerCase();

      if (BLOCKLIST.includes(normalized)) {
        genericLabels++;
        if (samples.length < MAX_ITEMS) {
          samples.push({
            selector: utils.getSelector(el),
            text
          });
        }
      }
    }

    return {
      buttons_checked: buttons.length,
      generic_labels: genericLabels,
      samples,
      pass: genericLabels === 0
    };
  }

  // ─── AA-16: Destructive Action Visual Weight ───────────────────────

  function aa16_destructiveActionWeight() {
    const DESTRUCTIVE_PATTERNS = [
      'delete', 'remove', 'cancel', 'destroy',
      'clear all', 'reset', 'revoke', 'disable'
    ];

    // Detect page theme (same as AA-02)
    const pageBg = utils.getEffectiveBackground(document.body);
    const pageLum = pageBg
      ? utils.relativeLuminance(pageBg.r, pageBg.g, pageBg.b)
      : 0.95;
    const isDarkMode = pageLum < 0.2;

    // Collect all button-like elements (same collection as AA-02)
    const buttons = [];

    const btnEls = utils.queryVisible('button, [role="button"]');
    for (const el of btnEls) {
      if (utils.isInViewport(el)) buttons.push(el);
    }

    const links = utils.queryVisible('a');
    for (const el of links) {
      if (!utils.isInViewport(el)) continue;
      const style = window.getComputedStyle(el);
      const bg = utils.parseColor(style.backgroundColor);
      const border = parseFloat(style.borderWidth) || 0;
      if ((bg && bg.a > 0.1) || border >= 1) {
        if (!el.hasAttribute('role') || el.getAttribute('role') !== 'button') {
          buttons.push(el);
        }
      }
    }

    let destructiveButtons = 0;
    let destructiveAsPrimary = 0;
    const violations = [];

    for (const el of buttons) {
      const text = (el.textContent || '').trim();
      const normalized = text.toLowerCase();

      const isDestructive = DESTRUCTIVE_PATTERNS.some(p => normalized === p);
      if (!isDestructive) continue;

      destructiveButtons++;

      // Check if button is classified as primary (same isPrimary logic as AA-02)
      const style = window.getComputedStyle(el);
      const bg = utils.parseColor(style.backgroundColor);
      const hasVisibleBg = bg && bg.a > 0.1;

      let isPrimary = false;

      if (hasVisibleBg) {
        const bgLum = utils.relativeLuminance(bg.r, bg.g, bg.b);
        const bgHsl = utils.rgbToHsl(bg.r, bg.g, bg.b);

        if (isDarkMode) {
          const contrastVsPage = pageBg
            ? utils.contrastRatio(bg, pageBg)
            : 1;
          isPrimary = contrastVsPage >= 3 && (bgLum > pageLum + 0.1 || bgHsl.s > 30);
        } else {
          const isWhiteBg = bg.r > 240 && bg.g > 240 && bg.b > 240;
          isPrimary = !isWhiteBg && bgHsl.s > 30;
        }
      }

      if (isPrimary) {
        destructiveAsPrimary++;
        if (violations.length < MAX_ITEMS) {
          violations.push({
            selector: utils.getSelector(el),
            text
          });
        }
      }
    }

    return {
      destructive_buttons: destructiveButtons,
      destructive_as_primary: destructiveAsPrimary,
      violations,
      pass: destructiveAsPrimary === 0
    };
  }

  // ─── Execute all checks and assemble result ───────────────────────

  return {
    aa01_visual_weight_ranking: aa01_visualWeightRanking(),
    aa02_button_hierarchy: aa02_buttonHierarchy(),
    aa03_interactive_affordance: aa03_interactiveAffordance(),
    aa04_icon_text_labels: aa04_iconTextLabels(),
    aa05_link_affordance_body: aa05_linkAffordanceInBody(),
    aa06_form_label_presence: aa06_formLabelPresence(),
    aa07_disabled_buttons: aa07_disabledButtons(),
    aa08_generic_link_text: aa08_genericLinkText(),
    aa09_navigation_item_count: aa09_navigationItemCount(),
    aa10_tab_order_visual: aa10_tabOrderVisualOrder(),
    aa11_form_field_border_contrast: aa11_formFieldBorderContrast(),
    aa12_generic_button_text: aa12_genericButtonText(),
    aa16_destructive_action_weight: aa16_destructiveActionWeight()
  };
}
