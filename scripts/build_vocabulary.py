"""Build a reviewable bilingual seed from a local ECDICT CSV and source corpus.
No API keys, resume text, names, contact details or document excerpts are exported.
Run from the project root. Imported definitions are labelled, never called examples.
"""

import csv
import hashlib
import json
import re
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data/corpus"
SEED = ROOT / "backend/seed"
DICTIONARY = "https://github.com/skywind3000/ECDICT"
JOB = """algorithm architecture asynchronous synchronous authentication authorization automation backend frontend bandwidth benchmark binary boolean buffer byte compiler compilation compression configuration connectivity constructor context coroutine database debugger debugging declaration dependency deprecated deterministic diagnostic directory distributed documentation encoding executable execution expression framework function generic identifier immutable implementation initialization integration interpreter iteration iterator library literal memory migration module namespace networking optimization overload override parameter persistence pointer protocol recursion reference repository request response routing runtime scheduler semaphore serialization socket specification storage streaming subscription synchronization syntax template terminal timeout timestamp tracing troubleshooting tuple validation variable vector version virtualization worker adapter aggregate annotation assertion assignment attribute batch binding breakpoint browser checksum client collection command compatibility component computation constraint constructor counter daemon dashboard decorator delimiter destination encryption entity enumeration environment event filter firmware format generator handler hierarchy host increment initialization instruction integer interrupt interval invocation keyword layer listener location mapping metadata modifier notification operand operator overload packet parser pattern performance platform plugin polling port precision procedure processor proxy receiver redirect reflection registration registry rendering resolver retention retry revision router sampling segment sequence signature snapshot source statement stream string structure subscriber suffix symbol terminal topology trigger unicode upload utility value virtual widget alias abort allocate append apply assert attach bind bootstrap buffer calculate cancel cascade cast catch concatenate connect construct convert decode decrement deduplicate defer delete deserialize detach dispatch dispose emit enqueue evaluate execute expand expose extend fetch flush format forward generate hash implement import increment inject initialize insert inspect instantiate invoke iterate join load lookup map marshal modify mutate normalize notify optimize override parse persist poll process propagate publish queue read reconnect recover recurse redirect refresh register reload render replicate request resolve restore retrieve retry return revert rotate route sanitize scan schedule search select serialize shuffle sort split subscribe synchronize terminate throttle trace transform traverse truncate unsubscribe update upgrade upload validate verify wrap yield accuracy accessibility adapter aggregation asynchronous audit authorization capacity checkpoint checksum collaboration complexity compliance compression configuration consensus conversion coordination correlation correctness coverage decomposition delegation design detection diagnosis discovery efficiency elimination encoding enhancement exception expiration failure flexibility garbage guideline handshake heartbeat incident instrumentation integrity interoperability limitation localization maintenance manifest mechanism membership mitigation modification monitoring negotiation notification nullability operation pagination parallelism pipeline portability priority production profiling provisioning readiness recoverability redundancy reliability rendering reproducibility requirement resolution responsiveness scalability shutdown simulation stability standardization strategy telemetry termination tolerance transparency usability utilization verification versioning visibility workload""".split()
BUSINESS = """accountability agenda agreement allocation allowance amendment announcement appointment appraisal approval arbitration arrangement assessment asset assignment assurance attachment attendance attention audit authority authorization balance bankruptcy benefit bid billing bonus brand breakdown briefing brokerage budget cancellation candidate capability capital career cash challenge collaboration colleague commitment compensation competitor complaint compliance compromise concern concession confidentiality confirmation conflict consent consideration consolidation consultant consultation consumer contingency contractor contribution cooperation coordination corporation correspondence cost credit creditor currency customer deadline decision deduction delegation demand department depreciation deposit description designation development discount discretion discrimination discrepancy dismissal dispute distribution dividend earnings efficiency eligibility employment engagement enterprise entrepreneur equity escalation estimate evaluation expenditure expense expertise extension facility feedback finance forecast franchise fraud funding guarantee guidance headquarters incentive income incorporation increment indicator industry inflation initiative innovation inquiry insight inspection installment institution insurance interest inventory investment invoice jurisdiction leadership lease liability license logistics management mandate manufacture margin marketing maturity milestone minutes mission motivation negotiation objective obligation occupancy onboarding operation opportunity organization outcome outsourcing overhead ownership partnership payroll pension permission planning portfolio position presentation priority procurement productivity profit projection promotion proposal prospect provision purchase qualification quotation receipt recommendation recruitment referral refund regulation reimbursement rejection relationship relocation remuneration renewal rent reputation requirement resignation resource responsibility restructuring retention retirement revenue revision reward risk salary sales sanction schedule scope security shareholder shipment signature sponsorship stability standard stakeholder statement strategy subsidiary succession summary supplier supervision supply surplus sustainability target taxation tender termination threshold trademark training transaction transparency turnover undertaking valuation variance vendor verification vision warranty workflow workforce workshop expenditure receivable payable deduction collateral solvency arrears consortium fiduciary merger acquisition valuation liquidity investment reimbursement reimbursement reimbursement""".split()
IELTS_TOPICS = """academic accommodation accumulation achievement adaptation adequate adjacent adjustment advocate agriculture alternative ambiguity analysis annual anticipate apparent application appropriate approximation arbitrary assessment assumption attitude attribution autonomy availability awareness barrier beneficial biodiversity boundary capability capacity category circumstance classification coherent coincide commitment communication comparison compensation complexity component comprehensive concentration conclusion concurrent consequence considerable consistent constitute consumption contemporary context contrast contribution conventional conversion cooperation correlation crucial cumulative curriculum debate decline deduction demonstrate denote depression derive deterioration deviation dimension discrimination displacement distinction distribution diversity domestic dominant duration dynamic economic ecosystem efficiency eliminate empirical enable encounter energy enhance ensure environment equivalent erosion establish estimate evaluate evident evolution exceed exclude expansion expenditure explicit exploitation external extract facilitate factor feature federal fertile finite flexibility fluctuate framework fundamental furthermore gender generation global hypothesis identical ideology illustrate immigration implication incentive incidence inclination income indicator inevitable infrastructure inherent initial initiative innovation input insight inspection instance institution instruction integration interaction internal interpretation interval intervention intrinsic investigation investment isolation labor legislation liberal link logical marginal migration modification motivation mutual network neutral nevertheless nonetheless norm nuclear nutrition objective obtain obvious occupation offset ongoing option orientation outcome output overall paradigm parallel parameter participant perception period perspective phenomenon philosophy physical policy portion positive potential practitioner preceding predominant preliminary presume previous primary principle priority procedure process proportion prospect protocol psychological publication pursuit qualitative quantitative radical random range ratio rational recover region regulation reinforce reject relevant reliable removal require research reside resolution resource response restrict retain reveal revenue reverse revision revolution rigid role scenario schedule scope sector sequence shift significant similar simulation sole source specific specify stability statistic status straightforward strategy stress structure subsequent subsidy substitute sufficient supplement survey sustainable symbol target task technical technique technology temporary theory thereby thesis topic trace tradition transfer transform transition transmission trend trigger ultimate undergo underlying undertake uniform unique utilize valid variation version virtual visible visual voluntary whereas widespread workforce environment habitat conservation renewable pollution emission climate transport urban rural population sanitation healthcare literacy education scholarship tuition vocational curriculum qualification biodiversity waste recycling consumption fossil renewable ecological urbanization unemployment inequality affordability accessibility globalization sustainable trade export import metropolitan congestion pedestrian infrastructure entrepreneurship unemployment welfare housing resident commuting municipal leisure recreation tourism heritage culture diversity inclusion minority equality opportunity public policy unemployment poverty poverty poverty""".split()


