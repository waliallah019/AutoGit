"""Basic Git Tools - Simple Git Operations"""
import subprocess
from langchain_core.tools import tool


@tool
def git_add() -> dict:
    """Stage all repository changes for commit.
    
    Returns:
        Dictionary with status and message about the staging operation.
    """
    result = subprocess.run(['git', 'add', '-A'], capture_output=True, text=True)
    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip() or "git add failed"
        return {"status": "error", "message": f"❌ {error_msg}"}

    return {"status": "success", "message": "✅ All changes staged"}


@tool
def git_branch_rename(new_name: str) -> dict:
    """Rename the current branch to a new name.
    
    Args:
        new_name: The new name for the current branch.
    
    Returns:
        Dictionary with status and message about the branch rename operation.
    """
    result = subprocess.run(['git', 'branch', '-M', new_name], capture_output=True, text=True)
    return {"status": "success", "message": f"✅ Branch renamed to: {new_name}"}


@tool
def git_remote_add(url: str) -> dict:
    """Add remote origin URL to the repository.
    
    Args:
        url: The GitHub repository URL to add as remote origin.
    
    Returns:
        Dictionary with status and message about the remote add operation.
    """
    subprocess.run(['git', 'remote', 'remove', 'origin'], capture_output=True, text=True)
    result = subprocess.run(['git', 'remote', 'add', 'origin', url], capture_output=True, text=True)
    return {"status": "success", "message": f"✅ Remote added: {url}"}


@tool
def git_push(branch: str = "main") -> dict:
    """Push code to the remote repository.
    
    Args:
        branch: The branch name to push. Defaults to "main".
    
    Returns:
        Dictionary with status and message about the push operation.
    """
    result = subprocess.run(['git', 'push', '-u', 'origin', branch], capture_output=True, text=True)
    if result.returncode == 0:
        return {"status": "success", "message": f"✅ Code pushed to origin/{branch}"}
    
    error_msg = result.stderr.strip()
    solution = ""
    
    # Analyze different push errors
    if "permission denied" in error_msg.lower() or "403" in error_msg:
        solution = """\n
💡 SOLUTION - Permission Denied:
   Problem: You don't have access to push to this repository
   
   Possible Causes:
   1. Wrong GitHub account credentials
   2. Not the repository owner
   3. Need to authenticate
   
   Fix:
   • Check whose account is configured:
     git config user.name
     git config user.email
   
   • Update to your GitHub username:
     git config user.name "YourGitHubUsername"
     git config user.email "your@email.com"
   
   • Clear cached credentials (Windows):
     In Control Panel > Credential Manager > Windows Credentials
     Remove any GitHub credentials and try again
   
   • Or use Personal Access Token:
     git remote set-url origin https://YOUR_TOKEN@github.com/username/repo.git"""
    
    elif "repository not found" in error_msg.lower() or "404" in error_msg:
        solution = """\n
💡 SOLUTION - Repository Not Found:
   • Repository doesn't exist on GitHub
   • Create it first: https://github.com/new
   • Then add remote: git remote set-url origin YOUR_REPO_URL"""
    
    elif "failed to push" in error_msg.lower() and "rejected" in error_msg.lower():
        solution = """\n
💡 SOLUTION - Push Rejected:
   • Remote has changes you don't have locally
   • Pull first: git pull origin main
   • Then push: git push origin main"""
    
    elif "no remote" in error_msg.lower() or "does not appear" in error_msg.lower():
        solution = """\n
💡 SOLUTION - No Remote Repository:
   • Add remote URL: git remote add origin YOUR_GITHUB_URL
   • Get URL from your GitHub repository"""
    
    return {"status": "error", "message": f"❌ Push failed: {error_msg}{solution}"}


@tool
def git_status() -> dict:
    """Check the current git repository status.
    
    Returns:
        Dictionary with status and output showing current repository state.
    """
    result = subprocess.run(['git', 'status', '--short'], capture_output=True, text=True)
    
    # If error (not a git repo)
    if result.returncode != 0:
        return {
            "status": "error", 
            "output": "❌ Not a git repository\n💡 Solution: Run 'git init' to initialize"
        }
    
    status_output = result.stdout.strip()
    
    if not status_output:
        # Check if there are commits
        log_result = subprocess.run(['git', 'log', '-1'], capture_output=True, text=True)
        if log_result.returncode != 0:
            return {
                "status": "success", 
                "output": "✅ Working tree clean (No commits yet)\n💡 Create your first commit!"
            }
        return {"status": "success", "output": "✅ Working tree clean"}
    
    # Parse and explain status
    lines = status_output.split('\n')
    explanation = "\n📊 Status Analysis:\n"
    
    for line in lines[:5]:  # Show first 5 files
        if line.startswith('??'):
            explanation += f"   🆕 Untracked: {line[3:]}\n"
        elif line.startswith('M '):
            explanation += f"   ✏️  Modified (staged): {line[3:]}\n"
        elif line.startswith(' M'):
            explanation += f"   ✏️  Modified (not staged): {line[3:]}\n"
        elif line.startswith('A '):
            explanation += f"   ➕ Added: {line[3:]}\n"
        elif line.startswith('D '):
            explanation += f"   ❌ Deleted: {line[3:]}\n"
    
    if len(lines) > 5:
        explanation += f"   ... and {len(lines) - 5} more files\n"
    
    return {"status": "success", "output": status_output + explanation}


