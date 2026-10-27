# Unbuilt features

These are capabilities the app doesn't have yet, found during QA. They are not bugs: the app works as built, but a consultant needs these for real engagements.

Most came from the Kestrel Shield test engagement (QA, October 2026). Bugs found in the same run are fixed in code, not listed here.

Each entry says what is missing and why it matters.

## People and roles

- **Participants who are not directors.** Example: the Company Secretary, who the client wants to rate board processes and the Chair. There is no way to give such a participant a role, so the selection rules block every question for them. The question bank already has items for the Company Secretary as a rater.
- **Manually linking a participant to a board member.** This is needed when the participant's email differs from the one on the board record, for example a personal address. At the moment the participant stays "Not linked" for good.
- **Removing or merging a participant.** This is for one registered twice, or by mistake, before they have answered anything.
- **Separate role and category.** "Governance role" holds both the role and the category, so the Chairman can't also be recorded as a non-executive director.
- **Dated role history.** For example, an ED Finance who became MD/CEO part-way through the year.

## Dated history

- **Resignation date for a director.** Today the only option is Deactivate, which records no date.
- **Committee membership start and end dates.** This would also allow linking an inactive or former director to a committee they sat on during the review period.
- **More committee membership types:** "attends by invitation", and "unconfirmed" (the client has said so but hasn't sent the resolution). Today the only roles are Member and Chair.

## Extraction

- **Propose board members from company documents** (annual report, director profiles). Today directors are entered by hand.
- **Per-director extraction without uploading the same file again** for each director.
- **Flag name spelling differences** between documents and the board record, for example a hyphenated surname written without the hyphen.
- **Compare board size with the Board tab.** The board-size fact on the Profile tab should be checked against the directors actually recorded, and the app should show how many people served during the review period.
- **Month-only dates** such as "joined the Board in July 2020". Dates are stored as full dates, so extraction leaves these out rather than invent a day. Store the precision with the date.
- **Choose a different source for a corrected fact.** This includes "client brief" and "consultant knowledge" as sources.

## Question selection

- **Mid-year joiners.** Compare a director's appointment date with the review period. Don't ask about events before they joined, and say they are rating only part of the year.
- **Committee type in rules.** Some committee items (for example executive KPI assessment and ED succession) should go only to the committees that handle those topics.
- **Tenure limits from the governance codes or the board charter,** instead of a fixed 9 years. Example: a charter allowing 8 years for INEDs and 12 for NEDs.
- **Plain-language rule builder** in the question bank, to replace the raw JSON conditions.
- **Show timing assumptions** for each answer type next to the time estimate.

## Old screens

These belong to the old question flow. Retire them once assembled sets drive invites and the portal, rather than polishing them:

- **Tracks:** contradicts the question bank (who rates the Chair) and shows every track as "Not included".
- **Responses and export:** uses developer wording such as "seed demo responses" and "header questionnaire".
- **Workspace menu:** "Soft reset" and "Reset workspace…" don't say what they reset.
