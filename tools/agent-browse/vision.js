/**
 * Vision integration module for agent-browse.
 * Phase 6: Enable visual understanding for AI agents.
 */

import Anthropic from '@anthropic-ai/sdk';

// Lazy-loaded API clients
let anthropicClient = null;

function getAnthropicClient() {
    if (!anthropicClient) {
        anthropicClient = new Anthropic();
    }
    return anthropicClient;
}

/**
 * Capture screenshot as base64 for vision APIs
 */
export async function captureForVision(page, options = {}) {
    const { fullPage = false, selector = null } = options;
    
    let target = page;
    if (selector) {
        target = page.locator(selector);
    }
    
    const buffer = await target.screenshot({
        fullPage,
        type: 'png',
    });
    
    return {
        base64: buffer.toString('base64'),
        mimeType: 'image/png',
        size: buffer.length,
    };
}

/**
 * Describe page using Claude Vision
 */
export async function describePage(page, options = {}) {
    const {
        detail = 'medium', // low, medium, high
        focus = null, // Specific area to focus on
        fullPage = false,
    } = options;
    
    const image = await captureForVision(page, { fullPage });
    
    const prompts = {
        low: 'Briefly describe what you see on this web page in 1-2 sentences.',
        medium: 'Describe this web page. Include the main content, navigation, and any notable UI elements. Be concise but comprehensive.',
        high: 'Provide a detailed description of this web page. Include:\n- Page type and purpose\n- Header/navigation elements\n- Main content areas\n- Forms and input fields\n- Buttons and interactive elements\n- Any modals, popups, or overlays\n- Notable visual design elements',
    };
    
    let prompt = prompts[detail] || prompts.medium;
    if (focus) {
        prompt = `Focus on the ${focus} area. ` + prompt;
    }
    
    const client = getAnthropicClient();
    const response = await client.messages.create({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1024,
        messages: [{
            role: 'user',
            content: [
                {
                    type: 'image',
                    source: {
                        type: 'base64',
                        media_type: image.mimeType,
                        data: image.base64,
                    },
                },
                {
                    type: 'text',
                    text: prompt,
                },
            ],
        }],
    });
    
    return {
        description: response.content[0].text,
        model: 'claude-sonnet-4-20250514',
        imageSize: image.size,
    };
}

/**
 * Find element by visual description
 */
export async function findByVisual(page, description, options = {}) {
    const { action = null } = options; // click, fill, etc.
    
    const image = await captureForVision(page);
    
    const prompt = `Look at this web page screenshot. I need to find: "${description}"

Return a JSON object with:
- found: boolean (whether you can identify the element)
- description: string (what you found)
- location: object with approximate {x, y} coordinates of the element's center (as percentages of image dimensions, 0-100)
- confidence: "high", "medium", or "low"
- selector_hint: string (a CSS selector hint based on visible text/attributes, if possible)

Return ONLY the JSON object, no other text.`;

    const client = getAnthropicClient();
    const response = await client.messages.create({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 512,
        messages: [{
            role: 'user',
            content: [
                {
                    type: 'image',
                    source: {
                        type: 'base64',
                        media_type: image.mimeType,
                        data: image.base64,
                    },
                },
                {
                    type: 'text',
                    text: prompt,
                },
            ],
        }],
    });
    
    try {
        const text = response.content[0].text;
        // Extract JSON from response (handle potential markdown code blocks)
        const jsonMatch = text.match(/\{[\s\S]*\}/);
        if (!jsonMatch) {
            return { found: false, error: 'Could not parse response' };
        }
        
        const result = JSON.parse(jsonMatch[0]);
        
        // Convert percentage coordinates to pixels if found
        if (result.found && result.location) {
            const viewport = page.viewportSize() || { width: 1280, height: 720 };
            result.pixelLocation = {
                x: Math.round((result.location.x / 100) * viewport.width),
                y: Math.round((result.location.y / 100) * viewport.height),
            };
        }
        
        return result;
    } catch (e) {
        return { found: false, error: 'Failed to parse vision response', raw: response.content[0].text };
    }
}

