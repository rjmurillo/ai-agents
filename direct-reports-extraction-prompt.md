# Direct Reports Information Extraction Prompt

## Objective

Extract and consolidate information about my direct reports from Loop workspace, Microsoft Teams (meetings and chats), and Azure DevOps work items for the last 365 days. Output everything in portable Markdown format for archival and analysis.

## Scope and Time Range

- **Time Range**: Last 365 days from today's date
- **Data Sources**:
  - Microsoft Loop workspace
  - Microsoft Teams (meetings and chats)
  - Azure DevOps (work items assigned to direct reports)
- **Output Format**: Structured Markdown files

## Direct Reports List

Before beginning extraction, identify all direct reports by:

1. Checking organizational hierarchy in the directory
2. Listing each direct report with:
   - Full name
   - Email address
   - Role/Title
   - Start date of reporting relationship (if within last 365 days)

Output this as a preliminary section.

## Extraction Instructions

### 1. Loop Workspace Data

For each direct report, extract:

**Collaborative Documents:**

- All Loop pages/documents where the direct report is a contributor or mentioned
- Document titles, creation dates, last modified dates
- Key content summaries (3-5 sentence overview per document)
- Action items or decisions attributed to the direct report
- Comments or feedback they provided

**Output Structure:**

```markdown
## Loop Workspace - [Direct Report Name]

### Documents Created
- **[Document Title]** (Created: YYYY-MM-DD, Modified: YYYY-MM-DD)
  - Summary: [3-5 sentence overview]
  - Key contributions: [bullet points]
  - Status: [Draft/In Progress/Complete]

### Documents Contributed To
- **[Document Title]** (Last contribution: YYYY-MM-DD)
  - Their contributions: [summary]
  - Comments/feedback: [key points]

### Action Items
- [ ] [Action item text] - Assigned: YYYY-MM-DD, Due: YYYY-MM-DD, Status: [Open/Closed]
```

### 2. Microsoft Teams - Meetings

For each direct report, extract:

**1:1 Meetings:**

- All scheduled 1:1 meetings (including recurring)
- Meeting dates, duration, attendance status
- Meeting notes, action items, and decisions
- Follow-up items and their resolution status

**Team Meetings:**

- Team meetings where the direct report attended
- Their participation level (presented, contributed, attended)
- Action items assigned to them
- Key decisions or discussions involving them

**Output Structure:**

```markdown
## Teams Meetings - [Direct Report Name]

### 1:1 Meetings Summary
- **Total 1:1s**: [count]
- **Meeting frequency**: [e.g., Weekly, Bi-weekly]
- **Attendance rate**: [X%]

#### Meeting Log
##### [Meeting Date - YYYY-MM-DD]
- **Duration**: [minutes]
- **Topics Discussed**:
  - [Topic 1]
  - [Topic 2]
- **Key Points**:
  - [Point 1]
  - [Point 2]
- **Action Items**:
  - [ ] [Action] - Due: YYYY-MM-DD - Status: [Open/Closed]
- **Decisions Made**:
  - [Decision 1]
- **Follow-up Items**:
  - [Item 1] - Resolved: [Yes/No/Partial]

### Team Meetings
#### [Meeting Date - YYYY-MM-DD] - [Meeting Title]
- **Role**: [Presenter/Contributor/Attendee]
- **Key Contributions**:
  - [Contribution 1]
- **Action Items Assigned**:
  - [ ] [Action] - Status: [Open/Closed]
```

### 3. Microsoft Teams - Chats

For each direct report, extract:

**Direct Messages (DMs):**

- Significant 1:1 chat threads (exclude routine/social)
- Work-related topics, questions, escalations
- Decisions made via chat
- Support requests or blockers raised

**Channel Conversations:**

- Threads where they actively participated
- Questions they answered or asked
- Expertise demonstrated
- Team interactions and collaboration

**Output Structure:**

```markdown
## Teams Chats - [Direct Report Name]

### Direct Message Highlights (Last 365 Days)
- **Total DM threads**: [count]
- **Topics Summary**: [brief overview of main themes]

#### Key Conversations
##### [Date - YYYY-MM-DD] - [Topic/Subject]
- **Context**: [What prompted the conversation]
- **Summary**: [Key points discussed]
- **Outcome**: [Decision/resolution/action taken]
- **Follow-up**: [Any ongoing items]

### Channel Participation
#### [Channel Name]
- **Thread participation**: [count]
- **Notable contributions**:
  - **[Date]** - [Thread topic]: [Their contribution summary]
- **Expertise demonstrated**: [Technical areas, problem-solving, etc.]
```

### 4. Azure DevOps - Work Items

For each direct report, extract:

**Work Items Assigned:**

- All work items assigned to them (User Stories, Tasks, Bugs, Features)
- Work item state transitions and velocity
- Completion rates and cycle time
- Quality metrics (bugs created vs. resolved)

**Work Items Created:**

- Work items they created (especially bugs, issues, improvements)
- Shows initiative and problem identification

**Code Reviews & Pull Requests:**

- PRs authored and reviewed
- Review quality and feedback patterns

**Output Structure:**

