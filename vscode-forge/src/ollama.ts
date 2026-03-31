import * as http from 'http';
import * as https from 'https';

export interface OllamaGenerateOptions {
    model: string;
    prompt: string;
    suffix?: string;
    system?: string;
    stream?: boolean;
    options?: {
        num_predict?: number;
        temperature?: number;
        top_p?: number;
        stop?: string[];
    };
}

export interface OllamaChatMessage {
    role: string;
    content: string;
}

export interface OllamaChatOptions {
    model: string;
    messages: OllamaChatMessage[];
    stream?: boolean;
    options?: {
        num_predict?: number;
        temperature?: number;
        top_p?: number;
        stop?: string[];
    };
}

export interface OllamaResponse {
    response: string;
    done: boolean;
    model: string;
    total_duration?: number;
    eval_count?: number;
}

export interface OllamaChatChunk {
    message?: { role: string; content: string };
    done: boolean;
}

export interface OllamaModelInfo {
    name: string;
    size: number;
    modified_at?: string;
    digest?: string;
}

export class OllamaClient {
    constructor(private baseUrl: string = 'http://localhost:11434') {}

    async listModels(): Promise<OllamaModelInfo[]> {
        return new Promise((resolve, reject) => {
            const url = new URL(`${this.baseUrl}/api/tags`);
            const client = url.protocol === 'https:' ? https : http;

            const req = client.request(url, { method: 'GET', timeout: 10000 }, (res) => {
                let data = '';
                res.on('data', (chunk) => { data += chunk; });
                res.on('end', () => {
                    try {
                        const parsed = JSON.parse(data);
                        const models: OllamaModelInfo[] = (parsed.models || []).map((m: any) => ({
                            name: m.name || '',
                            size: m.size || 0,
                            modified_at: m.modified_at,
                            digest: m.digest,
                        }));
                        resolve(models);
                    } catch {
                        reject(new Error(`Invalid response from Ollama /api/tags: ${data.slice(0, 200)}`));
                    }
                });
            });

            req.on('error', (err) => reject(err));
            req.on('timeout', () => { req.destroy(); reject(new Error('Ollama /api/tags request timed out')); });
            req.end();
        });
    }

    async generate(opts: OllamaGenerateOptions): Promise<string> {
        const payload: Record<string, any> = {
            model: opts.model,
            prompt: opts.prompt,
            stream: false,
            options: opts.options || {},
        };
        if (opts.suffix) { payload.suffix = opts.suffix; }
        if (opts.system) { payload.system = opts.system; }
        const body = JSON.stringify(payload);

        return new Promise((resolve, reject) => {
            const url = new URL(`${this.baseUrl}/api/generate`);
            const client = url.protocol === 'https:' ? https : http;

            const req = client.request(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(body),
                },
                timeout: 30000,
            }, (res) => {
                let data = '';
                res.on('data', (chunk) => { data += chunk; });
                res.on('end', () => {
                    try {
                        const parsed: OllamaResponse = JSON.parse(data);
                        resolve(parsed.response || '');
                    } catch {
                        reject(new Error(`Invalid response from Ollama: ${data.slice(0, 200)}`));
                    }
                });
            });

            req.on('error', (err) => reject(err));
            req.on('timeout', () => { req.destroy(); reject(new Error('Ollama request timed out')); });
            req.write(body);
            req.end();
        });
    }

    async streamGenerate(opts: OllamaGenerateOptions, onToken: (token: string) => void): Promise<string> {
        const body = JSON.stringify({
            model: opts.model,
            prompt: opts.prompt,
            system: opts.system || '',
            stream: true,
            options: opts.options || {},
        });

        return new Promise((resolve, reject) => {
            const url = new URL(`${this.baseUrl}/api/generate`);
            const client = url.protocol === 'https:' ? https : http;
            let full = '';

            const req = client.request(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(body),
                },
                timeout: 60000,
            }, (res) => {
                res.on('data', (chunk) => {
                    const lines = chunk.toString().split('\n').filter((l: string) => l.trim());
                    for (const line of lines) {
                        try {
                            const parsed: OllamaResponse = JSON.parse(line);
                            if (parsed.response) {
                                full += parsed.response;
                                onToken(parsed.response);
                            }
                        } catch { /* partial JSON, skip */ }
                    }
                });
                res.on('end', () => resolve(full));
            });

            req.on('error', (err) => reject(err));
            req.on('timeout', () => { req.destroy(); reject(new Error('Ollama request timed out')); });
            req.write(body);
            req.end();
        });
    }

    async streamChat(opts: OllamaChatOptions, onToken: (token: string) => void): Promise<string> {
        const body = JSON.stringify({
            model: opts.model,
            messages: opts.messages,
            stream: true,
            options: opts.options || {},
        });

        return new Promise((resolve, reject) => {
            const url = new URL(`${this.baseUrl}/api/chat`);
            const client = url.protocol === 'https:' ? https : http;
            let full = '';
            let buffer = '';

            const req = client.request(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(body),
                },
                timeout: 120000,
            }, (res) => {
                res.on('data', (chunk) => {
                    buffer += chunk.toString();
                    const lines = buffer.split('\n');
                    // Keep last partial line in buffer
                    buffer = lines.pop() || '';
                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (!trimmed) { continue; }
                        try {
                            const parsed: OllamaChatChunk = JSON.parse(trimmed);
                            if (parsed.message && parsed.message.content) {
                                full += parsed.message.content;
                                onToken(parsed.message.content);
                            }
                        } catch { /* partial JSON, skip */ }
                    }
                });
                res.on('end', () => {
                    // Process any remaining data in buffer
                    if (buffer.trim()) {
                        try {
                            const parsed: OllamaChatChunk = JSON.parse(buffer.trim());
                            if (parsed.message && parsed.message.content) {
                                full += parsed.message.content;
                                onToken(parsed.message.content);
                            }
                        } catch { /* ignore */ }
                    }
                    resolve(full);
                });
            });

            req.on('error', (err) => reject(err));
            req.on('timeout', () => { req.destroy(); reject(new Error('Ollama chat request timed out')); });
            req.write(body);
            req.end();
        });
    }

    async isAvailable(): Promise<boolean> {
        return new Promise((resolve) => {
            const url = new URL(this.baseUrl);
            const client = url.protocol === 'https:' ? https : http;

            const req = client.request(url, { method: 'GET', timeout: 3000 }, (res) => {
                resolve(res.statusCode === 200);
            });
            req.on('error', () => resolve(false));
            req.on('timeout', () => { req.destroy(); resolve(false); });
            req.end();
        });
    }
}
