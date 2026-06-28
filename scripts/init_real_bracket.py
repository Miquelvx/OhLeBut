import sqlite3
import os
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), "../data", "wc2026.db")


def get_connection():
    return sqlite3.connect(DB_PATH)


# ══════════════════════════════════════════════════════════════════
# MAPPING fixture_id -> bracket_id
# A corriger si l'ordre des matchs dans la DB ne correspond pas
# au bracket officiel FIFA
# ══════════════════════════════════════════════════════════════════

FIXTURE_TO_BRACKET = {
    # LAST_32 — 32es de finale
    537417: "M1",   # 29/06  1E   vs 3ABCDF
    537415: "M2",   # 30/06  1I   vs 3CDFGH
    537423: "M3",   # 28/06  2A   vs 2B
    537416: "M4",   # 30/06  1F   vs 2C
    537418: "M5",   # 03/07  2K   vs 2L
    537424: "M6",   # 02/07  1H   vs 2J
    537422: "M7",   # 02/07  1D   vs 3BEFIJ
    537425: "M8",   # 01/07  1G   vs 3AEHIJ
    537426: "M9",   # 29/06  1C   vs 2F
    537419: "M10",  # 30/06  2E   vs 2I
    537420: "M11",  # 01/07  1A   vs 3CEFHI
    537421: "M12",  # 01/07  1L   vs 3EHIJK
    537427: "M13",  # 04/07  1J   vs 2H
    537428: "M14",  # 03/07  2D   vs 2G
    537429: "M15",  # 03/07  1B   vs 3EFGIJ
    537430: "M16",  # 04/07  1K   vs 3DEIJL

    # LAST_16 — 16es de finale
    537375: "R8_1",  # 04/07  W(M1)  vs W(M2)
    537376: "R8_2",  # 04/07  W(M3)  vs W(M4)
    537377: "R8_3",  # 05/07  W(M5)  vs W(M6)
    537378: "R8_4",  # 07/07  W(M7)  vs W(M8)
    537379: "R8_5",  # 05/07  W(M9)  vs W(M10)
    537380: "R8_6",  # 06/07  W(M11) vs W(M12)
    537381: "R8_7",  # 07/07  W(M13) vs W(M14)
    537382: "R8_8",  # 07/07  W(M15) vs W(M16)

    # QUARTER_FINALS
    537383: "QF1",   # 09/07  W(R8_1) vs W(R8_2)
    537384: "QF2",   # 10/07  W(R8_3) vs W(R8_4)
    537385: "QF3",   # 11/07  W(R8_5) vs W(R8_6)
    537386: "QF4",   # 12/07  W(R8_7) vs W(R8_8)

    # SEMI_FINALS
    537387: "SF1",   # 14/07  W(QF1) vs W(QF2)
    537388: "SF2",   # 15/07  W(QF3) vs W(QF4)

    # THIRD_PLACE & FINAL
    537389: "3RD",   # 18/07
    537390: "FIN",   # 19/07
}

BRACKET_TO_FIXTURE = {v: k for k, v in FIXTURE_TO_BRACKET.items()}

# ══════════════════════════════════════════════════════════════════
# STRUCTURE BRACKET — reprise exacte de predict_knockout_real
# ══════════════════════════════════════════════════════════════════

THIRD_ELIGIBLE = {
    "M1": ["A","B","C","D","F"], "M2": ["C","D","F","G","H"],
    "M7": ["B","E","F","I","J"], "M8": ["A","E","H","I","J"],
    "M11":["C","E","F","H","I"], "M12":["E","H","I","J","K"],
    "M15":["E","F","G","I","J"], "M16":["D","E","I","J","L"],
}
FIXED_R16 = {
    "M3": ("2A","2B"),  "M4": ("1F","2C"),
    "M5": ("2K","2L"),  "M6": ("1H","2J"),
    "M9": ("1C","2F"),  "M10":("2E","2I"),
    "M13":("1J","2H"),  "M14":("2D","2G"),
}
THIRD_R16 = {
    "M1":"1E",  "M2":"1I",
    "M7":"1D",  "M8":"1G",
    "M11":"1A", "M12":"1L",
    "M15":"1B", "M16":"1K",
}


# ══════════════════════════════════════════════════════════════════
# 1. AJOUT COLONNE bracket_id
# ══════════════════════════════════════════════════════════════════

def add_bracket_id_column(conn):
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE wc2026_fixtures ADD COLUMN bracket_id TEXT")
        conn.commit()
        print("Colonne bracket_id ajoutee")
    except sqlite3.OperationalError:
        print("   Colonne bracket_id deja presente")


# ══════════════════════════════════════════════════════════════════
# 2. ASSIGNATION DES bracket_id
# ══════════════════════════════════════════════════════════════════

def assign_bracket_ids(conn):
    c = conn.cursor()
    updated = 0
    for fixture_id, bracket_id in FIXTURE_TO_BRACKET.items():
        c.execute(
            "UPDATE wc2026_fixtures SET bracket_id = ? WHERE fixture_id = ?",
            (bracket_id, fixture_id)
        )
        updated += c.rowcount
    conn.commit()
    print(f"{updated} bracket_id assignes")


# ══════════════════════════════════════════════════════════════════
# 3. CONSTRUCTION DU BRACKET R16 (logique identique a predict_knockout_real)
# ══════════════════════════════════════════════════════════════════

