import streamlit as st
import pandas as pd

st.set_page_config(page_title="Climate Regulation Tracker", layout="centered")

SHEET_ID = "1sRVlCyzbXiLKTk33dFeqxcz5WRdMNl2Wulo0QXnbNas"
GID = "628203108"


@st.cache_data(ttl=300)  # re-fetches from Google at most once every 5 min
def load_data():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"
    df = pd.read_csv(url, skiprows=2)          # your real headers are on row 3
    df.columns = df.columns.str.strip()        # removes stray spaces in header names


    df.columns.values[15:22] = [
        "Disclosure: Scope 1", "Disclosure: Scope 2", "Disclosure: Scope 3",
        "Disclosure: PCF/LCA", "Disclosure: Climate Risk",
        "Disclosure: Target Setting", "Disclosure: Social & Governance",
    ]
    df.columns.values[22:26] = [
        "RefData: Scope 1", "RefData: Scope 2", "RefData: Scope 3", "RefData: PCF/LCA",
    ]
   
    df.columns.values[27:30] = [
        "Alignment (Calc Method): Scope 1+2", "Alignment (Calc Method): Scope 3",
        "Alignment (Calc Method): PCF/LCA",
    ]
    df.columns.values[30:33] = [
        "Alignment (Ref Data): Scope 1+2", "Alignment (Ref Data): Scope 3",
        "Alignment (Ref Data): PCF/LCA",
    ]
    return df


def alignment_chip(value):
    """Turn a raw 'Fully'/'Partially'/'Not at all'/'Irrelevant' cell into a quick-glance chip."""
    v = str(value).strip().lower()
    if v == "fully":
        return "🟢 Fully"
    if v == "partially":
        return "🟡 Partially"
    if v == "not at all":
        return "🔴 Not at all"
    if v == "irrelevant":
        return "⚪ Irrelevant"
    return "❔ Not yet assessed"


def alignment_summary(row):
    """Build a copy-paste-ready sentence grouping the 6 alignment dimensions by status."""
    dims = [
        ("Scope 1+2 calc. methodology", "Alignment (Calc Method): Scope 1+2"),
        ("Scope 3 calc. methodology", "Alignment (Calc Method): Scope 3"),
        ("PCF/LCA calc. methodology", "Alignment (Calc Method): PCF/LCA"),
        ("Scope 1+2 reference datasets", "Alignment (Ref Data): Scope 1+2"),
        ("Scope 3 reference datasets", "Alignment (Ref Data): Scope 3"),
        ("PCF/LCA reference datasets", "Alignment (Ref Data): PCF/LCA"),
    ]
    by_status = {}
    for label, col_name in dims:
        val = str(row.get(col_name, "")).strip()
        status = val if val and val.lower() != "nan" else "Not yet assessed"
        by_status.setdefault(status, []).append(label)

    order = ["Fully", "Partially", "Not at all", "Irrelevant", "Not yet assessed"]
    sentences = []
    for status in order:
        if status in by_status:
            sentences.append(f"**{status}** on {', '.join(by_status[status])}")
    return "; ".join(sentences) + "."


if "screen" not in st.session_state:
    st.session_state.screen = "role"


def go_to(screen_name):
    st.session_state.screen = screen_name


if st.session_state.screen == "role":
    st.title("Climate Regulation Tracker")
    st.write("Who's using this today?")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📊 Data team", use_container_width=True):
            go_to("data")
    with col2:
        if st.button("🧑‍💼 Sustainability team", use_container_width=True):
            go_to("sust")
    with col3:
        if st.button("📈 Product team", use_container_width=True):
            go_to("product")

