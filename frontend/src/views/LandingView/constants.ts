import { Bot, GraduationCap, MessageSquare, User, Waypoints } from 'lucide-react'

import type { AudienceTrackData, FaqItemData, HowItWorksStepData } from './types'

/**
 * The brand headline: the single Fraunces display moment (hero H1) and the
 * footer tagline share this one string.
 */
export const HERO_HEADLINE = 'Learn anything, in the right order.'

/** Plain-language category line for the hero: names what Wren *is* (AC5). */
export const HERO_SUBHEAD =
  'Wren is a learning-roadmap tool that considers what you already know and gives you the exact order to learn what you want next.'

/**
 * Subordinate setup expectation shown beneath the primary CTA: prepares the
 * visitor for the connect-your-agent step without adding a competing button.
 */
export const CTA_SETUP_MICROCOPY = 'Bring your own AI agent. Connecting it takes a few minutes.'

/**
 * Full node labels for the cropped hero screenshot (the fixed-width nodes clip
 * long titles in the raster, so the alt text carries the complete labels).
 */
export const HERO_VISUAL_ALT =
  'A Wren roadmap laid out as a prerequisite graph: Arrays & two pointers (done) unlocks Hashing & frequency maps (up next), then Recursion & backtracking and Graph traversal (locked).'

export const HOW_IT_WORKS_STEPS: HowItWorksStepData[] = [
  {
    icon: MessageSquare,
    title: 'Connect your AI agent',
    body: "Connect your AI agent and tell it what you want to learn and where you're starting.",
  },
  {
    icon: Waypoints,
    title: 'Get a roadmap built for you',
    body: 'Your agent turns your goal into a roadmap in Wren, ordering each concept so it builds on the ones before it.',
  },
  {
    icon: GraduationCap,
    title: 'Learn in the right order',
    body: "Wren provides the structure for your agent to tutor you through, so you learn each concept right when you're ready for it.",
  },
]

export const VALUE_PULL_QUOTE = "Every step is one you're ready for: never too easy, never too hard."

export const VALUE_BENEFIT =
  'Wren sequences each roadmap by what you can take on next, so you keep momentum instead of stalling on something too advanced or coasting through what you already know.'

export const VALUE_FOOTNOTE = 'Learning scientists call this your zone of proximal development.'

export const DUAL_AUDIENCE_TRACKS: AudienceTrackData[] = [
  {
    icon: User,
    heading: 'For you',
    body: 'Open the web app and learn: check off what you finish and always see what unlocks next.',
  },
  {
    icon: Bot,
    heading: 'For your AI agent',
    body: 'Your agent builds the roadmap and can drive study alongside you, working from the same plan you see, so the two of you never drift apart.',
  },
]

export const FAQ_ITEMS: FaqItemData[] = [
  {
    question: 'Do I need to be technical?',
    answer:
      "You don't need to be a developer, and Wren works for any subject you can describe, from coding to cooking to music theory. Just connect Wren's MCP to an AI agent you already use, and it builds your roadmap from there.",
  },
  {
    question: "What's the AI-agent part?",
    answer:
      "Wren's MCP provides your AI agent the right tools to create a structured approach to building your knowledge, using what it already knows about you and the goal you're after. You can follow and track that roadmap from the web, working from the same plan your agent does, so the two of you never drift apart.",
  },
  {
    question: 'How does Wren decide the order?',
    answer:
      "Your agent works out what each concept depends on, then sequences your learning to start from what you already know and expand from there, skipping what you've already covered and filling only the gaps.",
  },
]