def assign_thirds(available):
    slots = sorted(THIRD_ELIGIBLE.keys(),
        key=lambda s: len([g for g in THIRD_ELIGIBLE[s] if g in available]))

    def backtrack(idx, assignment, used):
        if idx == len(slots): return assignment.copy()
        slot = slots[idx]
        eligible = sorted(
            [g for g in THIRD_ELIGIBLE[slot] if g in available and g not in used],
            key=lambda g: available[g])
        for grp in eligible:
            assignment[slot] = grp; used.add(grp)
            result = backtrack(idx + 1, assignment, used)
            if result is not None: return result
            del assignment[slot]; used.remove(grp)
        return None

    return backtrack(0, {}, set()) or {}


def build_r16_bracket(standings, thirds_df):
    def get_team(code):
        pos = int(code[0]); grp = code[1:]
        row = standings[(standings["group_name"] == grp) & (standings["position"] == pos)]
        if len(row) == 0: return None, "TBD"
        r = row.iloc[0]
        return int(r["team_id"]), r["team_label"]

    available  = {r["group_name"]: int(r["fifa_ranking"]) for _, r in thirds_df.iterrows()}
    assignment = assign_thirds(available)
    bracket    = {}

    for mid, (ca, cb) in FIXED_R16.items():
        ta, la = get_team(ca)
        tb, lb = get_team(cb)
        if ta and tb:
            bracket[mid] = (ta, tb, la, lb)

    for mid, ca in THIRD_R16.items():
        ta, la = get_team(ca)
        grp    = assignment.get(mid)
        tb, lb = None, "TBD"
        if grp:
            row = thirds_df[thirds_df["group_name"] == grp]
            if len(row) > 0:
                r  = row.iloc[0]
                tb = int(r["team_id"]); lb = r["team_label"]
        if ta and tb:
            bracket[mid] = (ta, tb, la, lb)

    return bracket, assignment


# ══════════════════════════════════════════════════════════════════
# 4. REMPLISSAGE DE wc2026_fixtures
# ══════════════════════════════════════════════════════════════════

def fill_last32_teams(conn, bracket, standings):
    c = conn.cursor()
    filled = 0

    for mid, (home_id, away_id, home_label, away_label) in bracket.items():
        fixture_id = BRACKET_TO_FIXTURE.get(mid)
        if not fixture_id:
            print(f"  Pas de fixture_id pour {mid}")
            continue

        def get_rank(tid):
            row = standings[standings["team_id"] == tid]
            return int(row.iloc[0]["fifa_ranking"]) if len(row) > 0 else None

        home_rank = get_rank(home_id)
        away_rank = get_rank(away_id)

        c.execute("""
            UPDATE wc2026_fixtures
            SET home_team_id      = ?,
                away_team_id      = ?,
                home_team_label   = ?,
                away_team_label   = ?,
                home_fifa_ranking = ?,
                away_fifa_ranking = ?
            WHERE fixture_id = ?
        """, (home_id, away_id, home_label, away_label,
              home_rank, away_rank, fixture_id))
        filled += c.rowcount
        print(f"  {mid:<6} ({fixture_id})  {home_label:<25} vs {away_label}")

    conn.commit()
    print(f"\n{filled} matchs LAST_32 remplis avec les equipes reelles")


# ══════════════════════════════════════════════════════════════════
# 5. VERIFICATION
# ══════════════════════════════════════════════════════════════════

def verify(conn):
    df = pd.read_sql_query("""
        SELECT bracket_id, fixture_id, stage, match_date,
               home_team_label, away_team_label,
               actual_home_goals, actual_away_goals, actual_result,
               pred_home_goals, pred_away_goals
        FROM wc2026_fixtures
        WHERE bracket_id IS NOT NULL
        ORDER BY match_date, fixture_id
    """, conn)

    print(f"\n{'='*80}")
    print("  Etat du bracket knockout")
    print(f"{'='*80}")
    print(f"  {'BID':<6} {'FID':<8} {'Date':<12} {'Domicile':<22} {'Exterieur':<22} Statut")
    print(f"  {'-'*78}")

    for _, r in df.iterrows():
        if r["actual_result"]:
            statut = f"OK {int(r['actual_home_goals'])}-{int(r['actual_away_goals'])} ({r['actual_result']})"
        elif r["pred_home_goals"] is not None:
            statut = f"Predit {r['pred_home_goals']:.0f}-{r['pred_away_goals']:.0f}"
        elif r["home_team_label"] and r["home_team_label"] != "TBD":
            statut = "Equipes connues, pas encore predit"
        else:
            statut = "TBD"
        home = r["home_team_label"] or "TBD"
        away = r["away_team_label"] or "TBD"
        print(f"  {(r['bracket_id'] or '?'):<6} {r['fixture_id']:<8} {r['match_date']:<12} {home:<22} {away:<22} {statut}")


# ══════════════════════════════════════════════════════════════════
# POINT D'ENTREE
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 65)
    print("  Initialisation bracket knockout WC2026")
    print("=" * 65)

    conn = get_connection()

    standings = pd.read_sql_query(
        "SELECT * FROM real_group_standings ORDER BY group_name, position", conn)
    thirds_df = pd.read_sql_query(
        "SELECT * FROM real_third_place WHERE qualified=1 ORDER BY rank", conn)

    add_bracket_id_column(conn)
    assign_bracket_ids(conn)

    print("\nConstruction du bracket R16...")
    bracket, assignment = build_r16_bracket(standings, thirds_df)

    print(f"\n  Attribution des meilleurs 3emes :")
    for mid, grp in sorted(assignment.items()):
        print(f"    {mid} <- 3e Groupe {grp}")

    print("\nRemplissage des equipes LAST_32...")
    fill_last32_teams(conn, bracket, standings)

    verify(conn)

    conn.close()
    print("\nBracket initialise.")
    print("   -> Lancer ensuite : python predict_knockout_real.py")