import re
import json
from urllib.parse import urljoin

import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup

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
    # Same duplicate-header problem again further right: "Fully/Partially/Not at
    # all/Irrelevant" alignment ratings appear as TWO more Scope1+2/Scope3/PCF-LCA
    # trios -- one for calculation methodology, one for reference datasets. Same
    # position-based fix, same caveat about re-checking if the sheet layout changes.
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


# ---------------------------------------------------------------------------
# Article extraction: fetch a pasted article (and any "Read more" link it
# points to), then ask an LLM to pull out tracker-shaped facts -- grounded
# strictly in that text, never from the model's own general knowledge.
# ---------------------------------------------------------------------------
READ_MORE_PATTERN = re.compile(r"read more|full story|learn more|continue reading", re.IGNORECASE)

EXTRACTION_COLUMNS = [
    "Regulation/Standard/Framework", "Country", "Region", "Sector", "Compliance",
    "Penalty for Non-Compliance", "Category", "Governing Body Type", "Target Businesses",
    "Published Date", "Current Implementation Status", "Phased", "Earliest Year of Impact",
    "Link to Framework", "Regulating Body",
    "Disclosure: Scope 1", "Disclosure: Scope 2", "Disclosure: Scope 3", "Disclosure: PCF/LCA",
    "Disclosure: Climate Risk", "Disclosure: Target Setting", "Disclosure: Social & Governance",
    "RefData: Scope 1", "RefData: Scope 2", "RefData: Scope 3", "RefData: PCF/LCA",
    "Summary of what changed",
]

EXTRACTION_SYSTEM_PROMPT = f"""You are extracting factual data points about sustainability/
climate regulations from source text, to help fill in a regulation-tracking spreadsheet.

RULES -- follow strictly:
- Use ONLY information explicitly stated in the provided source text. No outside knowledge,
  no inference, no filling gaps from what you generally know about a named regulation.
- If a field is not stated in the source text, write exactly "Not stated in this source".
- The source text may cover MULTIPLE distinct regulations/updates (e.g. a digest page with
  several unrelated stories). Return ONE object per distinct topic -- do not merge unrelated
  topics into one entry, and do not split a single topic into several entries.
- For "Country": use the single word "Any" for anything global/international/multi-jurisdiction
  (do NOT use "International", "Global", "ISO", etc. -- this tracker's standard term is "Any").
- Do NOT attempt to fill "Relevant Feature(s)" or any "Alignment" field -- these describe
  Unravel's own product and cannot be known from an external source. Do not include them
  in your output at all.
- For each entry, include "source_article_url": the specific SOURCE label (URL) shown in the
  text below that this entry's information actually came from.

Return ONLY a JSON array of objects (no markdown fences, no commentary). Each object must
have exactly these keys: {json.dumps(EXTRACTION_COLUMNS + ["source_article_url"])}
"""


def fetch_page_text(url, max_chars=6000):
    """Fetch a URL and return (visible_text, parsed_soup)."""
    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars], soup


def find_read_more_links(soup, base_url, limit=8):
    """Find links whose visible text looks like 'Read more' / 'Learn more' etc."""
    links, seen = [], set()
    for a in soup.find_all("a", href=True):
        label = a.get_text(strip=True)
        if READ_MORE_PATTERN.search(label):
            full_url = urljoin(base_url, a["href"])
            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)
        if len(links) >= limit:
            break
    return links


def gather_source_text(main_url):
    """Fetch the pasted page, plus any 'Read more' targets it links to.
    Returns (combined_text, list_of_followed_links)."""
    main_text, soup = fetch_page_text(main_url)
    chunks = [f"=== SOURCE: {main_url} ===\n{main_text}"]

    followed = []
    for link in find_read_more_links(soup, main_url):
        try:
            sub_text, _ = fetch_page_text(link)
            chunks.append(f"=== SOURCE: {link} ===\n{sub_text}")
            followed.append(link)
        except requests.RequestException:
            continue  # a broken/blocked follow-up link shouldn't fail the whole extraction

    return "\n\n".join(chunks), followed


