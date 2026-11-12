import { exportSession } from './session.js';
import { verifySession } from './session-verify.js';

// File exports need no daemon or browser. Verification owns and closes its
// headless browser; neither command disturbs another agent's active session.
try {
    const [command, name, argument] = process.argv.slice(2);
    let result;
    if (command === 'export' && name && argument) {
        result = { success: true, ...exportSession(name, argument) };
    } else if (command === 'verify' && name) {
        const verification = await verifySession(name, argument || 'youtube');
        result = { success: verification.signedIn === true, ...verification };
    } else {
        throw new Error('[SESSION_USAGE] Expected export <name> <file> or verify <name> [youtube].');
    }
    console.log(JSON.stringify(result));
    if (!result.success) process.exitCode = 2;
} catch (error) {
    const code = /^\[([A-Z_]+)\]/.exec(error.message)?.[1] || 'SESSION_REFUSED';
    console.error(JSON.stringify({ success: false, code, error: code === 'SESSION_REFUSED' ? 'Unable to read or write the saved session.' : error.message }));
    process.exitCode = 2;
}
