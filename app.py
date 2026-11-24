import hashlib
import json
from urllib.parse import quote_plus

import streamlit as st
from google import genai
from google.genai import errors, types

SYSTEM_PROMPT = """
You are a friendly, honest career counsellor for students and job seekers in India.
Use the attached resume and the person's weekly study time as the source for
personal background. Base recommendations on evidence in the resume.
Do not invent personal details, education, skills, experience, interests or goals
that are not supported by the resume. If a goal is not stated, recommend suitable
career directions based on the resume.
Keep all advice simple and practical, like an expert speaking to a beginner.
Use a warm and encouraging tone.
Suggest other skills commonly requested for the recommended roles, based on broad
hiring trends, prioritizing skills not already supported by the resume. Do not
claim to have checked live job postings. For each skill gap and additional skill,
name a free learning resource and a topic to search for. Also recommend one real,
free YouTube channel for each skill, and provide its channel name only.
Do not recommend paid-only resources.
Never promise a job or a salary. Every salary range must be labelled as indicative.
Keep the plan realistic for the person's resume and weekly study time.
"""

st.set_page_config(page_title="AI Career Planner", page_icon="🎯", layout="centered")

# Let users switch the page between light and dark themes.
if "theme_mode" not in st.session_state:
    st.session_state["theme_mode"] = "☀️ Light"

_, appearance_column = st.columns([5, 2])
with appearance_column:
    st.radio(
        "Choose appearance",
        ["☀️ Light", "🌙 Dark"],
        horizontal=True,
        label_visibility="collapsed",
        key="theme_mode",
    )

dark_mode = st.session_state["theme_mode"] == "🌙 Dark"
theme = {
    "background": "#0B1220" if dark_mode else "#FFFFFF",
    "surface": "#111C2E" if dark_mode else "#F8FAFC",
    "text": "#E2E8F0" if dark_mode else "#0F172A",
    "muted": "#94A3B8" if dark_mode else "#475569",
    "accent": "#60A5FA" if dark_mode else "#2563EB",
    "action_background": "#123329" if dark_mode else "#DCFCE7",
    "action_border": "#22C55E" if dark_mode else "#16A34A",
    "action_text": "#BBF7D0" if dark_mode else "#166534",
    "color_scheme": "dark" if dark_mode else "light",
}

