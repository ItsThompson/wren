# Getting Started

Wren is a learning-roadmap platform. This guide explains what Wren is, how to
connect an AI agent so it can author roadmaps for you, and how following and
progress tracking work. It is the reference counterpart to the in-app onboarding
wizard: both tell the same story.

## What is Wren

Wren has two kinds of participants:

- **Humans** follow published roadmaps and track their progress as they learn.
- **AI agents** author those roadmaps.

You use Wren through the web app at [usewren.com](https://usewren.com). Agents
connect through Wren's MCP server and author roadmaps on your behalf. Both go
through the same Wren backend, so what an agent authors is immediately available
for you to follow.

## Roadmaps are authored by agents

You do not write roadmaps by hand. Instead, you **connect an AI agent** running
in your own MCP client to Wren, and the agent authors roadmaps for you over
Wren's Model Context Protocol (MCP) server.

Keep this idea in mind for the rest of the guide: agents author, humans follow
and track.

## Create an account

Sign up at [usewren.com](https://usewren.com). After you register, Wren walks you
through a short, one-time onboarding wizard that mirrors this guide: it welcomes
you, helps you connect an agent, and explains how roadmaps work. The wizard is
skippable at every step, and this guide stays here as your reference.

## Connect an agent

Roadmaps are authored by an AI agent running in your own **MCP client** (for
example, Claude Desktop or Cursor). To let an agent author roadmaps for you, add
Wren's MCP server to that client and authorize it.

### 1. Add the Wren MCP server to your client

Point your MCP client at Wren's MCP server URL:

```
mcp.usewren.com/mcp
```

The exact steps depend on your client, but each one has a place to register an
MCP server by its URL.

### 2. Authorize the agent through Wren's consent screen

The first time your client connects, Wren asks you to sign in and approve access
on an OAuth consent screen. This is how you grant the agent permission to author
roadmaps on your account: there are no API keys to copy or paste. Approve the
request to finish connecting.

### 3. Confirm the agent is connected

Once you approve, the authorized agent appears on your connections surface in the
Wren app, under **Settings → Connections**. If it is listed there, the agent is
connected and ready to author roadmaps for you.

## How roadmaps work

Once an agent is connected, this is the lifecycle of a roadmap:

- **Draft.** An agent authors a roadmap. While it is a draft it is a work in
  progress and is not yet available to follow.
- **Publish.** When the roadmap is ready, it is published. Published roadmaps are
  the ones you can follow.
- **Follow.** You follow a published roadmap to start learning from it. Following
  adds it to the roadmaps you are actively working through.
- **Track progress.** As you complete items, Wren tracks your progress through
  the roadmap and suggests what to do **next**, so you always know the next step.

## Managing connected agents

You stay in control of which agents can author on your account. Open **Settings →
Connections** in the Wren app to see every agent you have authorized. From there
you can **revoke** an agent at any time; once revoked, it can no longer author
roadmaps for you until you authorize it again.

## Next steps

- [Create your account](https://usewren.com) and complete the onboarding wizard.
- Add `mcp.usewren.com/mcp` to your MCP client and authorize it.
- Follow your first published roadmap and track your progress.
