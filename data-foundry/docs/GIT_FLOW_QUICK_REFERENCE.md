# Git Flow Quick Reference Card

## Branch Overview

| Branch | Purpose | Base | Merge To |
|--------|---------|------|----------|
| `feature/frontend-development` | Parent feature | develop | develop |
| `feature/frontend-development-ui` | Next.js UI work | feature/frontend-development | feature/frontend-development |
| `feature/stripe-billing` | Stripe backend | feature/frontend-development | feature/frontend-development |

## Quick Commands

### Frontend Developer (UI Work)

```bash
# Setup
git checkout feature/frontend-development-ui
git pull origin feature/frontend-development-ui

# Daily work
git add src/components/MyComponent.tsx
git commit -m "feat(ui): add new component"
git push origin feature/frontend-development-ui

# Sync with parent
git fetch origin
git merge origin/feature/frontend-development
git push origin feature/frontend-development-ui
```

### Backend Developer (Billing Work)

```bash
# Setup
cd /home/carlos/projects/data_foundry/stripe-billing-wt
git pull origin feature/stripe-billing

# Daily work
git add app/routers/billing.py
git commit -m "feat(billing): add subscription endpoint"
git push origin feature/stripe-billing

# Sync with parent
git fetch origin
git merge origin/feature/frontend-development
git push origin feature/stripe-billing
```

### Team Lead (Merging)

```bash
# Merge UI to parent
git checkout feature/frontend-development
git pull origin feature/frontend-development
git merge --no-ff feature/frontend-development-ui
git push origin feature/frontend-development

# Merge Billing to parent
git merge --no-ff feature/stripe-billing
git push origin feature/frontend-development

# Merge to develop
git checkout develop
git pull origin develop
git merge --no-ff feature/frontend-development
git push origin develop
```

## Commit Message Templates

### Feature Addition
```
feat(scope): brief description

- Detailed point 1
- Detailed point 2

Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

### Bug Fix
```
fix(scope): brief description

- What was broken
- How it's fixed

Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

### Documentation
```
docs: update documentation

- Changes made

Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

## Conflict Resolution

```bash
# 1. Identify conflicts
git status

# 2. Edit conflicting files (remove <<<, ===, >>> markers)

# 3. Complete merge
git add <resolved-files>
git commit -m "chore: resolve merge conflicts"
git push origin <branch-name>
```

## Status Checks

```bash
# View current branch and status
git status

# View all branches
git branch -vv

# View commit history
git log --oneline --graph --decorate -10

# Check what's different from origin
git fetch origin
git diff origin/<branch-name>
```

## Emergency Commands

### Undo last commit (not pushed)
```bash
git reset --soft HEAD~1  # Keep changes
git reset --hard HEAD~1  # Discard changes
```

### Discard local changes
```bash
git checkout -- <file>    # Single file
git reset --hard HEAD     # All files
```

### Switch branch with uncommitted changes
```bash
git stash                 # Save changes
git checkout <branch>     # Switch branch
git stash pop            # Restore changes
```

## Worktree Commands

```bash
# List worktrees
git worktree list

# Switch to billing worktree
cd /home/carlos/projects/data_foundry/stripe-billing-wt

# Switch to main worktree
cd /home/carlos/projects/data_foundry/data-foundry
```

## Branch Protection Checklist

Before merging to `feature/frontend-development`:
- [ ] All tests passing locally
- [ ] Code reviewed by peer
- [ ] No merge conflicts with parent
- [ ] Commit messages follow convention
- [ ] Documentation updated if needed

Before merging to `develop`:
- [ ] Integration tests passing
- [ ] UI and Billing features tested together
- [ ] No breaking changes (or documented)
- [ ] Version bumped if applicable
- [ ] CHANGELOG updated

## Help Commands

```bash
# Get help on any git command
git help <command>

# View git configuration
git config --list

# View remote URLs
git remote -v

# View branch relationships
git show-branch develop feature/frontend-development feature/frontend-development-ui feature/stripe-billing
```

## Common Issues

| Issue | Solution |
|-------|----------|
| Branch behind origin | `git pull origin <branch>` |
| Merge conflict | Edit files, `git add`, `git commit` |
| Wrong branch | `git stash`, `git checkout <correct-branch>`, `git stash pop` |
| Need to undo commit | `git reset --soft HEAD~1` (not pushed) |
| Accidentally deleted file | `git checkout HEAD -- <file>` |

## Links

- Full workflow: `/home/carlos/projects/data_foundry/data-foundry/docs/GIT_FLOW_WORKFLOW.md`
- Branch diagrams: `/home/carlos/projects/data_foundry/data-foundry/docs/BRANCH_STRUCTURE_DIAGRAM.md`
- GitHub repo: `git@github.com:ai-rio/data-foundry.git`

---

**Print this out and keep it handy!**
