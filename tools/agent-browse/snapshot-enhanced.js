/**
 * Enhanced snapshot with element refs, bounding boxes, and semantic labels.
 * Phase 2 enhancement for agent-browse.
 *
 * Features:
 *   - Bounding boxes (x, y, width, height) for each element
 *   - Semantic labels (login-form, nav-menu, modal, etc.)
 *   - Multiple output formats (tree, json, csv, markdown)
 *   - Viewport awareness (flags off-screen elements)
 *   - Input type detection (email, password, phone, etc.)
 */

let refCounter = 0;

export function resetRefs() {
    refCounter = 0;
}

function nextRef() {
    return `e${++refCounter}`;
}

const INTERACTIVE_ROLES = new Set([
    'button', 'link', 'textbox', 'checkbox', 'radio', 'combobox', 'listbox',
    'menuitem', 'menuitemcheckbox', 'menuitemradio', 'option', 'searchbox',
    'slider', 'spinbutton', 'switch', 'tab', 'treeitem',
]);

const CONTENT_ROLES = new Set([
    'heading', 'cell', 'gridcell', 'columnheader', 'rowheader', 'listitem',
    'article', 'region', 'main', 'navigation',
]);

const STRUCTURAL_ROLES = new Set([
    'generic', 'group', 'list', 'table', 'row', 'rowgroup', 'grid', 'treegrid',
    'menu', 'menubar', 'toolbar', 'tablist', 'tree', 'directory', 'document',
    'application', 'presentation', 'none',
]);

const LANDMARK_ROLES = new Set([
    'banner', 'complementary', 'contentinfo', 'form', 'main', 'navigation',
    'region', 'search',
]);

/**
 * Semantic pattern detection
 */
const SEMANTIC_PATTERNS = {
    'login-form': {
        indicators: ['password', 'email', 'username', 'sign in', 'log in', 'login'],
        requiredRoles: ['textbox'],
    },
    'search-box': {
        indicators: ['search', 'find', 'query'],
        requiredRoles: ['textbox', 'searchbox'],
    },
    'nav-menu': {
        indicators: ['menu', 'navigation', 'nav'],
        requiredRoles: ['link', 'menuitem'],
    },
    'modal-dialog': {
        indicators: ['dialog', 'modal', 'popup', 'overlay'],
        requiredRoles: ['dialog', 'alertdialog'],
    },
    'cookie-banner': {
        indicators: ['cookie', 'consent', 'privacy', 'accept'],
        requiredRoles: ['button'],
    },
    'signup-form': {
        indicators: ['sign up', 'register', 'create account', 'join'],
        requiredRoles: ['textbox'],
    },
    'contact-form': {
        indicators: ['contact', 'message', 'inquiry', 'feedback'],
        requiredRoles: ['textbox'],
    },
    'payment-form': {
        indicators: ['payment', 'credit card', 'card number', 'cvv', 'billing'],
        requiredRoles: ['textbox'],
    },
};

/**
 * Input type detection patterns
 */
const INPUT_TYPE_PATTERNS = {
    'email': ['email', 'e-mail', '@'],
    'password': ['password', 'pwd', 'pass'],
    'phone': ['phone', 'tel', 'mobile', 'cell'],
    'date': ['date', 'birthday', 'dob'],
    'credit-card': ['card number', 'credit card', 'cc number'],
    'cvv': ['cvv', 'cvc', 'security code'],
    'zip': ['zip', 'postal', 'postcode'],
    'name': ['name', 'first name', 'last name', 'full name'],
    'address': ['address', 'street', 'city', 'state'],
    'url': ['url', 'website', 'link'],
    'username': ['username', 'user name', 'user id', 'login'],
};