@tool
def git_init() -> dict:
    """Initialize a new git repository in the current directory.
    
    Returns:
        Dictionary with status and message about the initialization.
    """
    result = subprocess.run(['git', 'init'], capture_output=True, text=True)
    return {"status": "success", "message": "✅ Repository initialized"}


@tool
def get_branch_info() -> dict:
    """Get the current branch name.
    
    Returns:
        Dictionary with status and the current branch name.
    """
    result = subprocess.run(['git', 'branch', '--show-current'], capture_output=True, text=True)
    return {"status": "success", "branch": result.stdout.strip() or "main"}


@tool
def diagnose_git_config() -> dict:
    """Diagnose Git configuration and identify any issues with user settings, remote, or branch.
    
    Returns:
        Dictionary with status, diagnostic message, configuration info, and whether issues were found.
    """
    issues = []
    warnings = []
    config_info = {}
    
    # Check user.name
    name_result = subprocess.run(['git', 'config', 'user.name'], capture_output=True, text=True)
    if name_result.returncode == 0 and name_result.stdout.strip():
        config_info['user.name'] = name_result.stdout.strip()
    else:
        issues.append("❌ Git user.name not configured")
        issues.append("   Fix: git config --global user.name \"Your Name\"")
    
    # Check user.email
    email_result = subprocess.run(['git', 'config', 'user.email'], capture_output=True, text=True)
    if email_result.returncode == 0 and email_result.stdout.strip():
        config_info['user.email'] = email_result.stdout.strip()
    else:
        issues.append("❌ Git user.email not configured")
        issues.append("   Fix: git config --global user.email \"your@email.com\"")
    
    # Check remote
    remote_result = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True, text=True)
    if remote_result.returncode == 0:
        config_info['remote.origin'] = remote_result.stdout.strip()
    else:
        warnings.append("⚠️  No remote repository configured")
        warnings.append("   Add: git remote add origin YOUR_REPO_URL")
    
    # Check current branch
    branch_result = subprocess.run(['git', 'branch', '--show-current'], capture_output=True, text=True)
    if branch_result.returncode == 0:
        config_info['current.branch'] = branch_result.stdout.strip() or "Not on any branch"
    
    # Build response
    message = "🔍 Git Configuration Diagnosis:\n\n"
    
    if config_info:
        message += "✅ Current Configuration:\n"
        for key, value in config_info.items():
            message += f"   • {key}: {value}\n"
        message += "\n"
    
    if issues:
        message += "🚨 Critical Issues Found:\n"
        for issue in issues:
            message += f"{issue}\n"
        message += "\n"
    
    if warnings:
        message += "⚠️  Warnings:\n"
        for warning in warnings:
            message += f"{warning}\n"
    
    if not issues and not warnings:
        message += "✅ All configurations look good!\n"
    
    return {
        "status": "success" if not issues else "warning",
        "message": message,
        "config": config_info,
        "has_issues": len(issues) > 0
    }


