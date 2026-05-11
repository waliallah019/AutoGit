"""AI Git Agent - LangChain Agent with Groq Native Tool Calling"""
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_groq import ChatGroq
from tools import (
    git_status,
    git_add,
    git_commit,
    git_init,
    git_branch_rename,
    get_branch_info,
    diagnose_git_config,
    get_remote_url,
    git_remote_add,
    git_push,
    generate_version_documentation,
    resolve_conflicts,
    get_merge_conflicts,
    validate_git_repository,
    git_reinitialize
)


class AIGitAgent:
    def __init__(self, groq_api_key: str):
        self.api_key = groq_api_key
        self.tools = self._load_tools()
        self.tools_dict = {tool.name: tool for tool in self.tools}

        base_llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=groq_api_key,
            temperature=0.1,
            max_tokens=800
        )

        self.llm = base_llm.bind_tools(self.tools)

    def _load_tools(self) -> list:
        """Load all available LangChain tools"""
        return [
            git_status,
            git_add,
            git_commit,
            git_init,
            git_branch_rename,
            get_branch_info,
            diagnose_git_config,
            get_remote_url,
            git_remote_add,
            git_push,
            generate_version_documentation,
            resolve_conflicts,
            get_merge_conflicts,
            validate_git_repository,
            git_reinitialize
        ]

    def _get_system_message(self) -> str:
        """Get system prompt"""
        return """You are a friendly and helpful Git automation assistant.

IMPORTANT: Always show the ACTUAL output from tools. Never say something succeeded unless you see a success message from the tool.

⚠️ REPOSITORY CONTEXT NOTE:
The repository metadata you see (owner: user, repo: repo) is just an EXAMPLE placeholder.
NEVER use "https://github.com/user/repo.git" or auto-generate URLs from this metadata.
ALWAYS ask the user for their actual GitHub repository URL when needed.

GUIDELINES:
• Respond naturally to greetings and casual conversation
• For Git-related requests, use the appropriate tools to help
• Only use tools when the user asks for Git operations
• ALWAYS report what the tools actually returned - don't make assumptions
• If a tool shows an error, report that error to the user
• Be conversational and friendly
• When git_remote_add is needed, ASK the user for their actual repository URL first

WHEN TO USE TOOLS:

0. BEFORE ANY GIT OPERATIONS (CRITICAL):
   • ALWAYS call validate_git_repository FIRST before doing any push, commit, or remote operations
   • This checks if Git is initialized in the correct folder
   • If validation shows issues, inform user and ask what they want to do
   • If user wants to reinitialize, call git_reinitialize
   • Only proceed with other operations after validation passes

1. Repository Status:
   • "check status" / "status" / "what changed" → use git_status

2. Branch Info:
   • "what branch" / "current branch" → use get_branch_info

3. Configuration:
   • "diagnose" / "check config" → use diagnose_git_config
   • "get remote" / "remote url" → use get_remote_url

4. Commit:
   • "commit" / "save changes" / "commit with message X" →
     a) Call git_add to stage files
     b) Generate a clear, descriptive commit message based on the staged changes
     c) ALWAYS display the commit message to the user like this:
        "📝 Commit message: <your message here>"
        "✅ Committing automatically..."
     d) Call git_commit with the message — ALWAYS proceed, do NOT wait for user confirmation
     e) Report actual results
     DO NOT PUSH unless explicitly asked!

5. Push Code:
   • "push" / "push my code" / "upload to github" → You MUST do ALL these steps IN ORDER:
     a) Call validate_git_repository FIRST (CRITICAL - detects wrong repo configuration)
     b) If validation fails or shows parent repo, stop and inform user
     c) If user wants to reinitialize, call git_reinitialize
     d) Check git_status
     e) Call get_branch_info to determine current branch
     f) If NOT on 'main':
        - Call git_branch_rename to rename the current branch to 'main'
        - Report that branch was renamed to main
     g) Call git_add to stage changes
     h) Call generate_version_documentation to create detailed PDF documentation
     i) Generate and DISPLAY the commit message:
        "📝 Commit message: <your message here>"
        "✅ Committing and pushing automatically..."
     j) Call git_commit with the message
     k) Call git_push — ALWAYS push to 'main' branch
     l) Report the actual results from each step

6. Initialize/Reinitialize:
   • "init" / "create repo" → use git_init
   • "reinitialize" / "reinit" / "fresh start" → use git_reinitialize
   • "validate" / "check git" / "check repo" → use validate_git_repository

7. Generate Documentation:
   • "generate docs" / "create documentation" / "document changes" / "document my code" →
     Call generate_version_documentation ONCE to create a detailed PDF report
     It automatically detects current changes (staged or unstaged)
     IMPORTANT: Only call this tool ONE TIME, then report the result

8. Merge Conflict Resolution:
   • "resolve conflicts" / "fix merge conflicts" / "merge conflict" →
     a) First call get_merge_conflict_info to analyze conflicts
     b) Then call resolve_merge_conflicts with strategy='ai' for intelligent resolution
     c) Report results and next steps
   • "check conflicts" / "show conflicts" → use get_merge_conflict_info
   • For manual strategy: resolve_merge_conflicts(strategy='ours'|'theirs'|'both')

WHEN NOT TO USE TOOLS:
• Greetings: "hi", "hello", "hey" → Just greet back warmly
• Questions: "how are you", "what can you do" → Explain your capabilities
• Thanks: "thank you", "thanks" → Acknowledge politely
• Casual chat → Respond naturally without using tools

CRITICAL: Base your response ONLY on actual tool outputs. If you don't call a tool, don't claim it succeeded."""

    def run(self, user_command: str) -> str:
        """Process a command with console output (CLI-style)."""
        return self._run(user_command, verbose=True)

    def process_message(self, user_command: str, conversation_history: list[dict] | None = None) -> str:
        """Process a command and return a response string for API usage."""
        return self._run(user_command, verbose=False, conversation_history=conversation_history)

    def _run(self, user_command: str, verbose: bool, conversation_history: list[dict] | None = None) -> str:
        """Main method to process commands using Groq native tool calling."""
        if verbose:
            print(f"\nUser: {user_command}\n")
            print("AI Agent: Processing your request...\n")

        final_response = ""
        pdf_path: str | None = None

        try:
            history = conversation_history or []

            # Build messages: system + conversation history + new user message
            messages = [
                {"role": "system", "content": self._get_system_message()},
                *history,
                HumanMessage(content=user_command)
            ]

            max_iterations = 10
            iteration = 0
            tool_call_tracker = {}

            while iteration < max_iterations:
                iteration += 1

                # Get response from LLM
                response = self.llm.invoke(messages)
                messages.append(response)

                # No tool calls → final text response
                if not response.tool_calls:
                    if response.content:
                        final_response = response.content
                        if verbose:
                            print(f"\n{response.content}\n")
                    break

                # Execute all tool calls in this round
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call.get("args", {})

                    # Deduplicate generate_version_documentation
                    if tool_name == "generate_version_documentation":
                        if tool_name in tool_call_tracker:
                            tool_message = ToolMessage(
                                content="Documentation already generated.",
                                tool_call_id=tool_call["id"]
                            )
                            messages.append(tool_message)
                            continue
                        tool_call_tracker[tool_name] = True

                    if verbose:
                        print(f"Calling: {tool_name}({tool_args})")

                    if tool_name in self.tools_dict:
                        result = self.tools_dict[tool_name].invoke(tool_args)

                        # Capture PDF path if returned
                        if isinstance(result, dict):
                            pdf_path = result.get("pdf_path") or pdf_path

                        if verbose:
                            if isinstance(result, dict):
                                msg = result.get("message", result.get("output", str(result)))
                                print(f"  → {msg}\n")
                            else:
                                print(f"  → {result}\n")

                        tool_message = ToolMessage(
                            content=str(result),
                            tool_call_id=tool_call["id"]
                        )
                        messages.append(tool_message)
                    else:
                        error_msg = f"Tool '{tool_name}' not found in available tools."
                        if verbose:
                            print(f"  ⚠ {error_msg}\n")
                        tool_message = ToolMessage(
                            content=error_msg,
                            tool_call_id=tool_call["id"]
                        )
                        messages.append(tool_message)

        except Exception as e:
            final_response = f"Error: {str(e)}"
            if verbose:
                print(f"\n{final_response}\n")

        if verbose:
            print("Done.\n")

        # Append PDF path to response if generated
        if pdf_path and pdf_path not in (final_response or ""):
            suffix = f"\n\n📄 PDF generated at: {pdf_path}"
            final_response = (final_response or "Documentation generated.") + suffix

        return final_response or "No response generated."