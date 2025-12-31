# Data Foundry Branch Structure Diagram

## Visual Branch Hierarchy

```
                                    main
                                     |
                          (production releases)
                                     |
                                     |
                                  develop
                                     |
                          (integration branch)
                                     |
                                     |
                     feature/frontend-development (parent)
                                     |
                         (10 commits ahead of develop)
                                     |
                    +----------------+----------------+
                    |                                 |
                    |                                 |
    feature/frontend-development-ui      feature/stripe-billing
                    |                                 |
              (UI Development)                (Backend Billing)
                    |                                 |
         - Next.js components            - Stripe API integration
         - Pages & routing                - Subscription management
         - React hooks                    - Webhook handlers
         - Tailwind styling               - Payment processing
                    |                                 |
                    |                                 |
                    +----------------+----------------+
                                     |
                                     v
                     feature/frontend-development
                                     |
                              (after merge)
                                     |
                                     v
                                  develop
                                     |
                              (after merge)
                                     |
                                     v
                                    main
                          (via release/vX.Y.Z)
```

## Timeline Flow

```
Week 1-2: Parallel Development
┌─────────────────────────────────────────────────────┐
│                                                       │
│  feature/frontend-development-ui                     │
│  ├─ commit: Add dashboard components                 │
│  ├─ commit: Implement user profile UI                │
│  └─ commit: Add data visualization                   │
│                                                       │
│  feature/stripe-billing                              │
│  ├─ commit: Add billing endpoints                    │
│  ├─ commit: Implement webhook handlers               │
│  └─ commit: Add subscription management              │
│                                                       │
└─────────────────────────────────────────────────────┘

Week 3: Integration to Parent Feature
┌─────────────────────────────────────────────────────┐
│                                                       │
│  feature/frontend-development                        │
│  ├─ merge: feature/frontend-development-ui           │
│  ├─ test: Integration tests                          │
│  └─ merge: feature/stripe-billing                    │
│                                                       │
└─────────────────────────────────────────────────────┘

Week 4: Integration to Develop
┌─────────────────────────────────────────────────────┐
│                                                       │
│  develop                                             │
│  └─ merge: feature/frontend-development              │
│                                                       │
└─────────────────────────────────────────────────────┘

Week 5: Release to Production
┌─────────────────────────────────────────────────────┐
│                                                       │
│  release/v2.0.0 (from develop)                       │
│  ├─ QA testing                                       │
│  ├─ Bug fixes                                        │
│  └─ merge to main + tag v2.0.0                       │
│                                                       │
└─────────────────────────────────────────────────────┘
```

## Commit Flow Diagram

```
develop (6857827)
    |
    | [10 commits]
    v
feature/frontend-development (f58756f)
    |
    +-----------------------+
    |                       |
    |                       |
    v                       v
feature/frontend-        feature/stripe-
development-ui           billing
(f58756f)                (f58756f)
    |                       |
    | [UI commits]          | [Billing commits]
    v                       v
    |                       |
    |                       |
    +-----------+-----------+
                |
                v
    feature/frontend-development
            (merged)
                |
                v
            develop
                |
                v
            release/vX.Y.Z
                |
                v
              main
```

## Worktree Structure

```
/home/carlos/projects/data_foundry/
├── data-foundry/                    (main worktree)
│   └── .git/                        (git repository)
│       ├── Current branch: feature/frontend-development-ui
│       └── Working directory for UI development
│
└── stripe-billing-wt/               (linked worktree)
    ├── Current branch: feature/stripe-billing
    └── Working directory for billing development
```

## Merge Dependency Chain

```
Step 1: Complete Individual Work
┌─────────────────────────────────┐
│ feature/frontend-development-ui │  (Ready: Tests passing)
└─────────────────────────────────┘
            │
            v
┌─────────────────────────────────┐
│ feature/stripe-billing          │  (Ready: Tests passing)
└─────────────────────────────────┘

Step 2: Merge to Parent Feature (Order: UI first, then Billing)
            │
            v
┌─────────────────────────────────┐
│ Merge UI → feature/frontend-    │
│            development           │
└─────────────────────────────────┘
            │
            v
┌─────────────────────────────────┐
│ Run integration tests            │
└─────────────────────────────────┘
            │
            v
┌─────────────────────────────────┐
│ Merge Billing → feature/        │
│                 frontend-        │
│                 development      │
└─────────────────────────────────┘
            │
            v
┌─────────────────────────────────┐
│ Run full test suite              │
└─────────────────────────────────┘

Step 3: Merge to Develop
            │
            v
┌─────────────────────────────────┐
│ feature/frontend-development    │
│            ↓                     │
│         develop                  │
└─────────────────────────────────┘
            │
            v
┌─────────────────────────────────┐
│ Deploy to staging environment    │
└─────────────────────────────────┘

Step 4: Release
            │
            v
┌─────────────────────────────────┐
│ Create release/v2.0.0 from      │
│ develop                          │
└─────────────────────────────────┘
            │
            v
┌─────────────────────────────────┐
│ QA & Final Testing               │
└─────────────────────────────────┘
            │
            v
┌─────────────────────────────────┐
│ Merge to main + Tag v2.0.0       │
└─────────────────────────────────┘
            │
            v
┌─────────────────────────────────┐
│ Deploy to production             │
└─────────────────────────────────┘
```