/**
 * Click element found by visual description
 */
export async function clickByVisual(page, description) {
    const result = await findByVisual(page, description);
    
    if (!result.found || !result.pixelLocation) {
        return { clicked: false, error: 'Element not found', ...result };
    }
    
    await page.mouse.click(result.pixelLocation.x, result.pixelLocation.y);
    return { clicked: true, location: result.pixelLocation, ...result };
}

/**
 * Analyze page for specific elements or patterns
 */
export async function analyzePattern(page, pattern, options = {}) {
    const image = await captureForVision(page, options);
    
    const patterns = {
        'errors': 'List any error messages, warnings, or alert banners visible on this page. Return JSON: {found: boolean, errors: [{text: string, type: "error"|"warning"|"info", location: string}]}',
        'forms': 'Identify all forms on this page. Return JSON: {forms: [{purpose: string, fields: [{name: string, type: string, required: boolean}], submitButton: string}]}',
        'navigation': 'Describe the navigation structure. Return JSON: {mainNav: [{label: string, hasDropdown: boolean}], breadcrumbs: string[], footer: [{section: string, links: string[]}]}',
        'products': 'List products/items visible. Return JSON: {items: [{name: string, price: string, image: boolean, button: string}]}',
        'login': 'Analyze the login/signup flow. Return JSON: {type: "login"|"signup"|"both", fields: string[], socialOptions: string[], forgotPassword: boolean}',
    };
    
    const prompt = patterns[pattern] || `Analyze this page for: ${pattern}. Return a structured JSON response.`;
    
    const client = getAnthropicClient();
    const response = await client.messages.create({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1024,
        messages: [{
            role: 'user',
            content: [
                {
                    type: 'image',
                    source: {
                        type: 'base64',
                        media_type: image.mimeType,
                        data: image.base64,
                    },
                },
                {
                    type: 'text',
                    text: prompt + '\n\nReturn ONLY valid JSON.',
                },
            ],
        }],
    });
    
    try {
        const text = response.content[0].text;
        const jsonMatch = text.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
            return JSON.parse(jsonMatch[0]);
        }
        return { raw: text };
    } catch (e) {
        return { error: 'Failed to parse response', raw: response.content[0].text };
    }
}

/**
 * Compare two screenshots for changes
 */
export async function compareScreenshots(image1Base64, image2Base64) {
    const client = getAnthropicClient();
    
    const response = await client.messages.create({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1024,
        messages: [{
            role: 'user',
            content: [
                {
                    type: 'text',
                    text: 'Compare these two screenshots and describe what changed between them. Focus on UI changes, content updates, and state changes.',
                },
                {
                    type: 'image',
                    source: {
                        type: 'base64',
                        media_type: 'image/png',
                        data: image1Base64,
                    },
                },
                {
                    type: 'image',
                    source: {
                        type: 'base64',
                        media_type: 'image/png',
                        data: image2Base64,
                    },
                },
            ],
        }],
    });
    
    return {
        changes: response.content[0].text,
    };
}

/**
 * Explain what will happen if an action is taken
 */
export async function explainAction(page, action, target) {
    const image = await captureForVision(page);
    
    const prompt = `Look at this web page. If I ${action} on "${target}", what do you predict will happen? Consider:
- Navigation changes
- Form submissions
- Modal/popup appearances
- State changes
- Potential errors

Be specific and practical.`;

    const client = getAnthropicClient();
    const response = await client.messages.create({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 512,
        messages: [{
            role: 'user',
            content: [
                {
                    type: 'image',
                    source: {
                        type: 'base64',
                        media_type: image.mimeType,
                        data: image.base64,
                    },
                },
                {
                    type: 'text',
                    text: prompt,
                },
            ],
        }],
    });
    
    return {
        prediction: response.content[0].text,
        action,
        target,
    };
}
