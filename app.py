import json

import streamlit as st
from google import genai
from google.genai import errors, types

SYSTEM_PROMPT = """
You are a friendly, honest career counsellor for students and job seekers in India.
Given a person's profile, reply with exactly the structured career plan requested.
Keep all advice simple and practical, like an expert speaking to a beginner.
Use a warm and encouraging tone.
Never promise a job or a salary. Every salary range must be labelled as indicative.
Keep the plan realistic for the person's education, situation, skills, interests,
weekly study time and goal.
"""

st.set_page_config(page_title="AI Career Planner", page_icon="🎯", layout="centered")

# Keep the existing page style.
st.markdown(
    """
    <style>
    [data-testid="stMainBlockContainer"] { max-width: 1000px; padding-top: 2.5rem; }
    .hero { text-align: center; margin-bottom: 1.5rem; }
    .hero h1 { font-size: 2.6rem; margin-bottom: 0.2rem; }
    .hero p { color: #475569; font-size: 1.1rem; margin: 0; }
    .step { color: #2563EB; font-weight: 600; font-size: 0.85rem;
            letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 0.3rem; }
    .score { font-size: 2.4rem; font-weight: 700; color: #2563EB; line-height: 1.1; }
    .score span { font-size: 1rem; font-weight: 500; color: #475569; }
    .footer { text-align: center; color: #64748B; font-size: 0.85rem; padding: 0.5rem 0 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Hero title and subtitle.
st.markdown(
    """
    <div class="hero">
      <h1>🎯 AI Career Planner</h1>
      <p>My first AI product, built by Ardra.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def friendly_error(error):
    if isinstance(error, KeyError):
        return "No API key found. Check GEMINI_API_KEY in .streamlit/secrets.toml."
    if isinstance(error, errors.APIError):
        if error.code in (429, 500, 503, 504):
            return "Gemini is very busy or the free limit is reached. Wait a minute and try again."
        if error.code in (400, 401, 403):
            return "Your Gemini API key was rejected. Check GEMINI_API_KEY in .streamlit/secrets.toml."
    if isinstance(error, (ValueError, json.JSONDecodeError)):
        return "The AI answer was incomplete. Please try again."
    return "I couldn't plan your career just now. Please check your connection and try again."


def plan_schema():
    level_schema = types.Schema(type=types.Type.INTEGER, minimum=0, maximum=10)
    score_schema = types.Schema(type=types.Type.INTEGER, minimum=0, maximum=100)
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "roles": types.Schema(
                type=types.Type.ARRAY,
                min_items=3,
                max_items=3,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "title": types.Schema(type=types.Type.STRING),
                        "why_it_fits": types.Schema(type=types.Type.STRING),
                        "match_score": score_schema,
                        "salary_range_lpa": types.Schema(type=types.Type.STRING),
                    },
                    required=["title", "why_it_fits", "match_score", "salary_range_lpa"],
                ),
            ),
            "skill_gaps": types.Schema(
                type=types.Type.ARRAY,
                min_items=4,
                max_items=6,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "skill": types.Schema(type=types.Type.STRING),
                        "current_level": level_schema,
                        "needed_level": level_schema,
                        "free_resource": types.Schema(type=types.Type.STRING),
                    },
                    required=["skill", "current_level", "needed_level", "free_resource"],
                ),
            ),
            "roadmap": types.Schema(
                type=types.Type.OBJECT,
                properties={
                    name: types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "tasks": types.Schema(
                                type=types.Type.ARRAY,
                                min_items=3,
                                max_items=3,
                                items=types.Schema(type=types.Type.STRING),
                            ),
                            "mini_project": types.Schema(type=types.Type.STRING),
                        },
                        required=["tasks", "mini_project"],
                    )
                    for name in ("days_1_30", "days_31_60", "days_61_90")
                },
                required=["days_1_30", "days_31_60", "days_61_90"],
            ),
            "todays_action": types.Schema(type=types.Type.STRING),
        },
        required=["roles", "skill_gaps", "roadmap", "todays_action"],
    )


