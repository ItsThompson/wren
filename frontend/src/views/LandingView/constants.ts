import { Bot, GraduationCap, MessageSquare, User, Waypoints } from 'lucide-react'

import type { AudienceTrackData, FaqItemData, HowItWorksStepData } from './types'

/** Plain-language category line for the hero: names what Wren *is* (AC5). */
export const HERO_SUBHEAD =
  'Wren is a learning-roadmap tool: tell it what you already know, and it builds the sequenced, prerequisite-aware path of what to learn next. Built for you and your AI agent.'

/**
 * Full node labels for the cropped hero screenshot (the fixed-width nodes clip
 * long titles in the raster, so the alt text carries the complete labels).
 */
export const HERO_VISUAL_ALT =
  'A Wren roadmap laid out as a prerequisite graph: Arrays & two pointers (done) unlocks Hashing & frequency maps (up next), then Recursion & backtracking and Graph traversal (locked).'

export const HOW_IT_WORKS_STEPS: HowItWorksStepData[] = [
  {
    icon: MessageSquare,
    title: 'Tell Wren what you already know',
    body: "Start from your real level: name the topic and where you're at, from first day to nearly fluent.",
  },
  {
    icon: Waypoints,
    title: 'Get a sequenced roadmap',
    body: 'Wren orders every concept by its prerequisites, so each step builds on the last instead of a flat checklist.',
  },
  {
    icon: GraduationCap,
    title: 'Learn in the right order',
    body: 'Work through one unlocked step at a time, and your AI agent can follow the very same roadmap.',
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
    body: 'Open the web app and learn interactively: check off what you finish and always see what unlocks next.',
  },
  {
    icon: Bot,
    heading: 'For your AI agent',
    body: 'Your AI agent can follow the same roadmap, so you and it stay in sync on one shared plan.',
  },
]

export const FAQ_ITEMS: FaqItemData[] = [
  {
    question: 'Do I need to be technical?',
    answer:
      'No. Wren works for any subject you can describe, from coding to cooking to music theory. If you can tell it what you want to learn, it can sequence a path.',
  },
  {
    question: "What's the AI-agent part?",
    answer:
      'The roadmap Wren builds is one your AI agent can read and follow too. You learn in the web app; your agent works from the identical plan, so the two of you never drift apart.',
  },
  {
    question: 'How does Wren decide the order?',
    answer:
      'It maps the prerequisites between concepts and sequences them so each step builds on what came before, rather than handing you a flat list.',
  },
  {
    question: 'Can I change the roadmap?',
    answer:
      "Yes. The roadmap is yours: mark what you already know and Wren re-sequences what's left so it always starts from where you are.",
  },
]

export const FOOTER_TAGLINE = 'Sequenced learning for you and your AI agent.'