def extract_regulations(source_text, api_key, model="gemini-3.5-flash"):
    """Send the gathered text to Gemini and parse the JSON array it returns."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    resp = requests.post(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "system_instruction": {"parts": [{"text": EXTRACTION_SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": source_text}]}],
            "generationConfig": {"temperature": 0},
        },
        timeout=60,
    )
    if not resp.ok:
        # Surface Google's actual error body -- a bare status code alone
        # doesn't say whether it's billing, a bad model name, or something else.
        raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text}")

    data = resp.json()
    try:
        content = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        raise RuntimeError(f"Unexpected Gemini response shape: {data}")

    if content.startswith("```"):
        content = re.sub(r"^```(json)?|```$", "", content, flags=re.MULTILINE).strip()
    return json.loads(content)


if "screen" not in st.session_state:
    st.session_state.screen = "role"


def go_to(screen_name):
    st.session_state.screen = screen_name


if st.session_state.screen == "role":
    st.title("Climate Regulation Tracker")
    st.write("Who's using this today?")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("📊 Data team", use_container_width=True):
            go_to("data")
    with col2:
        if st.button("🧑‍💼 Sustainability team", use_container_width=True):
            go_to("sust")
    with col3:
        if st.button("📈 Product team", use_container_width=True):
            go_to("product")
    with col4:
        if st.button("🔎 Extract from article", use_container_width=True):
            go_to("extract")

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
            st.write("**Summary — copy/paste for a client reply:**")
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
    st.caption("Placeholder -- we'll build real counts/charts here next.")

    df = load_data()
    st.dataframe(df, use_container_width=True)

# ======================================================================
# SCREEN 2d -- extract structured data from a pasted article link
# ======================================================================
elif st.session_state.screen == "extract":
    if st.button("← back"):
        go_to("role")
    st.header("Extract regulation updates from an article")
    st.caption(
        "Paste a link to a news article or regulatory update. If that page links out "
        "to a fuller 'Read more' source, that gets pulled in too. If the page covers "
        "several separate stories (like a monthly digest), each one comes back as its "
        "own row below -- just ignore the ones that aren't relevant."
    )

    url = st.text_input("Article URL")
    go = st.button("Extract")

    if go and url:
        try:
            with st.spinner("Fetching the article..."):
                source_text, followed_links = gather_source_text(url)
        except requests.RequestException as e:
            st.error(f"Couldn't fetch that page: {e}")
            st.stop()

        if followed_links:
            st.caption(f"Also followed {len(followed_links)} 'Read more' link(s) found on the page:")
            for link in followed_links:
                st.caption(f"— {link}")

        try:
            with st.spinner("Extracting data (this calls the AI, takes a few seconds)..."):
                api_key = st.secrets["GEMINI_API_KEY"]  # set in Streamlit Cloud's app Secrets
                results = extract_regulations(source_text, api_key)
        except KeyError:
            st.error("No Gemini API key found. Add GEMINI_API_KEY in the app's Secrets settings.")
            st.stop()
        except Exception as e:
            st.error(f"Extraction failed: {e}")
            st.stop()

        if not results:
            st.write("No distinct regulation topics found in that page.")
        else:
            st.success(f"Found {len(results)} topic(s). Review each before copying into the tracker.")

            # quick-copy table across all topics at once
            st.dataframe(pd.DataFrame(results), use_container_width=True)

            # full detail per topic, easier to read one at a time
            for i, row in enumerate(results):
                title = row.get("Regulation/Standard/Framework") or f"Topic {i + 1}"
                with st.expander(title, expanded=(len(results) == 1)):
                    st.caption(f"Source: {row.get('source_article_url', 'Not stated in this source')}")
                    for col in EXTRACTION_COLUMNS:
                        val = row.get(col, "Not stated in this source")
                        st.markdown(f"**{col}:** {val}")
    elif go and not url:
        st.warning("Paste a URL first.")
