import sqlite3
import os
import sys
from itertools import combinations

DB_PATH = os.path.join(os.path.dirname(__file__), "../data", "wc2026.db")


def get_connection():
    return sqlite3.connect(DB_PATH)


# ══════════════════════════════════════════════════════════════════
# 1. CHARGEMENT DES RÉSULTATS RÉELS
# ══════════════════════════════════════════════════════════════════

def load_actual_fixtures(conn):
    import pandas as pd
    df = pd.read_sql_query("""
        SELECT fixture_id, group_name, match_date,
               home_team_id, away_team_id,
               home_team_label, away_team_label,
               home_fifa_ranking, away_fifa_ranking,
               actual_home_goals, actual_away_goals, actual_result
        FROM wc2026_fixtures
        WHERE stage = 'GROUP_STAGE'
          AND actual_home_goals IS NOT NULL
          AND actual_away_goals IS NOT NULL
        ORDER BY group_name, match_date
    """, conn)

    missing = df[df["actual_home_goals"].isnull()]
    if len(missing) > 0:
        print(f"⚠️  {len(missing)} matchs sans résultat réel :")
        for _, m in missing.iterrows():
            print(f"   Groupe {m['group_name']} — {m['home_team_label']} vs {m['away_team_label']}")

    print(f"✅ {len(df)} matchs de groupe chargés avec résultats réels")
    return df


# ══════════════════════════════════════════════════════════════════
# 2. CALCUL DES CLASSEMENTS
# ══════════════════════════════════════════════════════════════════

def compute_group_stats(group_df):
    """Calcule les stats brutes pour chaque équipe d'un groupe."""
    teams = {}

    for _, m in group_df.iterrows():
        hid = int(m["home_team_id"])
        aid = int(m["away_team_id"])
        hg  = int(m["actual_home_goals"])
        ag  = int(m["actual_away_goals"])

        for tid in [hid, aid]:
            if tid not in teams:
                label = m["home_team_label"] if tid == hid else m["away_team_label"]
                rank  = m["home_fifa_ranking"] if tid == hid else m["away_fifa_ranking"]
                teams[tid] = {
                    "team_id": tid, "label": label, "fifa_ranking": int(rank),
                    "pts": 0, "played": 0, "w": 0, "d": 0, "l": 0,
                    "gf": 0, "ga": 0, "gd": 0,
                }

        # Domicile
        teams[hid]["played"] += 1
        teams[hid]["gf"] += hg
        teams[hid]["ga"] += ag
        teams[hid]["gd"] += hg - ag

        # Extérieur
        teams[aid]["played"] += 1
        teams[aid]["gf"] += ag
        teams[aid]["ga"] += hg
        teams[aid]["gd"] += ag - hg

        if hg > ag:
            teams[hid]["pts"] += 3; teams[hid]["w"] += 1; teams[aid]["l"] += 1
        elif hg == ag:
            teams[hid]["pts"] += 1; teams[hid]["d"] += 1
            teams[aid]["pts"] += 1; teams[aid]["d"] += 1
        else:
            teams[aid]["pts"] += 3; teams[aid]["w"] += 1; teams[hid]["l"] += 1

    return teams


def head_to_head_stats(tied_tids, group_df):
    """Stats H2H entre équipes ex-aequo."""
    h2h = {tid: {"pts": 0, "gd": 0, "gf": 0} for tid in tied_tids}
    tid_set = set(tied_tids)

    for _, m in group_df.iterrows():
        hid = int(m["home_team_id"])
        aid = int(m["away_team_id"])
        if hid not in tid_set or aid not in tid_set:
            continue
        hg = int(m["actual_home_goals"])
        ag = int(m["actual_away_goals"])

        h2h[hid]["gf"] += hg; h2h[hid]["gd"] += hg - ag
        h2h[aid]["gf"] += ag; h2h[aid]["gd"] += ag - hg

        if hg > ag:
            h2h[hid]["pts"] += 3
        elif hg == ag:
            h2h[hid]["pts"] += 1; h2h[aid]["pts"] += 1
        else:
            h2h[aid]["pts"] += 3

    return h2h


def sort_group(teams, group_df):
    """Trie les équipes selon les règles FIFA avec H2H."""
    tids = list(teams.keys())

    def sort_key_global(tid):
        t = teams[tid]
        return (t["pts"], t["gd"], t["gf"], -t["fifa_ranking"])

    # Tri initial global
    tids.sort(key=sort_key_global, reverse=True)

    # Résoudre les égalités par H2H puis critères généraux
    def resolve_ties(group_tids):
        if len(group_tids) <= 1:
            return group_tids

        # Regrouper par points
        result = []
        i = 0
        while i < len(group_tids):
            j = i + 1
            while j < len(group_tids) and teams[group_tids[j]]["pts"] == teams[group_tids[i]]["pts"]:
                j += 1

            tied = group_tids[i:j]
            if len(tied) == 1:
                result.extend(tied)
            else:
                # H2H entre les ex-aequo
                h2h = head_to_head_stats(tied, group_df)
                tied.sort(key=lambda t: (
                    h2h[t]["pts"], h2h[t]["gd"], h2h[t]["gf"],
                    teams[t]["gd"], teams[t]["gf"],
                    -teams[t]["fifa_ranking"]
                ), reverse=True)
                result.extend(tied)
            i = j

        return result

    return resolve_ties(tids)


