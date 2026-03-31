import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { OllamaClient, OllamaChatMessage } from './ollama';

export class ForgeChatViewProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'forge.chatView';
    private webviewView?: vscode.WebviewView;
    private client: OllamaClient;
    private messages: Array<{role: string, content: string}> = [];

    constructor(private extensionUri: vscode.Uri, client: OllamaClient) {
        this.client = client;
    }

    resolveWebviewView(
        webviewView: vscode.WebviewView,
        _context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ) {
        this.webviewView = webviewView;
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this.extensionUri],
        };
        webviewView.webview.html = this.getHtml();

        webviewView.webview.onDidReceiveMessage(async (msg) => {
            if (msg.type === 'chat') {
                await this.handleChat(msg.text);
            } else if (msg.type === 'clear') {
                this.messages = [];
            }
        });
    }

    async handleChat(userMessage: string) {
        if (!this.webviewView) { return; }
        const config = vscode.workspace.getConfiguration('forge');
        const model = config.get<string>('model', 'qwen2.5-coder:14b');

        // Read URL fresh from config so config changes propagate immediately
        const url = config.get<string>('ollamaUrl', 'http://localhost:11434');
        this.client = new OllamaClient(url);

        // Get active editor context
        const editor = vscode.window.activeTextEditor;
        let fileContext = '';
        if (editor) {
            const doc = editor.document;
            const sel = editor.selection;
            const fileName = doc.fileName.split(/[/\\]/).pop() || '';
            const lang = doc.languageId;

            if (!sel.isEmpty) {
                const selected = doc.getText(sel);
                fileContext = `\n\nUser has selected this code in ${fileName} (${lang}):\n\`\`\`${lang}\n${selected}\n\`\`\`\n`;
            } else {
                // Send visible range for context
                const visRange = editor.visibleRanges[0];
                if (visRange) {
                    const visible = doc.getText(visRange);
                    fileContext = `\n\nUser is viewing ${fileName} (${lang}), lines ${visRange.start.line + 1}-${visRange.end.line + 1}:\n\`\`\`${lang}\n${visible}\n\`\`\`\n`;
                }
            }
        }

        // Workspace context: open tabs, file tree, imports, diagnostics
        let workspaceContext = '';
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (workspaceFolders && workspaceFolders.length > 0) {
            const folderName = workspaceFolders[0].name;
            workspaceContext += `\nWorkspace: ${folderName}`;

            // File tree: top-level files and first-level subdirectories (max 50)
            try {
                const rootPath = workspaceFolders[0].uri.fsPath;
                const entries = fs.readdirSync(rootPath, { withFileTypes: true });
                const treeItems: string[] = [];
                for (const entry of entries) {
                    if (treeItems.length >= 50) { break; }
                    if (entry.name.startsWith('.') || entry.name === 'node_modules' || entry.name === '__pycache__') {
                        continue;
                    }
                    if (entry.isDirectory()) {
                        treeItems.push(`${entry.name}/`);
                        // List first-level children of subdirectory
                        try {
                            const subEntries = fs.readdirSync(path.join(rootPath, entry.name), { withFileTypes: true });
                            for (const sub of subEntries.slice(0, 10)) {
                                if (treeItems.length >= 50) { break; }
                                treeItems.push(`  ${sub.name}${sub.isDirectory() ? '/' : ''}`);
                            }
                            if (subEntries.length > 10) {
                                treeItems.push(`  ... (${subEntries.length - 10} more)`);
                            }
                        } catch { /* permission denied or similar */ }
                    } else {
                        treeItems.push(entry.name);
                    }
                }
                if (treeItems.length > 0) {
                    workspaceContext += `\nFile tree:\n${treeItems.join('\n')}`;
                }
            } catch { /* workspace not readable */ }
        }

        const openTabs = vscode.window.tabGroups.all
            .flatMap(group => group.tabs)
            .map(tab => {
                if (tab.input && typeof tab.input === 'object' && 'uri' in tab.input) {
                    const uri = (tab.input as { uri: vscode.Uri }).uri;
                    return uri.path.split(/[/\\]/).pop() || '';
                }
                return '';
            })
            .filter(name => name.length > 0);

        if (openTabs.length > 0) {
            workspaceContext += `\nOpen files: ${openTabs.join(', ')}`;
        }

        // Active file imports/requires (first 5 matching lines)
        if (editor) {
            const doc = editor.document;
            const importLines: string[] = [];
            const importPattern = /^\s*(import |from |require\(|#include )/;
            const lineCount = Math.min(doc.lineCount, 100); // only scan first 100 lines
            for (let i = 0; i < lineCount && importLines.length < 5; i++) {
                const lineText = doc.lineAt(i).text;
                if (importPattern.test(lineText)) {
                    importLines.push(lineText.trim());
                }
            }
            if (importLines.length > 0) {
                workspaceContext += `\nActive file imports:\n${importLines.join('\n')}`;
            }
        }

        // Diagnostics from Problems panel
        const allDiagnostics = vscode.languages.getDiagnostics();
        const errors: string[] = [];
        for (const [uri, diags] of allDiagnostics) {
            for (const diag of diags) {
                if (diag.severity === vscode.DiagnosticSeverity.Error && errors.length < 10) {
                    const fileName = uri.path.split(/[/\\]/).pop() || '';
                    errors.push(`${fileName}:${diag.range.start.line + 1}: ${diag.message}`);
                }
            }
        }
        if (errors.length > 0) {
            workspaceContext += `\nCurrent errors:\n${errors.join('\n')}`;
        }

        const system = `You are Forge, a local AI coding assistant. You help with code questions, debugging, refactoring, and explanations. Be concise and direct. When showing code, use markdown code blocks with the language identifier.${workspaceContext}`;

        // Build the user message content with file context
        const userContent = fileContext ? `${fileContext}\n\n${userMessage}` : userMessage;

        // Keep last 50 messages to prevent exceeding context window
        while (this.messages.length > 50) {
            // Keep system message (index 0), remove oldest user/assistant pair
            if (this.messages[0]?.role === 'system') {
                this.messages.splice(1, 2);
            } else {
                this.messages.splice(0, 2);
            }
        }

        // Push user message to conversation history
        this.messages.push({ role: 'user', content: userContent });

        // Build the full messages array with system prompt
        const chatMessages: OllamaChatMessage[] = [
            { role: 'system', content: system },
            ...this.messages,
        ];

        // Show typing indicator
        this.webviewView.webview.postMessage({ type: 'startResponse' });

        try {
            const fullResponse = await this.client.streamChat(
                { model, messages: chatMessages, options: { temperature: 0.3 } },
                (token) => {
                    this.webviewView?.webview.postMessage({ type: 'token', text: token });
                }
            );

            // Push assistant response to conversation history
            this.messages.push({ role: 'assistant', content: fullResponse });

            this.webviewView.webview.postMessage({ type: 'endResponse' });
        } catch (err: any) {
            // Remove the user message if the request failed so the conversation stays consistent
            this.messages.pop();

            this.webviewView.webview.postMessage({
                type: 'error',
                text: err.message || 'Failed to reach Ollama',
            });
        }
    }

    private getHtml(): string {
        return `<!DOCTYPE html>
<html>
<head>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: var(--vscode-font-family);
    font-size: var(--vscode-font-size);
    color: var(--vscode-foreground);
    background: var(--vscode-sideBar-background);
    display: flex;
    flex-direction: column;
    height: 100vh;
}
#toolbar {
    display: flex;
    justify-content: flex-end;
    padding: 4px 8px;
    border-bottom: 1px solid var(--vscode-panel-border);
}
#new-chat {
    background: none;
    color: var(--vscode-foreground);
    border: 1px solid var(--vscode-panel-border);
    border-radius: 3px;
    padding: 2px 8px;
    cursor: pointer;
    font-size: calc(var(--vscode-font-size) - 1px);
    opacity: 0.8;
}
#new-chat:hover {
    opacity: 1;
    background: var(--vscode-toolbar-hoverBackground);
}
#messages {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
}
.msg {
    margin-bottom: 12px;
    line-height: 1.5;
}
.msg.user {
    color: var(--vscode-textLink-foreground);
}
.msg.user::before { content: '> '; opacity: 0.5; }
.msg.assistant {
    color: var(--vscode-foreground);
}
.msg.error {
    color: var(--vscode-errorForeground);
}
.msg code {
    background: var(--vscode-textCodeBlock-background);
    border-radius: 3px;
    padding: 1px 4px;
    font-family: var(--vscode-editor-font-family);
    font-size: var(--vscode-editor-font-size);
}
.code-block-wrapper {
    position: relative;
    margin: 6px 0;
}
.code-block-wrapper pre {
    background: var(--vscode-textCodeBlock-background);
    border-radius: 3px;
    padding: 8px;
    overflow-x: auto;
    display: block;
    margin: 0;
}
.code-block-wrapper pre code {
    padding: 0;
    background: none;
    font-family: var(--vscode-editor-font-family);
    font-size: var(--vscode-editor-font-size);
    white-space: pre;
}
.code-block-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--vscode-textCodeBlock-background);
    border-radius: 3px 3px 0 0;
    padding: 2px 8px;
    font-size: calc(var(--vscode-font-size) - 2px);
    opacity: 0.7;
}
.code-block-header + pre {
    border-radius: 0 0 3px 3px;
}
.copy-btn {
    background: none;
    border: 1px solid var(--vscode-panel-border);
    color: var(--vscode-foreground);
    border-radius: 3px;
    padding: 1px 6px;
    cursor: pointer;
    font-size: calc(var(--vscode-font-size) - 2px);
    opacity: 0.7;
}
.copy-btn:hover { opacity: 1; }
.msg h1, .msg h2, .msg h3, .msg h4, .msg h5, .msg h6 {
    margin: 8px 0 4px 0;
    font-weight: bold;
}
.msg h1 { font-size: 1.4em; }
.msg h2 { font-size: 1.2em; }
.msg h3 { font-size: 1.1em; }
.msg ul, .msg ol {
    margin: 4px 0;
    padding-left: 20px;
}
.msg li {
    margin: 2px 0;
}
.msg a {
    color: var(--vscode-textLink-foreground);
    text-decoration: none;
}
.msg a:hover {
    text-decoration: underline;
}
.msg p {
    margin: 4px 0;
}
.msg strong { font-weight: bold; }
.msg em { font-style: italic; }
#input-row {
    display: flex;
    border-top: 1px solid var(--vscode-panel-border);
    padding: 6px;
    gap: 4px;
}
#input {
    flex: 1;
    background: var(--vscode-input-background);
    color: var(--vscode-input-foreground);
    border: 1px solid var(--vscode-input-border);
    border-radius: 4px;
    padding: 6px 8px;
    font-family: var(--vscode-font-family);
    font-size: var(--vscode-font-size);
    resize: none;
    min-height: 32px;
    max-height: 120px;
}
#input:focus { outline: 1px solid var(--vscode-focusBorder); }
#send {
    background: var(--vscode-button-background);
    color: var(--vscode-button-foreground);
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
    cursor: pointer;
    font-size: var(--vscode-font-size);
}
#send:hover { background: var(--vscode-button-hoverBackground); }
.typing { opacity: 0.5; font-style: italic; }
</style>
</head>
<body>
<div id="toolbar">
    <button id="new-chat" title="Clear conversation and start fresh">New Chat</button>
</div>
<div id="messages"></div>
<div id="input-row">
    <textarea id="input" rows="1" placeholder="Ask Forge..."></textarea>
    <button id="send">Send</button>
</div>
<script>
const vscode = acquireVsCodeApi();
const messagesDiv = document.getElementById('messages');
const input = document.getElementById('input');
const send = document.getElementById('send');
const newChatBtn = document.getElementById('new-chat');
let currentResponse = null;
let currentResponseText = '';

function escapeHtml(text) {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function renderMarkdown(text) {
    // Step 1: Extract code blocks and replace with placeholders
    const codeBlocks = [];
    let processed = text.replace(/\`\`\`(\\w*)\\n([\\s\\S]*?)\`\`\`/g, function(match, lang, code) {
        const index = codeBlocks.length;
        codeBlocks.push({ lang: lang, code: code });
        return '%%CODEBLOCK_' + index + '%%';
    });

    // Step 2: Extract inline code and replace with placeholders
    const inlineCodes = [];
    processed = processed.replace(/\`([^\`]+)\`/g, function(match, code) {
        const index = inlineCodes.length;
        inlineCodes.push(code);
        return '%%INLINECODE_' + index + '%%';
    });

    // Step 3: HTML-escape the remaining text
    processed = escapeHtml(processed);

    // Step 4: Apply markdown formatting on the escaped text
    // Bold
    processed = processed.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
    // Italic (single * not preceded/followed by *)
    processed = processed.replace(/(?<!\\*)\\*(?!\\*)(.+?)(?<!\\*)\\*(?!\\*)/g, '<em>$1</em>');
    // Headers (must be at start of line)
    processed = processed.replace(/^######\\s+(.+)$/gm, '<h6>$1</h6>');
    processed = processed.replace(/^#####\\s+(.+)$/gm, '<h5>$1</h5>');
    processed = processed.replace(/^####\\s+(.+)$/gm, '<h4>$1</h4>');
    processed = processed.replace(/^###\\s+(.+)$/gm, '<h3>$1</h3>');
    processed = processed.replace(/^##\\s+(.+)$/gm, '<h2>$1</h2>');
    processed = processed.replace(/^#\\s+(.+)$/gm, '<h1>$1</h1>');
    // Links
    processed = processed.replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, '<a href="$2" target="_blank">$1</a>');
    // Sanitize non-http(s) links (block javascript: URLs etc.)
    processed = processed.replace(/href="(?!https?:\\/\\/)[^"]*"/g, 'href="#"');

    // Unordered lists: consecutive lines starting with "- "
    processed = processed.replace(/(?:^|\\n)((?:- .+(?:\\n|$))+)/g, function(match, block) {
        const items = block.trim().split('\\n').map(function(line) {
            return '<li>' + line.replace(/^- /, '') + '</li>';
        }).join('');
        return '<ul>' + items + '</ul>';
    });

    // Ordered lists: consecutive lines starting with "N. "
    processed = processed.replace(/(?:^|\\n)((?:\\d+\\.\\s+.+(?:\\n|$))+)/g, function(match, block) {
        const items = block.trim().split('\\n').map(function(line) {
            return '<li>' + line.replace(/^\\d+\\.\\s+/, '') + '</li>';
        }).join('');
        return '<ol>' + items + '</ol>';
    });

    // Wrap remaining plain text lines in <p> tags (skip lines that are already wrapped in block elements)
    processed = processed.split('\\n').map(function(line) {
        const trimmed = line.trim();
        if (!trimmed) return '';
        if (trimmed.startsWith('<h') || trimmed.startsWith('<ul') || trimmed.startsWith('<ol') ||
            trimmed.startsWith('<li') || trimmed.startsWith('</') || trimmed.startsWith('%%CODEBLOCK_')) {
            return trimmed;
        }
        return '<p>' + trimmed + '</p>';
    }).join('\\n');

    // Step 5: Restore inline code with escaped content
    for (let i = 0; i < inlineCodes.length; i++) {
        processed = processed.replace('%%INLINECODE_' + i + '%%', '<code>' + escapeHtml(inlineCodes[i]) + '</code>');
    }

    // Step 6: Restore code blocks with escaped content and copy button
    for (let i = 0; i < codeBlocks.length; i++) {
        const block = codeBlocks[i];
        const langLabel = block.lang || 'text';
        const langClass = block.lang ? ' class="language-' + escapeHtml(block.lang) + '"' : '';
        const escapedCode = escapeHtml(block.code);
        const replacement = '<div class="code-block-wrapper">' +
            '<div class="code-block-header"><span>' + escapeHtml(langLabel) + '</span>' +
            '<button class="copy-btn" onclick="copyCode(this)">Copy</button></div>' +
            '<pre><code' + langClass + '>' + escapedCode + '</code></pre></div>';
        processed = processed.replace('%%CODEBLOCK_' + i + '%%', replacement);
    }

    return processed;
}

function copyCode(btn) {
    const wrapper = btn.closest('.code-block-wrapper');
    const code = wrapper.querySelector('code');
    const text = code.textContent || '';
    navigator.clipboard.writeText(text).then(function() {
        btn.textContent = 'Copied!';
        setTimeout(function() { btn.textContent = 'Copy'; }, 1500);
    });
}

function addMsg(cls, text) {
    const div = document.createElement('div');
    div.className = 'msg ' + cls;
    div.textContent = text;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return div;
}

newChatBtn.onclick = function() {
    messagesDiv.innerHTML = '';
    currentResponse = null;
    currentResponseText = '';
    vscode.postMessage({ type: 'clear' });
};

send.onclick = function() {
    const text = input.value.trim();
    if (!text) return;
    addMsg('user', text);
    input.value = '';
    input.style.height = 'auto';
    vscode.postMessage({ type: 'chat', text: text });
};

input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send.click();
    }
});

input.addEventListener('input', function() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
});

window.addEventListener('message', function(e) {
    const msg = e.data;
    if (msg.type === 'startResponse') {
        currentResponseText = '';
        currentResponse = addMsg('assistant', '');
    } else if (msg.type === 'token' && currentResponse) {
        currentResponseText += msg.text;
        currentResponse.textContent = currentResponseText;
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    } else if (msg.type === 'endResponse' && currentResponse) {
        currentResponse.innerHTML = renderMarkdown(currentResponseText);
        currentResponse = null;
        currentResponseText = '';
    } else if (msg.type === 'error') {
        addMsg('error', msg.text);
        currentResponse = null;
        currentResponseText = '';
    }
});
</script>
</body>
</html>`;
    }
}