function buildSelector(role, name) {
    if (name) {
        const escapedName = name.replace(/"/g, '\\"');
        return `getByRole('${role}', { name: "${escapedName}", exact: true })`;
    }
    return `getByRole('${role}')`;
}

/**
 * Detect input type from name/placeholder
 */
function detectInputType(name) {
    if (!name) return null;
    const lower = name.toLowerCase();
    for (const [type, patterns] of Object.entries(INPUT_TYPE_PATTERNS)) {
        if (patterns.some(p => lower.includes(p))) {
            return type;
        }
    }
    return null;
}

/**
 * Get bounding boxes for all elements with refs
 */
async function getBoundingBoxes(page, refs) {
    const boxes = {};
    const viewport = page.viewportSize() || { width: 1280, height: 720 };
    
    for (const [ref, data] of Object.entries(refs)) {
        try {
            let locator;
            if (data.nth !== undefined) {
                locator = page.getByRole(data.role, { name: data.name, exact: true }).nth(data.nth);
            } else if (data.name) {
                locator = page.getByRole(data.role, { name: data.name, exact: true });
            } else {
                locator = page.getByRole(data.role).first();
            }
            
            const box = await locator.boundingBox({ timeout: 1000 }).catch(() => null);
            if (box) {
                boxes[ref] = {
                    x: Math.round(box.x),
                    y: Math.round(box.y),
                    width: Math.round(box.width),
                    height: Math.round(box.height),
                    // Viewport awareness
                    visible: box.x >= 0 && box.y >= 0 && 
                             box.x + box.width <= viewport.width &&
                             box.y + box.height <= viewport.height,
                    offScreen: box.y + box.height < 0 || box.y > viewport.height ||
                               box.x + box.width < 0 || box.x > viewport.width,
                    // Relative position
                    center: {
                        x: Math.round(box.x + box.width / 2),
                        y: Math.round(box.y + box.height / 2),
                    },
                };
            }
        } catch (e) {
            // Element may not be visible or accessible
        }
    }
    return boxes;
}

/**
 * Detect semantic regions in the page
 */
function detectSemanticRegions(refs, tree) {
    const regions = [];
    const treeLower = tree.toLowerCase();
    const refValues = Object.values(refs);
    
    for (const [regionType, pattern] of Object.entries(SEMANTIC_PATTERNS)) {
        const hasIndicator = pattern.indicators.some(i => treeLower.includes(i));
        const hasRequiredRole = pattern.requiredRoles.some(r => 
            refValues.some(ref => ref.role === r)
        );
        
        if (hasIndicator && hasRequiredRole) {
            // Find refs that belong to this region
            const regionRefs = [];
            for (const [ref, data] of Object.entries(refs)) {
                const nameLower = (data.name || '').toLowerCase();
                if (pattern.indicators.some(i => nameLower.includes(i)) ||
                    pattern.requiredRoles.includes(data.role)) {
                    regionRefs.push(ref);
                }
            }
            if (regionRefs.length > 0) {
                regions.push({
                    type: regionType,
                    refs: regionRefs,
                    confidence: hasIndicator && hasRequiredRole ? 'high' : 'medium',
                });
            }
        }
    }
    return regions;
}

/**
 * Enhanced snapshot with all Phase 2 features
 */
export async function getEnhancedSnapshot(page, options = {}) {
    resetRefs();
    const refs = {};
    
    const locator = options.selector ? page.locator(options.selector) : page.locator(':root');
    const ariaTree = await locator.ariaSnapshot();
    
    if (!ariaTree) {
        return {
            tree: '(empty)',
            refs: {},
            boxes: {},
            regions: [],
            format: options.format || 'tree',
        };
    }
    
    // Process ARIA tree (existing logic)
    const enhancedTree = processAriaTree(ariaTree, refs, options);
    
    // Phase 2: Get bounding boxes if requested
    let boxes = {};
    if (options.withBoxes || options.format === 'json') {
        boxes = await getBoundingBoxes(page, refs);
    }
    
    // Phase 2: Detect semantic regions
    const regions = detectSemanticRegions(refs, ariaTree);
    
    // Phase 2: Add input type detection to refs
    for (const [ref, data] of Object.entries(refs)) {
        if (data.role === 'textbox' || data.role === 'searchbox') {
            const inputType = detectInputType(data.name);
            if (inputType) {
                refs[ref].inputType = inputType;
            }
        }
    }
    
    // Format output based on requested format
    const result = {
        tree: enhancedTree,
        refs,
        boxes,
        regions,
    };
    
    if (options.format === 'json') {
        return formatAsJson(result, options);
    } else if (options.format === 'csv') {
        return formatAsCsv(result, options);
    } else if (options.format === 'markdown') {
        return formatAsMarkdown(result, options);
    }
    
    return result;
}

/**
 * Format output as JSON with full metadata
 */
function formatAsJson(result, options) {
    const elements = [];
    for (const [ref, data] of Object.entries(result.refs)) {
        const element = {
            ref,
            role: data.role,
            name: data.name || null,
            inputType: data.inputType || null,
            box: result.boxes[ref] || null,
        };
        if (data.nth !== undefined) element.nth = data.nth;
        elements.push(element);
    }
    
    return {
        tree: result.tree,
        refs: result.refs,
        boxes: result.boxes,
        regions: result.regions,
        elements,
        stats: {
            total: elements.length,
            interactive: elements.filter(e => INTERACTIVE_ROLES.has(e.role)).length,
            visible: Object.values(result.boxes).filter(b => b && b.visible).length,
            offScreen: Object.values(result.boxes).filter(b => b && b.offScreen).length,
        },
    };
}

/**
 * Format output as CSV for analysis
 */
function formatAsCsv(result, options) {
    const lines = ['ref,role,name,inputType,x,y,width,height,visible,offScreen'];
    for (const [ref, data] of Object.entries(result.refs)) {
        const box = result.boxes[ref] || {};
        const row = [
            ref,
            data.role,
            `"${(data.name || '').replace(/"/g, '""')}"`,
            data.inputType || '',
            box.x ?? '',
            box.y ?? '',
            box.width ?? '',
            box.height ?? '',
            box.visible ?? '',
            box.offScreen ?? '',
        ];
        lines.push(row.join(','));
    }
    return {
        tree: result.tree,
        refs: result.refs,
        boxes: result.boxes,
        regions: result.regions,
        csv: lines.join('\n'),
    };
}

/**
 * Format output as markdown for human reading
 */
function formatAsMarkdown(result, options) {
    const lines = ['# Page Snapshot\n'];
    
    // Semantic regions summary
    if (result.regions.length > 0) {
        lines.push('## Detected Regions\n');
        for (const region of result.regions) {
            lines.push(`- **${region.type}** (${region.confidence}): refs ${region.refs.join(', ')}`);
        }
        lines.push('');
    }
    
    // Interactive elements table
    const interactive = Object.entries(result.refs).filter(([, d]) => INTERACTIVE_ROLES.has(d.role));
    if (interactive.length > 0) {
        lines.push('## Interactive Elements\n');
        lines.push('| Ref | Role | Name | Input Type | Position |');
        lines.push('|-----|------|------|------------|----------|');
        for (const [ref, data] of interactive) {
            const box = result.boxes[ref];
            const pos = box ? `${box.x},${box.y}` : 'N/A';
            lines.push(`| ${ref} | ${data.role} | ${data.name || '-'} | ${data.inputType || '-'} | ${pos} |`);
        }
        lines.push('');
    }
    
    // Full tree
    lines.push('## Accessibility Tree\n');
    lines.push('```');
    lines.push(result.tree);
    lines.push('```');
    
    return {
        tree: result.tree,
        refs: result.refs,
        boxes: result.boxes,
        regions: result.regions,
        markdown: lines.join('\n'),
    };
}

function createRoleNameTracker() {
    const counts = new Map();
    const refsByKey = new Map();
    return {
        counts,
        refsByKey,
        getKey(role, name) {
            return `${role}:${name ?? ''}`;
        },
        getNextIndex(role, name) {
            const key = this.getKey(role, name);
            const current = counts.get(key) ?? 0;
            counts.set(key, current + 1);
            return current;
        },
        trackRef(role, name, ref) {
            const key = this.getKey(role, name);
            const refs = refsByKey.get(key) ?? [];
            refs.push(ref);
            refsByKey.set(key, refs);
        },
        getDuplicateKeys() {
            const duplicates = new Set();
            for (const [key, refs] of refsByKey) {
                if (refs.length > 1) {
                    duplicates.add(key);
                }
            }
            return duplicates;
        },
    };
}

function processAriaTree(ariaTree, refs, options) {
    const lines = ariaTree.split('\n');
    const result = [];
    const tracker = createRoleNameTracker();
    
    if (options.interactive) {
        for (const line of lines) {
            const match = line.match(/^(\s*-\s*)(\w+)(?:\s+"([^"]*)")?(.*)$/);
            if (!match) continue;
            const [, , role, name, suffix] = match;
            const roleLower = role.toLowerCase();
            if (INTERACTIVE_ROLES.has(roleLower)) {
                const ref = nextRef();
                const nth = tracker.getNextIndex(roleLower, name);
                tracker.trackRef(roleLower, name, ref);
                refs[ref] = {
                    selector: buildSelector(roleLower, name),
                    role: roleLower,
                    name,
                    nth,
                };
                let enhanced = `- ${role}`;
                if (name) enhanced += ` "${name}"`;
                enhanced += ` [ref=${ref}]`;
                if (nth > 0) enhanced += ` [nth=${nth}]`;
                if (suffix && suffix.includes('[')) enhanced += suffix;
                result.push(enhanced);
            }
        }
        removeNthFromNonDuplicates(refs, tracker);
        return result.join('\n') || '(no interactive elements)';
    }
    
    for (const line of lines) {
        const processed = processLine(line, refs, options, tracker);
        if (processed !== null) {
            result.push(processed);
        }
    }
    removeNthFromNonDuplicates(refs, tracker);
    
    if (options.compact) {
        return compactTree(result.join('\n'));
    }
    return result.join('\n');
}

function removeNthFromNonDuplicates(refs, tracker) {
    const duplicateKeys = tracker.getDuplicateKeys();
    for (const [ref, data] of Object.entries(refs)) {
        const key = tracker.getKey(data.role, data.name);
        if (!duplicateKeys.has(key)) {
            delete refs[ref].nth;
        }
    }
}

function getIndentLevel(line) {
    const match = line.match(/^(\s*)/);
    return match ? Math.floor(match[1].length / 2) : 0;
}

function processLine(line, refs, options, tracker) {
    const depth = getIndentLevel(line);
    if (options.maxDepth !== undefined && depth > options.maxDepth) {
        return null;
    }
    
    const match = line.match(/^(\s*-\s*)(\w+)(?:\s+"([^"]*)")?(.*)$/);
    if (!match) {
        if (options.interactive) return null;
        return line;
    }
    
    const [, prefix, role, name, suffix] = match;
    const roleLower = role.toLowerCase();
    if (role.startsWith('/')) return line;
    
    const isInteractive = INTERACTIVE_ROLES.has(roleLower);
    const isContent = CONTENT_ROLES.has(roleLower);
    const isStructural = STRUCTURAL_ROLES.has(roleLower);
    
    if (options.interactive && !isInteractive) return null;
    if (options.compact && isStructural && !name) return null;
    
    const shouldHaveRef = isInteractive || (isContent && name);
    if (shouldHaveRef) {
        const ref = nextRef();
        const nth = tracker.getNextIndex(roleLower, name);
        tracker.trackRef(roleLower, name, ref);
        refs[ref] = {
            selector: buildSelector(roleLower, name),
            role: roleLower,
            name,
            nth,
        };
        let enhanced = `${prefix}${role}`;
        if (name) enhanced += ` "${name}"`;
        enhanced += ` [ref=${ref}]`;
        if (nth > 0) enhanced += ` [nth=${nth}]`;
        if (suffix) enhanced += suffix;
        return enhanced;
    }
    return line;
}

function compactTree(tree) {
    const lines = tree.split('\n');
    const result = [];
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (line.includes('[ref=')) {
            result.push(line);
            continue;
        }
        if (line.includes(':') && !line.endsWith(':')) {
            result.push(line);
            continue;
        }
        const currentIndent = getIndentLevel(line);
        let hasRelevantChildren = false;
        for (let j = i + 1; j < lines.length; j++) {
            const childIndent = getIndentLevel(lines[j]);
            if (childIndent <= currentIndent) break;
            if (lines[j].includes('[ref=')) {
                hasRelevantChildren = true;
                break;
            }
        }
        if (hasRelevantChildren) {
            result.push(line);
        }
    }
    return result.join('\n');
}

export function parseRef(arg) {
    if (arg.startsWith('@')) return arg.slice(1);
    if (arg.startsWith('ref=')) return arg.slice(4);
    if (/^e\d+$/.test(arg)) return arg;
    return null;
}

export function getSnapshotStats(tree, refs) {
    const interactive = Object.values(refs).filter((r) => INTERACTIVE_ROLES.has(r.role)).length;
    return {
        lines: tree.split('\n').length,
        chars: tree.length,
        tokens: Math.ceil(tree.length / 4),
        refs: Object.keys(refs).length,
        interactive,
    };
}
