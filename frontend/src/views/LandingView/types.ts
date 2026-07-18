import type { LucideIcon } from 'lucide-react'

/** One "How it works" step: an icon, a title, and a one-line explanation. */
export interface HowItWorksStepData {
  icon: LucideIcon
  title: string
  body: string
}

/** One dual-audience track: who the roadmap is for and what they do with it. */
export interface AudienceTrackData {
  icon: LucideIcon
  heading: string
  body: string
}

/** One FAQ entry: a question with a plain-language answer. */
export interface FaqItemData {
  question: string
  answer: string
}
