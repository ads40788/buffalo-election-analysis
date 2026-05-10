"""
Generate a formatted literature review .docx for the Buffalo coalition inversion paper.
Run: python src/build_litreview.py
Output: docs/litreview_draft.docx
"""

from pathlib import Path
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import re

OUT = Path(__file__).parent.parent / "docs" / "litreview_draft.docx"
OUT.parent.mkdir(parents=True, exist_ok=True)

# ── Helpers ────────────────────────────────────────────────────────────────────

def add_hyperlink(paragraph, text, url):
    """Add a clickable hyperlink run to an existing paragraph."""
    part   = paragraph.part
    r_id   = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    hl     = OxmlElement("w:hyperlink")
    hl.set(qn("r:id"), r_id)
    new_r  = OxmlElement("w:r")
    rPr    = OxmlElement("w:rPr")
    style  = OxmlElement("w:rStyle")
    style.set(qn("w:val"), "Hyperlink")
    rPr.append(style)
    new_r.append(rPr)
    t = OxmlElement("w:t")
    t.text = text
    new_r.append(t)
    hl.append(new_r)
    paragraph._p.append(hl)
    return hl


def set_font(run, bold=False, italic=False, size=11, color=None):
    run.bold   = bold
    run.italic = italic
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor(*color)


def h1(doc, text):
    p = doc.add_heading(text, level=1)
    p.runs[0].font.size = Pt(18)
    p.runs[0].font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)
    return p


def h2(doc, text):
    p = doc.add_heading(text, level=2)
    p.runs[0].font.size = Pt(14)
    p.runs[0].font.color.rgb = RGBColor(0x4e, 0x79, 0xa7)
    return p


def body(doc, text, space_after=6):
    p = doc.add_paragraph(text)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.alignment   = WD_ALIGN_PARAGRAPH.JUSTIFY
    for run in p.runs:
        run.font.size = Pt(11)
    return p


def entry(doc, citation, url, insights, relevance):
    """Add one bibliography entry block."""
    # Citation line (bold author/year, hyperlinked title)
    cite_parts = re.match(r"^(.*?\)\.)\s+(.+?\.)(.*)$", citation, re.DOTALL)

    p = doc.add_paragraph()
    p.paragraph_format.left_indent    = Cm(0.6)
    p.paragraph_format.first_line_indent = Cm(-0.6)
    p.paragraph_format.space_after   = Pt(4)
    p.paragraph_format.space_before  = Pt(10)

    if cite_parts:
        author_run = p.add_run(cite_parts.group(1) + " ")
        set_font(author_run, bold=True, size=11)
        title_text = cite_parts.group(2).strip()
        rest_text  = cite_parts.group(3).strip()
        if url:
            add_hyperlink(p, title_text, url)
            if rest_text:
                r = p.add_run(" " + rest_text)
                set_font(r, size=11)
        else:
            r = p.add_run(title_text + (" " + rest_text if rest_text else ""))
            set_font(r, size=11)
    else:
        r = p.add_run(citation)
        set_font(r, bold=True, size=11)

    # Key insights
    for i, ins in enumerate(insights, 1):
        pi = doc.add_paragraph(style="List Bullet")
        pi.paragraph_format.left_indent  = Cm(1.2)
        pi.paragraph_format.space_after  = Pt(2)
        r_lbl = pi.add_run(f"Insight {i}: ")
        set_font(r_lbl, bold=True, size=10.5)
        r_txt = pi.add_run(ins)
        set_font(r_txt, size=10.5)

    # Relevance
    pr = doc.add_paragraph()
    pr.paragraph_format.left_indent = Cm(1.2)
    pr.paragraph_format.space_after = Pt(8)
    r_lbl = pr.add_run("Relevance to Buffalo study: ")
    set_font(r_lbl, bold=True, italic=True, size=10.5, color=(0x4e, 0x79, 0xa7))
    r_txt = pr.add_run(relevance)
    set_font(r_txt, italic=True, size=10.5)


