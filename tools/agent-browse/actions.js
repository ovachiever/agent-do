import { successResponse, errorResponse } from './protocol.js';
import { saveSession, restoreSession, listSessions, deleteSession, exportSession, importSession } from './session.js';
import { RequestTracker, setThrottle, clearThrottle, THROTTLE_PRESETS } from './network.js';
import { generateTOTPSync, getTOTPTimeRemaining, detectLoginForm, autoFillLogin, detectCaptcha, waitForCaptchaSolved } from './auth.js';
import { describePage, findByVisual, clickByVisual, analyzePattern, compareScreenshots, explainAction, captureForVision } from './vision.js';
import { executeGoal, explorePage, explainPage, attemptRecovery } from './agent.js';
// Callback for screencast frames - will be set by the daemon when streaming is active
let screencastFrameCallback = null;
// Phase 4: Request tracker for HAR export
let requestTracker = new RequestTracker();
/**
 * Set the callback for screencast frames
 * This is called by the daemon to set up frame streaming
 */
export function setScreencastFrameCallback(callback) {
    screencastFrameCallback = callback;
}
/**
 * Convert Playwright errors to AI-friendly messages
 * @internal Exported for testing
 */
export function toAIFriendlyError(error, selector) {
    const message = error instanceof Error ? error.message : String(error);
    // Handle strict mode violation (multiple elements match)
    if (message.includes('strict mode violation')) {
        // Extract count if available
        const countMatch = message.match(/resolved to (\d+) elements/);
        const count = countMatch ? countMatch[1] : 'multiple';
        // Provide actionable suggestions based on selector type
        const isRef = selector?.startsWith('@');
        const suggestion = isRef
            ? `Use '${selector} >> nth=0' for first match, or 'role=X >> nth=N' pattern.`
            : `Use '${selector} >> nth=0' for first match.`;
        return new Error(`Selector "${selector}" matched ${count} elements. ${suggestion}`);
    }
    // Handle element not interactable (must be checked BEFORE timeout case)
    // This includes cases where an overlay/modal blocks the element
    if (message.includes('intercepts pointer events')) {
        return new Error(`Element "${selector}" is blocked by another element (likely a modal or overlay). ` +
            `Try dismissing any modals/cookie banners first.`);
    }
    // Handle element not visible
    if (message.includes('not visible') && !message.includes('Timeout')) {
        return new Error(`Element "${selector}" is not visible. ` +
            `Try scrolling it into view or check if it's hidden.`);
    }
    // Handle element not found (timeout waiting for element)
    if (message.includes('waiting for') &&
        (message.includes('to be visible') || message.includes('Timeout'))) {
        return new Error(`Element "${selector}" not found or not visible. ` +
            `Run 'snapshot' to see current page elements.`);
    }
    // Return original error for unknown cases
    return error instanceof Error ? error : new Error(message);
}
/**
 * Execute a command and return a response
 */
