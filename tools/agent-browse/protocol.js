import { z } from 'zod';
// Base schema for all commands
const baseCommandSchema = z.object({
    id: z.string(),
    action: z.string(),
});
// Individual action schemas
const launchSchema = baseCommandSchema.extend({
    action: z.literal('launch'),
    headless: z.boolean().optional(),
    viewport: z
        .object({
        width: z.number().positive(),
        height: z.number().positive(),
    })
        .optional(),
    browser: z.enum(['chromium', 'firefox', 'webkit']).optional(),
    cdpPort: z.number().positive().optional(),
    executablePath: z.string().optional(),
    extensions: z.array(z.string()).optional(),
    headers: z.record(z.string()).optional(),
    proxy: z
        .object({
        server: z.string().min(1),
        bypass: z.string().optional(),
        username: z.string().optional(),
        password: z.string().optional(),
    })
        .optional(),
});
const navigateSchema = baseCommandSchema.extend({
    action: z.literal('navigate'),
    url: z.string().min(1),
    waitUntil: z.enum(['load', 'domcontentloaded', 'networkidle']).optional(),
    headers: z.record(z.string()).optional(),
});
const clickSchema = baseCommandSchema.extend({
    action: z.literal('click'),
    selector: z.string().min(1),
    button: z.enum(['left', 'right', 'middle']).optional(),
    clickCount: z.number().positive().optional(),
    delay: z.number().nonnegative().optional(),
});
const typeSchema = baseCommandSchema.extend({
    action: z.literal('type'),
    selector: z.string().min(1),
    text: z.string(),
    delay: z.number().nonnegative().optional(),
    clear: z.boolean().optional(),
});
const fillSchema = baseCommandSchema.extend({
    action: z.literal('fill'),
    selector: z.string().min(1),
    value: z.string(),
});
const checkSchema = baseCommandSchema.extend({
    action: z.literal('check'),
    selector: z.string().min(1),
});
const uncheckSchema = baseCommandSchema.extend({
    action: z.literal('uncheck'),
    selector: z.string().min(1),
});
const uploadSchema = baseCommandSchema.extend({
    action: z.literal('upload'),
    selector: z.string().min(1),
    files: z.union([z.string(), z.array(z.string())]),
});
const dblclickSchema = baseCommandSchema.extend({
    action: z.literal('dblclick'),
    selector: z.string().min(1),
});
const focusSchema = baseCommandSchema.extend({
    action: z.literal('focus'),
    selector: z.string().min(1),
});
const dragSchema = baseCommandSchema.extend({
    action: z.literal('drag'),
    source: z.string().min(1),
    target: z.string().min(1),
});
const frameSchema = baseCommandSchema.extend({
    action: z.literal('frame'),
    selector: z.string().min(1).optional(),
    name: z.string().optional(),
    url: z.string().optional(),
});
const mainframeSchema = baseCommandSchema.extend({
    action: z.literal('mainframe'),
});
const getByRoleSchema = baseCommandSchema.extend({
    action: z.literal('getbyrole'),
    role: z.string().min(1),
    name: z.string().optional(),
    subaction: z.enum(['click', 'fill', 'check', 'hover']),
    value: z.string().optional(),
});
const getByTextSchema = baseCommandSchema.extend({
    action: z.literal('getbytext'),
    text: z.string().min(1),
    exact: z.boolean().optional(),
    subaction: z.enum(['click', 'hover']),
});
const getByLabelSchema = baseCommandSchema.extend({
    action: z.literal('getbylabel'),
    label: z.string().min(1),
    subaction: z.enum(['click', 'fill', 'check']),
    value: z.string().optional(),
});
const getByPlaceholderSchema = baseCommandSchema.extend({
    action: z.literal('getbyplaceholder'),
    placeholder: z.string().min(1),
    subaction: z.enum(['click', 'fill']),
    value: z.string().optional(),
});
const cookiesGetSchema = baseCommandSchema.extend({
    action: z.literal('cookies_get'),
    urls: z.array(z.string()).optional(),
});
const cookiesSetSchema = baseCommandSchema.extend({
    action: z.literal('cookies_set'),
    cookies: z.array(z.object({
        name: z.string(),
        value: z.string(),
        url: z.string().optional(),
        domain: z.string().optional(),
        path: z.string().optional(),
        expires: z.number().optional(),
        httpOnly: z.boolean().optional(),
        secure: z.boolean().optional(),
        sameSite: z.enum(['Strict', 'Lax', 'None']).optional(),
    })),
});
const cookiesClearSchema = baseCommandSchema.extend({
    action: z.literal('cookies_clear'),
});
const storageGetSchema = baseCommandSchema.extend({
    action: z.literal('storage_get'),
    key: z.string().optional(),
    type: z.enum(['local', 'session']),
});
const storageSetSchema = baseCommandSchema.extend({
    action: z.literal('storage_set'),
    key: z.string().min(1),
    value: z.string(),
    type: z.enum(['local', 'session']),
});
const storageClearSchema = baseCommandSchema.extend({
    action: z.literal('storage_clear'),
    type: z.enum(['local', 'session']),
});
const dialogSchema = baseCommandSchema.extend({
    action: z.literal('dialog'),
    response: z.enum(['accept', 'dismiss']),
    promptText: z.string().optional(),
});
const pdfSchema = baseCommandSchema.extend({
    action: z.literal('pdf'),
    path: z.string().min(1),
    format: z
        .enum(['Letter', 'Legal', 'Tabloid', 'Ledger', 'A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6'])
        .optional(),
});
const routeSchema = baseCommandSchema.extend({
    action: z.literal('route'),
    url: z.string().min(1),
    response: z
        .object({
        status: z.number().optional(),
        body: z.string().optional(),
        contentType: z.string().optional(),
        headers: z.record(z.string()).optional(),
    })
        .optional(),
    abort: z.boolean().optional(),
});
const unrouteSchema = baseCommandSchema.extend({
    action: z.literal('unroute'),
    url: z.string().optional(),
});
const requestsSchema = baseCommandSchema.extend({
    action: z.literal('requests'),
    filter: z.string().optional(),
    clear: z.boolean().optional(),
});
const downloadSchema = baseCommandSchema.extend({
    action: z.literal('download'),
    selector: z.string().min(1),
    path: z.string().min(1),
});
const geolocationSchema = baseCommandSchema.extend({
    action: z.literal('geolocation'),
    latitude: z.number(),
    longitude: z.number(),
    accuracy: z.number().optional(),
});
const permissionsSchema = baseCommandSchema.extend({
    action: z.literal('permissions'),
    permissions: z.array(z.string()),
    grant: z.boolean(),
});
const viewportSchema = baseCommandSchema.extend({
    action: z.literal('viewport'),
    width: z.number().positive(),
    height: z.number().positive(),
});
const userAgentSchema = baseCommandSchema.extend({
    action: z.literal('useragent'),
    userAgent: z.string().min(1),
});
const deviceSchema = baseCommandSchema.extend({
    action: z.literal('device'),
    device: z.string().min(1),
});
const backSchema = baseCommandSchema.extend({
    action: z.literal('back'),
});
const forwardSchema = baseCommandSchema.extend({
    action: z.literal('forward'),
});
const reloadSchema = baseCommandSchema.extend({
    action: z.literal('reload'),
});
const urlSchema = baseCommandSchema.extend({
    action: z.literal('url'),
});
const titleSchema = baseCommandSchema.extend({
    action: z.literal('title'),
});
const getAttributeSchema = baseCommandSchema.extend({
    action: z.literal('getattribute'),
    selector: z.string().min(1),
    attribute: z.string().min(1),
});
const getTextSchema = baseCommandSchema.extend({
    action: z.literal('gettext'),
    selector: z.string().min(1),
});
const isVisibleSchema = baseCommandSchema.extend({
    action: z.literal('isvisible'),
    selector: z.string().min(1),
});
const isEnabledSchema = baseCommandSchema.extend({
    action: z.literal('isenabled'),
    selector: z.string().min(1),
});
const isCheckedSchema = baseCommandSchema.extend({
    action: z.literal('ischecked'),
    selector: z.string().min(1),
});
const countSchema = baseCommandSchema.extend({
    action: z.literal('count'),
    selector: z.string().min(1),
});
const boundingBoxSchema = baseCommandSchema.extend({
    action: z.literal('boundingbox'),
    selector: z.string().min(1),
});
const stylesSchema = baseCommandSchema.extend({
    action: z.literal('styles'),
    selector: z.string().min(1),
});
const videoStartSchema = baseCommandSchema.extend({
    action: z.literal('video_start'),
    path: z.string().min(1),
});
const videoStopSchema = baseCommandSchema.extend({
    action: z.literal('video_stop'),
});
// Recording schemas (Playwright native video recording)
const recordingStartSchema = baseCommandSchema.extend({
    action: z.literal('recording_start'),
    path: z.string().min(1),
    url: z.string().min(1).optional(),
});
const recordingStopSchema = baseCommandSchema.extend({
    action: z.literal('recording_stop'),
});
const recordingRestartSchema = baseCommandSchema.extend({
    action: z.literal('recording_restart'),
    path: z.string().min(1),
    url: z.string().min(1).optional(),
});
const traceStartSchema = baseCommandSchema.extend({
    action: z.literal('trace_start'),
    screenshots: z.boolean().optional(),
    snapshots: z.boolean().optional(),
});
const traceStopSchema = baseCommandSchema.extend({
    action: z.literal('trace_stop'),
    path: z.string().min(1),
});
const harStartSchema = baseCommandSchema.extend({
    action: z.literal('har_start'),
});
const harStopSchema = baseCommandSchema.extend({
    action: z.literal('har_stop'),
    path: z.string().min(1),
});
// Phase 4: Network intelligence
const throttleSchema = baseCommandSchema.extend({
    action: z.literal('throttle'),
    preset: z.string().optional(), // 'offline', 'slow-3g', '3g', '4g', 'fast', or 'off'
    download: z.number().optional(), // Custom: bytes per second
    upload: z.number().optional(),
    latency: z.number().optional(), // ms
});
const networkStatsSchema = baseCommandSchema.extend({
    action: z.literal('network_stats'),
});
// Phase 5: Auth helpers
const totpSchema = baseCommandSchema.extend({
    action: z.literal('totp'),
    secret: z.string().min(1),
    fill: z.string().optional(), // selector to fill
});
const detectLoginSchema = baseCommandSchema.extend({
    action: z.literal('detect_login'),
});
const autofillLoginSchema = baseCommandSchema.extend({
    action: z.literal('autofill_login'),
    username: z.string().min(1),
    password: z.string().min(1),
    submit: z.boolean().optional(),
});
const detectCaptchaSchema = baseCommandSchema.extend({
    action: z.literal('detect_captcha'),
});
const waitCaptchaSchema = baseCommandSchema.extend({
    action: z.literal('wait_captcha'),
    timeout: z.number().optional(),
});
// Phase 6: Vision integration
const visionDescribeSchema = baseCommandSchema.extend({
    action: z.literal('vision_describe'),
    detail: z.enum(['low', 'medium', 'high']).optional(),
    focus: z.string().optional(),
    fullPage: z.boolean().optional(),
});
const visionFindSchema = baseCommandSchema.extend({
    action: z.literal('vision_find'),
    description: z.string().min(1),
});
const visionClickSchema = baseCommandSchema.extend({
    action: z.literal('vision_click'),
    description: z.string().min(1),
});
const visionAnalyzeSchema = baseCommandSchema.extend({
    action: z.literal('vision_analyze'),
    pattern: z.string().min(1), // errors, forms, navigation, products, login, or custom
    fullPage: z.boolean().optional(),
});
const visionCompareSchema = baseCommandSchema.extend({
    action: z.literal('vision_compare'),
    before: z.string().min(1), // base64 or path
    after: z.string().min(1).optional(), // if not provided, use current page
});
const visionExplainSchema = baseCommandSchema.extend({
    action: z.literal('vision_explain'),
    action_type: z.string().min(1), // click, fill, etc.
    target: z.string().min(1), // what to act on
});
// Phase 7: AI agent helpers
const agentGoalSchema = baseCommandSchema.extend({
    action: z.literal('agent_goal'),
    goal: z.string().min(1),
    maxSteps: z.number().positive().optional(),
    verbose: z.boolean().optional(),
});
const agentExploreSchema = baseCommandSchema.extend({
    action: z.literal('agent_explore'),
    depth: z.number().nonnegative().optional(),
    maxLinks: z.number().positive().optional(),
    sameOrigin: z.boolean().optional(),
});
const agentExplainSchema = baseCommandSchema.extend({
    action: z.literal('agent_explain'),
});
const agentRecoverSchema = baseCommandSchema.extend({
    action: z.literal('agent_recover'),
});
const stateSaveSchema = baseCommandSchema.extend({
    action: z.literal('state_save'),
    path: z.string().min(1),
});
const stateLoadSchema = baseCommandSchema.extend({
    action: z.literal('state_load'),
    path: z.string().min(1),
});
// Phase 3: Session management
const sessionSaveSchema = baseCommandSchema.extend({
    action: z.literal('session_save'),
    name: z.string().min(1),
    description: z.string().optional(),
});
const sessionLoadSchema = baseCommandSchema.extend({
    action: z.literal('session_load'),
    name: z.string().min(1),
});
const sessionListSchema = baseCommandSchema.extend({
    action: z.literal('session_list'),
});
const sessionDeleteSchema = baseCommandSchema.extend({
    action: z.literal('session_delete'),
    name: z.string().min(1),
});
const sessionExportSchema = baseCommandSchema.extend({
    action: z.literal('session_export'),
    name: z.string().min(1),
    path: z.string().min(1),
});
const sessionImportSchema = baseCommandSchema.extend({
    action: z.literal('session_import'),
    path: z.string().min(1),
    name: z.string().optional(),
});
const consoleSchema = baseCommandSchema.extend({
    action: z.literal('console'),
    clear: z.boolean().optional(),
});
const errorsSchema = baseCommandSchema.extend({
    action: z.literal('errors'),
    clear: z.boolean().optional(),
});
const keyboardSchema = baseCommandSchema.extend({
    action: z.literal('keyboard'),
    keys: z.string().min(1),
});
const wheelSchema = baseCommandSchema.extend({
    action: z.literal('wheel'),
    deltaX: z.number().optional(),
    deltaY: z.number().optional(),
    selector: z.string().optional(),
});
const tapSchema = baseCommandSchema.extend({
    action: z.literal('tap'),
    selector: z.string().min(1),
});
const clipboardSchema = baseCommandSchema.extend({
    action: z.literal('clipboard'),
    operation: z.enum(['copy', 'paste', 'read']),
    text: z.string().optional(),
});
const highlightSchema = baseCommandSchema.extend({
    action: z.literal('highlight'),
    selector: z.string().min(1),
});
const clearSchema = baseCommandSchema.extend({
    action: z.literal('clear'),
    selector: z.string().min(1),
});
const selectAllSchema = baseCommandSchema.extend({
    action: z.literal('selectall'),
    selector: z.string().min(1),
});
const innerTextSchema = baseCommandSchema.extend({
    action: z.literal('innertext'),
    selector: z.string().min(1),
});
const innerHtmlSchema = baseCommandSchema.extend({
    action: z.literal('innerhtml'),
    selector: z.string().min(1),
});
const inputValueSchema = baseCommandSchema.extend({
    action: z.literal('inputvalue'),
    selector: z.string().min(1),
});
const setValueSchema = baseCommandSchema.extend({
    action: z.literal('setvalue'),
    selector: z.string().min(1),
    value: z.string(),
});
const dispatchSchema = baseCommandSchema.extend({
    action: z.literal('dispatch'),
    selector: z.string().min(1),
    event: z.string().min(1),
    eventInit: z.record(z.unknown()).optional(),
});
const evalHandleSchema = baseCommandSchema.extend({
    action: z.literal('evalhandle'),
    script: z.string().min(1),
});
const exposeSchema = baseCommandSchema.extend({
    action: z.literal('expose'),
    name: z.string().min(1),
});
const addScriptSchema = baseCommandSchema.extend({
    action: z.literal('addscript'),
    content: z.string().optional(),
    url: z.string().optional(),
});
const addStyleSchema = baseCommandSchema.extend({
    action: z.literal('addstyle'),
    content: z.string().optional(),
    url: z.string().optional(),
});
const emulateMediaSchema = baseCommandSchema.extend({
    action: z.literal('emulatemedia'),
    media: z.enum(['screen', 'print']).nullable().optional(),
    colorScheme: z.enum(['light', 'dark', 'no-preference']).nullable().optional(),
    reducedMotion: z.enum(['reduce', 'no-preference']).nullable().optional(),
    forcedColors: z.enum(['active', 'none']).nullable().optional(),
});
const offlineSchema = baseCommandSchema.extend({
    action: z.literal('offline'),
    offline: z.boolean(),
});
const headersSchema = baseCommandSchema.extend({
    action: z.literal('headers'),
    headers: z.record(z.string()),
});
const pauseSchema = baseCommandSchema.extend({
    action: z.literal('pause'),
});
const getByAltTextSchema = baseCommandSchema.extend({
    action: z.literal('getbyalttext'),
    text: z.string().min(1),
    exact: z.boolean().optional(),
    subaction: z.enum(['click', 'hover']),
});
const getByTitleSchema = baseCommandSchema.extend({
    action: z.literal('getbytitle'),
    text: z.string().min(1),
    exact: z.boolean().optional(),
    subaction: z.enum(['click', 'hover']),
});
const getByTestIdSchema = baseCommandSchema.extend({
    action: z.literal('getbytestid'),
    testId: z.string().min(1),
    subaction: z.enum(['click', 'fill', 'check', 'hover']),
    value: z.string().optional(),
});
const nthSchema = baseCommandSchema.extend({
    action: z.literal('nth'),
    selector: z.string().min(1),
    index: z.number(),
    subaction: z.enum(['click', 'fill', 'check', 'hover', 'text']),
    value: z.string().optional(),
});
const waitForUrlSchema = baseCommandSchema.extend({
    action: z.literal('waitforurl'),
    url: z.string().min(1),
    timeout: z.number().positive().optional(),
});
const waitForLoadStateSchema = baseCommandSchema.extend({
    action: z.literal('waitforloadstate'),
    state: z.enum(['load', 'domcontentloaded', 'networkidle']),
    timeout: z.number().positive().optional(),
});
const setContentSchema = baseCommandSchema.extend({
    action: z.literal('setcontent'),
    html: z.string(),
});
const timezoneSchema = baseCommandSchema.extend({
    action: z.literal('timezone'),
    timezone: z.string().min(1),
});
const localeSchema = baseCommandSchema.extend({
    action: z.literal('locale'),
    locale: z.string().min(1),
});
const credentialsSchema = baseCommandSchema.extend({
    action: z.literal('credentials'),
    username: z.string(),
    password: z.string(),
});
const mouseMoveSchema = baseCommandSchema.extend({
    action: z.literal('mousemove'),
    x: z.number(),
    y: z.number(),
});
const mouseDownSchema = baseCommandSchema.extend({
    action: z.literal('mousedown'),
    button: z.enum(['left', 'right', 'middle']).optional(),
});
const mouseUpSchema = baseCommandSchema.extend({
    action: z.literal('mouseup'),
    button: z.enum(['left', 'right', 'middle']).optional(),
});
const bringToFrontSchema = baseCommandSchema.extend({
    action: z.literal('bringtofront'),
});
const waitForFunctionSchema = baseCommandSchema.extend({
    action: z.literal('waitforfunction'),
    expression: z.string().min(1),
    timeout: z.number().positive().optional(),
});
const scrollIntoViewSchema = baseCommandSchema.extend({
    action: z.literal('scrollintoview'),
    selector: z.string().min(1),
});
const addInitScriptSchema = baseCommandSchema.extend({
    action: z.literal('addinitscript'),
    script: z.string().min(1),
});
const keyDownSchema = baseCommandSchema.extend({
    action: z.literal('keydown'),
    key: z.string().min(1),
});
const keyUpSchema = baseCommandSchema.extend({
    action: z.literal('keyup'),
    key: z.string().min(1),
});
const insertTextSchema = baseCommandSchema.extend({
    action: z.literal('inserttext'),
    text: z.string(),
});
const multiSelectSchema = baseCommandSchema.extend({
    action: z.literal('multiselect'),
    selector: z.string().min(1),
    values: z.array(z.string()),
});
const waitForDownloadSchema = baseCommandSchema.extend({
    action: z.literal('waitfordownload'),
    path: z.string().optional(),
    timeout: z.number().positive().optional(),
});
const responseBodySchema = baseCommandSchema.extend({
    action: z.literal('responsebody'),
    url: z.string().min(1),
    timeout: z.number().positive().optional(),
});
// Screencast schemas for streaming browser viewport
const screencastStartSchema = baseCommandSchema.extend({
    action: z.literal('screencast_start'),
    format: z.enum(['jpeg', 'png']).optional(),
    quality: z.number().min(0).max(100).optional(),
    maxWidth: z.number().positive().optional(),
    maxHeight: z.number().positive().optional(),
    everyNthFrame: z.number().positive().optional(),
});
const screencastStopSchema = baseCommandSchema.extend({
    action: z.literal('screencast_stop'),
});
// Input injection schemas for pair browsing
const inputMouseSchema = baseCommandSchema.extend({
    action: z.literal('input_mouse'),
    type: z.enum(['mousePressed', 'mouseReleased', 'mouseMoved', 'mouseWheel']),
    x: z.number(),
    y: z.number(),
    button: z.enum(['left', 'right', 'middle', 'none']).optional(),
    clickCount: z.number().positive().optional(),
    deltaX: z.number().optional(),
    deltaY: z.number().optional(),
    modifiers: z.number().optional(),
});
const inputKeyboardSchema = baseCommandSchema.extend({
    action: z.literal('input_keyboard'),
    type: z.enum(['keyDown', 'keyUp', 'char']),
    key: z.string().optional(),
    code: z.string().optional(),
    text: z.string().optional(),
    modifiers: z.number().optional(),
});
const inputTouchSchema = baseCommandSchema.extend({
    action: z.literal('input_touch'),
    type: z.enum(['touchStart', 'touchEnd', 'touchMove', 'touchCancel']),
    touchPoints: z.array(z.object({
        x: z.number(),
        y: z.number(),
        id: z.number().optional(),
    })),
    modifiers: z.number().optional(),
});
const pressSchema = baseCommandSchema.extend({
    action: z.literal('press'),
    key: z.string().min(1),
    selector: z.string().min(1).optional(),
});
const screenshotSchema = baseCommandSchema.extend({
    action: z.literal('screenshot'),
    path: z.string().nullable().optional(),
    fullPage: z.boolean().optional(),
    selector: z.string().min(1).optional(),
    format: z.enum(['png', 'jpeg']).optional(),
    quality: z.number().min(0).max(100).optional(),
});
const snapshotSchema = baseCommandSchema.extend({
    action: z.literal('snapshot'),
    interactive: z.boolean().optional(),
    maxDepth: z.number().nonnegative().optional(),
    compact: z.boolean().optional(),
    selector: z.string().optional(),
    // Phase 2 enhancements
    format: z.enum(['tree', 'json', 'csv', 'markdown']).optional(),
    withBoxes: z.boolean().optional(),
});
const evaluateSchema = baseCommandSchema.extend({
    action: z.literal('evaluate'),
    script: z.string().min(1),
    args: z.array(z.unknown()).optional(),
});
const waitSchema = baseCommandSchema.extend({
    action: z.literal('wait'),
    selector: z.string().min(1).optional(),
    timeout: z.number().positive().optional(),
    state: z.enum(['attached', 'detached', 'visible', 'hidden']).optional(),
});
const scrollSchema = baseCommandSchema.extend({
    action: z.literal('scroll'),
    selector: z.string().min(1).optional(),
    x: z.number().optional(),
    y: z.number().optional(),
    direction: z.enum(['up', 'down', 'left', 'right']).optional(),
    amount: z.number().positive().optional(),
});
const selectSchema = baseCommandSchema.extend({
    action: z.literal('select'),
    selector: z.string().min(1),
    values: z.union([z.string(), z.array(z.string())]),
});
const hoverSchema = baseCommandSchema.extend({
    action: z.literal('hover'),
    selector: z.string().min(1),
});
const contentSchema = baseCommandSchema.extend({
    action: z.literal('content'),
    selector: z.string().min(1).optional(),
});
const closeSchema = baseCommandSchema.extend({
    action: z.literal('close'),
});
// Tab/Window schemas
const tabNewSchema = baseCommandSchema.extend({
    action: z.literal('tab_new'),
    url: z.string().min(1).optional(),
});
const tabListSchema = baseCommandSchema.extend({
    action: z.literal('tab_list'),
});
const tabSwitchSchema = baseCommandSchema.extend({
    action: z.literal('tab_switch'),
    index: z.number().nonnegative(),
});
const tabCloseSchema = baseCommandSchema.extend({
    action: z.literal('tab_close'),
    index: z.number().nonnegative().optional(),
});
const windowNewSchema = baseCommandSchema.extend({
    action: z.literal('window_new'),
    viewport: z
        .object({
        width: z.number().positive(),
        height: z.number().positive(),
    })
        .optional(),
});
// Union schema for all commands
const commandSchema = z.discriminatedUnion('action', [
    launchSchema,
    navigateSchema,
    clickSchema,
    typeSchema,
    fillSchema,
    checkSchema,
    uncheckSchema,
    uploadSchema,
    dblclickSchema,
    focusSchema,
    dragSchema,
    frameSchema,
    mainframeSchema,
    getByRoleSchema,
    getByTextSchema,
    getByLabelSchema,
    getByPlaceholderSchema,
    pressSchema,
    screenshotSchema,
    snapshotSchema,
    evaluateSchema,
    waitSchema,
    scrollSchema,
    selectSchema,
    hoverSchema,
    contentSchema,
    closeSchema,
    tabNewSchema,
    tabListSchema,
    tabSwitchSchema,
    tabCloseSchema,
    windowNewSchema,
    cookiesGetSchema,
    cookiesSetSchema,
    cookiesClearSchema,
    storageGetSchema,
    storageSetSchema,
    storageClearSchema,
    dialogSchema,
    pdfSchema,
    routeSchema,
    unrouteSchema,
    requestsSchema,
    downloadSchema,
    geolocationSchema,
    permissionsSchema,
    viewportSchema,
    userAgentSchema,
    deviceSchema,
    backSchema,
    forwardSchema,
    reloadSchema,
    urlSchema,
    titleSchema,
    getAttributeSchema,
    getTextSchema,
    isVisibleSchema,
    isEnabledSchema,
    isCheckedSchema,
    countSchema,
    boundingBoxSchema,
    stylesSchema,
    videoStartSchema,
    videoStopSchema,
    recordingStartSchema,
    recordingStopSchema,
    recordingRestartSchema,
    traceStartSchema,
    traceStopSchema,
    harStartSchema,
    harStopSchema,
    throttleSchema,
    networkStatsSchema,
    totpSchema,
    detectLoginSchema,
    autofillLoginSchema,
    detectCaptchaSchema,
    waitCaptchaSchema,
    stateSaveSchema,
    stateLoadSchema,
    sessionSaveSchema,
    sessionLoadSchema,
    sessionListSchema,
    sessionDeleteSchema,
    sessionExportSchema,
    sessionImportSchema,
    consoleSchema,
    errorsSchema,
    keyboardSchema,
    wheelSchema,
    tapSchema,
    clipboardSchema,
    highlightSchema,
    clearSchema,
    selectAllSchema,
    innerTextSchema,
    innerHtmlSchema,
    inputValueSchema,
    setValueSchema,
    dispatchSchema,
    evalHandleSchema,
    exposeSchema,
    addScriptSchema,
    addStyleSchema,
    emulateMediaSchema,
    offlineSchema,
    headersSchema,
    pauseSchema,
    getByAltTextSchema,
    getByTitleSchema,
    getByTestIdSchema,
    nthSchema,
    waitForUrlSchema,
    waitForLoadStateSchema,
    setContentSchema,
    timezoneSchema,
    localeSchema,
    credentialsSchema,
    mouseMoveSchema,
    mouseDownSchema,
    mouseUpSchema,
    bringToFrontSchema,
    waitForFunctionSchema,
    scrollIntoViewSchema,
    addInitScriptSchema,
    keyDownSchema,
    keyUpSchema,
    insertTextSchema,
    multiSelectSchema,
    waitForDownloadSchema,
    responseBodySchema,
    screencastStartSchema,
    screencastStopSchema,
    inputMouseSchema,
    inputKeyboardSchema,
    inputTouchSchema,
    // Phase 6: Vision
    visionDescribeSchema,
    visionFindSchema,
    visionClickSchema,
    visionAnalyzeSchema,
    visionCompareSchema,
    visionExplainSchema,
    // Phase 7: AI Agent
    agentGoalSchema,
    agentExploreSchema,
    agentExplainSchema,
    agentRecoverSchema,
]);
/**
 * Parse a JSON string into a validated command
 */
export function parseCommand(input) {
    // First, try to parse JSON
    let json;
    try {
        json = JSON.parse(input);
    }
    catch {
        return { success: false, error: 'Invalid JSON' };
    }
    // Extract id for error responses if possible
    const id = typeof json === 'object' && json !== null && 'id' in json
        ? String(json.id)
        : undefined;
    // Validate against schema
    const result = commandSchema.safeParse(json);
    if (!result.success) {
        const errors = result.error.errors.map((e) => `${e.path.join('.')}: ${e.message}`).join(', ');
        return { success: false, error: `Validation error: ${errors}`, id };
    }
    return { success: true, command: result.data };
}
/**
 * Create a success response
 */
export function successResponse(id, data) {
    return { id, success: true, data };
}
/**
 * Create an error response
 */
export function errorResponse(id, error) {
    return { id, success: false, error };
}
/**
 * Serialize a response to JSON string
 */
export function serializeResponse(response) {
    return JSON.stringify(response);
}
//# sourceMappingURL=protocol.js.map