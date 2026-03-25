import * as vscode from 'vscode';
import { OllamaClient } from './ollama';

// Models with native fill-in-middle support in Ollama.
// When matched, we use Ollama's `suffix` parameter and it handles
// the model-specific FIM tokens automatically.
const FIM_MODEL_PATTERNS = [
    'qwen2.5-coder', 'qwen2-coder',
    'codellama', 'code-llama',
    'starcoder', 'starcoder2',
    'deepseek-coder',
    'codegemma',
    'codestral',
    'yi-coder',
    'stable-code',
];

function supportsFIM(model: string): boolean {
    const base = model.split(':')[0].toLowerCase();
    return FIM_MODEL_PATTERNS.some(p => base.includes(p));
}

export class ForgeCompletionProvider implements vscode.InlineCompletionItemProvider {
    private debounceTimer: NodeJS.Timeout | undefined;
    private lastCancel: vscode.CancellationTokenSource | undefined;

    constructor() {}

    async provideInlineCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position,
        context: vscode.InlineCompletionContext,
        token: vscode.CancellationToken
    ): Promise<vscode.InlineCompletionItem[] | undefined> {
        const config = vscode.workspace.getConfiguration('forge');
        if (!config.get<boolean>('completionEnabled', true)) {
            return undefined;
        }

        // Read URL fresh from config on every request so config changes propagate
        const url = config.get<string>('ollamaUrl', 'http://localhost:11434');
        const client = new OllamaClient(url);

        // Cancel any previous pending request
        if (this.lastCancel) {
            this.lastCancel.cancel();
        }
        this.lastCancel = new vscode.CancellationTokenSource();

        // Debounce
        const delay = config.get<number>('completionDelay', 500);
        await new Promise<void>((resolve) => {
            if (this.debounceTimer) { clearTimeout(this.debounceTimer); }
            this.debounceTimer = setTimeout(resolve, delay);
        });

        if (token.isCancellationRequested) { return undefined; }

        // Build context from surrounding lines
        const contextLines = config.get<number>('contextLines', 50);
        const startLine = Math.max(0, position.line - contextLines);
        const endLine = Math.min(document.lineCount - 1, position.line + contextLines);

        const prefix = document.getText(new vscode.Range(startLine, 0, position.line, position.character));
        const suffix = document.getText(new vscode.Range(position.line, position.character, endLine, document.lineAt(endLine).text.length));

        const lang = document.languageId;
        const fileName = document.fileName.split(/[/\\]/).pop() || '';

        const model = config.get<string>('completionModel', '') || config.get<string>('model', 'qwen2.5-coder:14b');
        const maxTokens = config.get<number>('maxCompletionTokens', 128);

        try {
            let response: string;

            if (supportsFIM(model)) {
                // Native FIM: Ollama applies model-specific tokens automatically
                response = await client.generate({
                    model,
                    prompt: prefix,
                    suffix: suffix,
                    options: {
                        num_predict: maxTokens,
                        temperature: 0.2,
                        top_p: 0.9,
                        stop: ['\n\n\n'],
                    },
                });
            } else {
                // Instruction fallback: works with any model
                const prompt = `<|file|>${fileName}\n<|lang|>${lang}\n<|prefix|>\n${prefix}<|cursor|>${suffix}\n<|complete|>`;
                const system = `You are a code completion engine. Output ONLY the code that should be inserted at <|cursor|>. No explanation, no markdown, no backticks. Just the raw code to insert. Keep it short and contextually appropriate.`;

                response = await client.generate({
                    model,
                    prompt,
                    system,
                    options: {
                        num_predict: maxTokens,
                        temperature: 0.2,
                        top_p: 0.9,
                        stop: ['\n\n\n', '<|', '```'],
                    },
                });
            }

            if (token.isCancellationRequested || !response.trim()) {
                return undefined;
            }

            // Clean up response — remove any markdown artifacts
            let completion = response.trim();
            if (completion.startsWith('```')) {
                completion = completion.replace(/^```\w*\n?/, '').replace(/```$/, '').trim();
            }

            if (!completion) { return undefined; }

            return [
                new vscode.InlineCompletionItem(
                    completion,
                    new vscode.Range(position, position)
                ),
            ];
        } catch (err) {
            // Silently fail — don't spam errors on every keystroke
            return undefined;
        }
    }
}
