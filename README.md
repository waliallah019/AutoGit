# 🤖 AutoGit - AI-Powered Git Automation Extension

AutoGit is a VS Code extension that brings AI-powered Git automation to your fingertips. Powered by Groq's LLaMA model and LangChain, it intelligently handles Git operations, detects errors, and generates comprehensive documentation.

## ✨ Features

- **Smart Git Automation**: Push code, commit changes, and manage branches with AI guidance
- **Error Detection & Solutions**: Get intelligent error messages with actionable solutions
- **Code Documentation**: Auto-generate professional PDF documentation for your changes
- **Chat Interface**: Conversational Git assistant right in your VS Code sidebar
- **User Accounts**: Create an account, sign in, sign out, and keep chat sessions tied to your profile
- **Saved Chats**: Previous chats are stored per user and can be reopened from the sidebar
- **Multi-language Support**: Handles Python, JavaScript, TypeScript, and more

## 📋 Prerequisites

Before starting, ensure you have:

1. **Git** installed and configured
   - Download from [git-scm.com](https://git-scm.com/)
   - Configure your Git user: 
     ```bash
     git config --global user.name "Your Name"
     git config --global user.email "your.email@example.com"
     ```

2. **Python 3.10 or higher**
   - Download from [python.org](https://www.python.org/)
   - Verify: `python --version`

3. **Node.js 18 or higher**
   - Download from [nodejs.org](https://nodejs.org/)
   - Verify: `node --version`

4. **VS Code 1.85.0 or higher**
   - Download from [code.visualstudio.com](https://code.visualstudio.com/)

5. **Groq API Key** (Free tier available)
   - Sign up at [console.groq.com](https://console.groq.com/)
   - Get your free API key from the dashboard

6. **MongoDB Atlas account**
   - Create a free cluster at [mongodb.com/atlas](https://www.mongodb.com/atlas)
   - Create a database user and allow network access for your development machine

## 🚀 Quick Start

### Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/AutoGit.git
cd AutoGit
```

### Step 2: Set Up the Backend

Navigate to the Backend folder and install Python dependencies:

```bash
cd Backend

# Create a Python virtual environment (optional but recommended)
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

Create a `.env` file in the `Backend` folder:

```bash
# Backend/.env
GROQ_API_KEY=your_groq_api_key_here
MONGODB_URI=your_mongodb_atlas_connection_string
MONGODB_DB=autogit
JWT_SECRET=choose_a_long_random_secret
```

Replace `your_groq_api_key_here` with your actual Groq API key.
Replace `your_mongodb_atlas_connection_string` with your MongoDB Atlas connection string.
Use a long random value for `JWT_SECRET` so user sessions stay signed securely.

**Where to find your Groq API Key:**
1. Go to [console.groq.com](https://console.groq.com/)
2. Sign in or create an account
3. Navigate to "API Keys"
4. Click "Create API Key"
5. Copy and paste it into the `.env` file

### Step 4: Start the Backend Server

From the `Backend` folder (with virtual environment activated if you created one):

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

You should see output like:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

Keep this terminal running while you use the extension.

### Step 5: Set Up the Frontend Extension

In a new terminal, navigate to the Frontend folder:

```bash
cd Frontend

# Install Node dependencies
npm install

# Compile TypeScript to JavaScript
npm run compile

# (Optional) Watch for changes during development
npm run watch
```

### Step 6: Load the Extension in VS Code

1. **Open VS Code**
2. **Open the Frontend folder** as a workspace:
   - File → Open Folder → Select the `Frontend` folder
3. **Launch the extension in debug mode**:
   - Press `F5` or go to Run → Start Debugging
   - A new VS Code window will open with the extension loaded
4. **Open the AutoGit view**:
   - Look for the AutoGit icon in the VS Code Activity Bar (left sidebar)
   - Click it to see the chat interface
5. **Start using AutoGit**!

When the sidebar opens, AutoGit checks whether you already have a saved session. If you are signed in, it shows the chat workspace, previous chat buttons, and sign-out controls. If you are not signed in, it asks you to create an account or sign in first.

## 📖 Usage

### Basic Commands

Once the extension is loaded, you can interact with AutoGit using natural language commands in the chat:

```
"push my code" 
→ Pushes your staged changes to GitHub with smart error handling

"generate docs"
→ Creates a detailed PDF documentation of your recent changes

"check status"
→ Shows the current Git status and repository information

"diagnose"
→ Analyzes your Git configuration and identifies issues
```

### Workflow Example

1. Make changes to your code
2. In the AutoGit chat, type: `"push my code"`
3. The AI will:
   - Validate your repository
   - Stage your changes
   - Generate documentation
   - Commit with a meaningful message
   - Push to GitHub
4. A PDF report will be generated and a link will appear in the chat
5. Click the "Open PDF" button to view the documentation

### Account Flow

1. Open the AutoGit sidebar in VS Code.
2. If you are new, create an account with email, password, and optional username.
3. If you already have an account, sign in instead.
4. Your chat sessions are stored in MongoDB Atlas and reappear as previous chat buttons.
5. Use the sign-out button to clear the current session from the extension.

## 🛠️ Project Structure

```
AutoGit/
├── Backend/
│   ├── main.py              # FastAPI server
│   ├── agent.py             # AI agent using LangChain & Groq
│   ├── requirements.txt      # Python dependencies
│   ├── .env                  # Your Groq API key (create this)
│   └── tools/
│       ├── git_command_tools.py
│       ├── commit_tool.py
│       ├── documentation_tool.py
│       └── merge_conflict_tool.py
│
├── Frontend/
│   ├── src/
│   │   ├── extension.ts      # VS Code extension entry point
│   │   └── chatViewProvider.ts # Chat UI implementation
│   ├── media/
│   │   ├── script.js         # Frontend chat logic
│   │   ├── styles.css        # Chat UI styling
│   │   └── icon.svg          # Extension icon
│   ├── package.json
│   ├── tsconfig.json
│   └── out/                  # Compiled JavaScript (generated)
│
└── README.md                 # This file
```

## 🔧 Troubleshooting

### "Connection error" or "Request timed out"

**Problem**: Frontend can't reach the backend

**Solution**:
1. Make sure the backend is running: `uvicorn main:app --reload --host 127.0.0.1 --port 8000`
2. Check that no other service is using port 8000
3. If the issue persists, check the AutoGit Output Channel in VS Code:
   - View → Output → Select "AutoGit" from dropdown

### "GROQ_API_KEY is not configured"

**Problem**: Backend can't find your Groq API key

**Solution**:
1. Create a `.env` file in the `Backend` folder (if not done)
2. Add your Groq API key: `GROQ_API_KEY=your_key_here`
3. Restart the backend server

### "Not a git repository"

**Problem**: AutoGit can't find a Git repository

**Solution**:
1. Make sure you're in a Git repository: `git status`
2. If not, initialize one: `git init`
3. Configure Git user (if not done globally):
   ```bash
   git config user.name "Your Name"
   git config user.email "your.email@example.com"
   ```

### "Failed to compile" or TypeScript errors

**Problem**: Frontend compilation failed

**Solution**:
1. Make sure Node.js is installed: `node --version`
2. Delete `node_modules` folder: `rm -r node_modules` (Windows: `rmdir /s node_modules`)
3. Reinstall dependencies: `npm install`
4. Try compiling again: `npm run compile`

## 📚 Development Tips

### Running in Watch Mode

**Frontend**: Press `F5` to start VS Code in debug mode. The extension will automatically reload when you make changes.

**Backend**: The `--reload` flag makes uvicorn auto-reload on file changes.

### Viewing Backend Logs

The backend prints detailed operation logs. Check the backend terminal to see:
- Git operations being performed
- LLM processing steps
- PDF generation progress
- Error details

### Viewing Frontend Logs

In VS Code:
1. Open Output panel: View → Output
2. Select "AutoGit" from the dropdown
3. See HTTP requests, errors, and debug info

## 📦 Dependencies

### Backend
- **FastAPI**: Modern Python web framework
- **LangChain**: AI/ML orchestration framework
- **Langchain-Groq**: Groq LLM integration
- **python-dotenv**: Environment variable management
- **ReportLab**: PDF generation
- **Uvicorn**: ASGI server

### Frontend
- **VS Code API**: Extension development
- **TypeScript**: Type-safe JavaScript

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Commit with clear messages
5. Push and open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

If you encounter issues:

1. Check the [Troubleshooting](#-troubleshooting) section
2. Check the AutoGit Output Channel (View → Output → AutoGit)
3. Open an issue on GitHub with:
   - Error message
   - Steps to reproduce
   - Your environment (OS, VS Code version, Python version)

## 🎯 Roadmap

- [ ] Support for multiple Git remotes
- [ ] Advanced merge conflict resolution UI
- [ ] Branch comparison and visualization
- [ ] Commit history exploration
- [ ] Integration with GitHub Issues
- [ ] Custom prompt templates
- [ ] Multi-language LLM models

---

## 🚀 Advanced Setup (Docker)

To run the backend in Docker:

```bash
cd Backend
docker build -t autogit-backend .
docker run -p 8000:8000 -e GROQ_API_KEY=your_key autogit-backend
```

## 📝 Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `GROQ_API_KEY` | Your Groq API key (required) | `gsk_xxxxxx` |

---

**Happy coding!** 🎉
