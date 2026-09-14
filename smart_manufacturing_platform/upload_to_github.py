import os
import sys
import json
import base64
import urllib.request
import urllib.error

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(PROJECT_DIR, ".env")

def load_env():
    # Check .env in current folder or home directory
    paths = [ENV_FILE, os.path.expanduser("~/.env")]
    for p in paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip("'\""))

def github_request(url, token, data=None, method=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Aero-MES-Deployer"
    }
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_body)
            raise RuntimeError(f"GitHub API error {e.code}: {err_json.get('message', err_body)}")
        except Exception:
            raise RuntimeError(f"GitHub API error {e.code}: {err_body}")

def get_repo_files(base_dir):
    ignore_dirs = {"__pycache__", ".git", ".idea", ".vscode", ".system_generated"}
    ignore_files = {".env", "factory.db", "upload_to_github.py"}
    ignore_exts = {".pyc", ".zip", ".log"}

    files_to_upload = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for f in files:
            if f in ignore_files:
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in ignore_exts:
                continue
            abs_path = os.path.join(root, f)
            rel_path = os.path.relpath(abs_path, base_dir).replace("\\", "/")
            files_to_upload.append((rel_path, abs_path))
    return files_to_upload

def main():
    load_env()
    token = os.environ.get("GITHUB_TOKEN")
    repo_input = os.environ.get("GITHUB_REPO", "smart-manufacturing-platform")

    if not token:
        print("ERROR: GITHUB_TOKEN is not set.")
        print(f"Please add GITHUB_TOKEN to {ENV_FILE} or set the GITHUB_TOKEN environment variable.")
        sys.exit(1)

    print("Authenticating with GitHub...")
    user_data = github_request("https://api.github.com/user", token)
    username = user_data["login"]
    print(f"Logged in as: {username}")

    if "/" in repo_input:
        owner, repo_name = repo_input.split("/", 1)
    else:
        owner, repo_name = username, repo_input

    # Check or create repo
    print(f"Checking repository '{owner}/{repo_name}'...")
    repo_exists = True
    try:
        repo_data = github_request(f"https://api.github.com/repos/{owner}/{repo_name}", token)
    except RuntimeError:
        repo_exists = False

    if not repo_exists:
        print(f"Creating repository '{repo_name}' on GitHub...")
        repo_data = github_request(
            "https://api.github.com/user/repos",
            token,
            data={
                "name": repo_name,
                "description": "Smart Manufacturing & Production Control Platform (AERO-MES 4.0)",
                "private": False,
                "auto_init": False
            }
        )
        print(f"Repository created: {repo_data['html_url']}")
    else:
        print(f"Found existing repository: {repo_data['html_url']}")

    # Collect project files
    files = get_repo_files(PROJECT_DIR)
    print(f"Preparing {len(files)} files for commit...")

    tree_entries = []
    for rel_path, abs_path in files:
        with open(abs_path, "rb") as f:
            content_bytes = f.read()
        b64_content = base64.b64encode(content_bytes).decode("utf-8")
        blob = github_request(
            f"https://api.github.com/repos/{owner}/{repo_name}/git/blobs",
            token,
            data={"content": b64_content, "encoding": "base64"}
        )
        tree_entries.append({
            "path": rel_path,
            "mode": "100644",
            "type": "blob",
            "sha": blob["sha"]
        })
        print(f"  + {rel_path}")

    # Create tree
    print("Creating Git tree...")
    tree = github_request(
        f"https://api.github.com/repos/{owner}/{repo_name}/git/trees",
        token,
        data={"tree": tree_entries}
    )

    # Get latest commit of default branch if exists
    default_branch = repo_data.get("default_branch", "main")
    parent_commits = []
    try:
        ref_data = github_request(f"https://api.github.com/repos/{owner}/{repo_name}/git/ref/heads/{default_branch}", token)
        parent_commits.append(ref_data["object"]["sha"])
    except RuntimeError:
        pass

    # Create commit
    print("Creating commit...")
    commit_data = {
        "message": "Initial commit: Smart Manufacturing & Production Control Platform (AERO-MES 4.0)",
        "tree": tree["sha"],
        "parents": parent_commits
    }
    commit = github_request(
        f"https://api.github.com/repos/{owner}/{repo_name}/git/commits",
        token,
        data=commit_data
    )

    # Update or create branch ref
    if parent_commits:
        print(f"Updating branch '{default_branch}'...")
        github_request(
            f"https://api.github.com/repos/{owner}/{repo_name}/git/refs/heads/{default_branch}",
            token,
            data={"sha": commit["sha"], "force": True},
            method="PATCH"
        )
    else:
        print("Creating branch 'main'...")
        github_request(
            f"https://api.github.com/repos/{owner}/{repo_name}/git/refs",
            token,
            data={"ref": "refs/heads/main", "sha": commit["sha"]}
        )

    print("\n" + "=" * 60)
    print("  SUCCESSFULLY UPLOADED TO GITHUB!")
    print(f"  Repository URL: {repo_data['html_url']}")
    print("=" * 60)

if __name__ == "__main__":
    main()
