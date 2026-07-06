# aif-explore — entry-point examples

Non-normative reading aid moved out of `SKILL.md`. These show the explore-mode stance in action for four common entry points. Diagram style is the point: visualize liberally.

## User brings a vague idea

```
User: I'm thinking about adding real-time collaboration

You: Real-time collab is a big space. Let me think about this...

      COLLABORATION SPECTRUM

      Awareness          Coordination         Sync
          |                   |                 |
          v                   v                 v
      +--------+         +--------+        +--------+
      |Presence|         |Cursors |        |  CRDT  |
      |  "3    |         | Multi  |        |Conflict|
      |online" |         | select |        |  free  |
      +--------+         +--------+        +--------+
          |                   |                 |
       trivial            moderate           complex

      Where's your head at?
```

## User brings a specific problem

```
User: The auth system is a mess

You: [reads codebase]

     +---------------------------------------------+
     |              CURRENT AUTH FLOW              |
     +---------------------------------------------+
                        |
          +-------------+-------------+
          v             v             v
     +---------+  +---------+  +---------+
     | Google  |  |  GitHub |  |  Email  |
     |  OAuth  |  |  OAuth  |  |  Magic  |
     +----+----+  +----+----+  +----+----+
          |             |             |
          +-------------+-------------+
                        v
                  +-----------+
                  |  Session  |
                  +-----+-----+
                        |
                        v
                  +-----------+
                  |   Perms   |
                  +-----------+

     I see three tangles. Which one's burning?
```

## User is stuck mid-implementation

```
User: /aif-explore add-auth-system
      The OAuth integration is more complex than expected

You: [reads plan from .hermes-dev/plans/add-auth-system.md]

     You're on task 4: "Implement OAuth flow"

     Let me trace what's involved...

     [draws diagram, explores options, suggests paths]

     Want to update the plan to reflect this?
     Or add a spike task to investigate?
```

## User wants to compare options

```
User: Should we use Postgres or SQLite?

You: Generic answer is boring. What's the context?

User: A CLI tool that tracks local dev environments

You: That changes everything.

     +---------------------------------------------+
     |         CLI TOOL DATA STORAGE               |
     +---------------------------------------------+

     Key constraints:
     * No daemon running
     * Must work offline
     * Single user

                  SQLite          Postgres
     Deployment   embedded ok     needs server no
     Offline      yes ok          no no
     Single file  yes ok          no no

     SQLite. Not even close.

     Unless... is there a sync component?
```
