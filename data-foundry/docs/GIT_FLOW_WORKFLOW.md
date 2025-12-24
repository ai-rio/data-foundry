# Git Flow Workflow - Data Foundry Parallel Development

## Branch Structure Overview

```
main (production)
  |
  +-- develop (integration)
       |
       +-- feature/frontend-development (parent feature)
            |
            +-- feature/frontend-development-ui (Next.js UI development)
            |
            +-- feature/stripe-billing (Stripe backend integration)
```

## Current Branch State

### Primary Branches
- **main**: Production-ready code (commit: 143c218)
- **develop**: Integration branch (commit: 6857827)

### Feature Branches

#### feature/frontend-development
- **Base**: develop
- **Purpose**: Parent feature branch for all frontend and backend modernization work
- **Current HEAD**: f58756f
- **Commits ahead of develop**: 10
- **Remote tracking**: origin/feature/frontend-development

#### feature/frontend-development-ui
- **Base**: feature/frontend-development
- **Purpose**: Next.js UI development (components, pages, routing)
- **Current HEAD**: f58756f
- **Developer**: Frontend Developer
- **Remote tracking**: origin/feature/frontend-development-ui
- **Merge target**: feature/frontend-development

#### feature/stripe-billing
- **Base**: feature/frontend-development
- **Purpose**: Stripe payment integration backend
- **Current HEAD**: f58756f
- **Developer**: Backend Developer
- **Remote tracking**: origin/feature/stripe-billing
- **Worktree**: /home/carlos/projects/data_foundry/stripe-billing-wt
- **Merge target**: feature/frontend-development

## Merge Strategy

### Phase 1: Parallel Development (Current)
```
feature/frontend-development-ui (UI work)
feature/stripe-billing (Backend work)
  |
  v
Both branches work independently
```

### Phase 2: Integration to Parent Feature
```
feature/frontend-development-ui --merge--> feature/frontend-development
feature/stripe-billing --merge--> feature/frontend-development
```

### Phase 3: Integration to Develop
```
feature/frontend-development --merge--> develop
```

### Phase 4: Release to Production
```
develop --merge--> main (via release/vX.Y.Z branch)
```

## Git Flow Conventions

### Branch Naming
- **Feature branches**: `feature/<descriptive-name>`
- **Release branches**: `release/vX.Y.Z`
- **Hotfix branches**: `hotfix/<descriptive-name>`

### Commit Message Format
```
<type>(<scope>): <description>

[optional body]

Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## Developer Workflows

### Frontend Developer (feature/frontend-development-ui)

#### Initial Setup
```bash
# Clone repository (if not already done)
git clone git@github.com:ai-rio/data-foundry.git
cd data-foundry

# Checkout UI development branch
git checkout feature/frontend-development-ui
git pull origin feature/frontend-development-ui
```

#### Daily Workflow
```bash
# Start work
git pull origin feature/frontend-development-ui

# Make changes to Next.js UI components
# ... work on components, pages, etc ...

# Stage and commit changes
git add src/components/NewComponent.tsx
git commit -m "feat(ui): add new dashboard component

- Implement responsive dashboard layout
- Add data visualization charts
- Integrate with API hooks

Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"

# Push to remote
git push origin feature/frontend-development-ui
```

#### Sync with Parent Feature
```bash
# Pull latest changes from parent feature branch
git fetch origin
git merge origin/feature/frontend-development

# Resolve conflicts if any
# ... resolve conflicts ...
git add .
git commit -m "chore: merge latest from feature/frontend-development"

# Push updates
git push origin feature/frontend-development-ui
```

#### Complete UI Development
```bash
# Ensure branch is up to date
git pull origin feature/frontend-development-ui

# Merge parent feature changes first
git merge origin/feature/frontend-development

# Switch to parent feature branch
git checkout feature/frontend-development
git pull origin feature/frontend-development

# Merge UI work
git merge --no-ff feature/frontend-development-ui

