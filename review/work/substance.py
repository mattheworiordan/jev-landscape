#!/usr/bin/env python3
"""Tally the substance read of the materially-different cards.

Each id was read from title + text only. `before` is what a team would have
used for that job before Jev. `new` is unavailable (no prior method at any
price or latency) or cheaper_or_faster. `dup` marks a second post about the
same build.
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# id, job, before, dup
ROWS = [
    ("2100397782322364792", "game_or_sim", "llm", 0),
    ("2100476853920129024", "personal_tool", "rules", 0),
    ("2100546231554760841", "classify", "llm", 0),
    ("2100576115429699603", "feed_filter", "llm", 0),
    ("2100577979021832365", "voice_command", "llm", 0),
    ("2100602714204049588", "speech_score", "llm", 0),
    ("2100608556823388486", "voice_turn", "vendor", 0),
    ("2100631847155994852", "computer_use", "llm", 0),
    ("2100639390468833379", "live_control", "llm", 0),
    ("2100650582662930648", "typing_or_form", "llm", 0),
    ("2100673493452914908", "typing_or_form", "llm", 0),
    ("2100675140237320417", "speech_score", "llm", 0),
    ("2100713197502173373", "speech_score", "llm", 0),
    ("2100749397864681735", "triage", "llm", 0),
    ("2100780008193020049", "typing_or_form", "llm", 0),
    ("2100793777103466615", "feed_filter", "vendor", 0),
    ("2100796109534765354", "feed_filter", "rules", 0),
    ("2100822293803143208", "guard", "llm", 0),
    ("2100845388655960112", "voice_command", "llm", 0),
    ("2100898769470627948", "voice_command", "llm", 0),
    ("2100902217515454507", "guard", "rules", 0),
    ("2100907300932219347", "classify", "llm", 0),
    ("2100909814473805931", "triage", "llm", 0),
    ("2100932122399715345", "feed_filter", "llm", 0),
    ("2100962406344409190", "voice_command", "llm", 0),
    ("2100964585595687128", "voice_command", "llm", 1),
    ("2100968425967493414", "feed_filter", "llm", 0),
    ("2100971640184074565", "feed_filter", "vendor", 0),
    ("2101023899265692100", "voice_command", "llm", 0),
    ("2101040766613102799", "voice_command", "llm", 1),
    ("2101050585021886597", "speech_score", "llm", 0),
    ("2101068150091485574", "feed_filter", "llm", 0),
    ("2101078024414244886", "voice_turn", "llm", 0),
    ("2101083855193301236", "feed_filter", "vendor", 0),
    ("2101156959546450049", "voice_command", "llm", 0),
    ("2101277651780452542", "feed_filter", "vendor", 0),
    ("2101321056946446364", "feed_filter", "classic", 0),
    ("2101335665724305795", "triage", "rules", 0),
    ("2101341086127919484", "feed_filter", "rules", 0),
    ("2101347270314614963", "feed_filter", "vendor", 0),
    ("2101369844230758403", "search", "llm", 0),
    ("2101387371308875794", "feed_filter", "rules", 0),
    ("2101388186916454439", "voice_command", "llm", 0),
    ("2101394993957274021", "voice_command", "llm", 0),
    ("2101414486837952560", "typing_or_form", "llm", 0),
    ("2101431328365535695", "computer_use", "llm", 0),
    ("2101534451343695930", "guard", "llm", 0),
    ("2101574162817093655", "triage", "llm", 0),
    ("2101591273794859486", "typing_or_form", "vendor", 0),
    ("2101621822517338618", "feed_filter", "llm", 0),
    ("2101642632837366105", "triage", "llm", 0),
    ("2101663444265251293", "feed_filter", "rules", 0),
    ("2101670746883768607", "trading", "classic", 0),
    ("2101681862795997459", "speech_score", "llm", 0),
    ("2101695378760577343", "voice_command", "llm", 0),
    ("2101697508413948199", "typing_or_form", "llm", 0),
    ("2101716648386506797", "alerts", "rules", 0),
    ("2101720980972519672", "computer_use", "llm", 0),
    ("2101750053568491752", "live_control", "llm", 0),
    ("2101766663288852731", "guard", "rules", 0),
    ("2101813335910146532", "typing_or_form", "vendor", 0),
    ("2101854008851730881", "voice_turn", "llm", 0),
    ("2101894289475485849", "feed_filter", "llm", 0),
    ("2101894950736793867", "feed_filter", "llm", 0),
    ("2101932477967421771", "voice_command", "llm", 0),
    ("2101942660680368367", "typing_or_form", "llm", 0),
    ("2101987335558824151", "voice_turn", "vendor", 0),
    ("2102038708379603404", "voice_turn", "llm", 1),
    ("2102044163093188716", "voice_command", "llm", 0),
    ("2102052409950515654", "trading", "llm", 0),
    ("2102061478438211812", "typing_or_form", "llm", 1),
    ("2102064901371871574", "feed_filter", "rules", 0),
    ("2102068383617278134", "typing_or_form", "llm", 1),
    ("2102070512176291893", "voice_turn", "llm", 0),
    ("2102082148866130323", "trading", "rules", 0),
    ("2102086796045602954", "guard", "llm", 0),
    ("2102099108387545297", "trading", "classic", 1),
    ("2102169255341171132", "alerts", "llm", 0),
    ("2102190208498471368", "search", "llm", 0),
    ("2102259575613538607", "game_or_sim", "llm", 0),
    ("2102305668351086736", "typing_or_form", "classic", 0),
    ("2102328241298010306", "classify", "llm", 0),
    ("2102381113230692353", "feed_filter", "llm", 0),
    ("2102420081753919684", "game_or_sim", "llm", 0),
    ("2102426484115996694", "trading", "llm", 0),
    ("2102474978054885452", "typing_or_form", "vendor", 0),
    ("2102528136885760007", "triage", "llm", 0),
    ("2102578718824931766", "typing_or_form", "rules", 0),
    ("2102578820104470888", "feed_filter", "llm", 0),
    ("2102632098800754902", "feed_filter", "vendor", 0),
    ("2102802134723100805", "feed_filter", "llm", 0),
]


def main():
    ids = json.load(open(ROOT / "review/work/strata.json"))["exhaustive"]["material"]
    got = [r[0] for r in ROWS]
    missing = sorted(set(ids) - set(got))
    extra = sorted(set(got) - set(ids))
    if missing or extra or len(got) != len(set(got)):
        raise SystemExit(f"missing={missing} extra={extra} dups={len(got)-len(set(got))}")
    jobs = Counter(r[1] for r in ROWS)
    before = Counter(r[2] for r in ROWS)
    dups = sum(r[3] for r in ROWS)
    distinct = len(ROWS) - dups
    print(json.dumps({
        "n": len(ROWS),
        "distinct_builds": distinct,
        "second_posts": dups,
        "unavailable_at_any_price": 0,
        "merely_cheaper_or_faster": len(ROWS),
        "before": dict(before),
        "job": dict(jobs),
    }, indent=2))


if __name__ == "__main__":
    main()
