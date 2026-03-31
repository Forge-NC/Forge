import * as vscode from 'vscode';
import { OllamaClient } from './ollama';
import { ForgeCompletionProvider } from './completion';
import { ForgeChatViewProvider } from './chat';

let statusBarItem: vscode.StatusBarItem;
let tokenStatusItem: vscode.StatusBarItem;

function getModelDisplayName(): string {
    const config = vscode.workspace.getConfiguration('forge');
    const model = config.get<string>('model', 'qwen2.5-coder:14b');
    return model;
}

function formatBytes(bytes: number): string {
    if (bytes === 0) { return '0 B'; }
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

function updateStatusBar(online: boolean) {
    if (online) {
        const modelName = getModelDisplayName();
        statusBarItem.text = `$(hubot) Forge: ${modelName}`;
        statusBarItem.tooltip = `Forge — ${modelName} (click to switch model)`;
        statusBarItem.color = undefined;
    } else {
        statusBarItem.text = '$(hubot) Forge (offline)';
        statusBarItem.tooltip = 'Forge — Ollama not detected';
        statusBarItem.color = new vscode.ThemeColor('errorForeground');
    }
}

function updateTokenCount(evalCount: number | undefined) {
    if (evalCount && evalCount > 0) {
        tokenStatusItem.text = `$(symbol-number) ${evalCount} tokens`;
        tokenStatusItem.show();
    }
}

/**
 * Extract the first code block from a markdown response.
 * Returns the code content or undefined if no code block found.
 */
function extractCodeBlock(response: string): string | undefined {
    const match = response.match(/```\w*\n([\s\S]*?)```/);
    return match ? match[1].trimEnd() : undefined;
}

export function activate(context: vscode.ExtensionContext) {
    const config = vscode.workspace.getConfiguration('forge');
    const ollamaUrl = config.get<string>('ollamaUrl', 'http://localhost:11434');
    const client = new OllamaClient(ollamaUrl);

    // Status bar — model name, click to switch
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'forge.switchModel';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Token count status bar item
    tokenStatusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 99);
    tokenStatusItem.tooltip = 'Tokens used in last Forge response';
    context.subscriptions.push(tokenStatusItem);

    // Check Ollama on startup
    client.isAvailable().then((ok) => {
        updateStatusBar(ok);
        if (!ok) {
            vscode.window.showWarningMessage(
                'Forge: Ollama not detected. Start Ollama or configure forge.ollamaUrl.',
                'Open Settings'
            ).then((choice) => {
                if (choice === 'Open Settings') {
                    vscode.commands.executeCommand('workbench.action.openSettings', 'forge');
                }
            });
        }
    });

    // Inline completion provider
    const completionProvider = new ForgeCompletionProvider();
    context.subscriptions.push(
        vscode.languages.registerInlineCompletionItemProvider(
            { pattern: '**' },
            completionProvider
        )
    );

    // Chat sidebar
    const chatProvider = new ForgeChatViewProvider(context.extensionUri, client);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(ForgeChatViewProvider.viewType, chatProvider)
    );

    // Toggle completions
    context.subscriptions.push(
        vscode.commands.registerCommand('forge.toggleCompletion', () => {
            const cfg = vscode.workspace.getConfiguration('forge');
            const current = cfg.get<boolean>('completionEnabled', true);
            cfg.update('completionEnabled', !current, vscode.ConfigurationTarget.Global);
            vscode.window.showInformationMessage(
                `Forge inline completions: ${!current ? 'ON' : 'OFF'}`
            );
        })
    );

    // Open chat
    context.subscriptions.push(
        vscode.commands.registerCommand('forge.chat', () => {
            vscode.commands.executeCommand('forge.chatView.focus');
        })
    );

    // ─── Model Switching ───────────────────────────────────────────────
    context.subscriptions.push(
        vscode.commands.registerCommand('forge.switchModel', async () => {
            const cfg = vscode.workspace.getConfiguration('forge');
            const url = cfg.get<string>('ollamaUrl', 'http://localhost:11434');
            const ollamaClient = new OllamaClient(url);
            const currentModel = cfg.get<string>('model', 'qwen2.5-coder:14b');

            try {
                const models = await ollamaClient.listModels();
                if (models.length === 0) {
                    vscode.window.showWarningMessage('No models found in Ollama. Pull a model first.');
                    return;
                }

                const items: vscode.QuickPickItem[] = models.map(m => ({
                    label: m.name === currentModel ? `$(check) ${m.name}` : m.name,
                    description: formatBytes(m.size),
                    detail: m.modified_at ? `Modified: ${new Date(m.modified_at).toLocaleDateString()}` : undefined,
                }));

                const picked = await vscode.window.showQuickPick(items, {
                    placeHolder: `Current model: ${currentModel}`,
                    title: 'Forge: Switch Model',
                });

                if (picked) {
                    // Strip the checkmark prefix if present
                    const modelName = picked.label.replace(/^\$\(check\) /, '');
                    await cfg.update('model', modelName, vscode.ConfigurationTarget.Global);
                    updateStatusBar(true);
                    vscode.window.showInformationMessage(`Forge model switched to: ${modelName}`);
                }
            } catch (err: any) {
                vscode.window.showErrorMessage(`Failed to list models: ${err.message || err}`);
            }
        })
    );

    // ─── Fix Terminal Error ────────────────────────────────────────────
    context.subscriptions.push(
        vscode.commands.registerCommand('forge.fixTerminalError', async () => {
            // Read error text from clipboard (user copies error text first)
            const clipboardText = await vscode.env.clipboard.readText();
            if (!clipboardText || clipboardText.trim().length === 0) {
                vscode.window.showWarningMessage(
                    'Copy the terminal error text to clipboard first, then run this command.'
                );
                return;
            }

            const prompt = `Fix this terminal error. Explain what went wrong and provide the corrected command or code:\n\n\`\`\`\n${clipboardText.trim()}\n\`\`\``;
            chatProvider.handleChat(prompt);
            vscode.commands.executeCommand('forge.chatView.focus');
        })
    );

    // ─── /break Integration ────────────────────────────────────────────
    context.subscriptions.push(
        vscode.commands.registerCommand('forge.runBreak', () => {
            const terminal = vscode.window.createTerminal('Forge /break');
            terminal.show();
            terminal.sendText('python -m forge --run "/break --share"');
            vscode.window.showInformationMessage('Forge /break started. Check the terminal for output.');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('forge.runBreakFull', () => {
            const terminal = vscode.window.createTerminal('Forge /break --full');
            terminal.show();
            terminal.sendText('python -m forge --run "/break --full --share"');
            vscode.window.showInformationMessage('Forge /break --full started. Check the terminal for output.');
        })
    );

    // ─── Context Menu Actions (with diff preview for fix/refactor) ────
    const simpleActions: Record<string, string> = {
        'forge.explain': 'Explain this code clearly and concisely:\n\n',
        'forge.test': 'Generate unit tests for this code:\n\n',
    };

    // Simple actions: just send to chat
    for (const [cmdId, systemPrefix] of Object.entries(simpleActions)) {
        context.subscriptions.push(
            vscode.commands.registerCommand(cmdId, async () => {
                const editor = vscode.window.activeTextEditor;
                if (!editor || editor.selection.isEmpty) {
                    vscode.window.showWarningMessage('Select some code first.');
                    return;
                }

                const selected = editor.document.getText(editor.selection);
                const lang = editor.document.languageId;

                const prompt = `${systemPrefix}\`\`\`${lang}\n${selected}\n\`\`\``;

                chatProvider.handleChat(prompt);
                vscode.commands.executeCommand('forge.chatView.focus');
            })
        );
    }

    // Diff-preview actions: fix and refactor show a diff view
    const diffActions: Record<string, string> = {
        'forge.fix': 'Find and fix any bugs in this code. Return ONLY the corrected code in a single code block, no explanation:\n\n',
        'forge.refactor': 'Refactor this code for clarity and efficiency. Return ONLY the improved code in a single code block, no explanation:\n\n',
    };

    for (const [cmdId, systemPrefix] of Object.entries(diffActions)) {
        context.subscriptions.push(
            vscode.commands.registerCommand(cmdId, async () => {
                const editor = vscode.window.activeTextEditor;
                if (!editor || editor.selection.isEmpty) {
                    vscode.window.showWarningMessage('Select some code first.');
                    return;
                }

                const selected = editor.document.getText(editor.selection);
                const lang = editor.document.languageId;
                const selection = editor.selection;
                const docUri = editor.document.uri;

                const prompt = `${systemPrefix}\`\`\`${lang}\n${selected}\n\`\`\``;

                // Also send to chat for visibility
                chatProvider.handleChat(prompt);
                vscode.commands.executeCommand('forge.chatView.focus');

                // Separately, get a non-streaming response for the diff
                const cfg = vscode.workspace.getConfiguration('forge');
                const url = cfg.get<string>('ollamaUrl', 'http://localhost:11434');
                const model = cfg.get<string>('model', 'qwen2.5-coder:14b');
                const ollamaClient = new OllamaClient(url);

                try {
                    const response = await vscode.window.withProgress(
                        {
                            location: vscode.ProgressLocation.Notification,
                            title: cmdId === 'forge.fix' ? 'Forge: Generating fix...' : 'Forge: Refactoring...',
                            cancellable: false,
                        },
                        async () => {
                            return ollamaClient.generate({
                                model,
                                prompt: `${systemPrefix}\`\`\`${lang}\n${selected}\n\`\`\``,
                                system: 'You are a code assistant. Return ONLY the corrected/refactored code in a single fenced code block. No explanation.',
                                options: { temperature: 0.2 },
                            });
                        }
                    );

                    const extractedCode = extractCodeBlock(response);
                    if (!extractedCode) {
                        // No code block found — just show in chat, already handled above
                        return;
                    }

                    // Show diff: original (left) vs suggested (right)
                    const actionLabel = cmdId === 'forge.fix' ? 'Fix' : 'Refactor';
                    const originalContent = selected;
                    const suggestedContent = extractedCode;

                    // Register a temporary text document content provider
                    const scheme = 'forge-diff';
                    const contentMap = new Map<string, string>();
                    contentMap.set('original', originalContent);
                    contentMap.set('suggested', suggestedContent);

                    const provider = vscode.workspace.registerTextDocumentContentProvider(scheme, {
                        provideTextDocumentContent(uri: vscode.Uri): string {
                            return contentMap.get(uri.path) || '';
                        }
                    });

                    const leftUri = vscode.Uri.from({ scheme, path: 'original' });
                    const rightUri = vscode.Uri.from({ scheme, path: 'suggested' });

                    await vscode.commands.executeCommand(
                        'vscode.diff',
                        leftUri,
                        rightUri,
                        `Forge ${actionLabel}: Original vs Suggested`
                    );

                    // Offer to apply the change
                    const apply = await vscode.window.showInformationMessage(
                        `Apply the suggested ${actionLabel.toLowerCase()}?`,
                        'Apply',
                        'Dismiss'
                    );

                    if (apply === 'Apply') {
                        const targetEditor = vscode.window.visibleTextEditors.find(
                            e => e.document.uri.toString() === docUri.toString()
                        );
                        if (targetEditor) {
                            await targetEditor.edit(editBuilder => {
                                editBuilder.replace(selection, suggestedContent);
                            });
                            vscode.window.showInformationMessage(`Forge: ${actionLabel} applied.`);
                        } else {
                            // If original editor is not visible, open the document and apply
                            const doc = await vscode.workspace.openTextDocument(docUri);
                            const newEditor = await vscode.window.showTextDocument(doc);
                            await newEditor.edit(editBuilder => {
                                editBuilder.replace(selection, suggestedContent);
                            });
                            vscode.window.showInformationMessage(`Forge: ${actionLabel} applied.`);
                        }
                    }

                    provider.dispose();
                } catch (err: any) {
                    // Diff generation failed — the chat response is still visible
                    vscode.window.showErrorMessage(`Forge diff preview failed: ${err.message || err}`);
                }
            })
        );
    }

    // ─── Re-check Ollama when config changes ───────────────────────────
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration((e) => {
            if (e.affectsConfiguration('forge.ollamaUrl')) {
                const newUrl = vscode.workspace.getConfiguration('forge').get<string>('ollamaUrl', 'http://localhost:11434');
                const newClient = new OllamaClient(newUrl);
                newClient.isAvailable().then((ok) => {
                    updateStatusBar(ok);
                });
            }
            if (e.affectsConfiguration('forge.model')) {
                updateStatusBar(true);
            }
        })
    );

    console.log('Forge extension activated');
}

export function deactivate() {}