export async function executeCommand(command, browser) {
    try {
        switch (command.action) {
            case 'launch':
                return await handleLaunch(command, browser);
            case 'navigate':
                return await handleNavigate(command, browser);
            case 'click':
                return await handleClick(command, browser);
            case 'type':
                return await handleType(command, browser);
            case 'fill':
                return await handleFill(command, browser);
            case 'check':
                return await handleCheck(command, browser);
            case 'uncheck':
                return await handleUncheck(command, browser);
            case 'upload':
                return await handleUpload(command, browser);
            case 'dblclick':
                return await handleDoubleClick(command, browser);
            case 'focus':
                return await handleFocus(command, browser);
            case 'drag':
                return await handleDrag(command, browser);
            case 'frame':
                return await handleFrame(command, browser);
            case 'mainframe':
                return await handleMainFrame(command, browser);
            case 'getbyrole':
                return await handleGetByRole(command, browser);
            case 'getbytext':
                return await handleGetByText(command, browser);
            case 'getbylabel':
                return await handleGetByLabel(command, browser);
            case 'getbyplaceholder':
                return await handleGetByPlaceholder(command, browser);
            case 'press':
                return await handlePress(command, browser);
            case 'screenshot':
                return await handleScreenshot(command, browser);
            case 'snapshot':
                return await handleSnapshot(command, browser);
            case 'evaluate':
                return await handleEvaluate(command, browser);
            case 'wait':
                return await handleWait(command, browser);
            case 'scroll':
                return await handleScroll(command, browser);
            case 'select':
                return await handleSelect(command, browser);
            case 'hover':
                return await handleHover(command, browser);
            case 'content':
                return await handleContent(command, browser);
            case 'close':
                return await handleClose(command, browser);
            case 'tab_new':
                return await handleTabNew(command, browser);
            case 'tab_list':
                return await handleTabList(command, browser);
            case 'tab_switch':
                return await handleTabSwitch(command, browser);
            case 'tab_close':
                return await handleTabClose(command, browser);
            case 'window_new':
                return await handleWindowNew(command, browser);
            case 'cookies_get':
                return await handleCookiesGet(command, browser);
            case 'cookies_set':
                return await handleCookiesSet(command, browser);
            case 'cookies_clear':
                return await handleCookiesClear(command, browser);
            case 'storage_get':
                return await handleStorageGet(command, browser);
            case 'storage_set':
                return await handleStorageSet(command, browser);
            case 'storage_clear':
                return await handleStorageClear(command, browser);
            case 'dialog':
                return await handleDialog(command, browser);
            case 'pdf':
                return await handlePdf(command, browser);
            case 'route':
                return await handleRoute(command, browser);
            case 'unroute':
                return await handleUnroute(command, browser);
            case 'requests':
                return await handleRequests(command, browser);
            case 'download':
                return await handleDownload(command, browser);
            case 'geolocation':
                return await handleGeolocation(command, browser);
            case 'permissions':
                return await handlePermissions(command, browser);
            case 'viewport':
                return await handleViewport(command, browser);
            case 'useragent':
                return await handleUserAgent(command, browser);
            case 'device':
                return await handleDevice(command, browser);
            case 'back':
                return await handleBack(command, browser);
            case 'forward':
                return await handleForward(command, browser);
            case 'reload':
                return await handleReload(command, browser);
            case 'url':
                return await handleUrl(command, browser);
            case 'title':
                return await handleTitle(command, browser);
            case 'getattribute':
                return await handleGetAttribute(command, browser);
            case 'gettext':
                return await handleGetText(command, browser);
            case 'isvisible':
                return await handleIsVisible(command, browser);
            case 'isenabled':
                return await handleIsEnabled(command, browser);
            case 'ischecked':
                return await handleIsChecked(command, browser);
            case 'count':
                return await handleCount(command, browser);
            case 'getoptions':
                return await handleGetOptions(command, browser);
            case 'boundingbox':
                return await handleBoundingBox(command, browser);
            case 'styles':
                return await handleStyles(command, browser);
            case 'video_start':
                return await handleVideoStart(command, browser);
            case 'video_stop':
                return await handleVideoStop(command, browser);
            case 'trace_start':
                return await handleTraceStart(command, browser);
            case 'trace_stop':
                return await handleTraceStop(command, browser);
            case 'har_start':
                return await handleHarStart(command, browser);
            case 'har_stop':
                return await handleHarStop(command, browser);
            case 'throttle':
                return await handleThrottle(command, browser);
            case 'network_stats':
                return await handleNetworkStats(command, browser);
            case 'totp':
                return await handleTOTP(command, browser);
            case 'detect_login':
                return await handleDetectLogin(command, browser);
            case 'autofill_login':
                return await handleAutofillLogin(command, browser);
            case 'detect_captcha':
                return await handleDetectCaptcha(command, browser);
            case 'wait_captcha':
                return await handleWaitCaptcha(command, browser);
            case 'state_save':
                return await handleStateSave(command, browser);
            case 'state_load':
                return await handleStateLoad(command, browser);
            case 'session_save':
                return await handleSessionSave(command, browser);
            case 'session_load':
                return await handleSessionLoad(command, browser);
            case 'session_list':
                return await handleSessionList(command);
            case 'session_delete':
                return await handleSessionDelete(command);
            case 'session_export':
                return await handleSessionExport(command);
            case 'session_import':
                return await handleSessionImport(command);
            case 'console':
                return await handleConsole(command, browser);
            case 'errors':
                return await handleErrors(command, browser);
            case 'keyboard':
                return await handleKeyboard(command, browser);
            case 'wheel':
                return await handleWheel(command, browser);
            case 'tap':
                return await handleTap(command, browser);
            case 'clipboard':
                return await handleClipboard(command, browser);
            case 'highlight':
                return await handleHighlight(command, browser);
            case 'clear':
                return await handleClear(command, browser);
            case 'selectall':
                return await handleSelectAll(command, browser);
            case 'innertext':
                return await handleInnerText(command, browser);
            case 'innerhtml':
                return await handleInnerHtml(command, browser);
            case 'inputvalue':
                return await handleInputValue(command, browser);
            case 'setvalue':
                return await handleSetValue(command, browser);
            case 'dispatch':
                return await handleDispatch(command, browser);
            case 'evalhandle':
                return await handleEvalHandle(command, browser);
            case 'expose':
                return await handleExpose(command, browser);
            case 'addscript':
                return await handleAddScript(command, browser);
            case 'addstyle':
                return await handleAddStyle(command, browser);
            case 'emulatemedia':
                return await handleEmulateMedia(command, browser);
            case 'offline':
                return await handleOffline(command, browser);
            case 'headers':
                return await handleHeaders(command, browser);
            case 'pause':
                return await handlePause(command, browser);
            case 'getbyalttext':
                return await handleGetByAltText(command, browser);
            case 'getbytitle':
                return await handleGetByTitle(command, browser);
            case 'getbytestid':
                return await handleGetByTestId(command, browser);
            case 'nth':
                return await handleNth(command, browser);
            case 'waitforurl':
                return await handleWaitForUrl(command, browser);
            case 'waitforloadstate':
                return await handleWaitForLoadState(command, browser);
            case 'setcontent':
                return await handleSetContent(command, browser);
            case 'timezone':
                return await handleTimezone(command, browser);
            case 'locale':
                return await handleLocale(command, browser);
            case 'credentials':
                return await handleCredentials(command, browser);
            case 'mousemove':
                return await handleMouseMove(command, browser);
            case 'mousedown':
                return await handleMouseDown(command, browser);
            case 'mouseup':
                return await handleMouseUp(command, browser);
            case 'bringtofront':
                return await handleBringToFront(command, browser);
            case 'waitforfunction':
                return await handleWaitForFunction(command, browser);
            case 'scrollintoview':
                return await handleScrollIntoView(command, browser);
            case 'addinitscript':
                return await handleAddInitScript(command, browser);
            case 'keydown':
                return await handleKeyDown(command, browser);
            case 'keyup':
                return await handleKeyUp(command, browser);
            case 'inserttext':
                return await handleInsertText(command, browser);
            case 'multiselect':
                return await handleMultiSelect(command, browser);
            case 'waitfordownload':
                return await handleWaitForDownload(command, browser);
            case 'responsebody':
                return await handleResponseBody(command, browser);
            case 'screencast_start':
                return await handleScreencastStart(command, browser);
            case 'screencast_stop':
                return await handleScreencastStop(command, browser);
            case 'input_mouse':
                return await handleInputMouse(command, browser);
            case 'input_keyboard':
                return await handleInputKeyboard(command, browser);
            case 'input_touch':
                return await handleInputTouch(command, browser);
            case 'recording_start':
                return await handleRecordingStart(command, browser);
            case 'recording_stop':
                return await handleRecordingStop(command, browser);
            case 'recording_restart':
                return await handleRecordingRestart(command, browser);
            // Phase 6: Vision commands
            case 'vision_describe':
                return await handleVisionDescribe(command, browser);
            case 'vision_find':
                return await handleVisionFind(command, browser);
            case 'vision_click':
                return await handleVisionClick(command, browser);
            case 'vision_analyze':
                return await handleVisionAnalyze(command, browser);
            case 'vision_compare':
                return await handleVisionCompare(command, browser);
            case 'vision_explain':
                return await handleVisionExplain(command, browser);
            // Phase 7: Agent commands
            case 'agent_goal':
                return await handleAgentGoal(command, browser);
            case 'agent_explore':
                return await handleAgentExplore(command, browser);
            case 'agent_explain':
                return await handleAgentExplain(command, browser);
            case 'agent_recover':
                return await handleAgentRecover(command, browser);
            default: {
                // TypeScript narrows to never here, but we handle it for safety
                const unknownCommand = command;
                return errorResponse(unknownCommand.id, `Unknown action: ${unknownCommand.action}`);
            }
        }
    }
    catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return errorResponse(command.id, message);
    }
}
async function handleLaunch(command, browser) {
    await browser.launch(command);
    return successResponse(command.id, { launched: true });
}
async function handleNavigate(command, browser) {
    const page = browser.getPage();
    // If headers are provided, set up scoped headers for this origin
    if (command.headers && Object.keys(command.headers).length > 0) {
        await browser.setScopedHeaders(command.url, command.headers);
    }
    await page.goto(command.url, {
        waitUntil: command.waitUntil ?? 'load',
    });
    return successResponse(command.id, {
        url: page.url(),
        title: await page.title(),
    });
}
async function handleClick(command, browser) {
    // Support both refs (@e1) and regular selectors
    const locator = browser.getLocator(command.selector);
    try {
        await locator.click({
            button: command.button,
            clickCount: command.clickCount,
            delay: command.delay,
        });
    }
    catch (error) {
        throw toAIFriendlyError(error, command.selector);
    }
    return successResponse(command.id, { clicked: true });
}
async function handleType(command, browser) {
    const locator = browser.getLocator(command.selector);
    try {
        if (command.clear) {
            await locator.fill('');
        }
        await locator.pressSequentially(command.text, {
            delay: command.delay,
        });
    }
    catch (error) {
        throw toAIFriendlyError(error, command.selector);
    }
    return successResponse(command.id, { typed: true });
}
async function handlePress(command, browser) {
    const page = browser.getPage();
    if (command.selector) {
        await page.press(command.selector, command.key);
    }
    else {
        await page.keyboard.press(command.key);
    }
    return successResponse(command.id, { pressed: true });
}
async function handleScreenshot(command, browser) {
    const page = browser.getPage();
    const options = {
        fullPage: command.fullPage,
        type: command.format ?? 'png',
    };
    if (command.format === 'jpeg' && command.quality !== undefined) {
        options.quality = command.quality;
    }
    let target = page;
    if (command.selector) {
        target = page.locator(command.selector);
    }
    if (command.path) {
        await target.screenshot({ ...options, path: command.path });
        return successResponse(command.id, { path: command.path });
    }
    else {
        const buffer = await target.screenshot(options);
        return successResponse(command.id, { base64: buffer.toString('base64') });
    }
}
async function handleSnapshot(command, browser) {
    // Use enhanced snapshot with refs, boxes, and regions (Phase 2)
    const result = await browser.getSnapshot({
        interactive: command.interactive,
        maxDepth: command.maxDepth,
        compact: command.compact,
        selector: command.selector,
        format: command.format,
        withBoxes: command.withBoxes,
    });
    
    // Build response based on format
    const response = {
        snapshot: result.tree || 'Empty page',
    };
    
    // Simplify refs for output (role, name, inputType)
    if (result.refs && Object.keys(result.refs).length > 0) {
        const simpleRefs = {};
        for (const [ref, data] of Object.entries(result.refs)) {
            simpleRefs[ref] = { role: data.role, name: data.name };
            if (data.inputType) simpleRefs[ref].inputType = data.inputType;
        }
        response.refs = simpleRefs;
    }
    
    // Include boxes if requested or format is json
    if (result.boxes && Object.keys(result.boxes).length > 0) {
        response.boxes = result.boxes;
    }
    
    // Include semantic regions if detected
    if (result.regions && result.regions.length > 0) {
        response.regions = result.regions;
    }
    
    // Include format-specific output
    if (result.csv) response.csv = result.csv;
    if (result.markdown) response.markdown = result.markdown;
    if (result.elements) response.elements = result.elements;
    if (result.stats) response.stats = result.stats;
    
    return successResponse(command.id, response);
}
async function handleEvaluate(command, browser) {
    const page = browser.getPage();
    // Evaluate the script directly as a string expression
    const result = await page.evaluate(command.script);
    return successResponse(command.id, { result });
}
async function handleWait(command, browser) {
    const page = browser.getPage();
    
    // Check if state is a load state (networkidle, load, domcontentloaded)
    const loadStates = ['networkidle', 'load', 'domcontentloaded'];
    if (command.state && loadStates.includes(command.state)) {
        await page.waitForLoadState(command.state, { timeout: command.timeout });
        return successResponse(command.id, { waited: true, state: command.state });
    }
    
    if (command.selector) {
        await page.waitForSelector(command.selector, {
            state: command.state ?? 'visible',
            timeout: command.timeout,
        });
    }
    else if (command.text) {
        // Wait for text to appear on page
        await page.waitForFunction(
            (text) => document.body.innerText.includes(text),
            command.text,
            { timeout: command.timeout }
        );
        return successResponse(command.id, { waited: true, text: command.text });
    }
    else if (command.url) {
        // Wait for URL to match pattern
        await page.waitForURL(command.url, { timeout: command.timeout });
        return successResponse(command.id, { waited: true, url: page.url() });
    }
    else if (command.timeout) {
        await page.waitForTimeout(command.timeout);
    }
    else {
        // Default: wait for load state
        await page.waitForLoadState('load');
    }
    return successResponse(command.id, { waited: true });
}
async function handleScroll(command, browser) {
    const page = browser.getPage();
    if (command.selector) {
        const element = page.locator(command.selector);
        await element.scrollIntoViewIfNeeded();
        if (command.x !== undefined || command.y !== undefined) {
            await element.evaluate((el, { x, y }) => {
                el.scrollBy(x ?? 0, y ?? 0);
            }, { x: command.x, y: command.y });
        }
    }
    else {
        // Scroll the page
        let deltaX = command.x ?? 0;
        let deltaY = command.y ?? 0;
        if (command.direction) {
            const amount = command.amount ?? 100;
            switch (command.direction) {
                case 'up':
                    deltaY = -amount;
                    break;
                case 'down':
                    deltaY = amount;
                    break;
                case 'left':
                    deltaX = -amount;
                    break;
                case 'right':
                    deltaX = amount;
                    break;
            }
        }
        await page.evaluate(`window.scrollBy(${deltaX}, ${deltaY})`);
    }
    return successResponse(command.id, { scrolled: true });
}
async function handleSelect(command, browser) {
    const locator = browser.getLocator(command.selector);
    const values = Array.isArray(command.values) ? command.values : [command.values];
    try {
        await locator.selectOption(values);
    }
    catch (error) {
        throw toAIFriendlyError(error, command.selector);
    }
    return successResponse(command.id, { selected: values });
}
async function handleHover(command, browser) {
    const locator = browser.getLocator(command.selector);
    try {
        await locator.hover();
    }
    catch (error) {
        throw toAIFriendlyError(error, command.selector);
    }
    return successResponse(command.id, { hovered: true });
}
async function handleContent(command, browser) {
    const page = browser.getPage();
    let html;
    if (command.selector) {
        html = await page.locator(command.selector).innerHTML();
    }
    else {
        html = await page.content();
    }
    return successResponse(command.id, { html });
}
async function handleClose(command, browser) {
    await browser.close();
    return successResponse(command.id, { closed: true });
}
async function handleTabNew(command, browser) {
    const result = await browser.newTab();
    // Navigate to URL if provided (same pattern as handleNavigate)
    if (command.url) {
        const page = browser.getPage();
        await page.goto(command.url, { waitUntil: 'domcontentloaded' });
    }
    return successResponse(command.id, result);
}
async function handleTabList(command, browser) {
    const tabs = await browser.listTabs();
    return successResponse(command.id, {
        tabs,
        active: browser.getActiveIndex(),
    });
}
async function handleTabSwitch(command, browser) {
    const result = await browser.switchTo(command.index);
    const page = browser.getPage();
    return successResponse(command.id, {
        ...result,
        title: await page.title(),
    });
}
async function handleTabClose(command, browser) {
    const result = await browser.closeTab(command.index);
    return successResponse(command.id, result);
}
async function handleWindowNew(command, browser) {
    const result = await browser.newWindow(command.viewport);
    return successResponse(command.id, result);
}
// New handlers for enhanced Playwright parity
async function handleFill(command, browser) {
    const locator = browser.getLocator(command.selector);
    try {
        await locator.fill(command.value);
    }
    catch (error) {
        throw toAIFriendlyError(error, command.selector);
    }
    return successResponse(command.id, { filled: true });
}
async function handleCheck(command, browser) {
    const locator = browser.getLocator(command.selector);
    try {
        await locator.check();
    }
    catch (error) {
        throw toAIFriendlyError(error, command.selector);
    }
    return successResponse(command.id, { checked: true });
}
async function handleUncheck(command, browser) {
    const locator = browser.getLocator(command.selector);
    try {
        await locator.uncheck();
    }
    catch (error) {
        throw toAIFriendlyError(error, command.selector);
    }
    return successResponse(command.id, { unchecked: true });
}
async function handleUpload(command, browser) {
    const locator = browser.getLocator(command.selector);
    const files = Array.isArray(command.files) ? command.files : [command.files];
    try {
        await locator.setInputFiles(files);
    }
    catch (error) {
        throw toAIFriendlyError(error, command.selector);
    }
    return successResponse(command.id, { uploaded: files });
}
async function handleDoubleClick(command, browser) {
    const locator = browser.getLocator(command.selector);
    try {
        await locator.dblclick();
    }
    catch (error) {
        throw toAIFriendlyError(error, command.selector);
    }
    return successResponse(command.id, { clicked: true });
}
async function handleFocus(command, browser) {
    const locator = browser.getLocator(command.selector);
    try {
        await locator.focus();
    }
    catch (error) {
        throw toAIFriendlyError(error, command.selector);
    }
    return successResponse(command.id, { focused: true });
}
async function handleDrag(command, browser) {
    const frame = browser.getFrame();
    await frame.dragAndDrop(command.source, command.target);
    return successResponse(command.id, { dragged: true });
}
async function handleFrame(command, browser) {
    await browser.switchToFrame({
        selector: command.selector,
        name: command.name,
        url: command.url,
    });
    return successResponse(command.id, { switched: true });
}
async function handleMainFrame(command, browser) {
    browser.switchToMainFrame();
    return successResponse(command.id, { switched: true });
}
async function handleGetByRole(command, browser) {
    const page = browser.getPage();
    const locator = page.getByRole(command.role, { name: command.name });
    switch (command.subaction) {
        case 'click':
            await locator.click();
            return successResponse(command.id, { clicked: true });
        case 'fill':
            await locator.fill(command.value ?? '');
            return successResponse(command.id, { filled: true });
        case 'check':
            await locator.check();
            return successResponse(command.id, { checked: true });
        case 'hover':
            await locator.hover();
            return successResponse(command.id, { hovered: true });
    }
}
async function handleGetByText(command, browser) {
    const page = browser.getPage();
    const locator = page.getByText(command.text, { exact: command.exact });
    switch (command.subaction) {
        case 'click':
            await locator.click();
            return successResponse(command.id, { clicked: true });
        case 'hover':
            await locator.hover();
            return successResponse(command.id, { hovered: true });
    }
}
async function handleGetByLabel(command, browser) {
    const page = browser.getPage();
    const locator = page.getByLabel(command.label);
    switch (command.subaction) {
        case 'click':
            await locator.click();
            return successResponse(command.id, { clicked: true });
        case 'fill':
            await locator.fill(command.value ?? '');
            return successResponse(command.id, { filled: true });
        case 'check':
            await locator.check();
            return successResponse(command.id, { checked: true });
    }
}
async function handleGetByPlaceholder(command, browser) {
    const page = browser.getPage();
    const locator = page.getByPlaceholder(command.placeholder);
    switch (command.subaction) {
        case 'click':
            await locator.click();
            return successResponse(command.id, { clicked: true });
        case 'fill':
            await locator.fill(command.value ?? '');
            return successResponse(command.id, { filled: true });
    }
}
async function handleCookiesGet(command, browser) {
    const page = browser.getPage();
    const context = page.context();
    const cookies = await context.cookies(command.urls);
    return successResponse(command.id, { cookies });
}
async function handleCookiesSet(command, browser) {
    const page = browser.getPage();
    const context = page.context();
    // Auto-fill URL for cookies that don't have domain/path/url set
    const pageUrl = page.url();
    const cookies = command.cookies.map((cookie) => {
        if (!cookie.url && !cookie.domain && !cookie.path) {
            return { ...cookie, url: pageUrl };
        }
        return cookie;
    });
    await context.addCookies(cookies);
    return successResponse(command.id, { set: true });
}
async function handleCookiesClear(command, browser) {
    const page = browser.getPage();
    const context = page.context();
    await context.clearCookies();
    return successResponse(command.id, { cleared: true });
}
async function handleStorageGet(command, browser) {
    const page = browser.getPage();
    const storageType = command.type === 'local' ? 'localStorage' : 'sessionStorage';
    if (command.key) {
        const value = await page.evaluate(`${storageType}.getItem(${JSON.stringify(command.key)})`);
        return successResponse(command.id, { key: command.key, value });
    }
    else {
        const data = await page.evaluate(`
      (() => {
        const storage = ${storageType};
        const result = {};
        for (let i = 0; i < storage.length; i++) {
          const key = storage.key(i);
          if (key) result[key] = storage.getItem(key);
        }
        return result;
      })()
    `);
        return successResponse(command.id, { data });
    }
}
async function handleStorageSet(command, browser) {
    const page = browser.getPage();
    const storageType = command.type === 'local' ? 'localStorage' : 'sessionStorage';
    await page.evaluate(`${storageType}.setItem(${JSON.stringify(command.key)}, ${JSON.stringify(command.value)})`);
    return successResponse(command.id, { set: true });
}
async function handleStorageClear(command, browser) {
    const page = browser.getPage();
    const storageType = command.type === 'local' ? 'localStorage' : 'sessionStorage';
    await page.evaluate(`${storageType}.clear()`);
    return successResponse(command.id, { cleared: true });
}
async function handleDialog(command, browser) {
    browser.setDialogHandler(command.response, command.promptText);
    return successResponse(command.id, { handler: 'set', response: command.response });
}
async function handlePdf(command, browser) {
    const page = browser.getPage();
    await page.pdf({
        path: command.path,
        format: command.format ?? 'Letter',
    });
    return successResponse(command.id, { path: command.path });
}
// Network & Request handlers
async function handleRoute(command, browser) {
    await browser.addRoute(command.url, {
        response: command.response,
        abort: command.abort,
    });
    return successResponse(command.id, { routed: command.url });
}
async function handleUnroute(command, browser) {
    await browser.removeRoute(command.url);
    return successResponse(command.id, { unrouted: command.url ?? 'all' });
}
async function handleRequests(command, browser) {
    if (command.clear) {
        browser.clearRequests();
        return successResponse(command.id, { cleared: true });
    }
    // Start tracking if not already
    browser.startRequestTracking();
    const requests = browser.getRequests(command.filter);
    return successResponse(command.id, { requests });
}
async function handleDownload(command, browser) {
    const page = browser.getPage();
    const [download] = await Promise.all([
        page.waitForEvent('download'),
        page.click(command.selector),
    ]);
    await download.saveAs(command.path);
    return successResponse(command.id, {
        path: command.path,
        suggestedFilename: download.suggestedFilename(),
    });
}
async function handleGeolocation(command, browser) {
    await browser.setGeolocation(command.latitude, command.longitude, command.accuracy);
    return successResponse(command.id, {
        latitude: command.latitude,
        longitude: command.longitude,
    });
}
async function handlePermissions(command, browser) {
    await browser.setPermissions(command.permissions, command.grant);
    return successResponse(command.id, {
        permissions: command.permissions,
        granted: command.grant,
    });
}
async function handleViewport(command, browser) {
    await browser.setViewport(command.width, command.height);
    return successResponse(command.id, {
        width: command.width,
        height: command.height,
    });
}
async function handleUserAgent(command, browser) {
    const page = browser.getPage();
    const context = page.context();
    // Note: Can't change user agent after context is created, but we can for new pages
    return successResponse(command.id, {
        note: 'User agent can only be set at launch time. Use device command instead.',
    });
}
async function handleDevice(command, browser) {
    const device = browser.getDevice(command.device);
    if (!device) {
        const available = browser.listDevices().slice(0, 10).join(', ');
        throw new Error(`Unknown device: ${command.device}. Available: ${available}...`);
    }
    // Apply device viewport
    await browser.setViewport(device.viewport.width, device.viewport.height);
    return successResponse(command.id, {
        device: command.device,
        viewport: device.viewport,
        userAgent: device.userAgent,
    });
}
async function handleBack(command, browser) {
    const page = browser.getPage();
    await page.goBack();
    return successResponse(command.id, { url: page.url() });
}
async function handleForward(command, browser) {
    const page = browser.getPage();
    await page.goForward();
    return successResponse(command.id, { url: page.url() });
}
async function handleReload(command, browser) {
    const page = browser.getPage();
    await page.reload();
    return successResponse(command.id, { url: page.url() });
}
async function handleUrl(command, browser) {
    const page = browser.getPage();
    return successResponse(command.id, { url: page.url() });
}
async function handleTitle(command, browser) {
    const page = browser.getPage();
    const title = await page.title();
    return successResponse(command.id, { title });
}
async function handleGetAttribute(command, browser) {
    const locator = browser.getLocator(command.selector);
    const value = await locator.getAttribute(command.attribute);
    return successResponse(command.id, { attribute: command.attribute, value });
}
async function handleGetText(command, browser) {
    const locator = browser.getLocator(command.selector);
    const text = await locator.textContent();
    return successResponse(command.id, { text });
}
async function handleIsVisible(command, browser) {
    const locator = browser.getLocator(command.selector);
    const visible = await locator.isVisible();
    return successResponse(command.id, { visible });
}
async function handleIsEnabled(command, browser) {
    const locator = browser.getLocator(command.selector);
    const enabled = await locator.isEnabled();
    return successResponse(command.id, { enabled });
}
async function handleIsChecked(command, browser) {
    const locator = browser.getLocator(command.selector);
    const checked = await locator.isChecked();
    return successResponse(command.id, { checked });
}
async function handleCount(command, browser) {
    const page = browser.getPage();
    const count = await page.locator(command.selector).count();
    return successResponse(command.id, { count });
}
async function handleGetOptions(command, browser) {
    const page = browser.getPage();
    // If selector provided, get options from that element; otherwise find first open listbox/select
    const selector = command.selector || '[role=listbox], [role=menu], select';
    const locator = page.locator(selector).first();
    // Get all option elements
    const options = await locator.locator('[role=option], option').allTextContents();
    return successResponse(command.id, { options, selector });
}
async function handleBoundingBox(command, browser) {
    const page = browser.getPage();
    const box = await page.locator(command.selector).boundingBox();
    return successResponse(command.id, { box });
}
async function handleStyles(command, browser) {
    const page = browser.getPage();
    // Shared extraction logic as a string to be eval'd in browser context
    const extractStylesScript = `(function(el) {
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return {
      tag: el.tagName.toLowerCase(),
      text: el.innerText?.trim().slice(0, 80) || null,
      box: {
        x: Math.round(r.x),
        y: Math.round(r.y),
        width: Math.round(r.width),
        height: Math.round(r.height),
      },
      styles: {
        fontSize: s.fontSize,
        fontWeight: s.fontWeight,
        fontFamily: s.fontFamily.split(',')[0].trim().replace(/"/g, ''),
        color: s.color,
        backgroundColor: s.backgroundColor,
        borderRadius: s.borderRadius,
        border: s.border !== 'none' && s.borderWidth !== '0px' ? s.border : null,
        boxShadow: s.boxShadow !== 'none' ? s.boxShadow : null,
        padding: s.padding,
      },
    };
  })`;
    // Check if it's a ref - single element
    if (browser.isRef(command.selector)) {
        const locator = browser.getLocator(command.selector);
        const element = (await locator.evaluate((el, script) => {
            const fn = eval(script);
            return fn(el);
        }, extractStylesScript));
        return successResponse(command.id, { elements: [element] });
    }
    // CSS selector - can match multiple elements
    const elements = (await page.$$eval(command.selector, (els, script) => {
        const fn = eval(script);
        return els.map((el) => fn(el));
    }, extractStylesScript));
    return successResponse(command.id, { elements });
}
// Advanced handlers
async function handleVideoStart(command, browser) {
    // Video recording requires context-level setup at launch
    // For now, return a note about this limitation
    return successResponse(command.id, {
        note: 'Video recording must be enabled at browser launch. Use --video flag when starting.',
        path: command.path,
    });
}
async function handleVideoStop(command, browser) {
    const page = browser.getPage();
    const video = page.video();
    if (video) {
        const path = await video.path();
        return successResponse(command.id, { path });
    }
    return successResponse(command.id, { note: 'No video recording active' });
}
async function handleTraceStart(command, browser) {
    await browser.startTracing({
        screenshots: command.screenshots,
        snapshots: command.snapshots,
    });
    return successResponse(command.id, { started: true });
}
async function handleTraceStop(command, browser) {
    await browser.stopTracing(command.path);
    return successResponse(command.id, { path: command.path });
}
async function handleHarStart(command, browser) {
    const page = browser.getPage();
    requestTracker.clear();
    requestTracker.start(page);
    return successResponse(command.id, { started: true });
}
async function handleHarStop(command, browser) {
    const page = browser.getPage();
    requestTracker.stop(page);
    const result = requestTracker.saveHar(command.path);
    return successResponse(command.id, result);
}
// Phase 4: Network throttling
async function handleThrottle(command, browser) {
    const page = browser.getPage();
    
    if (command.preset === 'off') {
        await clearThrottle(page);
        return successResponse(command.id, { throttle: 'disabled' });
    }
    
    let config;
    if (command.preset) {
        config = await setThrottle(page, command.preset);
    } else if (command.download !== undefined || command.upload !== undefined || command.latency !== undefined) {
        config = await setThrottle(page, {
            offline: false,
            downloadThroughput: command.download ?? -1,
            uploadThroughput: command.upload ?? -1,
            latency: command.latency ?? 0,
        });
    } else {
        return successResponse(command.id, {
            presets: Object.keys(THROTTLE_PRESETS),
            current: 'unknown',
        });
    }
    
    return successResponse(command.id, { throttle: 'enabled', config });
}
async function handleNetworkStats(command, browser) {
    const stats = requestTracker.getStats();
    const failed = requestTracker.getFailedRequests();
    return successResponse(command.id, {
        stats,
        failedCount: failed.length,
        failed: failed.slice(0, 10), // First 10 failures
    });
}
// Phase 5: Auth helpers
async function handleTOTP(command, browser) {
    const code = generateTOTPSync(command.secret);
    const remaining = getTOTPTimeRemaining();
    
    if (command.fill) {
        const page = browser.getPage();
        await page.fill(command.fill, code);
        return successResponse(command.id, { code, remaining, filled: command.fill });
    }
    
    return successResponse(command.id, { code, remaining });
}
async function handleDetectLogin(command, browser) {
    const page = browser.getPage();
    const result = await detectLoginForm(page);
    return successResponse(command.id, result);
}
async function handleAutofillLogin(command, browser) {
    const page = browser.getPage();
    const result = await autoFillLogin(page, command.username, command.password);
    
    if (result.filled && command.submit && result.submitSelector) {
        await page.click(result.submitSelector);
        result.submitted = true;
    }
    
    return successResponse(command.id, result);
}
async function handleDetectCaptcha(command, browser) {
    const page = browser.getPage();
    const result = await detectCaptcha(page);
    return successResponse(command.id, result);
}
async function handleWaitCaptcha(command, browser) {
    const page = browser.getPage();
    const timeout = command.timeout || 120000;
    const result = await waitForCaptchaSolved(page, timeout);
    return successResponse(command.id, result);
}
async function handleStateSave(command, browser) {
    await browser.saveStorageState(command.path);
    return successResponse(command.id, { path: command.path });
}
async function handleStateLoad(command, browser) {
    // Storage state is loaded at context creation
    return successResponse(command.id, {
        note: 'Storage state must be loaded at browser launch. Use --state flag.',
        path: command.path,
    });
}
// Phase 3: Session management handlers
async function handleSessionSave(command, browser) {
    const page = browser.getPage();
    const context = browser.contexts[0];
    const result = await saveSession(page, context, command.name, command.description);
    return successResponse(command.id, result);
}
async function handleSessionLoad(command, browser) {
    // Auto-launch browser if not running
    if (!browser.isLaunched()) {
        await browser.launch({});
    }
    const page = browser.getPage();
    const result = await restoreSession(page, command.name);
    return successResponse(command.id, result);
}
async function handleSessionList(command) {
    const sessions = listSessions();
    return successResponse(command.id, { sessions });
}
async function handleSessionDelete(command) {
    const result = deleteSession(command.name);
    return successResponse(command.id, result);
}
async function handleSessionExport(command) {
    const result = exportSession(command.name, command.path);
    return successResponse(command.id, result);
}
async function handleSessionImport(command) {
    const result = importSession(command.path, command.name);
    return successResponse(command.id, result);
}
async function handleConsole(command, browser) {
    if (command.clear) {
        browser.clearConsoleMessages();
        return successResponse(command.id, { cleared: true });
    }
    const messages = browser.getConsoleMessages();
    return successResponse(command.id, { messages });
}
async function handleErrors(command, browser) {
    if (command.clear) {
        browser.clearPageErrors();
        return successResponse(command.id, { cleared: true });
    }
    const errors = browser.getPageErrors();
    return successResponse(command.id, { errors });
}
async function handleKeyboard(command, browser) {
    const page = browser.getPage();
    await page.keyboard.press(command.keys);
    return successResponse(command.id, { pressed: command.keys });
}
async function handleWheel(command, browser) {
    const page = browser.getPage();
    if (command.selector) {
        const element = page.locator(command.selector);
        await element.hover();
    }
    await page.mouse.wheel(command.deltaX ?? 0, command.deltaY ?? 0);
    return successResponse(command.id, { scrolled: true });
}
async function handleTap(command, browser) {
    const page = browser.getPage();
    await page.tap(command.selector);
    return successResponse(command.id, { tapped: true });
}
async function handleClipboard(command, browser) {
    const page = browser.getPage();
    switch (command.operation) {
        case 'copy':
            await page.keyboard.press('Control+c');
            return successResponse(command.id, { copied: true });
        case 'paste':
            await page.keyboard.press('Control+v');
            return successResponse(command.id, { pasted: true });
        case 'read':
            const text = await page.evaluate('navigator.clipboard.readText()');
            return successResponse(command.id, { text });
        default:
            return errorResponse(command.id, 'Unknown clipboard operation');
    }
}
async function handleHighlight(command, browser) {
    const page = browser.getPage();
    await page.locator(command.selector).highlight();
    return successResponse(command.id, { highlighted: true });
}
async function handleClear(command, browser) {
    const page = browser.getPage();
    await page.locator(command.selector).clear();
    return successResponse(command.id, { cleared: true });
}
async function handleSelectAll(command, browser) {
    const page = browser.getPage();
    await page.locator(command.selector).selectText();
    return successResponse(command.id, { selected: true });
}
async function handleInnerText(command, browser) {
    const page = browser.getPage();
    const text = await page.locator(command.selector).innerText();
    return successResponse(command.id, { text });
}
async function handleInnerHtml(command, browser) {
    const page = browser.getPage();
    const html = await page.locator(command.selector).innerHTML();
    return successResponse(command.id, { html });
}
async function handleInputValue(command, browser) {
    const locator = browser.getLocator(command.selector);
    const value = await locator.inputValue();
    return successResponse(command.id, { value });
}
async function handleSetValue(command, browser) {
    const page = browser.getPage();
    await page.locator(command.selector).fill(command.value);
    return successResponse(command.id, { set: true });
}
async function handleDispatch(command, browser) {
    const page = browser.getPage();
    await page.locator(command.selector).dispatchEvent(command.event, command.eventInit);
    return successResponse(command.id, { dispatched: command.event });
}
async function handleEvalHandle(command, browser) {
    const page = browser.getPage();
    const handle = await page.evaluateHandle(command.script);
    const result = await handle.jsonValue().catch(() => 'Handle (non-serializable)');
    return successResponse(command.id, { result });
}
async function handleExpose(command, browser) {
    const page = browser.getPage();
    await page.exposeFunction(command.name, () => {
        // Exposed function - can be extended
        return `Function ${command.name} called`;
    });
    return successResponse(command.id, { exposed: command.name });
}
async function handleAddScript(command, browser) {
    const page = browser.getPage();
    if (command.content) {
        await page.addScriptTag({ content: command.content });
    }
    else if (command.url) {
        await page.addScriptTag({ url: command.url });
    }
    return successResponse(command.id, { added: true });
}
async function handleAddStyle(command, browser) {
    const page = browser.getPage();
    if (command.content) {
        await page.addStyleTag({ content: command.content });
    }
    else if (command.url) {
        await page.addStyleTag({ url: command.url });
    }
    return successResponse(command.id, { added: true });
}
async function handleEmulateMedia(command, browser) {
    const page = browser.getPage();
    await page.emulateMedia({
        media: command.media,
        colorScheme: command.colorScheme,
        reducedMotion: command.reducedMotion,
        forcedColors: command.forcedColors,
    });
    return successResponse(command.id, { emulated: true });
}
async function handleOffline(command, browser) {
    await browser.setOffline(command.offline);
    return successResponse(command.id, { offline: command.offline });
}
async function handleHeaders(command, browser) {
    await browser.setExtraHeaders(command.headers);
    return successResponse(command.id, { set: true });
}
async function handlePause(command, browser) {
    const page = browser.getPage();
    await page.pause();
    return successResponse(command.id, { paused: true });
}
async function handleGetByAltText(command, browser) {
    const page = browser.getPage();
    const locator = page.getByAltText(command.text, { exact: command.exact });
    switch (command.subaction) {
        case 'click':
            await locator.click();
            return successResponse(command.id, { clicked: true });
        case 'hover':
            await locator.hover();
            return successResponse(command.id, { hovered: true });
    }
}
async function handleGetByTitle(command, browser) {
    const page = browser.getPage();
    const locator = page.getByTitle(command.text, { exact: command.exact });
    switch (command.subaction) {
        case 'click':
            await locator.click();
            return successResponse(command.id, { clicked: true });
        case 'hover':
            await locator.hover();
            return successResponse(command.id, { hovered: true });
    }
}
async function handleGetByTestId(command, browser) {
    const page = browser.getPage();
    const locator = page.getByTestId(command.testId);
    switch (command.subaction) {
        case 'click':
            await locator.click();
            return successResponse(command.id, { clicked: true });
        case 'fill':
            await locator.fill(command.value ?? '');
            return successResponse(command.id, { filled: true });
        case 'check':
            await locator.check();
            return successResponse(command.id, { checked: true });
        case 'hover':
            await locator.hover();
            return successResponse(command.id, { hovered: true });
    }
}
async function handleNth(command, browser) {
    const page = browser.getPage();
    const base = page.locator(command.selector);
    const locator = command.index === -1 ? base.last() : base.nth(command.index);
    switch (command.subaction) {
        case 'click':
            await locator.click();
            return successResponse(command.id, { clicked: true });
        case 'fill':
            await locator.fill(command.value ?? '');
            return successResponse(command.id, { filled: true });
        case 'check':
            await locator.check();
            return successResponse(command.id, { checked: true });
        case 'hover':
            await locator.hover();
            return successResponse(command.id, { hovered: true });
        case 'text':
            const text = await locator.textContent();
            return successResponse(command.id, { text });
    }
}
async function handleWaitForUrl(command, browser) {
    const page = browser.getPage();
    await page.waitForURL(command.url, { timeout: command.timeout });
    return successResponse(command.id, { url: page.url() });
}
async function handleWaitForLoadState(command, browser) {
    const page = browser.getPage();
    await page.waitForLoadState(command.state, { timeout: command.timeout });
    return successResponse(command.id, { state: command.state });
}
async function handleSetContent(command, browser) {
    const page = browser.getPage();
    await page.setContent(command.html);
    return successResponse(command.id, { set: true });
}
async function handleTimezone(command, browser) {
    // Timezone must be set at context level before navigation
    // This is a limitation - it sets for the current context
    const page = browser.getPage();
    await page.context().setGeolocation({ latitude: 0, longitude: 0 }); // Trigger context awareness
    return successResponse(command.id, {
        note: 'Timezone must be set at browser launch. Use --timezone flag.',
        timezone: command.timezone,
    });
}
async function handleLocale(command, browser) {
    // Locale must be set at context creation
    return successResponse(command.id, {
        note: 'Locale must be set at browser launch. Use --locale flag.',
        locale: command.locale,
    });
}
async function handleCredentials(command, browser) {
    const context = browser.getPage().context();
    await context.setHTTPCredentials({
        username: command.username,
        password: command.password,
    });
    return successResponse(command.id, { set: true });
}
async function handleMouseMove(command, browser) {
    const page = browser.getPage();
    await page.mouse.move(command.x, command.y);
    return successResponse(command.id, { moved: true, x: command.x, y: command.y });
}
async function handleMouseDown(command, browser) {
    const page = browser.getPage();
    await page.mouse.down({ button: command.button ?? 'left' });
    return successResponse(command.id, { down: true });
}
async function handleMouseUp(command, browser) {
    const page = browser.getPage();
    await page.mouse.up({ button: command.button ?? 'left' });
    return successResponse(command.id, { up: true });
}
async function handleBringToFront(command, browser) {
    const page = browser.getPage();
    await page.bringToFront();
    return successResponse(command.id, { focused: true });
}
async function handleWaitForFunction(command, browser) {
    const page = browser.getPage();
    await page.waitForFunction(command.expression, { timeout: command.timeout });
    return successResponse(command.id, { waited: true });
}
async function handleScrollIntoView(command, browser) {
    const page = browser.getPage();
    await page.locator(command.selector).scrollIntoViewIfNeeded();
    return successResponse(command.id, { scrolled: true });
}
async function handleAddInitScript(command, browser) {
    const context = browser.getPage().context();
    await context.addInitScript(command.script);
    return successResponse(command.id, { added: true });
}
async function handleKeyDown(command, browser) {
    const page = browser.getPage();
    await page.keyboard.down(command.key);
    return successResponse(command.id, { down: true, key: command.key });
}
async function handleKeyUp(command, browser) {
    const page = browser.getPage();
    await page.keyboard.up(command.key);
    return successResponse(command.id, { up: true, key: command.key });
}
async function handleInsertText(command, browser) {
    const page = browser.getPage();
    await page.keyboard.insertText(command.text);
    return successResponse(command.id, { inserted: true });
}
async function handleMultiSelect(command, browser) {
    const page = browser.getPage();
    const selected = await page.locator(command.selector).selectOption(command.values);
    return successResponse(command.id, { selected });
}
async function handleWaitForDownload(command, browser) {
    const page = browser.getPage();
    const download = await page.waitForEvent('download', { timeout: command.timeout });
    let filePath;
    if (command.path) {
        filePath = command.path;
        await download.saveAs(filePath);
    }
    else {
        filePath = (await download.path()) || download.suggestedFilename();
    }
    return successResponse(command.id, {
        path: filePath,
        filename: download.suggestedFilename(),
        url: download.url(),
    });
}
async function handleResponseBody(command, browser) {
    const page = browser.getPage();
    const response = await page.waitForResponse((resp) => resp.url().includes(command.url), {
        timeout: command.timeout,
    });
    const body = await response.text();
    let parsed = body;
    try {
        parsed = JSON.parse(body);
    }
    catch {
        // Keep as string if not JSON
    }
    return successResponse(command.id, {
        url: response.url(),
        status: response.status(),
        body: parsed,
    });
}
// Screencast and input injection handlers
async function handleScreencastStart(command, browser) {
    if (!screencastFrameCallback) {
        throw new Error('Screencast frame callback not set. Start the streaming server first.');
    }
    await browser.startScreencast(screencastFrameCallback, {
        format: command.format,
        quality: command.quality,
        maxWidth: command.maxWidth,
        maxHeight: command.maxHeight,
        everyNthFrame: command.everyNthFrame,
    });
    return successResponse(command.id, {
        started: true,
        format: command.format ?? 'jpeg',
        quality: command.quality ?? 80,
    });
}
async function handleScreencastStop(command, browser) {
    await browser.stopScreencast();
    return successResponse(command.id, { stopped: true });
}
async function handleInputMouse(command, browser) {
    await browser.injectMouseEvent({
        type: command.type,
        x: command.x,
        y: command.y,
        button: command.button,
        clickCount: command.clickCount,
        deltaX: command.deltaX,
        deltaY: command.deltaY,
        modifiers: command.modifiers,
    });
    return successResponse(command.id, { injected: true });
}
async function handleInputKeyboard(command, browser) {
    await browser.injectKeyboardEvent({
        type: command.type,
        key: command.key,
        code: command.code,
        text: command.text,
        modifiers: command.modifiers,
    });
    return successResponse(command.id, { injected: true });
}
async function handleInputTouch(command, browser) {
    await browser.injectTouchEvent({
        type: command.type,
        touchPoints: command.touchPoints,
        modifiers: command.modifiers,
    });
    return successResponse(command.id, { injected: true });
}
// Recording handlers (Playwright native video recording)
async function handleRecordingStart(command, browser) {
    await browser.startRecording(command.path, command.url);
    return successResponse(command.id, {
        started: true,
        path: command.path,
    });
}
async function handleRecordingStop(command, browser) {
    const result = await browser.stopRecording();
    return successResponse(command.id, result);
}
async function handleRecordingRestart(command, browser) {
    const result = await browser.restartRecording(command.path, command.url);
    return successResponse(command.id, {
        started: true,
        path: command.path,
        previousPath: result.previousPath,
        stopped: result.stopped,
    });
}
// Phase 6: Vision handlers
async function handleVisionDescribe(command, browser) {
    const page = browser.getPage();
    const result = await describePage(page, {
        detail: command.detail,
        focus: command.focus,
        fullPage: command.fullPage,
    });
    return successResponse(command.id, result);
}
async function handleVisionFind(command, browser) {
    const page = browser.getPage();
    const result = await findByVisual(page, command.description);
    return successResponse(command.id, result);
}
async function handleVisionClick(command, browser) {
    const page = browser.getPage();
    const result = await clickByVisual(page, command.description);
    return successResponse(command.id, result);
}
async function handleVisionAnalyze(command, browser) {
    const page = browser.getPage();
    const result = await analyzePattern(page, command.pattern, {
        fullPage: command.fullPage,
    });
    return successResponse(command.id, result);
}
async function handleVisionCompare(command, browser) {
    const page = browser.getPage();
    let afterImage;
    if (command.after) {
        afterImage = command.after;
    } else {
        // Capture current page as "after"
        const capture = await captureForVision(page);
        afterImage = capture.base64;
    }
    const result = await compareScreenshots(command.before, afterImage);
    return successResponse(command.id, result);
}
async function handleVisionExplain(command, browser) {
    const page = browser.getPage();
    const result = await explainAction(page, command.action_type, command.target);
    return successResponse(command.id, result);
}
// Phase 7: Agent handlers
async function handleAgentGoal(command, browser) {
    const page = browser.getPage();
    const result = await executeGoal(page, browser, command.goal, {
        maxSteps: command.maxSteps,
        verbose: command.verbose,
    });
    return successResponse(command.id, result);
}
async function handleAgentExplore(command, browser) {
    const page = browser.getPage();
    const result = await explorePage(page, browser, {
        depth: command.depth,
        maxLinks: command.maxLinks,
        sameOrigin: command.sameOrigin,
    });
    return successResponse(command.id, result);
}
async function handleAgentExplain(command, browser) {
    const page = browser.getPage();
    const result = await explainPage(page, browser);
    return successResponse(command.id, result);
}
async function handleAgentRecover(command, browser) {
    const page = browser.getPage();
    // Try to recover from any stuck state
    const result = await attemptRecovery(page, browser, new Error('manual recovery'), []);
    return successResponse(command.id, result);
}
//# sourceMappingURL=actions.js.map