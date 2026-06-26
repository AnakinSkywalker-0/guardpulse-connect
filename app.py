"""
app.py — Phase 4: GuardPulse Enterprise Portal.

Run with: streamlit run app.py

Two tabs:
  - CEO view:    search for a problem, see top matches, run sandbox queries,
                 download a Pilot Proposal PDF
  - Startup view: founders look up their own registered profile and see
                 their full GuardPulse scorecard
"""

import os
# pyrefly: ignore [missing-import]
import streamlit as st

from startup_store import list_all_startups
from matchmaking_engine import find_matches
from sandbox import run_sandbox_query
from pilot_proposal import generate_pilot_proposal

st.set_page_config(page_title="GuardPulse Connect", page_icon=None, layout="wide")

BADGE_COLORS = {
    "ENTERPRISE_READY": "#0F6E56",
    "CONDITIONAL":       "#854F0B",
    "NOT_READY":          "#A32D2D",
}


def badge_pill(badge_value: str) -> str:
    color = BADGE_COLORS.get(badge_value, "#888")
    label = badge_value.replace("_", " ")
    return f"<span style='background:{color}1A;color:{color};padding:3px 10px;border-radius:6px;font-size:12px;font-weight:600'>{label}</span>"


st.title("GuardPulse Connect")
st.caption("Enterprise-ready AI marketplace — compliance-audited startup matchmaking")

tab_ceo, tab_startup = st.tabs(["CEO — Find a vendor", "Startup — My scorecard"])


# ── CEO VIEW ───────────────────────────────────────────────────────────────────

with tab_ceo:
    st.subheader("Describe your business problem")
    problem_text = st.text_area(
        "What are you trying to solve?",
        placeholder="e.g. I need a vendor who can detect fraud in our payments platform",
        height=90,
        label_visibility="collapsed",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        top_k     = st.number_input("Top N", min_value=1, max_value=10, value=3)
        threshold = st.number_input("Trust threshold", min_value=0.0, max_value=100.0, value=80.0, step=5.0)
    with col2:
        search_clicked = st.button("Find matches", type="primary")

    if search_clicked and problem_text.strip():
        with st.spinner("Searching the verified startup registry..."):
            result = find_matches(problem_text, top_k=int(top_k), trust_threshold=threshold)
        st.session_state["match_result"] = result
        st.session_state["ceo_problem"]  = problem_text

    result = st.session_state.get("match_result")

    if result:
        st.markdown(
            f"**{result.total_candidates}** candidates found - "
            f"**{result.total_after_trust_filter}** passed the trust filter "
            f"(score >= {result.trust_threshold})"
        )

        if not result.matches:
            st.warning(
                "No startups meet the trust threshold yet. Lower the threshold "
                "above to see candidates, or register startups with higher scores."
            )
        else:
            for i, m in enumerate(result.matches, 1):
                s = m.startup
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 1, 1])
                    with c1:
                        st.markdown(f"**{i}. {s.startup_name}**  ·  {s.category.replace('_', ' ').title()}")
                        st.caption(s.description)
                        st.markdown(badge_pill(s.badge.value), unsafe_allow_html=True)
                    with c2:
                        st.metric("GuardPulse score", f"{s.guardpulse_score}/100")
                    with c3:
                        st.metric("Relevance", f"{m.relevance_score:.0%}")

                    st.caption(m.match_reason)

                    with st.expander("Run sandbox query"):
                        sandbox_key = f"sandbox_query_{s.startup_id}"
                        query = st.text_input(
                            "Sample query to test against this startup",
                            key=sandbox_key,
                            placeholder="e.g. Can you flag a transaction over $10,000 as suspicious?",
                        )
                        if st.button("Run", key=f"run_{s.startup_id}"):
                            with st.spinner("Simulating response..."):
                                sandbox_result = run_sandbox_query(s, query)
                            st.info(sandbox_result["notes"])
                            st.write(f"**Status:** {sandbox_result['status']}")
                            st.write(sandbox_result["response_summary"])
                            st.json(sandbox_result["sample_fields"])
                            st.caption(
                                f"Simulated latency: {sandbox_result['latency_ms']}ms - "
                                f"{sandbox_result['confidence_note']}"
                            )

                    if st.button("Generate Pilot Proposal PDF", key=f"proposal_{s.startup_id}"):
                        os.makedirs("proposals", exist_ok=True)
                        out_path = f"proposals/{s.startup_id}_pilot_proposal.pdf"
                        with st.spinner("Generating proposal..."):
                            generate_pilot_proposal(
                                match       = m,
                                ceo_problem = st.session_state.get("ceo_problem", problem_text),
                                output_path = out_path,
                            )
                        with open(out_path, "rb") as f:
                            st.download_button(
                                "Download Pilot Proposal",
                                data=f.read(),
                                file_name=f"{s.startup_id}_pilot_proposal.pdf",
                                mime="application/pdf",
                                key=f"download_{s.startup_id}",
                            )


# ── STARTUP FOUNDER VIEW ──────────────────────────────────────────────────────

with tab_startup:
    st.subheader("Look up your startup")
    startups = list_all_startups()

    if not startups:
        st.info("No startups registered yet. Use `python main.py register` to add one.")
    else:
        names    = [s.startup_name for s in startups]
        selected = st.selectbox("Select your startup", names)
        profile  = next(s for s in startups if s.startup_name == selected)

        st.markdown(badge_pill(profile.badge.value), unsafe_allow_html=True)
        st.write("")

        c1, c2, c3 = st.columns(3)
        c1.metric("GuardPulse score", f"{profile.guardpulse_score}/100")
        c2.metric("Legal score", f"{profile.legal_score}/100")
        c3.metric("Tech score", f"{profile.tech_score}/100")

        st.divider()
        st.markdown("**Description**")
        st.write(profile.description)

        st.markdown("**Category**")
        st.write(profile.category.replace("_", " ").title())

        st.markdown("**Registered capabilities**")
        st.write(", ".join(c.replace("_", " ") for c in profile.capabilities) or "None listed")

        st.markdown("**Document audited**")
        st.write(profile.document_audited)

        st.markdown("**Registered on**")
        st.write(profile.registered_at[:10] if profile.registered_at else "Unknown")

        st.divider()
        if profile.guardpulse_score >= 80:
            st.success(
                f"Score {profile.guardpulse_score}/100 meets the enterprise trust "
                f"threshold (80). Visible in CEO matchmaking results."
            )
        else:
            gap = round(80 - profile.guardpulse_score, 1)
            st.warning(
                f"Score {profile.guardpulse_score}/100 is {gap} points below the "
                f"trust threshold (80). Not yet visible to CEOs searching for vendors. "
                f"Re-run the swarm audit after addressing compliance gaps to improve your score."
            )