```markdown
## Azure DevOps - [Direct Report Name]

### Work Item Summary (Last 365 Days)
- **Total Items Assigned**: [count]
- **Completed**: [count] ([percentage]%)
- **In Progress**: [count]
- **Average Cycle Time**: [days]
- **Types Breakdown**:
  - User Stories: [count]
  - Tasks: [count]
  - Bugs: [count]
  - Features: [count]

### Completed Work Items
#### [Work Item ID] - [Title]
- **Type**: [User Story/Task/Bug/Feature]
- **Assigned Date**: YYYY-MM-DD
- **Completed Date**: YYYY-MM-DD
- **Cycle Time**: [days]
- **Description**: [Brief summary]
- **Acceptance Criteria**: [If applicable]
- **Outcome**: [Delivered value/impact]
- **Related PRs**: [Links to pull requests]

### In Progress Work Items
#### [Work Item ID] - [Title]
- **Type**: [User Story/Task/Bug/Feature]
- **Assigned Date**: YYYY-MM-DD
- **Current State**: [Active/Blocked/In Review]
- **Progress**: [X% complete or summary]
- **Blockers**: [Any impediments]
- **Expected Completion**: [Date or estimate]

### Work Items Created by Direct Report
#### [Work Item ID] - [Title]
- **Type**: [Bug/Issue/Improvement]
- **Created Date**: YYYY-MM-DD
- **Description**: [What they identified]
- **Impact**: [Severity/Priority]
- **Status**: [Resolved/Open]

### Code Contributions
- **Pull Requests Authored**: [count]
- **Pull Requests Reviewed**: [count]
- **Average Review Quality**: [Constructive/Thorough/Basic]
- **Key Contributions**:
  - **[PR ID]** - [Title] (Merged: YYYY-MM-DD)
    - [Brief description of change]
    - [Impact/value delivered]
```

## Consolidated View Per Direct Report

After extracting all data sources, create a consolidated summary for each direct report:

```markdown
# [Direct Report Name] - Annual Summary

## Profile
- **Name**: [Full Name]
- **Email**: [Email]
- **Role**: [Title]
- **Reporting Period**: [Start Date] to [Current Date]

## Executive Summary
[3-5 paragraph overview combining insights from all sources]

## Key Achievements
1. [Achievement 1 - with evidence from data sources]
2. [Achievement 2 - with evidence from data sources]
3. [Achievement 3 - with evidence from data sources]

## Areas of Expertise Demonstrated
- [Expertise area 1]: [Evidence from chats, work items, meetings]
- [Expertise area 2]: [Evidence]

## Collaboration & Communication
- **Meeting engagement**: [Summary from Teams meetings]
- **Team collaboration**: [Summary from Loop and Teams channels]
- **Communication style**: [Observations from chats and meetings]

## Delivery Metrics (Azure DevOps)
- **Completed work items**: [count]
- **Average cycle time**: [days]
- **Completion rate**: [percentage]
- **Quality indicators**: [Bug fix ratio, PR review engagement]

## Growth Areas & Development
[Based on patterns observed across all sources]
- [Area 1]: [Supporting evidence]
- [Area 2]: [Supporting evidence]

## Action Items & Follow-ups
### Open Items
- [ ] [Item from any source] - Due: YYYY-MM-DD - Source: [Loop/Teams/ADO]

### Completed Items
- [x] [Item] - Completed: YYYY-MM-DD - Source: [Loop/Teams/ADO]

## Notable Conversations & Decisions
[Key decisions or pivotal conversations from Teams/Loop]
- **[Date]** - [Topic]: [Decision/outcome]

## Recommendations for Next Period
[Forward-looking suggestions based on data]

---
**Report Generated**: [Date]
**Data Sources**: Loop, Microsoft Teams, Azure DevOps
**Time Range**: [Start Date] to [End Date]
```

## Output File Structure

Create a portable folder structure:

```text
direct-reports-export-[YYYY-MM-DD]/
├── README.md (Overview and instructions)
├── direct-reports-list.md (Preliminary list of all direct reports)
├── [Direct-Report-Name-1]/
│   ├── 00-consolidated-summary.md
│   ├── 01-loop-workspace.md
│   ├── 02-teams-meetings.md
│   ├── 03-teams-chats.md
│   └── 04-azure-devops.md
├── [Direct-Report-Name-2]/
│   ├── 00-consolidated-summary.md
│   ├── 01-loop-workspace.md
│   ├── 02-teams-meetings.md
│   ├── 03-teams-chats.md
│   └── 04-azure-devops.md
└── insights/
    ├── team-overview.md (Aggregate insights across all reports)
    ├── collaboration-matrix.md (Cross-report collaboration patterns)
    └── trends-analysis.md (Patterns and trends across the period)
```

## Quality Checks

Before finalizing the export:

1. **Completeness**: Verify all data sources accessed for each direct report
2. **Accuracy**: Cross-reference dates and ensure timeline consistency
3. **Privacy**: Confirm all data is work-related and appropriate for retention
4. **Portability**: Test that Markdown files render correctly in multiple viewers
5. **Links**: Preserve original source links where possible (ADO work items, Teams message links)
6. **Formatting**: Ensure consistent formatting across all files

## Usage Instructions

To use this prompt:

1. **Prepare API access** or use appropriate tools for:
   - Microsoft Graph API (Loop, Teams data)
   - Azure DevOps REST API
2. **Set date range**: Last 365 days from execution date
3. **Identify direct reports**: Query organizational structure
4. **Execute extraction**: Process each data source sequentially
5. **Generate Markdown files**: Follow the output structure above
6. **Create consolidated summaries**: Synthesize data across sources
7. **Package for portability**: Create folder structure with all files

## Notes for Implementation

- **Rate limiting**: Respect API rate limits when querying Microsoft Graph and Azure DevOps
- **Incremental processing**: Consider processing one direct report at a time
- **Error handling**: Log any data sources that are inaccessible or incomplete
- **Sanitization**: Remove any sensitive information that shouldn't be archived
- **Metadata preservation**: Include source URLs, timestamps, and version information where possible
