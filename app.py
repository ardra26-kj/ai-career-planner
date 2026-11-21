# CHECKPOINT 1 — "Hello, AI builder"
# This is the file every attendee starts with. If you can see this page
# in the preview on the right, your setup is done.
# It uses the same page layout as the final app, so the look never changes.

import json

import streamlit as st
from google import genai
from google.genai import errors, types

SYSTEM_PROMPT = """
You are a [friendly, Expertise] career counsellor for [Jobseekers who aspiring a career implement with AI]
Given a person's profile, reply in markdown with exactly these section:

# 3 role fit for you-[what to include for each role]

# 3 AI skills Fit for you - [What are the 3 skills in AI to improve the Current Job/Skill]

# Updated Skills - [what are the updated skills in tech industry related to the job, Learning resources in free]

# Your skill gap - What it's preferred and Learning resources in free (4 or 6 study materials)

# Job locations - reply in markdown with exactly these section:

# salary Expectation - [display the salary range based on job and location]

# your 90-day roadmap- [Split into three 30-day sprints with 12 focused tasks (1 per week):

Days 1–30 (Foundations — 4 tasks): Learn LLM basics, build a chat API, add structured outputs, and track token costs.

Days 31–60 (Applied AI — 4 tasks): Build a RAG app, test retrieval quality, add tool calling, and write basic evals.

Days 61–90 (Practice & Interview — 4 tasks): deploy 2 portfolio apps, write clear READMEs, and practice system design.]

Rules :[Simple English],[Tell like a Expert],[under 450 words]
 

"""

st.set_page_config(page_title="AI Career Planner", page_icon="🎯", layout="centered")

# A little CSS (page styling). "centered" layout keeps everything in a middle
# column; we make that column a bit wider so the 3 role cards fit side by side.
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

# Centered title and subtitle
st.markdown(
    """
    <div class="hero">
      <h1>🎯 AI Career Planner</h1>
      <p>My first AI product, built by Ardra.</p>
    </div>
    """,
    unsafe_allow_html=True,
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
            skills = st.text_area("Skills you already have")
        with interests_col:
            interests = st.text_area("What do you enjoy?")

        goal = st.text_input("Your goal")
        study_hours = st.slider("Hours per week you can study", 2, 40, 10)
        submitted = st.form_submit_button(
            "🚀 Plan my career", type="primary", use_container_width=True
        )

# Explain common Gemini failures in plain English.
def friendly_error(error):
    if isinstance(error, KeyError):
        return "No API key found. Check GEMINI_API_KEY in .streamlit/secrets.toml."
    if isinstance(error, errors.APIError):
        if error.code in (429, 500, 503, 504):
            return "Gemini is very busy or the free limit is reached. Wait a minute and try again."
        if error.code in (400, 401, 403):
            return "Your Gemini API key was rejected. Check GEMINI_API_KEY in .streamlit/secrets.toml."
    if isinstance(error, ValueError):
        return "The AI answer was incomplete. Please try again."
    return "I couldn't plan your career just now. Please check your connection and try again."


if submitted:
    missing = []
    if not name.strip():
        missing.append("Your name")
    if not skills.strip():
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

        # Send the completed form to Gemini and keep the answer on screen.
        st.session_state["career_plan"] = None
        try:
            client = genai.Client(
                api_key=st.secrets["GEMINI_API_KEY"],
                http_options=types.HttpOptions(api_version="v1beta"),
            )

            profile_text = json.dumps(
                answers,
                ensure_ascii=False,
                indent=2,
            )
            profile_text += (
                "\nSalary ranges must always be labelled \"indicative\"."
            )

            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.7,
            )
            last_error = None
            for model in ("gemini-3-flash-preview", "gemini-2.5-flash-lite"):
                for attempt in range(2 if model == "gemini-3-flash-preview" else 1):
                    try:
                        with st.spinner("Thinking about your career..."):
                            response = client.models.generate_content(
                                model=model,
                                contents=profile_text,
                                config=config,
                            )
                        break
                    except errors.APIError as error:
                        if error.code not in (429, 500, 503, 504):
                            raise
                        last_error = error
                else:
                    continue
                break
            else:
                raise last_error

            if not getattr(response, "text", None):
                raise ValueError("Gemini returned an empty answer.")

            st.session_state["career_plan"] = response.text
        except Exception as error:
            st.error(friendly_error(error))

if st.session_state.get("career_plan"):
    st.subheader("Your AI career plan")
    with st.container(border=True):
        st.markdown(st.session_state["career_plan"])

# Footer
st.divider()
st.markdown(
    '<div class="footer">Built at the Techolas AI Wing weekend · AI suggestions, not guarantees.</div>',
    unsafe_allow_html=True,
)