# ── Document ───────────────────────────────────────────────────────────────────

doc = Document()

# Page margins
for section in doc.sections:
    section.top_margin    = Inches(1.1)
    section.bottom_margin = Inches(1.1)
    section.left_margin   = Inches(1.25)
    section.right_margin  = Inches(1.25)

# Default body font
doc.styles["Normal"].font.name = "Calibri"
doc.styles["Normal"].font.size = Pt(11)

# ── Title block ────────────────────────────────────────────────────────────────

t = doc.add_heading("Coalition Inversion in Urban Mayoralty", level=0)
t.alignment = WD_ALIGN_PARAGRAPH.CENTER
t.runs[0].font.size  = Pt(22)
t.runs[0].font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)

st = doc.add_paragraph("Literature Review Draft — Byron Brown and the 2021 Buffalo Write-In Campaign")
st.alignment = WD_ALIGN_PARAGRAPH.CENTER
st.runs[0].font.size   = Pt(12)
st.runs[0].font.color.rgb = RGBColor(0x55, 0x55, 0x55)
st.runs[0].italic = True

doc.add_paragraph()

# ── Introduction ───────────────────────────────────────────────────────────────

h1(doc, "Introduction")
body(doc,
    "Byron Brown's 2021 Buffalo mayoral campaign offers a rare natural experiment in urban electoral politics. "
    "After sixteen years in office, Brown lost the Democratic primary to democratic-socialist India Walton — "
    "then won the November general election as a write-in candidate, assembling a coalition almost perfectly "
    "inverted from the one that had sustained him throughout his tenure. Neighborhoods where he had been "
    "strongest in 2017 became his weakest in 2021, and vice versa (Pearson r ≈ −0.79 at the neighborhood level). "
    "This pattern sits at the intersection of at least five distinct bodies of literature: coalition theory, "
    "deracialization and Black urban leadership, incumbency advantage, the ecological structure of urban voting, "
    "and the political economy of white working-class realignment. The review below surveys each in turn, "
    "identifies the key theoretical claims, and notes where the Buffalo case confirms, complicates, or extends "
    "existing findings."
)

body(doc,
    "A note on methodology: the empirical results in this study are computed at the neighborhood level (N ≈ 35) "
    "and election-district level (N ≈ 207) using official Erie County Board of Elections canvass data merged "
    "with ACS 2020 5-year demographic estimates. Correlations and OLS regressions at the aggregate level are "
    "subject to the ecological inference caveat discussed in Section V."
)

# ── Section I ──────────────────────────────────────────────────────────────────

h2(doc, "I. Coalition Theory and the Minimum Winning Coalition")

body(doc,
    "The foundational question in coalition theory is not how large a winning coalition must be, "
    "but how small it can be. Riker's seminal formalization of this insight predicts that rational actors "
    "will avoid oversized coalitions because surplus members impose costs without providing additional benefit. "
    "Applied to electoral politics, this implies that a candidate who can construct a new minimum winning "
    "coalition after losing an old one faces a strategic, not merely a sentimental, calculus."
)

entry(doc,
    citation="Riker, W. H. (1962). The Theory of Political Coalitions. Yale University Press.",
    url="https://yalebooks.yale.edu/book/9780300001211/the-theory-of-political-coalitions/",
    insights=[
        "Political actors form the minimum coalition necessary to win and no larger — surplus members are costly and should be shed.",
        "Coalition boundaries are inherently unstable; the winning group has an incentive to exclude former partners once their votes are no longer decisive.",
    ],
    relevance=(
        "Brown's 2021 write-in strategy is a near-perfect Rikerian case: he shed his Black progressive base "
        "(which had defected to Walton) and recruited exactly enough white cross-over voters and Republicans "
        "to clear the general-election threshold — a textbook minimum winning coalition."
    ),
)