def quiz_schema():
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "skills": types.Schema(
                type=types.Type.ARRAY,
                min_items=1,
                max_items=5,
                items=types.Schema(type=types.Type.STRING),
            ),
            "questions": types.Schema(
                type=types.Type.ARRAY,
                min_items=3,
                max_items=15,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "skill": types.Schema(type=types.Type.STRING),
                        "difficulty": types.Schema(type=types.Type.STRING),
                        "question": types.Schema(type=types.Type.STRING),
                        "options": types.Schema(
                            type=types.Type.ARRAY,
                            min_items=4,
                            max_items=4,
                            items=types.Schema(type=types.Type.STRING),
                        ),
                        "correct_answer_index": types.Schema(
                            type=types.Type.INTEGER,
                            minimum=0,
                            maximum=3,
                        ),
                        "explanation": types.Schema(type=types.Type.STRING),
                    },
                    required=[
                        "skill",
                        "difficulty",
                        "question",
                        "options",
                        "correct_answer_index",
                        "explanation",
                    ],
                ),
            )
        },
        required=["skills", "questions"],
    )


def generate_with_retry(client, contents, config):
    models = ("gemini-3.5-flash-lite",)
    last_error = None
    for model_index, model in enumerate(models):
        attempts = 2 if model_index == 0 else 1
        for attempt in range(attempts):
            try:
                return client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
            except errors.APIError as error:
                if error.code not in (429, 500, 503, 504):
                    raise
                last_error = error
    raise last_error


def generate_quiz_with_retry(client, contents, config):
    models = ("gemini-3.5-flash", "gemini-3.5-flash-lite")
    last_error = None
    for model in models:
        for _ in range(2):
            try:
                return client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
            except errors.APIError as error:
                if error.code not in (429, 500, 503, 504):
                    raise
                last_error = error
    raise last_error


# Step 1 · Resume (optional).
st.markdown('<div class="step">Step 1 · Resume (optional)</div>', unsafe_allow_html=True)
resume = st.file_uploader(
    "Upload your resume PDF",
    type=["pdf"],
    accept_multiple_files=False,
)
st.caption(
    "Your resume is sent to Google Gemini to make your plan and is not stored by "
    "this app. On Gemini's free tier Google may use it to improve its products."
)

# Collect the user's career details.
with st.container(border=True):
    st.subheader("About you")
    with st.form("about_you_form"):
        name_col, education_col = st.columns(2)
        with name_col:
            name = st.text_input("Your name")
        with education_col:
            education = st.selectbox(
                "Highest education",
                [
                    "Plus Two / 12th",
                    "Diploma",
                    "B.Tech / B.E.",
                    "B.Sc / BCA",
                    "B.Com / BBA",
                    "BA",
                    "Master's degree",
                    "Other",
                ],
            )

        current_situation = st.radio(
            "Where are you right now?",
            [
                "Student",
                "Graduate looking for a job",
                "Working, want to switch",
                "Career break",
            ],
            horizontal=True,
        )

        skills_col, interests_col = st.columns(2)
        with skills_col:
            skills = st.text_area(
                "Skills you already have",
                help="Optional when you upload a resume.",
                disabled=False,
            )
        with interests_col:
            interests = st.text_area("What do you enjoy?")

        goal = st.text_input("Your goal")
        study_hours = st.slider("Hours per week you can study", 2, 40, 10)
        submitted = st.form_submit_button(
            "🚀 Plan my career", type="primary", use_container_width=True
        )


if submitted:
    missing = []
    if not name.strip():
        missing.append("Your name")
    if not resume and not skills.strip():
        missing.append("Skills you already have")
    if not goal.strip():
        missing.append("Your goal")

    if missing:
        st.warning("Please fill in: " + ", ".join(missing) + ".")
    else:
        answers = {
            "name": name,
            "highest_education": education,
            "current_situation": current_situation,
            "skills": skills,
            "interests": interests,
            "goal": goal,
            "hours_per_week_to_study": study_hours,
        }

        st.session_state["career_plan"] = None
        try:
            client = genai.Client(
                api_key=st.secrets["GEMINI_API_KEY"],
                http_options=types.HttpOptions(api_version="v1beta"),
            )

            profile_text = json.dumps(answers, ensure_ascii=False, indent=2)
            profile_text += '\nReturn salary ranges as indicative salary ranges.'
            contents = [profile_text]
            if resume is not None:
                contents.append(
                    types.Part.from_bytes(
                        data=resume.getvalue(),
                        mime_type="application/pdf",
                    )
                )

            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.7,
                response_mime_type="application/json",
                response_schema=plan_schema(),
            )

            with st.spinner("Thinking about your career..."):
                response = generate_with_retry(client, contents, config)

            if not getattr(response, "text", None):
                raise ValueError("Gemini returned an empty answer.")

            plan = json.loads(response.text)
            st.session_state["career_plan"] = plan
            st.session_state["chat_history"] = []
        except Exception as error:
            st.error(friendly_error(error))