# Apply the selected colors to the page and its custom sections.
st.markdown(
    f"""
    <style>
    :root {{
        --app-background: {theme["background"]};
        --app-surface: {theme["surface"]};
        --app-text: {theme["text"]};
        --app-muted: {theme["muted"]};
        --app-accent: {theme["accent"]};
        color-scheme: {theme["color_scheme"]};
    }}
    html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
        background-color: var(--app-background) !important;
        color: var(--app-text);
    }}
    [data-testid="stHeader"] {{ background-color: transparent; }}
    [data-testid="stMainBlockContainer"] {{ max-width: 1000px; padding-top: 2.5rem; }}
    [data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: var(--app-surface);
    }}
    [data-testid="stMarkdownContainer"],
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stWidgetLabel"] p,
    h1, h2, h3, h4, li {{ color: var(--app-text); }}
    [data-testid="stCaptionContainer"] p {{ color: var(--app-muted); }}
    .hero {{ text-align: center; margin-bottom: 1.5rem; }}
    .hero h1 {{ font-size: 2.6rem; margin-bottom: 0.2rem; }}
    .hero p {{ color: var(--app-muted); font-size: 1.1rem; margin: 0; }}
    .step {{ color: var(--app-accent); font-weight: 600; font-size: 0.85rem;
            letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 0.3rem; }}
    .score {{ font-size: 2.4rem; font-weight: 700; color: var(--app-accent); line-height: 1.1; }}
    .score span {{ font-size: 1rem; font-weight: 500; color: var(--app-muted); }}
    .today-action {{
        background: {theme["action_background"]};
        border-left: 6px solid {theme["action_border"]};
        border-radius: 8px;
        padding: 16px;
        margin: 8px 0 18px;
    }}
    .today-action h3 {{ color: {theme["action_text"]}; margin: 0 0 6px; }}
    .footer {{ text-align: center; color: var(--app-muted); font-size: 0.85rem; padding: 0.5rem 0 1rem; }}
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
                        "youtube_channel": types.Schema(type=types.Type.STRING),
                    },
                    required=[
                        "skill",
                        "current_level",
                        "needed_level",
                        "free_resource",
                        "youtube_channel",
                    ],
                ),
            ),
            "in_demand_skills": types.Schema(
                type=types.Type.ARRAY,
                min_items=3,
                max_items=5,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "skill": types.Schema(type=types.Type.STRING),
                        "relevant_roles": types.Schema(type=types.Type.STRING),
                        "why_it_matters": types.Schema(type=types.Type.STRING),
                        "free_resource": types.Schema(type=types.Type.STRING),
                        "youtube_channel": types.Schema(type=types.Type.STRING),
                    },
                    required=[
                        "skill",
                        "relevant_roles",
                        "why_it_matters",
                        "free_resource",
                        "youtube_channel",
                    ],
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
        required=[
            "roles",
            "skill_gaps",
            "in_demand_skills",
            "roadmap",
            "todays_action",
        ],
    )


def skill_extraction_schema():
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "skills": types.Schema(
                type=types.Type.ARRAY,
                min_items=1,
                max_items=20,
                items=types.Schema(type=types.Type.STRING),
            )
        },
        required=["skills"],
    )


def quiz_schema():
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "questions": types.Schema(
                type=types.Type.ARRAY,
                min_items=25,
                max_items=25,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
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
                        "question",
                        "options",
                        "correct_answer_index",
                        "explanation",
                    ],
                ),
            )
        },
        required=["questions"],
    )


def generate_with_retry(client, contents, config):
    models = ("gemini-3.5-flash-lite", "gemini-2.5-flash-lite")
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
    models = ("gemini-3.5-flash-lite", "gemini-2.5-flash-lite")
    for model_index, model in enumerate(models):
        attempts = 2 if model_index == 0 else 1
        last_error = None
        for _ in range(attempts):
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
        if model_index == len(models) - 1 and last_error is not None:
            raise last_error
    raise RuntimeError("Gemini did not return a quiz.")


# Step 1 · Resume and study time.
st.markdown('<div class="step">Step 1 · Resume and study time</div>', unsafe_allow_html=True)
resume = st.file_uploader(
    "Upload your resume PDF (required)",
    type=["pdf"],
    accept_multiple_files=False,
)
st.caption(
    "Your resume is sent to Google Gemini to make your plan and is not stored by "
    "this app. On Gemini's free tier Google may use it to improve its products."
)

# Use the resume for career details; only study time is asked separately.
with st.container(border=True):
    st.subheader("Create my career plan")
    with st.form("career_plan_form"):
        study_hours = st.slider("Hours per week you can study", 2, 40, 10)
        submitted = st.form_submit_button(
            "🚀 Plan my career", type="primary", use_container_width=True
        )


if submitted:
    st.session_state["career_plan"] = None
    if resume is None:
        st.warning("Please upload your resume PDF to create a career plan.")
    else:
        answers = {
            "hours_per_week_to_study": study_hours,
        }

        try:
            client = genai.Client(
                api_key=st.secrets["GEMINI_API_KEY"],
                http_options=types.HttpOptions(api_version="v1beta"),
            )

            profile_text = json.dumps(answers, ensure_ascii=False, indent=2)
            profile_text += (
                "\nUse the attached resume as the source for all career details. "
                "Return salary ranges as indicative salary ranges."
            )
            contents = [
                profile_text,
                types.Part.from_bytes(
                    data=resume.getvalue(),
                    mime_type="application/pdf",
                ),
            ]

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


# Build a YouTube search link from a channel name.
def youtube_channel_search_url(channel):
    query = quote_plus(f"{channel} channel")
    return f"https://www.youtube.com/results?search_query={query}"


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
            f"Free resource: {skill['free_resource']}. "
            f"[YouTube channel: {skill['youtube_channel']}]"
            f"({youtube_channel_search_url(skill['youtube_channel'])})"
        )

    lines.extend(["", "## Other commonly requested skills"])
    for skill in plan["in_demand_skills"]:
        lines.append(
            f"- **{skill['skill']}** ({skill['relevant_roles']}): "
            f"{skill['why_it_matters']} "
            f"Free resource: {skill['free_resource']}. "
            f"[YouTube channel: {skill['youtube_channel']}]"
            f"({youtube_channel_search_url(skill['youtube_channel'])})"
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
        <div class="today-action">
          <h3>Do this today</h3>
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
        st.markdown(
            f"[YouTube channel: {skill['youtube_channel']}]"
            f"({youtube_channel_search_url(skill['youtube_channel'])})"
        )

    # Show other commonly requested skills and free learning resources.
    st.subheader("Other commonly requested skills")
    st.caption(
        "These skills are suggested from broad hiring trends, not live job postings. "
        "Check current job descriptions for each role."
    )
    for skill in plan["in_demand_skills"]:
        st.markdown(
            f"**{skill['skill']}** — relevant to {skill['relevant_roles']}"
        )
        st.write(skill["why_it_matters"])
        st.caption(f"Free resource: {skill['free_resource']}")
        st.markdown(
            f"[YouTube channel: {skill['youtube_channel']}]"
            f"({youtube_channel_search_url(skill['youtube_channel'])})"
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

# The skill assessment quiz has its own tab.
quiz_tab = st.tabs(["Skill Assessment Quiz"])[0]
with quiz_tab:
    st.subheader("Skill Assessment Quiz")
    if resume is not None:
        st.caption(
            "Extract technical skills from your uploaded resume, then choose one "
            "skill and a difficulty. The PDF is sent to Gemini and is not saved."
        )
    else:
        st.info("Upload a resume above to extract technical skills for your quiz.")

    resume_fingerprint = (
        hashlib.sha256(resume.getvalue()).hexdigest() if resume is not None else None
    )
    if (
        st.session_state.get("skill_assessment_resume_fingerprint")
        != resume_fingerprint
    ):
        st.session_state["skill_assessment_resume_fingerprint"] = resume_fingerprint
        st.session_state["skill_assessment_skills"] = []
        st.session_state["skill_assessment_quiz"] = None
        st.session_state["skill_assessment_result"] = None
        st.session_state.pop("skill_assessment_selected_skill", None)
        st.session_state.pop("skill_assessment_selected_difficulty", None)
        for index in range(25):
            st.session_state.pop(f"skill_assessment_answer_{index}", None)

    # Extract resume skills once when the user requests them.
    with st.form("skill_assessment_extract_form"):
        extract_skills = st.form_submit_button(
            "Extract skills from resume",
            type="primary",
            use_container_width=True,
            disabled=resume is None,
        )

    if extract_skills and resume is not None:
        st.session_state["skill_assessment_skills"] = []
        st.session_state["skill_assessment_quiz"] = None
        st.session_state["skill_assessment_result"] = None
        st.session_state.pop("skill_assessment_selected_skill", None)
        for index in range(25):
            st.session_state.pop(f"skill_assessment_answer_{index}", None)
        try:
            client = genai.Client(
                api_key=st.secrets["GEMINI_API_KEY"],
                http_options=types.HttpOptions(api_version="v1beta"),
            )
            extraction_config = types.GenerateContentConfig(
                system_instruction=(
                    "Identify up to 20 distinct technical skills explicitly "
                    "supported by the attached resume. Return concise skill "
                    "names only. Do not infer soft skills or invent experience."
                ),
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=skill_extraction_schema(),
            )
            resume_content = [
                "Extract the technical skills from this resume.",
                types.Part.from_bytes(
                    data=resume.getvalue(),
                    mime_type="application/pdf",
                ),
            ]
            with st.spinner("Finding technical skills in your resume..."):
                response = generate_quiz_with_retry(
                    client, resume_content, extraction_config
                )
            if not getattr(response, "text", None):
                raise ValueError("Gemini returned no extracted skills.")
            extracted_skills = json.loads(response.text).get("skills")
            if (
                not isinstance(extracted_skills, list)
                or not 1 <= len(extracted_skills) <= 20
                or any(
                    not isinstance(skill, str) or not skill.strip()
                    for skill in extracted_skills
                )
            ):
                raise ValueError("Gemini returned an invalid skill list.")
            st.session_state["skill_assessment_skills"] = list(
                dict.fromkeys(skill.strip() for skill in extracted_skills)
            )
        except Exception as error:
            st.error(friendly_error(error))

    extracted_skills = st.session_state.get("skill_assessment_skills", [])
    if extracted_skills:
        # Select one extracted skill and a difficulty before making a quiz.
        with st.form("skill_quiz_form"):
            selected_skill = st.selectbox(
                "Choose one skill",
                extracted_skills,
                key="skill_assessment_selected_skill",
            )
            selected_difficulty = st.selectbox(
                "Choose difficulty",
                ["Easy", "Medium", "Hard"],
                key="skill_assessment_selected_difficulty",
            )
            generate_quiz = st.form_submit_button(
                "Start 25-question quiz",
                type="primary",
                use_container_width=True,
            )

        if generate_quiz:
            st.session_state["skill_assessment_quiz"] = None
            st.session_state["skill_assessment_result"] = None
            for index in range(25):
                st.session_state.pop(f"skill_assessment_answer_{index}", None)
            try:
                client = genai.Client(
                    api_key=st.secrets["GEMINI_API_KEY"],
                    http_options=types.HttpOptions(api_version="v1beta"),
                )
                quiz_config = types.GenerateContentConfig(
                    system_instruction=(
                        "Create exactly 25 distinct, accurate multiple-choice "
                        "questions for the requested technical skill and "
                        "difficulty. Every question must have four distinct "
                        "answer options, one correct answer, and a short "
                        "explanation. The correct_answer_index is zero-based. "
                        "Do not include questions about other skills."
                    ),
                    temperature=0.7,
                    response_mime_type="application/json",
                    response_schema=quiz_schema(),
                )
                quiz_prompt = json.dumps(
                    {
                        "skill": selected_skill,
                        "difficulty": selected_difficulty,
                        "question_count": 25,
                    },
                    ensure_ascii=False,
                )
                with st.spinner("Making your 25-question quiz..."):
                    response = generate_quiz_with_retry(
                        client, quiz_prompt, quiz_config
                    )
                if not getattr(response, "text", None):
                    raise ValueError("Gemini returned an empty quiz.")
                questions = json.loads(response.text).get("questions")
                if not isinstance(questions, list) or len(questions) != 25:
                    raise ValueError("Gemini returned an incomplete quiz.")
                for question in questions:
                    if (
                        not isinstance(question, dict)
                        or not isinstance(question.get("question"), str)
                        or not question["question"].strip()
                        or not isinstance(question.get("options"), list)
                        or len(question["options"]) != 4
                        or any(
                            not isinstance(option, str) or not option.strip()
                            for option in question["options"]
                        )
                        or len(
                            {
                                option.strip().casefold()
                                for option in question["options"]
                            }
                        )
                        != 4
                        or type(question.get("correct_answer_index")) is not int
                        or question["correct_answer_index"] not in range(4)
                        or not isinstance(question.get("explanation"), str)
                    ):
                        raise ValueError("Gemini returned an invalid question.")
                st.session_state["skill_assessment_quiz"] = {
                    "skill": selected_skill,
                    "difficulty": selected_difficulty,
                    "questions": questions,
                }
            except Exception as error:
                st.error(friendly_error(error))

    # Keep quiz questions and submitted answers in session state.
    quiz = st.session_state.get("skill_assessment_quiz")
    if quiz:
        quiz_questions = quiz["questions"]
        st.markdown(
            f"**Skill:** {quiz['skill']} &nbsp; · &nbsp; "
            f"**Difficulty:** {quiz['difficulty']}"
        )
        if st.session_state.get("skill_assessment_result") is None:
            with st.form("skill_quiz_answers_form"):
                answers = []
                for index, question in enumerate(quiz_questions):
                    st.markdown(
                        f"**{index + 1}. {question['question']}**"
                    )
                    answers.append(
                        st.radio(
                            f"Question {index + 1}",
                            options=range(4),
                            format_func=lambda option, choices=question["options"]: (
                                choices[option]
                            ),
                            index=None,
                            key=f"skill_assessment_answer_{index}",
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
                    st.session_state["skill_assessment_result"] = answers
                    st.rerun()

        quiz_result = st.session_state.get("skill_assessment_result")
        if quiz_result is not None:
            score = sum(
                answer == question["correct_answer_index"]
                for answer, question in zip(quiz_result, quiz_questions)
            )
            percentage = score / len(quiz_questions) * 100
            st.markdown("### Results Dashboard")
            score_col, percentage_col = st.columns(2)
            score_col.metric("Total Score", f"{score} / {len(quiz_questions)}")
            percentage_col.metric("Percentage", f"{percentage:.1f}%")

            st.markdown("### Question-by-Question Review")
            for index, (answer, question) in enumerate(
                zip(quiz_result, quiz_questions)
            ):
                correct_index = question["correct_answer_index"]
                correct_option = question["options"][correct_index]
                selected_option = question["options"][answer]
                with st.container(border=True):
                    st.markdown(f"**{index + 1}. {question['question']}**")
                    st.write(f"Your answer: {selected_option}")
                    if answer == correct_index:
                        st.success(f"Correct — {correct_option}")
                    else:
                        st.error(f"Incorrect — correct answer: {correct_option}")
                    st.caption(question["explanation"])

# Footer
st.divider()
st.markdown(
    '<div class="footer">Built at the Techolas AI Wing weekend · AI suggestions, not guarantees.</div>',
    unsafe_allow_html=True,
)