## Developer Workflow Swimlanes

```
Frontend Developer               Backend Developer              Team Lead
      |                                |                            |
      | Checkout                       | Navigate to worktree       |
      | feature/frontend-              | /stripe-billing-wt         |
      | development-ui                 |                            |
      |                                |                            |
      v                                v                            |
┌──────────┐                     ┌──────────┐                      |
│ Work on  │                     │ Work on  │                      |
│ Next.js  │                     │ Stripe   │                      |
│ UI       │                     │ API      │                      |
└──────────┘                     └──────────┘                      |
      |                                |                            |
      | git commit                     | git commit                 |
      | git push                       | git push                   |
      |                                |                            |
      v                                v                            |
┌──────────┐                     ┌──────────┐                      |
│ Tests    │                     │ Tests    │                      |
│ pass on  │                     │ pass on  │                      |
│ CI/CD    │                     │ CI/CD    │                      |
└──────────┘                     └──────────┘                      |
      |                                |                            |
      | Notify: UI complete            | Notify: Billing complete   |
      +--------------------------------+                            |
                                       |                            |
                                       v                            v
                                       +----------------------┌──────────┐
                                                              │ Merge UI │
                                                              │ to parent│
                                                              └──────────┘
                                                                    |
                                                                    v
                                                              ┌──────────┐
                                                              │ Test     │
                                                              │ integration│
                                                              └──────────┘
                                                                    |
                                                                    v
                                                              ┌──────────┐
                                                              │ Merge    │
                                                              │ Billing  │
                                                              │ to parent│
                                                              └──────────┘
                                                                    |
                                                                    v
                                                              ┌──────────┐
                                                              │ Full test│
                                                              │ suite    │
                                                              └──────────┘
                                                                    |
                                                                    v
                                                              ┌──────────┐
                                                              │ Merge to │
                                                              │ develop  │
                                                              └──────────┘
```

## Current State Snapshot (2025-12-24)

```
Branch                              Commit   Status           Tracking
──────────────────────────────────────────────────────────────────────
main                                143c218  Protected        origin/main
develop                             6857827  Protected        origin/develop
feature/frontend-development        f58756f  Active           origin/feature/frontend-development
feature/frontend-development-ui     f58756f  NEW - Active     origin/feature/frontend-development-ui
feature/stripe-billing              f58756f  Active (worktree) origin/feature/stripe-billing

Commits ahead of develop:
feature/frontend-development: 10 commits
feature/frontend-development-ui: 10 commits (inherited)
feature/stripe-billing: 10 commits (inherited)
```

## Git Flow State Machine

```
                    [Start]
                       |
                       v
            ┌─────────────────┐
            │ Create Feature  │
            │ from develop    │
            └─────────────────┘
                       |
                       v
            ┌─────────────────┐
            │ Development     │◄────┐
            │ (commit/push)   │     │
            └─────────────────┘     │
                       |            │
                       v            │
            ┌─────────────────┐     │
            │ Tests Pass?     │     │
            └─────────────────┘     │
                 |         |        │
                Yes        No───────┘
                 |
                 v
            ┌─────────────────┐
            │ Code Review     │
            └─────────────────┘
                       |
                       v
            ┌─────────────────┐
            │ Approved?       │
            └─────────────────┘
                 |         |
                Yes        No
                 |         └──> [Address feedback] ───┐
                 |                                     │
                 v                                     │
            ┌─────────────────┐                        │
            │ Merge to Parent │                        │
            │ Feature         │                        │
            └─────────────────┘                        │
                       |                               │
                       v                               │
            ┌─────────────────┐                        │
            │ Integration     │                        │
            │ Tests Pass?     │                        │
            └─────────────────┘                        │
                 |         |                           │
                Yes        No───────────────────────────┘
                 |
                 v
            ┌─────────────────┐
            │ Merge to Develop│
            └─────────────────┘
                       |
                       v
                 [Complete]
```

---

**Last Updated**: 2025-12-24
**Purpose**: Visual reference for Data Foundry Git Flow workflow
