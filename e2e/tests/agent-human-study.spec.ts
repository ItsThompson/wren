import { expect, test } from '../fixtures/test'

import { completeOnboarding, registerAccount } from '../browser/auth'
import {
  createAgentStudyJourneyState,
  expectOverallProgress,
  expectTreeNodeState,
  openRoadmapFromDashboard,
  openRoadmapView,
  reloadStudyState,
  setRoadmapDeadline,
  toggleChecklistItem,
} from '../browser/roadmap'
import {
  authoringScopes,
  createAuthoringContext,
  runAuthoringJourney,
} from '../agent/scenarios/authoring-journey'

test.describe('agent-to-human study journey', () => {
  test('continues an official-client roadmap through the same browser account', async ({
    attemptIdentity,
    browserAccountFactory,
    agentFactory,
    roadmapIdentity,
  }) => {
    const account = await browserAccountFactory.create('study')
    await registerAccount(account.page, account)
    await completeOnboarding(account.page)

    const session = await agentFactory.create(account.page, authoringScopes())
    const authoringContext = createAuthoringContext(session, attemptIdentity, account.username)
    const authoringResult = await runAuthoringJourney(authoringContext, roadmapIdentity)
    const studyState = createAgentStudyJourneyState(
      authoringResult.metadataRead,
      authoringContext.state,
      '2099-12-31',
    )

    await openRoadmapFromDashboard(account.page, studyState)
    const [firstItem, secondItem] = studyState.prerequisiteItems
    await expect(account.page.getByRole('checkbox', { name: firstItem.text, exact: true })).toBeChecked()
    await expect(account.page.getByRole('checkbox', { name: secondItem.text, exact: true })).not.toBeChecked()
    await expectOverallProgress(account.page, 33)

    await setRoadmapDeadline(account.page, studyState)
    await toggleChecklistItem(account.page, firstItem, false, studyState.roadmapId)
    await expectOverallProgress(account.page, 0)
    await toggleChecklistItem(account.page, firstItem, true, studyState.roadmapId)
    await expectOverallProgress(account.page, 33)

    await openRoadmapView(account.page, 'Tree')
    await expectTreeNodeState(account.page, studyState.secondSubsectionTitle, 'locked')

    await openRoadmapView(account.page, 'List')
    await toggleChecklistItem(account.page, secondItem, true, studyState.roadmapId)
    await expectOverallProgress(account.page, 67)

    await openRoadmapView(account.page, 'Tree')
    await expectTreeNodeState(account.page, studyState.secondSubsectionTitle, 'available')

    await openRoadmapView(account.page, 'List')
    await reloadStudyState(account.page, studyState, studyState.prerequisiteItems)
    await expectOverallProgress(account.page, 67)

    await toggleChecklistItem(account.page, studyState.finalItem, true, studyState.roadmapId)
    await expectOverallProgress(account.page, 100)
    await expect(account.page.getByText('You’re all caught up. Nice work.', { exact: true })).toBeVisible()
  })
})
