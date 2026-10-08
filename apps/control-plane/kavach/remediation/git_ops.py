import subprocess
import os

class GitOpsAdapter:
    def __init__(self, repo_path: str | None = None):
        self.repo_path = repo_path or os.getcwd()
        self.branch_name = "kavach/ops"

    def _run_git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_path,
            check=False,
            capture_output=True,
            text=True
        )

    def checkout_ops_branch(self) -> tuple[bool, str]:
        """Ensures we are on kavach/ops branch."""
        # Check current branch
        res = self._run_git("branch", "--show-current")
        if res.returncode == 0 and res.stdout.strip() == self.branch_name:
            return True, "Already on kavach/ops"

        # Check if branch exists
        res = self._run_git("show-branch", self.branch_name)
        if res.returncode == 0:
            # Branch exists, just checkout
            res = self._run_git("checkout", self.branch_name)
        else:
            # Create and checkout
            res = self._run_git("checkout", "-b", self.branch_name)
            
        if res.returncode == 0:
            return True, "Successfully checked out kavach/ops"
        return False, f"Failed to checkout kavach/ops: {res.stderr}"

    def commit_changes(self, file_path: str, message: str) -> tuple[bool, str]:
        """Stages a specific file and commits it."""
        res_add = self._run_git("add", file_path)
        if res_add.returncode != 0:
            return False, f"Failed to git add: {res_add.stderr}"
            
        res_commit = self._run_git("commit", "-m", message)
        if res_commit.returncode == 0:
            return True, f"Committed: {res_commit.stdout}"
        
        # If there's nothing to commit, return True but note it
        if "nothing to commit" in res_commit.stdout.lower() or "no changes added" in res_commit.stdout.lower():
            return True, "No changes to commit"
            
        return False, f"Failed to commit: {res_commit.stderr}"