# ======================================================================
# SCREEN 2a -- data team: "what reference data do we need, for this country"
# ======================================================================
elif st.session_state.screen == "data":
    if st.button("← back"):
        go_to("role")
    st.header("What reference data do we need to collect?")

    df = load_data()

    countries = sorted(df["Country"].dropna().unique())
    selected_country = st.selectbox("Country", countries)

    country_df = df[df["Country"] == selected_country]
    st.caption(f"{len(country_df)} regulation(s) found for {selected_country}")

    ref_cols = {
        "Scope 1": "RefData: Scope 1",
        "Scope 2": "RefData: Scope 2",
        "Scope 3": "RefData: Scope 3",
        "PCF/LCA": "RefData: PCF/LCA",
    }

    prescribed = {}   # scope -> [regulation names that MANDATE a specific dataset]
    recommended = {}  # scope -> [regulation names that merely ADVISE a dataset, optional]
    unassessed = {}   # scope -> [regulation names where this is still blank]

    for _, row in country_df.iterrows():
        reg_name = row["Regulation/Standard/Framework"]
        for scope_label, col_name in ref_cols.items():
            value = str(row.get(col_name, "")).strip().lower()
            if value == "prescribed":
                prescribed.setdefault(scope_label, []).append(reg_name)
            elif value == "recommended":
                recommended.setdefault(scope_label, []).append(reg_name)
            elif value == "" or value == "nan":
                unassessed.setdefault(scope_label, []).append(reg_name)

    if prescribed:
        st.write("**🔴 Must collect (Prescribed — mandatory):**")
        for scope_label, regs in prescribed.items():
            st.markdown(f"- **{scope_label}** — required by: {', '.join(regs)}")

    if recommended:
        st.write("**🟡 Should collect (Recommended — optional):**")
        for scope_label, regs in recommended.items():
            st.markdown(f"- **{scope_label}** — advised by: {', '.join(regs)}")

    if not prescribed and not recommended:
        st.write("No confirmed reference-dataset needs for this country yet.")

    if unassessed:
        st.warning(
            "Not fully assessed yet, don't assume 'not needed': "
            + "; ".join(f"{s} ({', '.join(r)})" for s, r in unassessed.items())
        )

    with st.expander("See full detail for this country"):
        st.dataframe(country_df, use_container_width=True)

# ======================================================================
# SCREEN 2b -- sustainability team: search a framework by name
# ======================================================================
elif st.session_state.screen == "sust":
    if st.button("← back"):
        go_to("role")
    st.header("Look up a framework")

    df = load_data()
    search = st.text_input("Framework name (e.g. JSE, ASRS, BRSR...)")

    if not search:
        st.caption("Type a name above to search.")
    else:
        matches = df[
            df["Regulation/Standard/Framework"].str.contains(search, case=False, na=False)
        ]

        if matches.empty:
            st.write("No matching framework found.")

        for _, row in matches.iterrows():
            st.subheader(row["Regulation/Standard/Framework"])
            st.caption(f"{row['Country']} · {row['Sector']} · {row['Compliance']}")

            # --- quick-glance chips: the fastest way to answer "are we aligned" ---
            st.write("**How aligned is Unravel? (calculation methodology)**")
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"Scope 1+2  \n{alignment_chip(row.get('Alignment (Calc Method): Scope 1+2'))}")
            c2.markdown(f"Scope 3  \n{alignment_chip(row.get('Alignment (Calc Method): Scope 3'))}")
            c3.markdown(f"PCF/LCA  \n{alignment_chip(row.get('Alignment (Calc Method): PCF/LCA'))}")

            st.write("**Reference dataset alignment**")
            c4, c5, c6 = st.columns(3)
            c4.markdown(f"Scope 1+2  \n{alignment_chip(row.get('Alignment (Ref Data): Scope 1+2'))}")
            c5.markdown(f"Scope 3  \n{alignment_chip(row.get('Alignment (Ref Data): Scope 3'))}")
            c6.markdown(f"PCF/LCA  \n{alignment_chip(row.get('Alignment (Ref Data): PCF/LCA'))}")

            # --- templated (not AI-generated) sentence, safe to paste into a client reply ---
            st.write("**Summary:**")
            st.info(f"{row['Regulation/Standard/Framework']}: {alignment_summary(row)}")

            # --- gap notes, only shown if the sheet actually has one ---
            gap = str(row.get("Gap Analysis/ Other Remarks", "")).strip()
            if gap and gap.lower() != "nan":
                st.write("**Gap analysis / notes:**")
                st.write(gap)

            with st.expander("See full row detail"):
                st.dataframe(row.to_frame().T, use_container_width=True)

            st.divider()

# ======================================================================
# SCREEN 2c -- product team: placeholder for now, full table too
# ======================================================================
elif st.session_state.screen == "product":
    if st.button("← back"):
        go_to("role")
    st.header("Aggregate view")
    st.caption("Placeholder.")

    df = load_data()
    st.dataframe(df, use_container_width=True)