def clean(s):
    return s.replace("\\n", "\n").strip()


def main():
    dictionary = {}
    with (CORPUS / "ecdict.csv").open() as f:
        for row in csv.DictReader(f):
            word = row["word"]
            if (
                re.fullmatch("[a-z][a-z -]{2,45}", word)
                and row["translation"]
                and row["definition"]
            ):
                dictionary[word] = row
    original = json.loads((SEED / "content.json").read_text())["words"]
    seen = {r["term"].lower() for r in original}
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    sources = [(r, (CORPUS / (r["id"] + ".txt")).read_text().lower()) for r in manifest]
    resume = (CORPUS / "resume.private.txt").read_text().lower()
    overrides = {}
    for line in (SEED / "context_glossary.tsv").read_text().splitlines():
        term, meaning, example, translation, collocation = line.split("|")
        overrides[term] = dict(
            meaning=meaning,
            example=example,
            translation=translation,
            collocation=collocation,
        )
    definitions_authored = {}
    for line in (SEED / "definition_overrides.tsv").read_text().splitlines():
        term, meaning, definition = line.split("|")
        definitions_authored[term] = (meaning, definition)
    result = []
    evidence = []

    def add(term, deck):
        if term in seen:
            return False
        d = dictionary.get(term)
        override = overrides.get(term)
        if not d and not override and term not in definitions_authored:
            return False
        if d and not override:
            # Exclude inflected-only entries; use the dictionary's headword instead.
            if re.search(r"(?:^|/)0:", d["exchange"]):
                return False
            definitions = clean(d["definition"]).splitlines()
            translations = clean(d["translation"]).splitlines()
            if deck == "job":
                definitions.sort(
                    key=lambda line: (
                        not bool(
                            re.search(
                                r"computer|program|software|data|system|network|code",
                                line,
                                re.I,
                            )
                        )
                    )
                )
                translations.sort(key=lambda line: "[计]" not in line)
            elif deck == "business":
                definitions.sort(
                    key=lambda line: (
                        not bool(
                            re.search(
                                r"business|financ|money|pay|employ|commercial|agreement|company",
                                line,
                                re.I,
                            )
                        )
                    )
                )
                translations.sort(key=lambda line: "[经]" not in line)
            definition = re.sub(r"^[a-z.]+\.\s*", "", definitions[0]).strip()
            if (
                len(definition) < 14
                or len(definition) > 450
                or re.search(
                    r"\b(genus|species|archaic|obsolete)\b|past participle|past tense",
                    definition,
                    re.I,
                )
            ):
                return False
            meaning = re.sub(r"\[[^]]+\]\s*", "", translations[0])[:300]
            pos = re.match(r"([a-z]+\.)", definitions[0])
            data = dict(
                meaning=meaning,
                example=definition[0].upper() + definition[1:].rstrip(".") + ".",
                translation="中文释义：" + meaning,
                collocation="",
                pos=pos.group(1) if pos else "词汇",
                example_kind="definition",
            )
        elif override:
            data = {
                **override,
                "pos": "phrase" if " " in term or "-" in term else "n.",
                "example_kind": "example",
            }
        else:
            meaning, definition = definitions_authored[term]
            data = dict(
                meaning=meaning,
                example=definition,
                translation="中文释义：" + meaning,
                collocation="",
                pos="n.",
                example_kind="definition",
            )
        if re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", resume):
            source_url = DICTIONARY
            label = "个人简历提取 · " + ("原创工作例句" if override else "ECDICT 释义")
            kind = "resume"
        else:
            source = next(
                (
                    s
                    for s, t in sources
                    if re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", t)
                ),
                None,
            )
            if source:
                source_url = source["url"]
                label = (
                    source["label"]
                    + " · "
                    + ("原创例句" if override else "ECDICT 释义")
                )
                kind = source["id"]
            else:
                source_url = DICTIONARY
                label = (
                    (
                        "软件与职场主题选编"
                        if deck == "job"
                        else "商务主题选编"
                        if deck == "business"
                        else "雅思主题选编"
                    )
                    + " · "
                    + ("原创例句" if override else "ECDICT 释义")
                )
                kind = "topic-selection"
        if term in definitions_authored and not override:
            meaning, definition = definitions_authored[term]
            data.update(
                meaning=meaning,
                example=definition,
                translation="中文释义：" + meaning,
                example_kind="definition",
            )
            label = label.replace("ECDICT 释义", "工作语境释义")
        verbs = set(
            "abort append apply assert attach bind bootstrap calculate cancel cascade catch concatenate connect construct convert decode decrement defer delete deserialize detach dispatch dispose emit evaluate execute expand expose extend fetch flush forward generate implement import inject initialize insert inspect instantiate invoke iterate join load lookup map marshal modify mutate normalize notify optimize override parse persist poll propagate publish recover refresh register reload render replicate request resolve restore retrieve retry return revert rotate route sanitize scan schedule search select serialize shuffle sort subscribe synchronize terminate throttle trace transform traverse truncate unsubscribe update upgrade upload validate verify wrap yield mount commit merge patch".split()
        )
        adjectives = set(
            "asynchronous synchronous deterministic diagnostic executable generic immutable virtual technical accessible functional empirical qualitative quantitative".split()
        )
        if term in verbs:
            data["pos"] = "v."
        if term in adjectives:
            data["pos"] = "adj."
        data["pos"] = {"s.": "adj.", "a.": "adj.", "r.": "adv."}.get(
            data["pos"], data["pos"]
        )
        data["example"] = re.sub(r"^[NSVAR] ", "", data["example"])
        row = dict(
            id="expanded-" + hashlib.sha256(term.encode()).hexdigest()[:16],
            deck=deck,
            term=term,
            source_url=source_url,
            source_label=label,
            **data,
        )
        result.append(row)
        seen.add(term)
        evidence.append(
            dict(
                word_id=row["id"],
                term=term,
                source_kind=kind,
                source_url=source_url,
                definition_source=None
                if override or term in definitions_authored
                else DICTIONARY,
            )
        )
        return True

    business_context = {
        "stakeholder",
        "procurement",
        "commission",
        "rebate",
        "disbursement",
        "payout",
        "affiliate",
        "attribution",
        "acquisition",
        "settlement",
        "governance",
        "deliverable",
        "actionable",
        "onboarding",
        "commission settlement",
    }
    for term in overrides:
        add(term, "business" if term in business_context else "job")
    for term in definitions_authored:
        add(
            term,
            "business"
            if term in {"capital", "asset"}
            else "ielts"
            if term == "technical"
            else "job",
        )
    for term in JOB:
        add(term, "job")
    for term in BUSINESS:
        add(term, "business")
    IELTS_TOPICS.extend(
        """abandon abolish absence absolute abstract absorb absorption abundant accelerate acceleration accessible accessory accommodate accomplish accordance accordingly accounting accumulate accurate accusation accustomed acknowledge acquisition activate activation acute adapt addiction additional adequate adherence adolescent adoption adverse advocate aerial affordable aggression alert align alignment alliance allocation alteration amend ample analogous analogy ancestor anecdote anonymous anticipation apology apparatus appeal appliance applicable appoint appreciable appreciate appreciation approximate aptitude aquatic architectural arouse articulate aspiration aspire assemble assembly assertion assimilate association assurance astronomy attachment attainable attribute authentic authenticity autonomous avenue awareness bachelor balanced bankrupt bankruptcy bargain behavioral benchmark bias biased bilateral biodegradable biography boundary bureaucracy carbon catastrophic causal cautious cease census certificate certainty charitable chronic circulation citation civil civilization clarity classification client coalition cognitive coincide coherent collective commence commentary commercial commodity communal comparable compatible compensate competent competence compile complement complementary compliance compose composition compound comprehensible compression comprise compulsory concede conceive conception concise conclude concrete condemn conduct confer conference confess confident confine conform confront consecutive conserve considerable consolidate conspicuous constant constraint construct constructive consult contaminate contamination contemplate contradict contradiction contrary controversy controversial convene convenience converge converse convey cooperative coordinate counterpart credible credibility criterion criticism critique cultivate cultivation curiosity currency deduction defect deficiency deficient define definite definition delegate deliberate delicate density dependent depict depiction derive descriptive desirable despite destruction destructive detect determination detrimental diagnose differential differentiate dilemma diminish diminish disability disadvantage disastrous disclose disclosure discrete discrepancy displace disposal dispose dispute disruption distort distortion distinctive distinguish distribute diverse divert dividend documentary dominant doubt duration earn ecosystem edible elaborate eligible emerge emergence emphasize emphasis empower encompass encourage endeavour enforce engage enhance enrich enrol enrollment enquire entail entire entity entrepreneur entrepreneurial envisage equality equitable eradicate ethical ethics ethnic evaluate evolution evolve exaggerate excellence exceptional excessive exclude exclusion exclusive exemplify exemption exert exhibit exhibition existential expand expectation explicit exposure express expression extensive extent extinguish fabrication facilitate factual feasible feasibility feedback flexibility fluctuate fluctuation forecast foremost formulate formula forthcoming foster foundation fragment friction frustrate fulfil functional funding furthermore generalize genetic geographical geological globalize gradual graduate grant greenhouse hierarchy historical holistic homogeneous horizontal hostile humanitarian identical identification identity illuminate imbalance immense immerse impartial imperative implicit imply incentive inclusive incomplete incorporate incremental independently indicate indispensable individual induce industrial inevitable inference infer inferior informal inhabit inhibit initiate inject innovate insert intact integral integrate intellectual intelligence intensive intermediate interpret interrupt intrinsic intuition invalid inverse invisible invoke irrelevant irrigate justify justification journal journalistic juvenile lateral legitimate legitimacy liable likelihood linguistic livelihood magnitude mainstream mature maximize measurable mediate mediation medium minimal minimize minimum moderate modification modify monitor motivate municipal narrative nationwide negate negligible neutralize notwithstanding notorious nourish nuance nurture obligation obscure obstacle obtain occasion occupational occurrence optimistic optimum organic originate outlook outstanding overlap overseas paradox partial participate participation partnership passive perceive percentage permanent persist perspective persuade persuasive plausible predominant predict prediction preliminary prescribe prescription prevalent preventive principal privilege probability probe productive productivity prohibit prohibition prolonged prominent promote proportionate prosperous prosperity prototype provision punctual qualitative quantify quarterly radical randomize rational rationality reassess rebuild reciprocal recommendation reconcile recovery recurrent redistribution refine refinement reflect reflection reform refrain refugee refute reinforce reinforcement relevance reluctance reluctant remedy renewable renovation reproduce reproduction requisite reservation resilience resolve respectively restore restrain restriction retrieve retrospective reusable reverse revision revive rigorous robust safeguard scarcity scatter secular segregate selective sensitivity sequential significance simultaneous sociology solidarity sophisticated spatial specialty spectrum speculate speculation spontaneous stabilize stagnant stimulate stimulus stipulate structural subsequently substantial succession successive summarize supervision supplement supplementary sustain synthesis systematic tackle tangible technological theoretical thorough tolerance traceable traditional transformation transmit transparent transportation trivial ultimate unanimous uncertain uncertainty underlying underestimate undergo undoubtedly unify unify unprecedented urban utilization valid validity versatile viable vibrant violate violation virtually vocation voluntary vulnerable vulnerability outweigh wellness wildlife yield attainment aspiration communicative conceptual conditional contractual diagnostic discriminatory exploratory financial informational instructional managerial methodological motivational nutritional organizational procedural promotional residential statistical transactional transitional vocational persuasive introductory analytical observational incremental operational environmental economical empirical chronological comparative competitive cooperative argumentative evaluative explanatory reflective supportive informative adaptive renewable renewable""".split()
    )
    for term in IELTS_TOPICS:
        if len(result) + len(original) >= 1200:
            break
        add(term, "ielts")

    def rank(d):
        try:
            return int(d["frq"]) or 999999
        except ValueError:
            return 999999

    excluded = set(
        "abroad abroad ambulance anatomy astronomy bachelor bizarre bliss blunt brass bronze cabbage cavalry cemetery chimney cloak coffin collar corpse coward crude cuisine curl dagger deaf deer donkey drown elbow embassy emperor endure envy excavate fairy feeble fierce flock funeral fury galaxy garment goat goose grave greedy groom guitar hammer herd hollow hook horn insect jewelry kneel lamb lawn lion liver lung luxury maid merchant monkey mud naked navy niece nun nurse opera orbit ox palm pepper pigeon pirate plague priest prince prophet purple rat razor roar robe rocket rope sailor scar shark sheep shepherd shield skull spear spider spill spine squirrel stab statue steam stomach sword thief thumb tiger tongue tooth tortoise towel trumpet uncle underwear volcano warrior wax widow wool wrist yacht zoo adolescent aesthetic aristocrat".split()
    )
    for term, d in sorted(dictionary.items(), key=lambda x: rank(x[1])):
        if len(result) + len(original) >= 1200:
            break
        if (
            term in excluded
            or "ielts" not in d["tag"].split()
            or "zk" in d["tag"].split()
            or not (1500 <= rank(d) <= 16000)
        ):
            continue
        if len(term) < 5 or " " in term:
            continue
        add(term, "ielts")
    assert len(result) + len(original) == 1200, len(result)
    assert all(r["meaning"] and r["example"] and r["translation"] for r in result)
    (SEED / "expanded.json").write_text(
        json.dumps({"version": 1, "words": result}, ensure_ascii=False, indent=2) + "\n"
    )
    (SEED / "vocabulary_provenance.json").write_text(
        json.dumps(
            {
                "sources": manifest,
                "dictionary": DICTIONARY,
                "notes": "简历仅记录词条命中，不保存或公开原文。IELTS 标签来自 ECDICT，并非雅思官方词表。英文释义与原创例句分别标注。",
                "words": evidence,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        "Total",
        len(result) + len(original),
        "New decks",
        Counter(r["deck"] for r in result),
        "Kinds",
        Counter(e["source_kind"] for e in evidence),
        "Examples",
        sum(r["example_kind"] == "example" for r in result),
    )
    print(
        "IELTS additions:", ", ".join(r["term"] for r in result if r["deck"] == "ielts")
    )


if __name__ == "__main__":
    main()