entry(doc,
    citation="Downs, A. (1957). An Economic Theory of Democracy. Harper & Row.",
    url="https://www.harpercollins.com/products/an-economic-theory-of-democracy-anthony-downs",
    insights=[
        "In a single-peaked, unimodal distribution of voter preferences, both candidates converge on the median voter — the 'median voter theorem.'",
        "The theorem breaks down when preferences are multimodal or when the candidate cannot credibly shift position between primary and general elections.",
    ],
    relevance=(
        "Buffalo's electorate in 2021 was effectively bimodal: a Black progressive bloc (activated by the primary) "
        "and a conservative-leaning white bloc mobilized for the general. Brown could not appeal to both simultaneously, "
        "making the median voter framework inapplicable and necessitating the coalition pivot."
    ),
)

# ── Section II ─────────────────────────────────────────────────────────────────

h2(doc, "II. Deracialization and Black Urban Leadership")

body(doc,
    "Deracialization — the strategic avoidance of explicitly racial appeals by Black candidates seeking "
    "to build cross-racial support — has been the dominant framework for understanding Black electoral success "
    "in majority-white cities since the 1980s. Brown's 2005–2017 tenure fit this mold reasonably well. "
    "His 2021 general-election campaign represents something more paradoxical: a candidate who had "
    "previously deracialized now winning by mobilizing a predominantly white coalition against a Black opponent."
)

entry(doc,
    citation=(
        "Perry, H. L. (1991). Deracialization as an Analytical Construct in American Urban Politics. "
        "Urban Affairs Quarterly, 27(2), 181–191."
    ),
    url="https://doi.org/10.1177/004208169102700201",
    insights=[
        "Deracialization involves three tactics: avoiding explicitly racial campaign themes, appealing to white economic anxieties, and building multiracial organizations.",
        "The strategy is most successful when the Black candidate can credibly project a 'race-neutral' governing image that does not threaten white voters.",
    ],
    relevance=(
        "Brown governed and campaigned in deracialized fashion for 16 years. The 2021 primary showed the limits of this "
        "approach when a more explicitly progressive Black challenger activated the base Brown had taken for granted."
    ),
)

entry(doc,
    citation=(
        "McCormick, J. P., & Jones, C. E. (1993). The Conceptualization of Deracialization: Thinking Through the Dilemma. "
        "In G. Persons (Ed.), Dilemmas of Black Politics. HarperCollins."
    ),
    url="https://www.google.com/books/edition/Dilemmas_of_Black_Politics/AAAACAAAQBAJ",
    insights=[
        "Deracialization creates a structural dilemma: winning white votes requires minimizing racial appeal, but this risks demobilizing the Black base that provides the electoral foundation.",
        "The dilemma intensifies when a Black challenger activates that base with an explicitly racial-justice framing.",
    ],
    relevance=(
        "The McCormick-Jones dilemma is precisely what materialized in the 2021 primary: Brown's 16-year deracialization "
        "left his Black coalition demobilized and susceptible to Walton's progressive mobilization."
    ),
)

entry(doc,
    citation=(
        "Hajnal, Z. L. (2007). America's Uneven Democracy: Race, Turnout, and Representation in City Politics. "
        "Cambridge University Press."
    ),
    url="https://doi.org/10.1017/CBO9780511755163",
    insights=[
        "Low, racially skewed turnout in city elections systematically benefits white voters — Black-preferred candidates win at lower rates than their population share would predict.",
        "When Black candidates do win, they typically do so with deracialized appeals that limit the scope of redistributive policy.",
    ],
    relevance=(
        "The primary/general turnout differential is central to the Buffalo case. The primary electorate was smaller and "
        "disproportionately progressive; the general electorate was larger and whiter — exactly the asymmetry Hajnal documents."
    ),
)

# ── Section III ────────────────────────────────────────────────────────────────

