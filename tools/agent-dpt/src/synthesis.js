// DPT Synthesis — Unified quality score from 5 perception layers
// Reads all layer outputs, computes per-dimension grades and overall score
// with hard-floor penalties. Returns structured scoring for any consumer.

function synthesis(cf, ts, sr, aa, co) {

  // ─── Helpers ────────────────────────────────────────────────────

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function grade(score) {
    if (score >= 90) return 'A';
    if (score >= 85) return 'A-';
    if (score >= 80) return 'B+';
    if (score >= 75) return 'B';
    if (score >= 70) return 'B-';
    if (score >= 65) return 'C+';
    if (score >= 60) return 'C';
    if (score >= 55) return 'C-';
    if (score >= 50) return 'D+';
    if (score >= 45) return 'D';
    if (score >= 40) return 'D-';
    return 'F';
  }

  function safe(obj, ...path) {
    let cur = obj;
    for (const k of path) {
      if (cur == null || typeof cur !== 'object') return undefined;
      cur = cur[k];
    }
    return cur;
  }

  function pctScale(n, total) {
    if (!total || total === 0) return 100;
    return clamp(Math.round((n / total) * 100), 0, 100);
  }

  // ─── Chromatic Field (0-100) ────────────────────────────────────

  const cf01 = cf.cf01_text_contrast || {};
  const cf02 = cf.cf02_palette || {};
  const cf03 = cf.cf03_grey_saturation || {};
  const cf04 = cf.cf04_interactive_primary || {};
  const cf06 = cf.cf06_dark_mode || {};
  const cf08 = cf.cf08_saturation_overuse || {};

  const adjustedRate = cf01.adjusted_pass_rate != null ? cf01.adjusted_pass_rate : (cf01.pass_rate != null ? cf01.pass_rate : 1);
  const contrastScore = clamp(Math.round(adjustedRate * 100), 0, 100);

  const hues = cf02.chromatic_hues || 0;
  const paletteScore = hues <= 4 ? 100 : hues <= 6 ? 75 : hues <= 8 ? 50 : 25;

  const tinted = cf03.tinted_greys || 0;
  const untinted = cf03.untinted_greys || 0;
  const greyTotal = tinted + untinted;
  const untintedRatio = greyTotal === 0 ? 0 : untinted / greyTotal;
  const greyScore = greyTotal === 0 ? 70 : untinted === 0 ? 100 :
    untintedRatio > 0.8 ? 0 : untintedRatio > 0.5 ? 20 : untintedRatio > 0.3 ? 40 : 60;

  const leaks = cf04.non_interactive_leaks || 0;
  const hueScore = leaks === 0 ? 100 : leaks <= 5 ? 70 : leaks <= 15 ? 40 : 10;

  const halation = cf06.halation_risk || false;
  const satEls = cf08.full_saturation_elements || 0;
  const satHues = cf08.full_saturation_hues || 0;
  const miscScore = (halation ? 0 : 50) + (satEls > 10 || satHues > 1 ? 0 : 50);

  // CF-10: Complementary adjacency (generalizes chromostereopsis to all hue pairs)
  const cf10 = cf.cf10_complementary_adjacency || {};
  const compPairs = cf10.complementary_pairs || 0;
  const compScore = compPairs === 0 ? 100 : compPairs <= 2 ? 70 : compPairs <= 5 ? 40 : 10;

  // CF-11: Saturated color area overuse
  const cf11 = cf.cf11_saturated_area || {};
  const overuseHues = cf11.overuse_hues || 0;
  const areaScore = overuseHues === 0 ? 100 : overuseHues === 1 ? 50 : 20;

  // CF-12: Perceived brightness consistency
  const cf12 = cf.cf12_perceived_brightness || {};
  const brightnessScore = (cf12.inconsistent_groups || 0) === 0 ? 100 : 50;

  // CF-09: Body text softness (pure black text is harsh — Santa Maria)
  const cf09 = cf.cf09_body_text_softness || {};
  const pureBlackBody = cf09.pure_black_body_text || 0;
  const softScore = pureBlackBody === 0 ? 100 : 0;

  const chromaticRaw = Math.round(
    contrastScore * 0.33 +
    paletteScore * 0.12 +
    greyScore * 0.11 +
    hueScore * 0.11 +
    miscScore * 0.08 +
    compScore * 0.08 +
    areaScore * 0.07 +
    softScore * 0.05 +
    brightnessScore * 0.05
  );
  const chromaticFloors = [];
  let chromaticScore = chromaticRaw;
  if (halation) { chromaticScore = Math.min(chromaticScore, 60); chromaticFloors.push('halation_risk'); }
  if (compPairs > 5) { chromaticScore = Math.min(chromaticScore, 60); chromaticFloors.push('complementary_adjacency'); }

  // ─── Typographic Skeleton (0-100) ──────────────────────────────

  const ts02 = ts.ts02_absolute_floor || {};
  const ts04 = ts.ts04_body_line_height || {};
  const ts06 = ts.ts06_typeface_family_count || {};
  const ts07 = ts.ts07_font_weight_count || {};
  const ts08 = ts.ts08_type_scale || {};
  const ts09 = ts.ts09_headline_size_jump || {};

  const sub12 = ts02.sub_12px_count || 0;
  const sub12Score = sub12 === 0 ? 100 : sub12 <= 10 ? 60 : sub12 <= 50 ? 30 : 0;

  const bands = ts07.band_count || 0;
  const bandScore = (bands >= 2 && bands <= 3) ? 100 : bands === 1 ? 70 : bands === 4 ? 50 : 0;

  const systematic = ts08.systematic || false;
  let scaleScore = systematic ? 100 : (ts08.detected_ratio ? 60 : 20);
  // Tier 3: anomalous ratio outside standard musical/typographic range caps score
  if (ts08.detected_ratio && (ts08.detected_ratio < 1.067 || ts08.detected_ratio > 1.618)) {
    scaleScore = Math.min(scaleScore, 40);
  }

  const medianLH = ts04.median_ratio || 0;
  const lhScore = (medianLH >= 1.4 && medianLH <= 1.6) ? 100
    : (medianLH >= 1.3 && medianLH <= 1.7) ? 70
    : (medianLH >= 1.2 && medianLH <= 1.8) ? 50 : 20;

  const familyCount = (ts06.families || []).length;
  const familyScore = familyCount <= 2 ? 100 : familyCount === 3 ? 50 : 0;

  const h1Ratio = ts09.ratio || 0;
  const h1Score = (h1Ratio >= 2.0 && h1Ratio <= 3.0) ? 100 : (h1Ratio >= 1.5 && h1Ratio <= 4.0) ? 60 : 20;

  // TS-17: Faux bold/italic (browser-synthesized = quality penalty)
  const ts17 = ts.ts17_faux_bold_italic || {};
  const fauxCount = (ts17.faux_bold || 0) + (ts17.faux_italic || 0);
  const fauxScore = fauxCount === 0 ? 100 : fauxCount <= 3 ? 60 : 20;

  // TS-19: Justified text without hyphenation (universally broken)
  const ts19 = ts.ts19_justified_hyphenation || {};
  const justifiedNoHyph = ts19.without_hyphens || 0;
  const justifiedScore = justifiedNoHyph === 0 ? 100 : 30;

  // TS-21: Typeface distortion (transform stretch/compress)
  const ts21 = ts.ts21_typeface_distortion || {};
  // TS-21 output key: distorted_elements
  const distorted = ts21.distorted_elements || 0;
  const distortionScore = distorted === 0 ? 100 : 0;

  // TS-01: Body text minimum size (< 16px = violation)
  const ts01 = ts.ts01_body_text_min_size || {};
  const bodyMinViols = ts01.violations || 0;
  const bodyMinScore = bodyMinViols === 0 ? 100 : bodyMinViols <= 5 ? 60 : 20;

  // TS-03: Line length violations
  const ts03 = ts.ts03_line_length || {};
  const llChecks = (ts03.checks || []).length;
  const llViols = ts03.violations || 0;
  const lineLengthScore = llChecks === 0 ? 70 : pctScale(llChecks - llViols, llChecks);

  // TS-05: Headline line-height
  const ts05 = ts.ts05_headline_line_height || {};
  const headlineLhScore = ts05.pass ? 100 : 50;

  // TS-13: Heading semantic-visual hierarchy
  const ts13 = ts.ts13_heading_semantic_visual || {};
  const headingHierScore = ts13.pass ? 100 : 30;

  // TS-14: Heading space asymmetry (proximity)
  const ts14 = ts.ts14_heading_space_asymmetry || {};
  const proxViols = ts14.violation_count || 0;
  const proxTotal = (ts14.headings || []).length;
  const headingProxScore = proxTotal === 0 ? 70 : pctScale(proxTotal - proxViols, proxTotal);

  // TS-22: Heading letter-spacing (positive tracking on headings = amateur)
  const ts22 = ts.ts22_heading_letter_spacing || {};
  const headingTrackScore = (ts22.positive_tracking || 0) === 0 ? 100 : 40;

  const typographyRaw = Math.round(
    sub12Score * 0.12 +
    bandScore * 0.13 +
    scaleScore * 0.07 +
    lhScore * 0.11 +
    familyScore * 0.06 +
    h1Score * 0.10 +
    fauxScore * 0.07 +
    justifiedScore * 0.05 +
    distortionScore * 0.05 +
    bodyMinScore * 0.04 +
    lineLengthScore * 0.05 +
    headlineLhScore * 0.03 +
    headingHierScore * 0.04 +
    headingProxScore * 0.05 +
    headingTrackScore * 0.03
  );
  const typographyFloors = [];
  let typographyScore = typographyRaw;
  if (sub12 > 100) typographyFloors.push('sub_12px');
  if (sub12 > 20) typographyFloors.push('sub_12px_severe');
  if (distorted > 0) typographyFloors.push('typeface_distortion');

  // ─── Spatial Rhythm (0-100) ─────────────────────────────────────

  const sr01 = sr.sr01_spacing_scale || {};
  const sr02 = sr.sr02_touch_targets || {};
  const sr04 = sr.sr04_border_radius || {};
  const sr05 = sr.sr05_shadow_elevation || {};
  const sr07 = sr.sr07_alignment_vectors || {};

  const spacingConf = sr01.confidence || 0;
  const spacingScore = clamp(Math.round(spacingConf * 100), 0, 100);

  const totalInteractive = sr02.total_interactive || 0;
  const undersized = sr02.undersized || 0;
  const touchScore = totalInteractive === 0 ? 70 : pctScale(totalInteractive - undersized, totalInteractive);

  const radii = (sr04.distinct_radii || []).length;
  const radiusScore = radii <= 3 ? 100 : radii <= 5 ? 70 : 40;

  const alignScore = sr07.alignment_score != null ? clamp(Math.round(sr07.alignment_score * 100), 0, 100) : 70;

  const shadowConsistent = sr05.direction_consistent != null ? sr05.direction_consistent : true;
  const shadowScore = shadowConsistent ? 100 : 30;

  // SR-09: Body text margin adequacy
  const sr09 = sr.sr09_body_text_margin || {};
  const marginInadequate = sr09.inadequate_margin || 0;
  const marginChecked = sr09.paragraphs_checked || 0;
  const marginScore = marginChecked === 0 ? 70 : pctScale(marginChecked - marginInadequate, marginChecked);

  // SR-06: Container max-width (blowout risk)
  const sr06 = sr.sr06_container_max_width || {};
  const blowouts = (sr06.blowout_risk || []).length;
  const containerScore = blowouts === 0 ? 100 : blowouts <= 2 ? 60 : 30;

  // SR-08: Whitespace density balance
  const sr08 = sr.sr08_whitespace_density || {};
  const whitespaceScore = clamp(Math.round((sr08.balance_score || 0) * 100), 0, 100);

  const spatialRaw = Math.round(
    spacingScore * 0.27 +
    touchScore * 0.16 +
    radiusScore * 0.12 +
    alignScore * 0.16 +
    shadowScore * 0.07 +
    marginScore * 0.12 +
    containerScore * 0.05 +
    whitespaceScore * 0.05
  );
  const spatialFloors = [];
  let spatialScore = spatialRaw;
  if (spacingConf === 0) { spatialScore = Math.min(spatialScore, 25); spatialFloors.push('zero_spacing_confidence'); }

  // ─── Attention Architecture (0-100) ─────────────────────────────

  const aa02 = aa.aa02_button_hierarchy || {};
  const aa03 = aa.aa03_interactive_affordance || {};
  const aa04 = aa.aa04_icon_text_labels || {};
  const aa06 = aa.aa06_form_label_presence || {};
  const aa09 = aa.aa09_navigation_item_count || {};
  const aa10 = aa.aa10_tab_order_visual || {};

  const primary = aa02.primary || 0;
  const secondary = aa02.secondary || 0;
  const btnScore = primary === 1 ? 100 : primary === 0 ? 20 : primary === 2 ? 60 : 30;

  const navItems = (aa09.items_per_nav || []);
  const maxNav = navItems.reduce((mx, n) => Math.max(mx, n.count || 0), 0);
  const navScore = maxNav === 0 ? 50 : (maxNav >= 4 && maxNav <= 6) ? 100 : maxNav === 7 ? 80 : (maxNav >= 8 && maxNav <= 10) ? 50 : 25;

  const affTotal = aa03.total || 0;
  const affWith = aa03.with_affordance || 0;
  const affScore = affTotal === 0 ? 70 : pctScale(affWith, affTotal);

  const iconsFound = aa04.icons_found || 0;
  const iconsLabeled = aa04.with_labels || 0;
  const iconScore = iconsFound === 0 ? 70 : pctScale(iconsLabeled, iconsFound);

  const tabMismatches = aa10.order_mismatches || 0;
  const formFields = aa06.fields || 0;
  const phOnly = aa06.placeholder_only || 0;
  const noLabel = aa06.no_label || 0;
  const formIssues = phOnly + noLabel;
  const tabFormScore = formFields === 0 && tabMismatches === 0
    ? 80
    : clamp(100 - tabMismatches * 10 - formIssues * 20, 0, 100);

  // AA-11: Form field border contrast (3:1 minimum per WCAG)
  const aa11 = aa.aa11_form_field_border_contrast || {};
  const fieldsBorderChecked = aa11.fields_checked || 0;
  const fieldsAdequate = aa11.adequate_contrast || 0;
  const borderContrastScore = fieldsBorderChecked === 0 ? 80 : pctScale(fieldsAdequate, fieldsBorderChecked);

  // AA-08: Generic link text ("click here", "read more", etc.)
  const aa08 = aa.aa08_generic_link_text || {};
  const genericLinks = aa08.generic_links || 0;
  const genericLinkScore = genericLinks === 0 ? 100 : genericLinks <= 3 ? 60 : 20;

  // AA-12: Generic button text ("Submit", "Click here", etc.)
  const aa12 = aa.aa12_generic_button_text || {};
  const genericBtnScore = (aa12.generic_labels || 0) === 0 ? 100 : (aa12.generic_labels <= 2) ? 60 : 20;

  const attentionRaw = Math.round(
    btnScore * 0.21 +
    navScore * 0.17 +
    affScore * 0.13 +
    iconScore * 0.11 +
    tabFormScore * 0.17 +
    borderContrastScore * 0.12 +
    genericLinkScore * 0.05 +
    genericBtnScore * 0.04
  );
  const attentionFloors = [];
  let attentionScore = attentionRaw;
  if (primary === 0 && secondary === 0) { attentionScore = Math.min(attentionScore, 50); attentionFloors.push('no_cta'); }

  // ─── Coherence (0-100) ──────────────────────────────────────────

  const co05 = co.co05_animation_duration_bounds || {};
  const co06 = co.co06_transition_property_specificity || {};
  const co08 = co.co08_overall_coherence || {};

  const coBase = co08.overall || 0;

  const tAll = co06.transition_all_count || 0;
  const tSpec = co06.specific_count || 0;
  const tTotal = tAll + tSpec;
  const transitionScore = tTotal === 0 ? 70 : pctScale(tSpec, tTotal);

  const animTotal = co05.transition_count || 0;
  const animWithin = co05.within_bounds || 0;
  const animScore = animTotal === 0 ? 70 : pctScale(animWithin, animTotal);

  const coherenceScore = Math.round(
    coBase * 0.70 +
    transitionScore * 0.15 +
    animScore * 0.15
  );
  const coherenceFloors = [];

  // ─── Overall Score ──────────────────────────────────────────────
  // Three structural principles:
  //   1. Coherence is a multiplier, not a peer — it scales the mechanical base
  //   2. Floor anchoring — overall can't outrun the weakest dimension by much
  //   3. Variance penalty — scattered passes among failures = no design intent

  const dims = [chromaticScore, typographyScore, spatialScore, attentionScore];
  const dimWeights = [0.20, 0.30, 0.25, 0.25];

  // Weighted average of the four mechanical dimensions
  const base = Math.round(
    dims[0] * dimWeights[0] +
    dims[1] * dimWeights[1] +
    dims[2] * dimWeights[2] +
    dims[3] * dimWeights[3]
  );

  // Coherence as a scaling factor — piecewise, not linear.
  // Above 70: a design system exists. Factor near 1.0.
  // 50-70: system is partial. Discount scales from 0.75 to 1.0.
  // Below 50: no real system. Discount scales from 0.55 to 0.75.
  const coherenceFactor = coherenceScore >= 70
    ? 0.95 + (coherenceScore - 70) * (0.05 / 30)   // 0.95 → 1.0
    : coherenceScore >= 50
      ? 0.75 + (coherenceScore - 50) * (0.20 / 20)  // 0.75 → 0.95
      : 0.55 + (coherenceScore / 50) * 0.20;         // 0.55 → 0.75
  const scaled = Math.round(base * coherenceFactor);

  // Floor anchoring: overall can't outrun the weakest dimension by much.
  // Per-dimension authority: chromatic and typography anchor hard,
  // spatial softer, attention softest (missing CTA on content page is less fatal).
  const dimAuthority = [1.0, 1.0, 0.8, 0.6]; // chromatic, typography, spatial, attention
  let dimMin = Infinity;
  let dimMinAuthority = 1.0;
  for (let i = 0; i < dims.length; i++) {
    if (dims[i] < dimMin) { dimMin = dims[i]; dimMinAuthority = dimAuthority[i]; }
  }
  const floorAnchor = dimMin + Math.round(20 * dimMinAuthority);

  // Variance penalty: standard deviation of the four mechanical dimensions.
  // High spread = scattered passes among failures = no design intent.
  // Kicks in above stdDev 8; penalty steepens with spread.
  const dimMean = dims.reduce((a, b) => a + b, 0) / dims.length;
  const variance = dims.reduce((sum, d) => sum + (d - dimMean) ** 2, 0) / dims.length;
  const stdDev = Math.sqrt(variance);
  const variancePenalty = stdDev > 8 ? Math.round((stdDev - 8) * 0.8) : 0;

  let overall = Math.min(scaled, floorAnchor) - variancePenalty;

  // Hard floor caps (critical failures override everything)
  const criticalFailures = [];
  const hardFloors = [];

  if (sub12 > 100) {
    hardFloors.push({ cap: 35, reason: `${sub12} elements below 12px` });
    criticalFailures.push(`${sub12} elements below 12px`);
  } else if (sub12 > 20) {
    hardFloors.push({ cap: 55, reason: `${sub12} elements below 12px` });
    criticalFailures.push(`${sub12} elements below 12px`);
  }

  const hardFails = cf01.hard_failures || 0;
  if (hardFails > 30) {
    hardFloors.push({ cap: 45, reason: `${hardFails} hard contrast failures` });
    criticalFailures.push(`${hardFails} hard contrast failures`);
  }

  if (spacingConf === 0) {
    hardFloors.push({ cap: 40, reason: 'zero spacing grid confidence' });
  }

  if (halation) {
    criticalFailures.push('halation risk (pure white on pure black)');
  }

  if (pureBlackBody > 20) {
    criticalFailures.push(`${pureBlackBody} pure black (#000) body text elements`);
  }

  if (primary === 0 && secondary === 0) {
    criticalFailures.push('no primary or secondary CTA');
  }

  if (totalInteractive > 0 && undersized === totalInteractive) {
    criticalFailures.push(`${undersized}/${totalInteractive} touch targets undersized`);
    if (undersized > 50) {
      hardFloors.push({ cap: 40, reason: `all ${undersized} touch targets undersized` });
    }
  }

  const aa16 = aa.aa16_destructive_action_weight || {};
  if ((aa16.destructive_as_primary || 0) > 0) {
    criticalFailures.push(`${aa16.destructive_as_primary} destructive action(s) styled as primary CTA`);
  }

  for (const floor of hardFloors) {
    overall = Math.min(overall, floor.cap);
  }

  // ─── Top Strengths ─────────────────────────────────────────────

  const topStrengths = [];
  if (adjustedRate >= 0.95) topStrengths.push(`${Math.round(adjustedRate * 100)}% contrast pass rate`);
  if (bands >= 2 && bands <= 3) topStrengths.push(`${bands} weight band${bands > 1 ? 's' : ''}`);
  if (medianLH >= 1.4 && medianLH <= 1.6) topStrengths.push(`${medianLH} body line-height`);
  if (systematic) topStrengths.push('systematic type scale');
  if (spacingConf >= 0.85) topStrengths.push(`${Math.round(spacingConf * 100)}% spacing grid confidence`);
  if (leaks === 0 && safe(cf04, 'primary_hue') != null) topStrengths.push('clean interactive hue containment');
  if (familyCount <= 2 && familyCount > 0) topStrengths.push(`${familyCount} typeface famil${familyCount === 1 ? 'y' : 'ies'}`);
  if (primary === 1) topStrengths.push('single primary CTA');
  if (genericLinks === 0) topStrengths.push('clean link text (no generic labels)');

  // ─── Assemble ──────────────────────────────────────────────────

  const finalScore = clamp(overall, 0, 100);

  return {
    overall_score: finalScore,
    overall_grade: grade(finalScore),
    scoring: {
      base,
      coherence_factor: Math.round(coherenceFactor * 100) / 100,
      scaled,
      floor_anchor: floorAnchor,
      variance_penalty: variancePenalty,
      std_dev: Math.round(stdDev * 10) / 10
    },
    dimensions: {
      chromatic:   { score: clamp(chromaticScore, 0, 100),   grade: grade(chromaticScore),   hard_floors_hit: chromaticFloors },
      typography:  { score: clamp(typographyScore, 0, 100),  grade: grade(typographyScore),  hard_floors_hit: typographyFloors },
      spatial:     { score: clamp(spatialScore, 0, 100),     grade: grade(spatialScore),     hard_floors_hit: spatialFloors },
      attention:   { score: clamp(attentionScore, 0, 100),   grade: grade(attentionScore),   hard_floors_hit: attentionFloors },
      coherence:   { score: clamp(coherenceScore, 0, 100),   grade: grade(coherenceScore),   hard_floors_hit: coherenceFloors }
    },
    critical_failures: criticalFailures,
    top_strengths: topStrengths.slice(0, 5)
  };
}