# Push to parent feature
git push origin feature/frontend-development
```

### Backend Developer (feature/stripe-billing)

#### Initial Setup
```bash
# Navigate to stripe-billing worktree
cd /home/carlos/projects/data_foundry/stripe-billing-wt

# Ensure branch is up to date
git pull origin feature/stripe-billing
```

#### Daily Workflow
```bash
# Navigate to worktree
cd /home/carlos/projects/data_foundry/stripe-billing-wt

# Start work
git pull origin feature/stripe-billing

# Make changes to Stripe integration
# ... implement billing endpoints, webhooks, etc ...

# Stage and commit changes
git add app/routers/billing.py
git commit -m "feat(billing): implement Stripe subscription management

- Add subscription creation endpoint
- Implement webhook handler for payment events
- Add usage-based billing calculations

Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"

# Push to remote
git push origin feature/stripe-billing
```

#### Sync with Parent Feature
```bash
# Pull latest changes from parent feature branch
git fetch origin
git merge origin/feature/frontend-development

# Resolve conflicts if any
# ... resolve conflicts ...
git add .
git commit -m "chore: merge latest from feature/frontend-development"

# Push updates
git push origin feature/stripe-billing
```

#### Complete Billing Development
```bash
# Ensure branch is up to date
git pull origin feature/stripe-billing

# Merge parent feature changes first
git merge origin/feature/frontend-development

# Switch to parent feature branch (main repo)
cd /home/carlos/projects/data_foundry/data-foundry
git checkout feature/frontend-development
git pull origin feature/frontend-development

# Merge billing work
git merge --no-ff feature/stripe-billing

# Push to parent feature
git push origin feature/frontend-development
```

## Merge Sequence Plan

### Step 1: Complete Individual Features
1. Frontend developer completes UI work on `feature/frontend-development-ui`
2. Backend developer completes Stripe integration on `feature/stripe-billing`
3. Both branches have passing tests

### Step 2: Sync with Parent Feature
```bash
# Both developers ensure their branches are synced
git fetch origin
git merge origin/feature/frontend-development
git push origin <their-branch-name>
```

### Step 3: Merge UI Work to Parent Feature
```bash
# Performed by: Frontend Developer or Team Lead
git checkout feature/frontend-development
git pull origin feature/frontend-development

# Run tests before merging
npm test  # or appropriate test command

# Merge with no-fast-forward to preserve history
git merge --no-ff feature/frontend-development-ui

# Push to remote
git push origin feature/frontend-development
```

### Step 4: Merge Billing Work to Parent Feature
```bash
# Performed by: Backend Developer or Team Lead
git checkout feature/frontend-development
git pull origin feature/frontend-development

# Run tests before merging
pytest  # or appropriate test command

# Merge with no-fast-forward to preserve history
git merge --no-ff feature/stripe-billing

# Push to remote
git push origin feature/frontend-development
```

### Step 5: Integration Testing
```bash
# On feature/frontend-development branch
# Run full integration tests
npm test
pytest
# ... any other test suites ...
```

### Step 6: Merge to Develop
```bash
# Performed by: Team Lead
git checkout develop
git pull origin develop

# Merge feature branch
git merge --no-ff feature/frontend-development

# Push to develop
git push origin develop
```

### Step 7: Cleanup (After Successful Merge)
```bash
# Delete local branches
git branch -d feature/frontend-development-ui
git branch -d feature/stripe-billing

# Delete remote branches
git push origin --delete feature/frontend-development-ui
git push origin --delete feature/stripe-billing