@tool
def validate_git_repository() -> dict:
    """Validate Git repository configuration and check if Git is initialized in the correct folder.
    
    This tool checks:
    - If Git is initialized in the current folder or a parent folder
    - The remote URL configuration
    - If the remote matches a different project
    
    Returns:
        Dictionary with validation status, issues found, and recommendations.
    """
    import os
    
    current_dir = os.getcwd()
    issues = []
    warnings = []
    info = {}
    
    # Check if Git is initialized
    git_check = subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'], 
                              capture_output=True, text=True)
    
    if git_check.returncode != 0:
        return {
            "status": "not_initialized",
            "message": "❌ Git is not initialized in this folder or any parent folder.\n💡 Initialize with: git init",
            "needs_action": True,
            "action": "initialize"
        }
    
    # Get Git root directory
    git_root = subprocess.run(['git', 'rev-parse', '--show-toplevel'], 
                             capture_output=True, text=True)
    
    if git_root.returncode == 0:
        git_root_path = git_root.stdout.strip().replace('/', os.sep)
        info['git_root'] = git_root_path
        info['current_dir'] = current_dir
        
        # Check if Git root is different from current directory
        if os.path.normpath(git_root_path) != os.path.normpath(current_dir):
            issues.append(f"⚠️  Git repository is initialized in a PARENT folder")
            issues.append(f"   📂 Git Root: {git_root_path}")
            issues.append(f"   📂 Current Folder: {current_dir}")
            issues.append("")
            issues.append("🤔 This means:")
            issues.append("   • Git is tracking files from the parent folder, not just this project")
            issues.append("   • Your commits may include unrelated files")
            issues.append("   • Remote URL might be for a different project")
            
            # Check remote URL
            remote_result = subprocess.run(['git', 'remote', 'get-url', 'origin'], 
                                          capture_output=True, text=True)
            if remote_result.returncode == 0:
                remote_url = remote_result.stdout.strip()
                info['remote_url'] = remote_url
                issues.append("")
                issues.append(f"   🔗 Current Remote: {remote_url}")
                
                # Extract repo name from URL
                if 'github.com' in remote_url:
                    repo_name = remote_url.split('/')[-1].replace('.git', '')
                    issues.append(f"   📦 Remote Repository: {repo_name}")
            
            message = "\n".join(issues)
            message += "\n\n❓ What would you like to do?\n"
            message += "   1️⃣  Keep using the parent folder's Git repository\n"
            message += "   2️⃣  Initialize a NEW Git repository in the current folder\n"
            message += "      (This will create a separate repo for this project only)\n"
            message += "\n💡 Recommendation: Initialize a new repository in the current folder\n"
            message += "   to keep this project separate from others."
            
            return {
                "status": "parent_repo_detected",
                "message": message,
                "needs_action": True,
                "action": "reinitialize",
                "info": info
            }
    
    # Check remote configuration
    remote_result = subprocess.run(['git', 'remote', 'get-url', 'origin'], 
                                  capture_output=True, text=True)
    if remote_result.returncode != 0:
        warnings.append("⚠️  No remote repository configured")
        warnings.append("💡 You'll need to add a remote before pushing")
    else:
        info['remote_url'] = remote_result.stdout.strip()
    
    # All good
    if not issues and not warnings:
        message = "✅ Git repository is properly configured!\n"
        if 'remote_url' in info:
            message += f"   🔗 Remote: {info['remote_url']}\n"
        message += f"   📂 Repository Root: {info.get('git_root', current_dir)}"
        return {
            "status": "valid",
            "message": message,
            "needs_action": False,
            "info": info
        }
    
    # Only warnings
    if warnings and not issues:
        message = "✅ Git repository structure is correct\n\n"
        message += "\n".join(warnings)
        return {
            "status": "valid_with_warnings",
            "message": message,
            "needs_action": False,
            "info": info
        }
    
    return {
        "status": "unknown",
        "message": "Unable to fully validate Git configuration",
        "needs_action": False
    }


@tool
def git_reinitialize() -> dict:
    """Reinitialize Git repository in the current folder.
    
    This will:
    1. Create a new Git repository in the current folder
    2. Remove connection to any parent repository
    3. Start fresh with no remote configured
    
    Returns:
        Dictionary with status and message about reinitialization.
    """
    import os
    
    current_dir = os.getcwd()
    
    # Initialize new Git repo in current folder
    result = subprocess.run(['git', 'init'], capture_output=True, text=True, cwd=current_dir)
    
    if result.returncode == 0:
        message = "✅ Git repository reinitialized successfully!\n\n"
        message += f"   📂 New Repository Location: {current_dir}\n"
        message += "   🔄 This folder now has its own Git repository\n"
        message += "   🎯 No remote configured (you'll need to add one before pushing)\n\n"
        message += "Next steps:\n"
        message += "   1. Create a new repository on GitHub\n"
        message += "   2. Add remote: git remote add origin YOUR_REPO_URL\n"
        message += "   3. Stage and commit your files\n"
        message += "   4. Push to GitHub"
        
        return {
            "status": "success",
            "message": message
        }
    else:
        return {
            "status": "error",
            "message": f"❌ Failed to reinitialize repository: {result.stderr.strip()}"
        }


@tool
def get_remote_url() -> dict:
    """Get the remote origin URL of the repository.
    
    Returns:
        Dictionary with status and the remote origin URL, or error message if not found.
    """
    result = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True, text=True)
    if result.returncode == 0:
        return {"status": "success", "url": result.stdout.strip()}
    return {
        "status": "error", 
        "url": None, 
        "message": "❌ No remote found\n💡 Solution: Add remote URL:\n   git remote add origin YOUR_GITHUB_REPO_URL"
    }
