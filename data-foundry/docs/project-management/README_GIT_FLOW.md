# Git Flow Documentation Index

This directory contains comprehensive Git Flow workflow documentation for Data Foundry parallel development.

## Quick Start

New to the project? Start here:
1. Read [GIT_FLOW_SETUP_SUMMARY.md](./GIT_FLOW_SETUP_SUMMARY.md) - Overview and handoff instructions
2. Check [BRANCH_STRUCTURE_DIAGRAM.md](./BRANCH_STRUCTURE_DIAGRAM.md) - Visual branch hierarchy
3. Keep [GIT_FLOW_QUICK_REFERENCE.md](./GIT_FLOW_QUICK_REFERENCE.md) handy for daily commands

## Documentation Files

### 1. GIT_FLOW_SETUP_SUMMARY.md
**Read this first** - Complete setup summary with handoff instructions

**Contents**:
- Setup overview and validation checklist
- Branch configuration details
- Developer handoff commands
- Merge strategy overview
- Next steps and recommendations

**Best for**: Team leads, new developers joining the project

### 2. GIT_FLOW_WORKFLOW.md
**Comprehensive reference** - Detailed workflow documentation

**Contents**:
- Complete Git Flow conventions
- Detailed developer workflows (frontend, backend, team lead)
- Merge sequence plans
- Conflict resolution guides
- Branch protection rules
- CI/CD integration
- Best practices and troubleshooting

**Best for**: Deep dives, understanding the complete workflow, troubleshooting issues

### 3. BRANCH_STRUCTURE_DIAGRAM.md
**Visual reference** - ASCII diagrams and flow charts

**Contents**:
- Branch hierarchy diagrams
- Timeline flows
- Commit flow visualizations
- Worktree structure
- Merge dependency chains
- Developer swimlanes
- State machines

**Best for**: Understanding branch relationships, planning merges, presentations

### 4. GIT_FLOW_QUICK_REFERENCE.md
**Daily use** - Quick command reference card

**Contents**:
- Essential commands for each role
- Commit message templates
- Quick conflict resolution
- Status check commands
- Emergency commands
- Common issues and solutions

**Best for**: Daily development work, quick lookups, printing as reference card

## Branch Overview

```
main (production)
  |
develop (integration)
  |
feature/frontend-development (parent)
  |
  +-- feature/frontend-development-ui (Next.js UI)
  +-- feature/stripe-billing (Stripe backend)
```

## Role-Based Quick Links

### Frontend Developer
1. Start with: [Developer Handoff - Frontend](./GIT_FLOW_SETUP_SUMMARY.md#for-frontend-developer-ui-work)
2. Daily commands: [Quick Reference - Frontend](./GIT_FLOW_QUICK_REFERENCE.md#frontend-developer-ui-work)
3. Detailed workflow: [Workflow - Frontend Developer](./GIT_FLOW_WORKFLOW.md#frontend-developer-featurefrontend-development-ui)

### Backend Developer
1. Start with: [Developer Handoff - Backend](./GIT_FLOW_SETUP_SUMMARY.md#for-backend-developer-billing-work)
2. Daily commands: [Quick Reference - Backend](./GIT_FLOW_QUICK_REFERENCE.md#backend-developer-billing-work)
3. Detailed workflow: [Workflow - Backend Developer](./GIT_FLOW_WORKFLOW.md#backend-developer-featurestripe-billing)

### Team Lead
1. Start with: [Developer Handoff - Team Lead](./GIT_FLOW_SETUP_SUMMARY.md#for-team-lead-merging)
2. Merge strategy: [Merge Sequence Plan](./GIT_FLOW_WORKFLOW.md#merge-sequence-plan)
3. Visual flow: [Merge Dependency Chain](./BRANCH_STRUCTURE_DIAGRAM.md#merge-dependency-chain)

## Common Tasks

### Starting Work on a Feature
```bash
# Frontend UI
git checkout feature/frontend-development-ui
git pull origin feature/frontend-development-ui

# Backend Billing
cd /home/carlos/projects/data_foundry/stripe-billing-wt
git pull origin feature/stripe-billing
```

### Committing Changes
```bash
git add <files>
git commit -m "feat(scope): description

- Details

Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
git push origin <branch-name>
```

### Syncing with Parent Feature
```bash
git fetch origin
git merge origin/feature/frontend-development
git push origin <branch-name>
```

### Checking Status
```bash
git status                           # Current branch status
git branch -vv                       # All branches with tracking
git log --oneline --graph --all -10  # Visual branch history
```

## Getting Help

1. **Quick questions**: Check [GIT_FLOW_QUICK_REFERENCE.md](./GIT_FLOW_QUICK_REFERENCE.md)
2. **Workflow questions**: See [GIT_FLOW_WORKFLOW.md](./GIT_FLOW_WORKFLOW.md)
3. **Visual understanding**: Review [BRANCH_STRUCTURE_DIAGRAM.md](./BRANCH_STRUCTURE_DIAGRAM.md)
4. **Setup questions**: Read [GIT_FLOW_SETUP_SUMMARY.md](./GIT_FLOW_SETUP_SUMMARY.md)

## Repository Information

- **GitHub**: git@github.com:ai-rio/data-foundry.git
- **Main Directory**: /home/carlos/projects/data_foundry/data-foundry
- **Billing Worktree**: /home/carlos/projects/data_foundry/stripe-billing-wt

## Last Updated

**Date**: 2025-12-24
**Status**: Setup Complete - Ready for Development

---

**Need to update this documentation?**
Coordinate with the team to keep workflow documentation in sync with actual practices.
