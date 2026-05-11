import * as vscode from "vscode";
import { ChatViewProvider } from "./chatViewProvider";

export function activate(context: vscode.ExtensionContext) {
  try {
    const output = vscode.window.createOutputChannel("AutoGit");
    const provider = new ChatViewProvider(context, output);
    output.appendLine("AutoGit extension activated");

    context.subscriptions.push(
      vscode.window.registerWebviewViewProvider(ChatViewProvider.viewType, provider, {
        webviewOptions: {
          retainContextWhenHidden: true
        }
      })
    );
    context.subscriptions.push(output);

    context.subscriptions.push(
      vscode.commands.registerCommand("autogit.openChat", async () => {
        await vscode.commands.executeCommand("workbench.view.extension.autogit");
        await vscode.commands.executeCommand("autogit.chatView.focus");
      })
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown activation error";
    vscode.window.showErrorMessage(`AutoGit activation failed: ${message}`);
  }
}

export function deactivate() {}