def plan_to_markdown(plan):
    lines = ["# My AI Career Plan", ""]
    lines.append("## Do this today")
    lines.append(plan["todays_action"])
    lines.extend(["", "## Recommended roles"])

    for role in plan["roles"]:
        lines.extend(
            [
                "",
                f"### {role['title']} - {role['match_score']}%",
                role["why_it_fits"],
                f"Indicative salary: {role['salary_range_lpa']}",
            ]
        )

    lines.extend(["", "## Skill gaps"])
    for skill in plan["skill_gaps"]:
        lines.append(
            f"- **{skill['skill']}**: current {skill['current_level']}/10, "
            f"needed {skill['needed_level']}/10. "
            f"Free resource: {skill['free_resource']}"
        )

    labels = [
        ("days_1_30", "Days 1-30"),
        ("days_31_60", "Days 31-60"),
        ("days_61_90", "Days 61-90"),
    ]
    lines.extend(["", "## 90-day roadmap"])
    for key, label in labels:
        lines.extend(["", f"### {label}"])
        for task in plan["roadmap"][key]["tasks"]:
            lines.append(f"- [ ] {task}")
        lines.append(f"- **Mini project:** {plan['roadmap'][key]['mini_project']}")

    return "\n".join(lines)


plan = st.session_state.get("career_plan")
if plan:
    st.subheader("Your career dashboard")

    # Today's action.
    st.markdown(
        """
        <div style="background:#DCFCE7;border-left:6px solid #16A34A;
                    border-radius:8px;padding:16px;margin:8px 0 18px;">
          <h3 style="color:#166534;margin:0 0 6px;">Do this today</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.success(plan["todays_action"])

    # Three role cards.
    role_cols = st.columns(3)
    for column, role in zip(role_cols, plan["roles"]):
        with column:
            with st.container(border=True):
                st.markdown(f"### {role['title']}")
                st.markdown(
                    f'<div class="score">{role["match_score"]}<span>/100</span></div>',
                    unsafe_allow_html=True,
                )
                st.progress(role["match_score"] / 100)
                st.write(role["why_it_fits"])
                st.caption(
                    f"Indicative salary: {role['salary_range_lpa']}"
                )

    # Skill gap chart and resources.
    st.subheader("Skill gaps")
    chart_data = {}
    for skill in plan["skill_gaps"]:
        chart_data[skill["skill"]] = [
            skill["current_level"],
            skill["needed_level"],
        ]
    st.bar_chart(chart_data, horizontal=True)
    st.caption("Blue = current level · Orange = needed level")
    for skill in plan["skill_gaps"]:
        st.markdown(
            f"**{skill['skill']}** — {skill['free_resource']}"
        )

    # 90-day roadmap.
    st.subheader("Your 90-day roadmap")
    tab_1, tab_2, tab_3 = st.tabs(
        ["Days 1-30", "Days 31-60", "Days 61-90"]
    )
    roadmap_tabs = [
        (tab_1, "days_1_30"),
        (tab_2, "days_31_60"),
        (tab_3, "days_61_90"),
    ]
    for tab, key in roadmap_tabs:
        with tab:
            for task_index, task in enumerate(plan["roadmap"][key]["tasks"]):
                st.checkbox(task, key=f"{key}_task_{task_index}")
            st.info(
                "Mini project: " + plan["roadmap"][key]["mini_project"]
            )

    st.download_button(
        "Download my plan",
        data=plan_to_markdown(plan),
        file_name="my-career-plan.md",
        mime="text/markdown",
        use_container_width=True,
    )

    # Follow-up chat uses the generated plan as context.
    st.subheader("Ask about your plan")
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    for message in st.session_state["chat_history"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Ask a question about your plan")
    if question:
        st.session_state["chat_history"].append(
            {"role": "user", "content": question}
        )
        try:
            client = genai.Client(
                api_key=st.secrets["GEMINI_API_KEY"],
                http_options=types.HttpOptions(api_version="v1beta"),
            )
            chat_prompt = (
                "Answer the user's follow-up question using this career plan as context "
                "and keep the answer under 150 words:\n\n"
                + json.dumps(plan, ensure_ascii=False)
                + "\n\nQuestion: "
                + question
            )
            chat_config = types.GenerateContentConfig(
                system_instruction=(
                    SYSTEM_PROMPT
                    + "\nFor this chat, give a helpful answer in under 150 words."
                ),
                temperature=0.7,
            )
            with st.spinner("Answering..."):
                chat_response = generate_with_retry(
                    client, chat_prompt, chat_config
                )
            answer = getattr(chat_response, "text", "").strip()
            if not answer:
                raise ValueError("Gemini returned an empty answer.")
        except Exception as error:
            answer = friendly_error(error)

        st.session_state["chat_history"].append(
            {"role": "assistant", "content": answer}
        )
        st.rerun()

# Skill assessment lives in its own tab.
quiz_tab = st.tabs(["Skill Assessment Quiz"])[0]
with quiz_tab:
    st.subheader("Skill Assessment Quiz")
    profile_skills = [
        item.strip()
        for item in skills.replace("\n", ",").split(",")
        if item.strip()
    ]
    plan_skills = [
        item["skill"]
        for item in (plan or {}).get("skill_gaps", [])
        if item.get("skill")
    ]
    fallback_skills = list(dict.fromkeys(profile_skills + plan_skills))
    if resume is not None:
        st.caption(
            "The quiz will extract technical skills from your uploaded resume. "
            "The PDF is sent to Gemini for this request and is not saved by the app."
        )
    elif fallback_skills:
        st.caption(
            "No resume is uploaded. The quiz will use your skills from the career "
            "profile instead."
        )
    else:
        st.info("Upload a resume above, or enter skills in your career profile, to begin.")

    # Extract skills and create questions at all three difficulty levels.
    with st.form("skill_quiz_form"):
        generate_quiz = st.form_submit_button(
            "Extract skills and generate quiz",
            type="primary",
            use_container_width=True,
        )

    if generate_quiz:
        if resume is None and not fallback_skills:
            st.warning(
                "Upload a resume or add skills to your career profile before "
                "generating a quiz."
            )
        else:
            st.session_state["skill_quiz"] = None
            st.session_state["skill_quiz_result"] = None
            for index in range(15):
                st.session_state.pop(f"skill_quiz_answer_{index}", None)
            try:
                client = genai.Client(
                    api_key=st.secrets["GEMINI_API_KEY"],
                    http_options=types.HttpOptions(api_version="v1beta"),
                )
                quiz_config = types.GenerateContentConfig(
                    system_instruction=(
                        "Identify up to five technical skills supported by the "
                        "provided resume, or use the provided skill list when "
                        "there is no resume. Create exactly one original "
                        "multiple-choice question for each skill at each of "
                        "these levels: Easy, Medium, and Hard. Use only those "
                        "skills. Give each question four distinct options, one "
                        "correct answer, and a short explanation. The "
                        "correct_answer_index is zero-based."
                    ),
                    temperature=0.7,
                    response_mime_type="application/json",
                    response_schema=quiz_schema(),
                )
                quiz_prompt = json.dumps(
                    {
                        "fallback_skills": fallback_skills,
                        "difficulty_levels": ["Easy", "Medium", "Hard"],
                        "maximum_skills": 5,
                    },
                    ensure_ascii=False,
                )
                quiz_contents = [quiz_prompt]
                if resume is not None:
                    quiz_contents.append(
                        types.Part.from_bytes(
                            data=resume.getvalue(),
                            mime_type="application/pdf",
                        )
                    )
                with st.spinner("Making your quiz..."):
                    response = generate_quiz_with_retry(
                        client, quiz_contents, quiz_config
                    )

                if not getattr(response, "text", None):
                    raise ValueError("Gemini returned an empty quiz.")
                quiz = json.loads(response.text)
                extracted_skills = quiz.get("skills")
                questions = quiz.get("questions")
                if (
                    not isinstance(extracted_skills, list)
                    or not 1 <= len(extracted_skills) <= 5
                    or not isinstance(questions, list)
                ):
                    raise ValueError("Gemini returned an incomplete quiz.")
                expected_questions = {
                    (skill, level)
                    for skill in extracted_skills
                    for level in ("Easy", "Medium", "Hard")
                }
                actual_questions = set()
                for question in questions:
                    if (
                        not isinstance(question, dict)
                        or question.get("skill") not in extracted_skills
                        or question.get("difficulty")
                        not in ("Easy", "Medium", "Hard")
                        or not isinstance(question.get("options"), list)
                        or len(question["options"]) != 4
                        or type(question.get("correct_answer_index")) is not int
                        or question["correct_answer_index"] not in range(4)
                    ):
                        raise ValueError("Gemini returned an invalid question.")
                    actual_questions.add(
                        (question["skill"], question["difficulty"])
                    )
                if (
                    len(questions) != len(expected_questions)
                    or actual_questions != expected_questions
                ):
                    raise ValueError("Gemini returned an incomplete quiz.")
                st.session_state["skill_quiz"] = {
                    "questions": questions,
                    "skills": extracted_skills,
                }
            except Exception as error:
                st.error(friendly_error(error))

    # Show questions and score answers while keeping quiz data across reruns.
    quiz = st.session_state.get("skill_quiz")
    if quiz:
        quiz_questions = quiz["questions"]
        st.write("Skills identified: " + ", ".join(quiz["skills"]))
        if st.session_state.get("skill_quiz_result") is None:
            with st.form("skill_quiz_answers_form"):
                answers = []
                for index, question in enumerate(quiz_questions):
                    st.markdown(
                        f"**{index + 1}. [{question['difficulty']}] "
                        f"{question['question']}**"
                    )
                    answers.append(
                        st.radio(
                            f"Question {index + 1}",
                            options=range(4),
                            format_func=lambda option, choices=question["options"]: (
                                choices[option]
                            ),
                            index=None,
                            key=f"skill_quiz_answer_{index}",
                            label_visibility="collapsed",
                        )
                    )
                submit_answers = st.form_submit_button(
                    "Check my answers", type="primary", use_container_width=True
                )

            if submit_answers:
                if any(answer is None for answer in answers):
                    st.warning("Please answer every question before checking.")
                else:
                    st.session_state["skill_quiz_result"] = answers
                    st.rerun()

        quiz_result = st.session_state.get("skill_quiz_result")
        if quiz_result is not None:
            score = sum(
                answer == question["correct_answer_index"]
                for answer, question in zip(quiz_result, quiz_questions)
            )
            st.markdown("### Your score")
            st.markdown(
                f'<div class="score">{score}<span> / {len(quiz_questions)}</span></div>',
                unsafe_allow_html=True,
            )

            skill_scores = {}
            for answer, question in zip(quiz_result, quiz_questions):
                skill = question["skill"]
                if skill not in skill_scores:
                    skill_scores[skill] = [0, 0]
                skill_scores[skill][1] += 1
                if answer == question["correct_answer_index"]:
                    skill_scores[skill][0] += 1

            st.markdown("### Score by skill")
            for skill, (correct, total) in skill_scores.items():
                st.write(f"**{skill}:** {correct} / {total}")

            st.markdown("### Correct answers")
            for index, question in enumerate(quiz_questions):
                correct_option = question["options"][
                    question["correct_answer_index"]
                ]
                st.markdown(
                    f"**{index + 1}. [{question['difficulty']}] "
                    f"{question['question']}**  \n"
                    f"Correct answer: **{correct_option}**  \n"
                    f"{question['explanation']}"
                )

# Footer
st.divider()
st.markdown(
    '<div class="footer">Built at the Techolas AI Wing weekend · AI suggestions, not guarantees.</div>',
    unsafe_allow_html=True,
)
