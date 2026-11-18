"""Ask Genie: the ACF Delta Share Compliance Genie space, embedded or via the Conversation API.

Primary experience is the embedded Genie Space (iframe). A native fallback uses
the Genie Conversation API for environments where iframe embedding is blocked
(third-party cookies disabled, or the workspace embedding policy is off).
"""

from __future__ import annotations

import streamlit as st

import config
from lib import genie, ui

ui.page_hero(
    "Ask Genie",
    "Ask about shares, agreements and findings: e.g. “Which shares expose direct identifiers "
    "that no agreement permits?” or “What must ACF do before changing shared data elements?”",
    icon="forum",
)

mode = st.segmented_control(
    "Mode",
    ["Embedded Genie", "Native (API)"],
    default="Embedded Genie",
    help=(
        "Embedded uses the Genie Space iframe. Native renders Genie answers "
        "inside this app via the Conversation API — use it if the iframe is "
        "blank (often caused by blocked third-party cookies)."
    ),
)

if mode == "Embedded Genie":
    if not config.GENIE_SPACE_ID:
        st.info(
            "No Genie Space configured yet. Run the job, then set the bundle variable `genie_space_id` "
            "to the ID printed by its create_genie_space task and run `databricks bundle deploy`.",
            icon=":material/info:",
        )
    else:
        embed_url = (
            f"{config.HOST}/embed/genie/rooms/{config.GENIE_SPACE_ID}"
            f"?o={config.ORG_ID}"
        )
        st.iframe(embed_url, height=780)
        st.caption(
            "If the panel is blank: enable third-party cookies, and confirm a "
            "workspace admin has allowlisted `*.databricksapps.com` under "
            "Settings → Security → External access → Embed dashboards."
        )

else:  # Native (API)
    if not genie.is_configured():
        st.info(
            "No Genie Space configured. Set the bundle variable `genie_space_id` and run `databricks bundle deploy`.",
            icon=":material/info:",
        )
        st.stop()

    if "genie_history" not in st.session_state:
        st.session_state.genie_history = []
        st.session_state.genie_conversation_id = None

    for turn in st.session_state.genie_history:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])
            if turn.get("sql"):
                with st.expander("Generated SQL", icon=":material/code:"):
                    st.code(turn["sql"], language="sql")
            if turn.get("dataframe") is not None:
                st.dataframe(turn["dataframe"], width="stretch")

    prompt = st.chat_input("Ask about Delta Share compliance…")
    if prompt:
        st.session_state.genie_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Asking Genie…"):
                try:
                    answer = genie.ask(
                        prompt, st.session_state.genie_conversation_id
                    )
                except Exception as exc:  # surface API/auth errors to the demoer
                    st.error(f"Genie request failed: {exc}", icon=":material/error:")
                    st.stop()
            st.session_state.genie_conversation_id = answer["conversation_id"]
            text = answer["text"] or "_(no narrative returned)_"
            st.markdown(text)
            if answer["sql"]:
                with st.expander("Generated SQL", icon=":material/code:"):
                    st.code(answer["sql"], language="sql")
            if answer["dataframe"] is not None:
                st.dataframe(answer["dataframe"], width="stretch")
        st.session_state.genie_history.append(
            {
                "role": "assistant",
                "content": text,
                "sql": answer["sql"],
                "dataframe": answer["dataframe"],
            }
        )
