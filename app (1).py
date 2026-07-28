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
    return df



if "screen" not in st.session_state:
    st.session_state.screen = "role"           # first time the app ever loads


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
# SCREEN 2a -- data team: full table, for now
# ======================================================================
elif st.session_state.screen == "data":
    if st.button("← back"):
        go_to("role")
    st.header("Reference data priorities")

    df = load_data()
    st.dataframe(df, use_container_width=True)

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
