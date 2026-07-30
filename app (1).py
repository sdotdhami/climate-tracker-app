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

    # The sheet reuses "Scope 1 / 2 / 3 / PCF-LCA" as a column header THREE
    # times for three different things (disclosure requirement, reference
    # dataset need, Unravel's own coverage). Pandas can't tell those apart
    # by name, so we rename the first two groups here by POSITION -- i.e.
    # by which column number they are, left to right, based on the sheet's
    # current layout. If someone adds/removes a column upstream in the
    # Google Sheet, these numbers will need to be re-checked.
    df.columns.values[15:22] = [
        "Disclosure: Scope 1", "Disclosure: Scope 2", "Disclosure: Scope 3",
        "Disclosure: PCF/LCA", "Disclosure: Climate Risk",
        "Disclosure: Target Setting", "Disclosure: Social & Governance",
    ]
    df.columns.values[22:26] = [
        "RefData: Scope 1", "RefData: Scope 2", "RefData: Scope 3", "RefData: PCF/LCA",
    ]
    return df


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

    needed = {}       # scope -> [regulation names that need it - Recommended or Prescribed]
    unassessed = {}   # scope -> [regulation names where this is still blank]

    for _, row in country_df.iterrows():
        reg_name = row["Regulation/Standard/Framework"]
        for scope_label, col_name in ref_cols.items():
            value = str(row.get(col_name, "")).strip()
            # FIX: "Prescribed" was being silently dropped before -- it's the
            # stronger of the two signals (a framework mandating a specific
            # dataset), so it must count as "needed" just like "Recommended".
            if value.lower() in ("recommended", "prescribed"):
                needed.setdefault(scope_label, []).append(reg_name)
            elif value == "" or value.lower() == "nan":
                unassessed.setdefault(scope_label, []).append(reg_name)

    if needed:
        st.write("**Collect reference data for:**")
        for scope_label, regs in needed.items():
            st.markdown(f"- **{scope_label}** — needed because of: {', '.join(regs)}")
    else:
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
    if search:
        matches = df[
            df["Regulation/Standard/Framework"].str.contains(search, case=False, na=False)
        ]
        st.dataframe(matches, use_container_width=True)
    else:
        st.caption("Type a name above to search.")

# ======================================================================
# SCREEN 2c -- product team: placeholder for now, full table too
# ======================================================================
elif st.session_state.screen == "product":
    if st.button("← back"):
        go_to("role")
    st.header("Aggregate view")
    st.caption("Placeholder -- we'll build real counts/charts here next.")

    df = load_data()
    st.dataframe(df, use_container_width=True)