def compute_all_standings(fixtures_df):
    """Calcule les classements pour tous les groupes."""
    standings = {}
    groups = sorted(fixtures_df["group_name"].dropna().unique())

    for grp in groups:
        gdf   = fixtures_df[fixtures_df["group_name"] == grp]
        teams = compute_group_stats(gdf)
        order = sort_group(teams, gdf)
        standings[grp] = {"order": order, "teams": teams}

        print(f"\n  Groupe {grp}")
        print(f"  {'Pos':<4} {'Équipe':<25} {'Pts':>4} {'J':>3} {'V':>3} {'N':>3} {'D':>3} {'BP':>4} {'BC':>4} {'Diff':>5} {'FIFA':>5}")
        print(f"  {'─'*72}")
        for pos, tid in enumerate(order, 1):
            t = teams[tid]
            qual = " ✓" if pos <= 2 else ""
            print(f"  {pos:<4} {t['label']:<25} {t['pts']:>4} {t['played']:>3} {t['w']:>3} {t['d']:>3} {t['l']:>3} {t['gf']:>4} {t['ga']:>4} {t['gd']:>+5} #{t['fifa_ranking']:>4}{qual}")

    return standings


# ══════════════════════════════════════════════════════════════════
# 3. MEILLEURS 3ÈMES
# ══════════════════════════════════════════════════════════════════

def select_best_thirds(standings):
    """
    Identifie les 8 meilleurs troisièmes parmi les 12 groupes.
    Critères FIFA : pts → diff buts → buts marqués → classement FIFA
    """
    thirds = []
    for grp, data in standings.items():
        if len(data["order"]) < 3:
            continue
        tid = data["order"][2]
        t   = data["teams"][tid]
        thirds.append({
            "group": grp, "team_id": tid, "label": t["label"],
            "pts": t["pts"], "gd": t["gd"], "gf": t["gf"],
            "fifa_ranking": t["fifa_ranking"],
            "played": t["played"], "w": t["w"], "d": t["d"], "l": t["l"],
            "ga": t["ga"],
        })

    thirds.sort(key=lambda x: (x["pts"], x["gd"], x["gf"], -x["fifa_ranking"]), reverse=True)

    print(f"\n{'═'*65}")
    print("  Classement des 12 troisièmes")
    print(f"{'═'*65}")
    print(f"  {'#':<3} {'Grp':<5} {'Équipe':<25} {'Pts':>4} {'Diff':>5} {'BP':>4} {'FIFA':>5} {'Qualifié'}")
    print(f"  {'─'*60}")
    for i, t in enumerate(thirds):
        qual = "✓ Qualifié" if i < 8 else "Éliminé"
        sep  = "  ── Éliminés ──" if i == 8 else ""
        if sep:
            print(sep)
        print(f"  {i+1:<3} {t['group']:<5} {t['label']:<25} {t['pts']:>4} {t['gd']:>+5} {t['gf']:>4} #{t['fifa_ranking']:>4} {qual}")

    return thirds


# ══════════════════════════════════════════════════════════════════
# 4. SAUVEGARDE EN BASE
# ══════════════════════════════════════════════════════════════════

def save(standings, thirds, conn):
    c = conn.cursor()

    # ── real_group_standings ──────────────────────────────────────
    c.execute("DROP TABLE IF EXISTS real_group_standings")
    c.execute("""
        CREATE TABLE real_group_standings (
            team_id       INTEGER PRIMARY KEY,
            group_name    TEXT,
            position      INTEGER,
            team_label    TEXT,
            fifa_ranking  INTEGER,
            points        INTEGER,
            played        INTEGER,
            won           INTEGER,
            drawn         INTEGER,
            lost          INTEGER,
            goals_for     INTEGER,
            goals_against INTEGER,
            goal_diff     INTEGER,
            qualified     TEXT
        )
    """)

    for grp, data in standings.items():
        for pos, tid in enumerate(data["order"], 1):
            t = data["teams"][tid]
            if pos == 1:   qual = "1ST"
            elif pos == 2: qual = "2ND"
            elif any(x["team_id"] == tid for x in thirds[:8]): qual = "3RD_BEST"
            else:          qual = "OUT"

            c.execute("""
                INSERT OR REPLACE INTO real_group_standings VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (tid, grp, pos, t["label"], t["fifa_ranking"],
                  t["pts"], t["played"], t["w"], t["d"], t["l"],
                  t["gf"], t["ga"], t["gd"], qual))

    # ── real_third_place ──────────────────────────────────────────
    c.execute("DROP TABLE IF EXISTS real_third_place")
    c.execute("""
        CREATE TABLE real_third_place (
            rank          INTEGER,
            group_name    TEXT,
            team_id       INTEGER,
            team_label    TEXT,
            fifa_ranking  INTEGER,
            points        INTEGER,
            played        INTEGER,
            won           INTEGER,
            drawn         INTEGER,
            lost          INTEGER,
            goals_for     INTEGER,
            goals_against INTEGER,
            goal_diff     INTEGER,
            qualified     INTEGER
        )
    """)

    for i, t in enumerate(thirds):
        c.execute("""
            INSERT INTO real_third_place VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (i + 1, t["group"], t["team_id"], t["label"], t["fifa_ranking"],
              t["pts"], t["played"], t["w"], t["d"], t["l"],
              t["gf"], t["ga"], t["gd"], 1 if i < 8 else 0))

    conn.commit()
    print(f"\n✅ real_group_standings et real_third_place sauvegardés en base")


# ══════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 65)
    print("  Classements réels — Phase de groupes WC2026")
    print("=" * 65)

    conn     = get_connection()
    fixtures = load_actual_fixtures(conn)
    standings = compute_all_standings(fixtures)
    thirds    = select_best_thirds(standings)
    save(standings, thirds, conn)
    conn.close()

    print("\n🎉 build_real_standings terminé.")
    print("   → Lancer ensuite : python predict_knockout_real.py")