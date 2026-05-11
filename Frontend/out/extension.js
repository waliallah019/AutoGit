"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const chatViewProvider_1 = require("./chatViewProvider");
function activate(context) {
    try {
        const output = vscode.window.createOutputChannel("AutoGit");
        const provider = new chatViewProvider_1.ChatViewProvider(context, output);
        output.appendLine("AutoGit extension activated");
        context.subscriptions.push(vscode.window.registerWebviewViewProvider(chatViewProvider_1.ChatViewProvider.viewType, provider, {
            webviewOptions: {
                retainContextWhenHidden: true
            }
        }));
        context.subscriptions.push(output);
        context.subscriptions.push(vscode.commands.registerCommand("autogit.openChat", async () => {
            await vscode.commands.executeCommand("workbench.view.extension.autogit");
            await vscode.commands.executeCommand("autogit.chatView.focus");
        }));
    }
    catch (error) {
        const message = error instanceof Error ? error.message : "Unknown activation error";
        vscode.window.showErrorMessage(`AutoGit activation failed: ${message}`);
    }
}
function deactivate() { }
//# sourceMappingURL=extension.js.map