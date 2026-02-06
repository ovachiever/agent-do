import { z } from 'zod';

// Base schema for all commands
const baseCommandSchema = z.object({
    id: z.string(),
    action: z.string(),
});

// Capture: start capturing network traffic
const captureStartSchema = baseCommandSchema.extend({
    action: z.literal('capture_start'),
    url: z.string().min(1),
    headless: z.boolean().optional(),
});

// Capture: stop and generate skill
const captureStopSchema = baseCommandSchema.extend({
    action: z.literal('capture_stop'),
    name: z.string().min(1),
});

// Capture: show status
const captureStatusSchema = baseCommandSchema.extend({
    action: z.literal('capture_status'),
});

// Close browser + daemon
const closeSchema = baseCommandSchema.extend({
    action: z.literal('close'),
});

// Union schema for all daemon commands
const commandSchema = z.discriminatedUnion('action', [
    captureStartSchema,
    captureStopSchema,
    captureStatusSchema,
    closeSchema,
]);

/**
 * Parse a JSON string into a validated command
 */
export function parseCommand(input) {
    let json;
    try {
        json = JSON.parse(input);
    } catch {
        return { success: false, error: 'Invalid JSON' };
    }

    const id = typeof json === 'object' && json !== null && 'id' in json
        ? String(json.id)
        : undefined;

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
    return { id, success: true, result: data };
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
