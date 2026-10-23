"""Original demonstration lessons, using only AAA's public programme outline.

This is not AAA's curriculum, assessment rubric, or career advice.
"""

COURSE_VERSION = 'pathways-demo-1'
SOURCE_URL = 'https://www.animaladvocacyafrica.org/pathways-programme'

LESSONS = [
    {
        'id': 'orientation', 'number': '00', 'title': 'Find your starting point',
        'topic': 'Orientation', 'minutes': 5, 'eyebrow': 'A place to begin',
        'intro': 'You do not need a complete career plan to start. Begin with what you know about yourself, and one question you would like to answer.',
        'paragraphs': [
            'This sample course helps you explore how your experience could contribute to work for farmed animals. You can move at your own pace, save each exercise, and return to your answers. The lessons and questions in this preview are examples, not AAA’s published teaching materials.',
            'Keep a short learning question in mind: perhaps you want to explore policy work, understand where your current skills would be useful, or compare working at an organisation with contributing alongside your current job.',
            'Treat your first idea as a starting point. You will gather information, compare possible paths and choose a small next step. The sample knowledge checks support learning; they do not rank participants or determine access to programmes.'
        ],
        'exercise': 'What would you like to understand about your next career step by the end of this course?',
        'questions': [
            {'id': 'OR01', 'text': 'What is a useful starting point for this course?', 'options': ['Commit to a permanent career decision now', 'Write down a question you want to explore', 'Choose the most impressive job title'], 'correct': 1},
            {'id': 'OR02', 'text': 'What do these sample knowledge checks measure?', 'options': ['Understanding of the sample lesson', 'Eligibility for an AAA fellowship', 'Your value as an advocate'], 'correct': 0}
        ]
    },
    {
        'id': 'values', 'number': '01', 'title': 'Connect your values to your work',
        'topic': 'Values and motivation', 'minutes': 7, 'eyebrow': 'What you want to change',
        'intro': 'Start with the change you hope to help bring about, then ask how a particular activity could contribute to it.',
        'paragraphs': [
            'Different activities can aim at the same outcome through different routes. For example, an organisation might work with businesses, support policy research, or help other advocates build their skills. Understanding the route makes it easier to judge whether a role fits your aims.',
            'For one possible project, write a short chain: the activity, the change it is expected to cause, and how that could improve conditions for animals. Mark assumptions rather than treating them as facts. Ask what evidence would strengthen or weaken the case.',
            'Motivation helps you choose where to spend your effort. Good decisions also consider uncertainty, local context, the people already doing the work, and what you could contribute. You can care deeply about an issue while still investigating which approach to take.'
        ],
        'exercise': 'Describe one change you would like to help make for farmed animals. What would you need to learn before choosing a way to contribute?',
        'questions': [
            {'id': 'VM01', 'text': 'Which question helps you examine a proposed project?', 'options': ['Does it have the longest description?', 'Does it sound ambitious?', 'How would its activities lead to better outcomes for animals?'], 'correct': 2},
            {'id': 'VM02', 'text': 'What should you do with an uncertain assumption?', 'options': ['Mark it and look for evidence', 'Present it as a proven fact', 'Ignore it if you like the project'], 'correct': 0}
        ]
    },
    {
        'id': 'reflection', 'number': '02', 'title': 'Understand your strengths and constraints',
        'topic': 'Self-reflection', 'minutes': 6, 'eyebrow': 'Your context matters',
        'intro': 'A promising path needs to work in your circumstances. Use examples from your life rather than trying to describe an ideal version of yourself.',
        'paragraphs': [
            'Think about tasks you have done well and work you would like to learn. Skills can come from employment, study, volunteering, caring responsibilities or community projects. A specific example gives you more to work with than a broad label such as “good communicator”.',
            'List the constraints that shape your options. These might include income needs, location, responsibilities, working hours, qualifications or access to opportunities. You do not have to share personal details here; record only what you are comfortable including in this demonstration.',
            'Separate what you know from what you would like to test. If you enjoy writing, you might explore research communication or campaigning, but that does not establish which role is a good fit. A conversation or short exercise can provide more information.'
        ],
        'exercise': 'Name one strength with a concrete example, and one condition a possible role would need to meet.',
        'questions': [
            {'id': 'SR01', 'text': 'Which is the most useful evidence of a strength?', 'options': ['A job title you hope to have', 'A specific task you completed well', 'A skill everyone says is important'], 'correct': 1},
            {'id': 'SR02', 'text': 'How should practical constraints affect your plan?', 'options': ['Hide them from yourself', 'Assume they will disappear', 'Include them when comparing options'], 'correct': 2}
        ]
    },
    {
        'id': 'leverage', 'number': '03', 'title': 'Explore how you can contribute',
        'topic': 'Personal leverage', 'minutes': 7, 'eyebrow': 'More than one route',
        'intro': 'You may contribute through your work, professional knowledge, relationships, time or financial support. Explore the options before choosing a route.',
        'paragraphs': [
            'A career change is one way to contribute, but it is not the only one. Someone might strengthen a team through operations, bring relevant expertise to a project, volunteer for a bounded task, or support effective work financially. Which option fits depends on the situation.',
            'Begin with a need that an organisation or community has actually identified. Ask whether your contribution would address it, what support you would require, and whether someone else is already better placed to help.',
            'Consider the cost of each option as well as the possible benefit. A small commitment you can sustain may be a better first experiment than taking on more responsibility than you can manage. The aim here is to identify a testable contribution, not to prescribe a single path.'
        ],
        'exercise': 'Describe two ways you could contribute using skills or resources you already have. Which could you test first?',
        'questions': [
            {'id': 'PL01', 'text': 'Where should you start when offering help?', 'options': ['An actual need you could help address', 'The most visible activity', 'A role that needs no discussion'], 'correct': 0},
            {'id': 'PL02', 'text': 'What makes a useful first contribution?', 'options': ['The largest possible commitment', 'A bounded task matched to your capacity', 'Taking over an unfamiliar project alone'], 'correct': 1}
        ]
    },
    {
        'id': 'exploration', 'number': '04', 'title': 'Compare possible career paths',
        'topic': 'Career exploration', 'minutes': 8, 'eyebrow': 'Turn options into questions',
        'intro': 'Compare a few plausible paths using the same questions. Keep uncertainty visible so you know what to investigate next.',
        'paragraphs': [
            'Choose two or three paths to explore. Examples might include research, policy, organisational operations or work with businesses. These are sample categories, not AAA recommendations for you or evidence that roles are currently available.',
            'For each option, consider the contribution it could make, how well it fits your skills and circumstances, the route into it, and what you still need to learn. If you use a weighted comparison, explain your criteria and avoid treating a precise-looking score as certainty.',
            'Choose an information-gathering step that could change your view. You might read a role description, speak to someone doing the work, or try a small relevant task. Check the date and location of any opportunity before acting on it.'
        ],
        'exercise': 'Compare two paths you are considering. What is one uncertainty about each, and how could you investigate it?',
        'questions': [
            {'id': 'CE01', 'text': 'How can you make a comparison more useful?', 'options': ['Use different criteria for every option', 'Use the same relevant criteria and note uncertainty', 'Choose the highest-sounding title'], 'correct': 1},
            {'id': 'CE02', 'text': 'What is a good next step when you lack information?', 'options': ['Treat a guess as evidence', 'Avoid considering the option again', 'Plan a conversation or small test'], 'correct': 2}
        ]
    },
    {
        'id': 'action', 'number': '05', 'title': 'Choose your next small step',
        'topic': 'Action planning', 'minutes': 6, 'eyebrow': 'From reflection to a plan',
        'intro': 'Finish with an action you can take, a realistic date and a question you will revisit after trying it.',
        'paragraphs': [
            'An action plan can be short. Describe the next step, when you will take it, what support or information you need, and how you will know it is complete. Keep the size of the task realistic for your current commitments.',
            'For example, you could arrange one informational conversation, read two relevant role descriptions, or try a short research task. Be clear about what you hope to learn and what would make you reconsider your current preference.',
            'Set a review point. A useful experiment can tell you that a path is a poor fit as well as a good one. Completing this demonstration records your progress; it does not award an official AAA certificate or promise access to support or a programme.'
        ],
        'exercise': 'Write one action, a target date and what you hope to learn. How will you review the result?',
        'questions': [
            {'id': 'AP01', 'text': 'Which action is easiest to follow through on?', 'options': ['Arrange one relevant conversation by a chosen date', 'Have a better career someday', 'Explore every possible role this week'], 'correct': 0},
            {'id': 'AP02', 'text': 'What should you do after trying your next step?', 'options': ['Assume your first preference must be right', 'Review what you learned and update the plan', 'Ignore information that challenges your view'], 'correct': 1}
        ]
    }
]

def public_course():
    return {'version': COURSE_VERSION, 'source_url': SOURCE_URL, 'sample': True,
            'lessons': [{**l, 'questions': [{k: v for k, v in q.items() if k != 'correct'} for q in l['questions']]} for l in LESSONS]}
