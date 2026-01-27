/**
 * AI Agent helpers module for agent-browse.
 * Phase 7: Goal execution, page exploration, smart recovery.
 */

import Anthropic from '@anthropic-ai/sdk';
import { captureForVision, describePage, findByVisual, analyzePattern } from './vision.js';

let anthropicClient = null;

function getAnthropicClient() {
    if (!anthropicClient) {
        anthropicClient = new Anthropic();
    }
    return anthropicClient;
}

/**
 * Execute a high-level goal through planning and action loop
 */
export async function executeGoal(page, browser, goal, options = {}) {
    const {
        maxSteps = 10,
        verbose = false,
        onStep = null, // callback for each step
    } = options;

    const history = [];
    let stepCount = 0;
    let completed = false;
    let error = null;

    // Get initial page state
    const snapshot = await browser.getSnapshot({ interactive: true, withBoxes: true });
    
    const systemPrompt = `You are an AI browser automation agent. You execute user goals by analyzing page state and taking actions.

Available actions:
- click <selector|@ref> - Click an element
- fill <selector|@ref> <value> - Fill a text field
- type <text> - Type text (for complex inputs)
- press <key> - Press keyboard key (Enter, Tab, Escape, etc.)
- scroll <direction> - Scroll up/down/left/right
- wait <ms> - Wait milliseconds
- navigate <url> - Go to URL
- back - Go back
- done - Goal completed successfully
- fail <reason> - Goal cannot be completed

Response format (JSON only):
{
  "thinking": "Brief analysis of current state",
  "action": "action_name",
  "args": ["arg1", "arg2"],
  "confidence": 0.95,
  "explanation": "Why this action"
}`;

    while (stepCount < maxSteps && !completed && !error) {
        stepCount++;
        
        // Capture current state
        const image = await captureForVision(page);
        const currentUrl = page.url();
        
        // Build context for the agent
        const context = `Goal: "${goal}"

Current URL: ${currentUrl}
Step: ${stepCount}/${maxSteps}

Page snapshot (interactive elements):
${snapshot.tree || 'Empty page'}

Previous actions:
${history.map((h, i) => `${i + 1}. ${h.action}(${h.args?.join(', ') || ''}) -> ${h.result}`).join('\n') || 'None'}

Analyze the screenshot and page state. What action should I take next to achieve the goal?`;

        try {
            const client = getAnthropicClient();
            const response = await client.messages.create({
                model: 'claude-sonnet-4-20250514',
                max_tokens: 1024,
                system: systemPrompt,
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
                            text: context,
                        },
                    ],
                }],
            });

            // Parse response
            const text = response.content[0].text;
            const jsonMatch = text.match(/\{[\s\S]*\}/);
            if (!jsonMatch) {
                error = 'Failed to parse agent response';
                break;
            }

            const step = JSON.parse(jsonMatch[0]);
            
            if (verbose || onStep) {
                const stepInfo = {
                    step: stepCount,
                    thinking: step.thinking,
                    action: step.action,
                    args: step.args,
                    confidence: step.confidence,
                };
                if (onStep) onStep(stepInfo);
            }

            // Execute action
            let result;
            switch (step.action) {
                case 'done':
                    completed = true;
                    result = 'Goal completed';
                    break;
                    
                case 'fail':
                    error = step.args?.[0] || 'Goal failed';
                    result = error;
                    break;
                    
                case 'click':
                    await browser.getLocator(step.args[0]).click();
                    result = 'clicked';
                    break;
                    
                case 'fill':
                    await browser.getLocator(step.args[0]).fill(step.args[1] || '');
                    result = 'filled';
                    break;
                    
                case 'type':
                    await page.keyboard.type(step.args[0] || '');
                    result = 'typed';
                    break;
                    
                case 'press':
                    await page.keyboard.press(step.args[0] || 'Enter');
                    result = 'pressed';
                    break;
                    
                case 'scroll':
                    const direction = step.args?.[0] || 'down';
                    const amount = 300;
                    if (direction === 'up') await page.mouse.wheel(0, -amount);
                    else if (direction === 'down') await page.mouse.wheel(0, amount);
                    else if (direction === 'left') await page.mouse.wheel(-amount, 0);
                    else if (direction === 'right') await page.mouse.wheel(amount, 0);
                    result = 'scrolled';
                    break;
                    
                case 'wait':
                    const ms = parseInt(step.args?.[0]) || 1000;
                    await page.waitForTimeout(ms);
                    result = 'waited';
                    break;
                    
                case 'navigate':
                    await page.goto(step.args[0], { waitUntil: 'domcontentloaded' });
                    result = 'navigated';
                    break;
                    
                case 'back':
                    await page.goBack();
                    result = 'went back';
                    break;
                    
                default:
                    result = `unknown action: ${step.action}`;
            }

            history.push({
                action: step.action,
                args: step.args,
                result,
                thinking: step.thinking,
            });

            // Small delay between actions
            await page.waitForTimeout(500);
            
        } catch (e) {
            // Try recovery
            const recovery = await attemptRecovery(page, browser, e, history);
            if (recovery.recovered) {
                history.push({
                    action: 'recovery',
                    args: [recovery.strategy],
                    result: recovery.result,
                });
            } else {
                error = `Action failed: ${e.message}`;
            }
        }
    }

    return {
        completed,
        error,
        steps: stepCount,
        history,
        url: page.url(),
    };
}

/**
 * Explore a page and discover all interactive elements and navigation
 */