h2(doc, "III. Incumbency Advantage and Its Limits in City Politics")

body(doc,
    "The incumbency advantage literature documents the substantial electoral benefits that accrue to sitting "
    "officeholders — name recognition, resource advantages, credit-claiming, and the ability to deter strong challengers. "
    "The Buffalo case is interesting precisely because these advantages failed in the primary while partially reconstituting "
    "in the general election in an unprecedented form."
)

entry(doc,
    citation=(
        "Trounstine, J. (2008). Political Monopolies in American Cities: The Rise and Fall of Bosses and Reformers. "
        "University of Chicago Press."
    ),
    url="https://press.uchicago.edu/ucp/books/book/chicago/P/bo5298416.html",
    insights=[
        "City incumbents build 'political monopolies' by delivering selective benefits to key constituencies, structuring electoral rules, and raising the cost of opposition — but these monopolies eventually become brittle as the coalition calcifies.",
        "Monopoly collapse tends to be sudden rather than gradual: a critical mass of dissatisfied voters coordinates around a viable challenger once one emerges.",
    ],
    relevance=(
        "Brown's 16-year tenure matches Trounstine's monopoly model closely. Walton's 2021 primary victory fits the "
        "'sudden collapse' prediction — Brown's coalition had calcified, and the progressive challenger provided the "
        "coordination point. The write-in general win is outside Trounstine's framework, however, representing a "
        "novel post-monopoly survival strategy."
    ),
)

entry(doc,
    citation=(
        "Ansolabehere, S., & Snyder, J. M. (2002). The Incumbency Advantage in U.S. Elections: An Analysis of State and Federal Offices, 1942–2000. "
        "Electoral Studies, 21(2), 197–231."
    ),
    url="https://doi.org/10.1016/S0261-3794(01)00031-8",
    insights=[
        "The incumbency advantage is large (5–10 percentage points) and has grown over the post-war period, driven primarily by the 'personal vote' rather than party label.",
        "The advantage is largest in low-information races — precisely the context of most city elections.",
    ],
    relevance=(
        "Brown's general-election write-in win — despite no ballot line and after a humiliating primary loss — "
        "reflects the durability of the personal vote even when the party label is absent. "
        "Voters who knew Brown's name wrote it in; this is incumbency advantage at its most stripped-down."
    ),
)

# ── Section IV ─────────────────────────────────────────────────────────────────

h2(doc, "IV. Urban Racial Coalitions and the Limits of Multiracial Governance")

body(doc,
    "A substantial literature examines the conditions under which Black mayors can sustain multiracial "
    "governing coalitions, and the particular vulnerabilities of those coalitions when economic conditions "
    "shift or when intra-group challengers emerge."
)

entry(doc,
    citation=(
        "Browning, R. P., Marshall, D. R., & Tabb, D. H. (1984). Protest Is Not Enough: The Struggle of Blacks "
        "and Hispanics for Equality in Urban Politics. University of California Press."
    ),
    url="https://www.ucpress.edu/book/9780520051836/protest-is-not-enough",
    insights=[
        "Durable minority political incorporation requires a 'dominant coalition' that includes minority groups as active partners, not just electoral foot soldiers — incumbents who treat the minority base instrumentally invite challengers.",
        "Economic incorporation (jobs, contracts, services) is what converts electoral coalition membership into durable political loyalty.",
    ],
    relevance=(
        "If Brown's Black community base felt instrumentally used rather than genuinely incorporated, "
        "the Browning/Marshall/Tabb framework predicts exactly the kind of defection seen in the 2021 primary. "
        "Our neighborhood data show the sharpest Brown decline in Black community neighborhoods."
    ),
)