# Remove worktree (for stripe-billing)
git worktree remove /home/carlos/projects/data_foundry/stripe-billing-wt
```

## Conflict Resolution

### When Conflicts Occur

1. **Identify conflicting files**:
```bash
git status
```

2. **Open conflicting files** and look for conflict markers:
```
<<<<<<< HEAD
Your changes
=======
Incoming changes
>>>>>>> branch-name
```

3. **Resolve conflicts**:
   - Keep your changes, their changes, or merge both
   - Remove conflict markers
   - Test the resolved code

4. **Complete the merge**:
```bash
git add <resolved-files>
git commit -m "chore: resolve merge conflicts with <branch-name>"
git push origin <current-branch>
```

### Common Conflict Scenarios

#### Scenario 1: Both branches modified same file
- **Resolution**: Manually merge changes, ensure functionality is preserved
- **Test**: Run tests for affected modules

#### Scenario 2: Package dependencies conflict
- **Resolution**: Review package.json/requirements.txt, choose compatible versions
- **Test**: Run `npm install` or `pip install` to verify

#### Scenario 3: Database schema changes conflict
- **Resolution**: Coordinate with team, may need to create new migration
- **Test**: Run migrations on development database

## Branch Protection Rules (Recommended)

### For GitHub Repository

#### main branch
- Require pull request reviews before merging (2 reviewers)
- Require status checks to pass before merging
- Require branches to be up to date before merging
- Include administrators in restrictions
- Restrict force pushes
- Restrict deletions

#### develop branch
- Require pull request reviews before merging (1 reviewer)
- Require status checks to pass before merging
- Require branches to be up to date before merging
- Restrict force pushes

#### feature/frontend-development
- Require status checks to pass before merging
- Allow force pushes (for rebasing/cleanup)

## CI/CD Integration

### Automated Tests on Push
```yaml
# Triggers for each branch
feature/frontend-development-ui:
  - Run frontend tests (Jest, Vitest)
  - Run ESLint
  - Build Next.js application

feature/stripe-billing:
  - Run backend tests (pytest)
  - Run type checking (mypy)
  - Test Stripe webhook handlers

feature/frontend-development:
  - Run all tests (frontend + backend)
  - Integration tests
  - Build full application
```

### Pull Request Automation
- Automated code review (SonarQube, CodeClimate)
- Test coverage reports
- Bundle size analysis (for frontend)
- Security vulnerability scanning

## Best Practices

### DO
- Pull from origin before starting new work
- Write descriptive commit messages
- Keep feature branches small and focused
- Run tests before committing
- Sync with parent feature branch regularly (daily)
- Use `--no-ff` for merges to preserve history
- Delete branches after successful merge

### DON'T
- Push directly to main or develop
- Force push to shared branches (unless coordinating with team)
- Commit broken code
- Merge without running tests
- Leave branches unmerged for long periods
- Commit sensitive data (API keys, credentials)

## Troubleshooting

### Issue: Branch is behind origin
```bash
git pull origin <branch-name>
# Or if you want to preserve local commits
git fetch origin
git rebase origin/<branch-name>
```

### Issue: Accidentally committed to wrong branch
```bash
# Save work
git stash

# Switch to correct branch
git checkout <correct-branch>

# Apply stashed changes
git stash pop
```

### Issue: Need to undo last commit (not pushed)
```bash
# Keep changes in working directory
git reset --soft HEAD~1

# Discard changes completely
git reset --hard HEAD~1
```

### Issue: Merge conflict during rebase
```bash
# Resolve conflicts in files
# Then continue rebase
git add <resolved-files>
git rebase --continue

# Or abort rebase
git rebase --abort
```

## Quick Reference Commands

### Switch Between Branches
```bash
# Frontend UI work
git checkout feature/frontend-development-ui

# Backend billing work (worktree)
cd /home/carlos/projects/data_foundry/stripe-billing-wt

# Parent feature
git checkout feature/frontend-development

# Integration branch
git checkout develop
```

### View Branch Status
```bash
# Current branch status
git status

# View all branches
git branch -vv

# View branch relationships
git log --oneline --graph --all --decorate
```

### Sync with Remote
```bash
# Fetch all remote changes
git fetch origin

# Pull current branch
git pull origin <branch-name>

# View remote branches
git branch -r
```

## Support and Questions

For questions about this workflow:
1. Review this documentation
2. Check git status and branch relationships
3. Consult with team lead before force-pushing or deleting shared branches
4. Use `git log --graph` to visualize branch history

---

**Last Updated**: 2025-12-24
**Maintained By**: Data Foundry Development Team