export async function explorePage(page, browser, options = {}) {
    const {
        depth = 1, // How many links deep to explore
        maxLinks = 10, // Max links to follow per page
        sameOrigin = true, // Only follow same-origin links
    } = options;

    const visited = new Set();
    const discovered = {
        pages: [],
        forms: [],
        interactions: [],
        navigation: [],
    };

    async function exploreUrl(url, currentDepth) {
        if (currentDepth > depth || visited.has(url)) return;
        if (sameOrigin && new URL(url).origin !== new URL(page.url()).origin) return;
        
        visited.add(url);
        
        await page.goto(url, { waitUntil: 'domcontentloaded' });
        
        // Get snapshot
        const snapshot = await browser.getSnapshot({ interactive: true, withBoxes: true });
        
        // Analyze page patterns
        const forms = await analyzePattern(page, 'forms');
        const nav = await analyzePattern(page, 'navigation');
        
        const pageInfo = {
            url,
            title: await page.title(),
            depth: currentDepth,
            elements: snapshot.stats?.interactive || 0,
            forms: forms.forms || [],
            navigation: nav.mainNav || [],
        };
        
        discovered.pages.push(pageInfo);
        
        if (forms.forms) discovered.forms.push(...forms.forms.map(f => ({ ...f, url })));
        if (nav.mainNav) discovered.navigation.push(...nav.mainNav.map(n => ({ ...n, url })));
        
        // Find links to explore
        if (currentDepth < depth) {
            const links = await page.$$eval('a[href]', (els) => 
                els.slice(0, 50).map(a => a.href).filter(h => h.startsWith('http'))
            );
            
            const uniqueLinks = [...new Set(links)].slice(0, maxLinks);
            for (const link of uniqueLinks) {
                await exploreUrl(link, currentDepth + 1);
            }
        }
    }

    await exploreUrl(page.url(), 0);
    
    return discovered;
}

/**
 * Attempt to recover from an error
 */
export async function attemptRecovery(page, browser, error, history) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    
    // Strategy 1: Element not found - try waiting and retrying
    if (errorMsg.includes('not found') || errorMsg.includes('not visible')) {
        await page.waitForTimeout(2000);
        return { recovered: true, strategy: 'wait_retry', result: 'waited 2s' };
    }
    
    // Strategy 2: Element blocked - try scrolling into view or dismissing overlay
    if (errorMsg.includes('intercepts pointer') || errorMsg.includes('blocked')) {
        // Try to dismiss common overlays
        const overlaySelectors = [
            '[class*="cookie"] button',
            '[class*="modal"] button[class*="close"]',
            '[class*="popup"] button[class*="close"]',
            '[aria-label="Close"]',
            '[aria-label="Dismiss"]',
        ];
        
        for (const selector of overlaySelectors) {
            try {
                const el = page.locator(selector).first();
                if (await el.isVisible()) {
                    await el.click();
                    await page.waitForTimeout(500);
                    return { recovered: true, strategy: 'dismiss_overlay', result: `clicked ${selector}` };
                }
            } catch {}
        }
    }
    
    // Strategy 3: Navigation error - go back or reload
    if (errorMsg.includes('navigation') || errorMsg.includes('timeout')) {
        try {
            await page.reload({ waitUntil: 'domcontentloaded' });
            return { recovered: true, strategy: 'reload', result: 'reloaded page' };
        } catch {
            try {
                await page.goBack();
                return { recovered: true, strategy: 'go_back', result: 'went back' };
            } catch {}
        }
    }
    
    return { recovered: false, strategy: null, result: null };
}

/**
 * Explain what's on the current page and what actions are possible
 */
export async function explainPage(page, browser) {
    const snapshot = await browser.getSnapshot({ interactive: true, withBoxes: true });
    const description = await describePage(page, { detail: 'high' });
    
    // Analyze key patterns
    const loginAnalysis = await analyzePattern(page, 'login');
    const formAnalysis = await analyzePattern(page, 'forms');
    const errorAnalysis = await analyzePattern(page, 'errors');
    
    return {
        url: page.url(),
        title: await page.title(),
        description: description.description,
        interactiveElements: snapshot.stats?.interactive || 0,
        visibleElements: snapshot.stats?.visible || 0,
        hasLoginForm: loginAnalysis.type === 'login' || loginAnalysis.type === 'both',
        forms: formAnalysis.forms || [],
        errors: errorAnalysis.errors || [],
        refs: snapshot.refs || {},
        regions: snapshot.regions || [],
    };
}

/**
 * Execute a sequence of actions with fallbacks
 */
export async function executeWithFallbacks(page, browser, actions) {
    const results = [];
    
    for (const action of actions) {
        const alternatives = Array.isArray(action) ? action : [action];
        let success = false;
        let lastError = null;
        
        for (const alt of alternatives) {
            try {
                const { type, ...params } = alt;
                
                switch (type) {
                    case 'click':
                        await browser.getLocator(params.selector).click();
                        break;
                    case 'fill':
                        await browser.getLocator(params.selector).fill(params.value);
                        break;
                    case 'press':
                        await page.keyboard.press(params.key);
                        break;
                    case 'wait':
                        await page.waitForTimeout(params.ms || 1000);
                        break;
                    case 'navigate':
                        await page.goto(params.url);
                        break;
                }
                
                results.push({ action: alt, success: true });
                success = true;
                break;
            } catch (e) {
                lastError = e;
            }
        }
        
        if (!success) {
            results.push({ action: alternatives[0], success: false, error: lastError?.message });
        }
    }
    
    return results;
}