entry(doc,
    citation=(
        "Kaufmann, K. M. (2004). The Urban Voter: Group Conflict and Mayoral Voting Behavior in American Cities. "
        "University of Michigan Press."
    ),
    url="https://doi.org/10.3998/mpub.17786",
    insights=[
        "Racial group identity is the dominant predictor of mayoral vote choice in American cities — stronger than income, partisanship, or ideology in most elections.",
        "When a Black and a white candidate compete, racial group solidarity is especially strong among Black voters, while white voters divide more by class and ideology.",
    ],
    relevance=(
        "Kaufmann's finding directly predicts the coalition structure we observe: in the 2021 general (Brown vs. Walton), "
        "racial group identity should have produced near-unanimous Walton support in Black neighborhoods — "
        "yet Brown's write-in won enough crossover votes to prevail, suggesting his personal vote partially overrode group cues."
    ),
)

entry(doc,
    citation=(
        "Hajnal, Z., & Trounstine, J. (2005). Where Turnout Matters: The Consequences of Uneven Turnout in City Politics. "
        "Journal of Politics, 67(2), 515–535."
    ),
    url="https://doi.org/10.1111/j.1468-2508.2005.00327.x",
    insights=[
        "Cities with higher and more even turnout produce governments more responsive to minority residents; low-turnout elections systematically over-represent affluent white voters.",
        "The composition of the electorate — not just its size — determines representational outcomes.",
    ],
    relevance=(
        "The 2021 Democratic primary had unusually high progressive mobilization relative to the general, "
        "flipping the normal turnout asymmetry. The general electorate then reverted to Hajnal-Trounstine's "
        "typical pattern: larger, whiter, more favorable to the incumbent."
    ),
)

# ── Section V ──────────────────────────────────────────────────────────────────

h2(doc, "V. Ecological Inference and Neighborhood-Level Analysis")

body(doc,
    "Because precinct and neighborhood data aggregate individual votes, drawing individual-level conclusions "
    "requires care. The ecological inference literature provides both the caution and the tools."
)

entry(doc,
    citation=(
        "Robinson, W. S. (1950). Ecological Correlations and the Behavior of Individuals. "
        "American Sociological Review, 15(3), 351–357."
    ),
    url="https://doi.org/10.2307/2087176",
    insights=[
        "The 'ecological fallacy': correlations computed at the aggregate level (census tracts, neighborhoods) can differ substantially — even reverse in sign — from individual-level correlations.",
        "Aggregate analysis is appropriate for studying aggregate phenomena (e.g., neighborhood-level swing) but cannot directly prove individual vote-switching.",
    ],
    relevance=(
        "Our r = −0.79 at the neighborhood level is a statement about neighborhood-level patterns, not individual voters. "
        "It is consistent with — but does not prove — that white working-class individuals switched to Brown while "
        "Black voters stayed home or backed Walton. This caveat should appear in the paper's methods section."
    ),
)

entry(doc,
    citation=(
        "King, G. (1997). A Solution to the Ecological Inference Problem: Reconstructing Individual Behavior "
        "from Aggregate Data. Princeton University Press."
    ),
    url="https://press.princeton.edu/books/paperback/9780691012438/a-solution-to-the-ecological-inference-problem",
    insights=[
        "King's EI method uses aggregate data with known marginals (total votes per group, total votes per candidate) to estimate the probability that a typical member of group X voted for candidate Y.",
        "The method produces bounds on individual-level parameters and is widely used in Voting Rights Act litigation and academic urban politics research.",
    ],
    relevance=(
        "If the data structure permits (we need racial composition + vote totals at the ED level), King's EI "
        "could produce defensible individual-level estimates of Brown's Black vs. white vote shares — "
        "substantially strengthening the paper's empirical contribution beyond neighborhood-level correlation."
    ),
)

# ── Section VI ─────────────────────────────────────────────────────────────────

h2(doc, "VI. White Working-Class Political Behavior and Cross-Racial Voting")

body(doc,
    "A growing literature examines why white working-class voters have shifted political allegiances across "
    "multiple electoral contexts. The Buffalo case — where lower-income white neighborhoods swung most sharply "
    "toward Brown in 2021 — connects to this literature at the local level."
)

