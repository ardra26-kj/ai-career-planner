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

# Footer
st.divider()
st.markdown(
    '<div class="footer">Built at the Techolas AI Wing weekend · AI suggestions, not guarantees.</div>',
    unsafe_allow_html=True,
)
