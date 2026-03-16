import * as vscode from 'vscode';
import { OllamaClient } from './ollama';
import { ForgeCompletionProvider } from './completion';
import { ForgeChatViewProvider } from './chat';

let statusBarItem: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext) {
    const config = vscode.workspace.getConfiguration('forge');
    const ollamaUrl = config.get<string>('ollamaUrl', 'http://localhost:11434');
    const client = new OllamaClient(ollamaUrl);

    // Status bar
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.text = '$(hubot) Forge';
    statusBarItem.tooltip = 'Forge — Local AI';
    statusBarItem.command = 'forge.chat';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Check Ollama on startup
    client.isAvailable().then((ok) => {
        if (ok) {
            statusBarItem.text = '$(hubot) Forge';
            statusBarItem.color = undefined;
        } else {
            statusBarItem.text = '$(hubot) Forge (offline)';
            statusBarItem.color = new vscode.ThemeColor('errorForeground');
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
    const completionProvider = new ForgeCompletionProvider(client);
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

    // Context menu actions
    const contextActions: Record<string, string> = {
        'forge.explain': 'Explain this code clearly and concisely:\n\n',
        'forge.fix': 'Find and fix any bugs in this code. Show the corrected version:\n\n',
        'forge.refactor': 'Refactor this code for clarity and efficiency. Show the improved version:\n\n',
        'forge.test': 'Generate unit tests for this code:\n\n',
    };

    for (const [cmdId, systemPrefix] of Object.entries(contextActions)) {
        context.subscriptions.push(
            vscode.commands.registerCommand(cmdId, async () => {
                const editor = vscode.window.activeTextEditor;
                if (!editor || editor.selection.isEmpty) {
                    vscode.window.showWarningMessage('Select some code first.');
                    return;
                }

                const selected = editor.document.getText(editor.selection);
                const lang = editor.document.languageId;
                const model = config.get<string>('model', 'qwen2.5-coder:14b');

                const prompt = `${systemPrefix}\`\`\`${lang}\n${selected}\n\`\`\``;

                // Show result in chat panel
                chatProvider.handleChat(prompt);
                vscode.commands.executeCommand('forge.chatView.focus');
            })
        );
    }

    // Re-check Ollama when config changes
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration((e) => {
            if (e.affectsConfiguration('forge.ollamaUrl')) {
                const newUrl = vscode.workspace.getConfiguration('forge').get<string>('ollamaUrl', 'http://localhost:11434');
                const newClient = new OllamaClient(newUrl);
                newClient.isAvailable().then((ok) => {
                    statusBarItem.text = ok ? '$(hubot) Forge' : '$(hubot) Forge (offline)';
                    statusBarItem.color = ok ? undefined : new vscode.ThemeColor('errorForeground');
                });
            }
        })
    );

    console.log('Forge extension activated');
}

export function deactivate() {}