entry(doc,
    citation=(
        "Gest, J. (2016). The New Minority: White Working Class Politics in an Age of Immigration and Inequality. "
        "Oxford University Press."
    ),
    url="https://doi.org/10.1093/acprof:oso/9780190600105.001.0001",
    insights=[
        "White working-class voters in deindustrialized cities exhibit a politics of 'nostalgic deprivation' — they vote to restore a perceived lost status rather than to advance material interests narrowly defined.",
        "Their attachment to local institutions and place-based identity makes them responsive to candidates who signal continuity and belonging rather than systemic change.",
    ],
    relevance=(
        "South Buffalo and working-class Niagara/North Buffalo neighborhoods drove Brown's strongest write-in numbers. "
        "Gest's framework suggests these voters may have backed Brown not despite his incumbency but because of it — "
        "he represented familiar continuity against Walton's explicitly transformational platform."
    ),
)

entry(doc,
    citation=(
        "Cramer, K. J. (2016). The Politics of Resentment: Rural Consciousness in Wisconsin and the Rise of Scott Walker. "
        "University of Chicago Press."
    ),
    url="https://press.uchicago.edu/ucp/books/book/chicago/P/bo22879533.html",
    insights=[
        "Place-based identity ('rural consciousness') operates as a politically potent frame that can override economic self-interest and override partisan cues — voters support candidates who validate their community's identity.",
        "Resentment toward perceived elites (in Cramer's case, Madison professionals; in urban contexts, progressive activists) is a powerful mobilizing force.",
    ],
    relevance=(
        "Though Cramer's subjects are rural Wisconsin voters, the mechanism maps onto South Buffalo's 'neighborhood consciousness.' "
        "Walton's progressive platform may have read as culturally elite to these voters, making Brown — despite his Democratic establishment ties — "
        "the identity-consistent choice."
    ),
)

# ── Section VII ────────────────────────────────────────────────────────────────

h2(doc, "VII. Primary Elections, Party Organization, and Nomination Politics")

body(doc,
    "The 2021 primary loss is the precipitating event for everything that follows. Primary electorates "
    "differ systematically from general electorates, and the conditions that allow insurgent primary victories "
    "have been extensively studied."
)

entry(doc,
    citation=(
        "Gerber, E. R., & Morton, R. B. (1998). Primary Election Systems and Representation. "
        "Journal of Law, Economics, and Organization, 14(2), 304–324."
    ),
    url="https://doi.org/10.1093/jleo/14.2.304",
    insights=[
        "Closed primary systems (only registered Democrats vote) produce more ideologically extreme nominees than open primaries — the activist base determines the outcome.",
        "Incumbents are most vulnerable to primary challenges when turnout is low and the challenger can mobilize a motivated ideological bloc.",
    ],
    relevance=(
        "New York's closed Democratic primary meant the 2021 contest was decided by a narrow, highly activated "
        "progressive electorate — exactly the condition under which Walton's mobilization was most potent. "
        "Brown's write-in general pivot was structurally enabled by the different composition of the general electorate."
    ),
)

entry(doc,
    citation=(
        "Key, V. O. (1949). Southern Politics in State and Nation. Alfred A. Knopf "
        "[reprinted 1984, University of Tennessee Press]."
    ),
    url="https://utpress.org/title/southern-politics-in-state-and-nation/",
    insights=[
        "In one-party systems, the primary is the only meaningful election — factionalism, personality, and local organization matter more than ideology.",
        "The candidate who can 'get out the vote' in a low-information, low-turnout primary context has a structural advantage that does not translate to the general.",
    ],
    relevance=(
        "Buffalo's effective one-party Democratic politics for most of the post-war period mirrors Key's Southern findings: "
        "the primary was effectively the election. Brown's 2021 general write-in victory is anomalous precisely because "
        "it broke this structure — the general suddenly became competitive."
    ),
)

# ── Section VIII ───────────────────────────────────────────────────────────────

h2(doc, "VIII. Gaps, Extensions, and Positioning the Buffalo Study")

body(doc,
    "The existing literature does not offer a clean template for what happened in Buffalo in 2021. "
    "Coalition inversion — not erosion, not loss, but a near-perfect sign-flip of the geographic coalition — "
    "is virtually undocumented in the urban politics literature. Several specific gaps emerge:"
)

gaps = [
    ("Write-in victories in partisan general elections",
     "The literature on write-in campaigns is thin and focused on non-partisan or low-salience races. "
     "A sitting mayor losing a major-party primary and winning the general as a write-in is historically rare."),
    ("Coalition inversion as distinct from coalition erosion",
     "Existing work (Trounstine, Browning et al.) describes loss of coalition members but not the geographic reversal "
     "documented here. A correlation of −0.79 between 2017G and 2021G Brown vote share is extreme and arguably "
     "constitutes a new electoral phenomenon warranting formal documentation."),
    ("Interaction of race and class in urban swing",
     "The OLS regression with the pct_white × income interaction term tests whether Brown's 2021 gains were "
     "concentrated in low-income (working-class) white neighborhoods — as opposed to affluent white neighborhoods "
     "or mixed neighborhoods. This is a novel empirical contribution."),
    ("Ecological inference at the election district level",
     "Applying King's EI to the Buffalo ED-level data (207 matched districts) could yield the first individual-level "
     "estimates of cross-racial voting in this race, providing a model for future urban write-in studies."),
]

for title, desc in gaps:
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.left_indent = Cm(0.6)
    p.paragraph_format.space_after = Pt(5)
    r1 = p.add_run(title + ": ")
    set_font(r1, bold=True, size=11)
    r2 = p.add_run(desc)
    set_font(r2, size=11)

doc.add_paragraph()

# ── Closing ────────────────────────────────────────────────────────────────────

h2(doc, "Suggested Publication Venues")

venues = [
    ("Urban Affairs Review", "Top peer-reviewed journal for urban political science; directly covers mayoral politics, racial coalitions, and city-level electoral analysis.", "https://journals.sagepub.com/home/uar"),
    ("PS: Political Science & Politics", "APSA's practitioner-facing journal; the 'Research Note' format (3,000–5,000 words) is ideal for a tightly scoped empirical finding like coalition inversion.", "https://www.cambridge.org/core/journals/ps-political-science-and-politics"),
    ("American Politics Research", "Publishes quantitative analyses of subnational electoral behavior; strong fit for the regression-based coalition analysis.", "https://journals.sagepub.com/home/apr"),
    ("SocArXiv (preprint)", "Open-access preprint server for social science; enables rapid dissemination before peer review. Recommended as a first step.", "https://osf.io/preprints/socarxiv"),
]

for name, desc, url in venues:
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.6)
    p.paragraph_format.space_after = Pt(6)
    r1 = p.add_run(name + " — ")
    set_font(r1, bold=True, size=11)
    r2 = p.add_run(desc + " ")
    set_font(r2, size=11)
    add_hyperlink(p, url, url)

doc.add_paragraph()
footer_p = doc.add_paragraph("Generated from Erie County BOE canvass data and ACS 2020 5-year estimates. "
                              "All correlation and regression results are computed at the neighborhood or election-district level. "
                              "Individual-level inference requires ecological inference methods (King 1997). "
                              "Draft — verify all DOIs and publication details before submission.")
footer_p.runs[0].font.size = Pt(9)
footer_p.runs[0].font.color.rgb = RGBColor(0x88, 0x88, 0x88)
footer_p.runs[0].italic = True

# ── Save ───────────────────────────────────────────────────────────────────────

doc.save(OUT)
print(f"Saved: {OUT}")
