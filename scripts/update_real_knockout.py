import sqlite3
import os
import sys
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), "../data", "wc2026.db")

# ══════════════════════════════════════════════════════════════════
# RESULTATS REELS — A REMPLIR AU FUR ET A MESURE
#
# Format :
#   "M1": (home_goals, away_goals)
#   "M1": (home_goals, away_goals, pen_home, pen_away)  # si penalties
#
# Laisser None si le match n'a pas encore ete joue.
# ══════════════════════════════════════════════════════════════════

ACTUAL_RESULTS = {

    # ── LAST_32 — 32es de finale ──────────────────────────────────
    "M1":  None,   # 29/06  1E   vs 3ABCDF
    "M2":  None,   # 30/06  1I   vs 3CDFGH
    "M3":  None,   # 28/06  2A   vs 2B
    "M4":  None,   # 30/06  1F   vs 2C
    "M5":  None,   # 03/07  2K   vs 2L
    "M6":  None,   # 02/07  1H   vs 2J
    "M7":  None,   # 02/07  1D   vs 3BEFIJ
    "M8":  None,   # 01/07  1G   vs 3AEHIJ
    "M9":  None,   # 29/06  1C   vs 2F
    "M10": None,   # 30/06  2E   vs 2I
    "M11": None,   # 01/07  1A   vs 3CEFHI
    "M12": None,   # 01/07  1L   vs 3EHIJK
    "M13": None,   # 04/07  1J   vs 2H
    "M14": None,   # 03/07  2D   vs 2G
    "M15": None,   # 03/07  1B   vs 3EFGIJ
    "M16": None,   # 04/07  1K   vs 3DEIJL

    # ── LAST_16 — 16es de finale ──────────────────────────────────
    "R8_1": None,  # W(M1)  vs W(M2)
    "R8_2": None,  # W(M3)  vs W(M4)
    "R8_3": None,  # W(M5)  vs W(M6)
    "R8_4": None,  # W(M7)  vs W(M8)
    "R8_5": None,  # W(M9)  vs W(M10)
    "R8_6": None,  # W(M11) vs W(M12)
    "R8_7": None,  # W(M13) vs W(M14)
    "R8_8": None,  # W(M15) vs W(M16)

    # ── QUARTS DE FINALE ──────────────────────────────────────────
    "QF1": None,   # W(R8_1) vs W(R8_2)
    "QF2": None,   # W(R8_3) vs W(R8_4)
    "QF3": None,   # W(R8_5) vs W(R8_6)
    "QF4": None,   # W(R8_7) vs W(R8_8)

    # ── DEMI-FINALES ──────────────────────────────────────────────
    "SF1": None,   # W(QF1) vs W(QF2)
    "SF2": None,   # W(QF3) vs W(QF4)

    # ── 3E PLACE & FINALE ─────────────────────────────────────────
    "3RD": None,   # Perdant SF1 vs Perdant SF2
    "FIN": None,   # W(SF1) vs W(SF2)
}

# ══════════════════════════════════════════════════════════════════
# STRUCTURE DU BRACKET — propagation des vainqueurs
# ══════════════════════════════════════════════════════════════════

# Pour chaque bracket_id, quel fixture du tour suivant et quel cote (home/away)
NEXT_ROUND = {
    "M1":   ("R8_1", "home"), "M2":   ("R8_1", "away"),
    "M3":   ("R8_2", "home"), "M4":   ("R8_2", "away"),
    "M5":   ("R8_3", "home"), "M6":   ("R8_3", "away"),
    "M7":   ("R8_4", "home"), "M8":   ("R8_4", "away"),
    "M9":   ("R8_5", "home"), "M10":  ("R8_5", "away"),
    "M11":  ("R8_6", "home"), "M12":  ("R8_6", "away"),
    "M13":  ("R8_7", "home"), "M14":  ("R8_7", "away"),
    "M15":  ("R8_8", "home"), "M16":  ("R8_8", "away"),
    "R8_1": ("QF1",  "home"), "R8_2": ("QF1",  "away"),
    "R8_3": ("QF2",  "home"), "R8_4": ("QF2",  "away"),
    "R8_5": ("QF3",  "home"), "R8_6": ("QF3",  "away"),
    "R8_7": ("QF4",  "home"), "R8_8": ("QF4",  "away"),
    "QF1":  ("SF1",  "home"), "QF2":  ("SF1",  "away"),
    "QF3":  ("SF2",  "home"), "QF4":  ("SF2",  "away"),
    "SF1":  ("FIN",  "home"), "SF2":  ("FIN",  "away"),
    # Les perdants des SF vont en 3e place
    # (gere separement via propagate_sf_losers)
}

SF_LOSER_NEXT = {
    "SF1": ("3RD", "home"),
    "SF2": ("3RD", "away"),
}


def get_connection():
    return sqlite3.connect(DB_PATH)


# ══════════════════════════════════════════════════════════════════
# 1. AJOUT COLONNES PENALTIES SI ABSENTES
# ══════════════════════════════════════════════════════════════════

def ensure_columns(conn):
    c = conn.cursor()
    for col in ["actual_home_penalties", "actual_away_penalties"]:
        try:
            c.execute(f"ALTER TABLE wc2026_fixtures ADD COLUMN {col} INTEGER")
        except sqlite3.OperationalError:
            pass
    conn.commit()


# ══════════════════════════════════════════════════════════════════
# 2. MISE A JOUR DES RESULTATS
# ══════════════════════════════════════════════════════════════════

def compute_result(hg, ag, pen_h=None, pen_a=None):
    """Determine H ou A. Utilise les penalties si score egal."""
    if hg > ag:   return "H"
    elif hg < ag: return "A"
    else:
        # Egalite apres 90min / AET → penalties obligatoires
        if pen_h is not None and pen_a is not None:
            return "H" if pen_h > pen_a else "A"
        raise ValueError(f"Score egal {hg}-{ag} sans penalties fournis")


def update_results(conn, dry_run=False):
    c = conn.cursor()

    # Charger les fixtures knockout pour affichage
    fixtures = pd.read_sql_query("""
        SELECT bracket_id, fixture_id,
               home_team_id, away_team_id,
               home_team_label, away_team_label,
               match_date
        FROM wc2026_fixtures
        WHERE bracket_id IS NOT NULL
    """, conn)
    fix_map = {r["bracket_id"]: r for _, r in fixtures.iterrows()}

    updated = skipped = errors = 0

    for bid, score in ACTUAL_RESULTS.items():
        if score is None:
            skipped += 1
            continue

        fix = fix_map.get(bid)
        if fix is None:
            print(f"  AVERTISSEMENT : bracket_id {bid} introuvable en base")
            errors += 1
            continue

        # Decoder le score
        if len(score) == 2:
            hg, ag = score
            pen_h = pen_a = None
        elif len(score) == 4:
            hg, ag, pen_h, pen_a = score
        else:
            print(f"  ERREUR format pour {bid} : {score}")
            errors += 1
            continue

        try:
            res = compute_result(hg, ag, pen_h, pen_a)
        except ValueError as e:
            print(f"  ERREUR {bid} : {e}")
            errors += 1
            continue

        home = fix["home_team_label"] or "TBD"
        away = fix["away_team_label"] or "TBD"
        pen_str = f" (pen {pen_h}-{pen_a})" if pen_h is not None else ""

        if dry_run:
            print(f"  [DRY] {bid:<6} {fix['match_date']}  {home:<22} {hg}-{ag}{pen_str}  {away:<22}  -> {res}")
        else:
            c.execute("""
                UPDATE wc2026_fixtures
                SET actual_home_goals    = ?,
                    actual_away_goals    = ?,
                    actual_home_penalties = ?,
                    actual_away_penalties = ?,
                    actual_result        = ?
                WHERE bracket_id = ?
            """, (hg, ag, pen_h, pen_a, res, bid))
            updated += 1
            print(f"  OK  {bid:<6} {fix['match_date']}  {home:<22} {hg}-{ag}{pen_str}  {away:<22}  -> {res}")

    if not dry_run:
        conn.commit()
        print(f"\n  {updated} resultats enregistres, {skipped} ignores (None)")
        if errors:
            print(f"  AVERTISSEMENT : {errors} erreurs")

    return updated


# ══════════════════════════════════════════════════════════════════
# 3. PROPAGATION DES VAINQUEURS AU TOUR SUIVANT
# ══════════════════════════════════════════════════════════════════

def propagate_winners(conn, dry_run=False):
    """
    Pour chaque match avec actual_result connu, remplit les equipes
    du match suivant dans wc2026_fixtures.
    """
    c = conn.cursor()

    # Charger tous les matchs knockout joues
    played = pd.read_sql_query("""
        SELECT bracket_id, fixture_id,
               home_team_id, away_team_id,
               home_team_label, away_team_label,
               home_fifa_ranking, away_fifa_ranking,
               actual_result
        FROM wc2026_fixtures
        WHERE bracket_id IS NOT NULL
          AND actual_result IS NOT NULL
        ORDER BY match_date
    """, conn)

    propagated = 0

    for _, m in played.iterrows():
        bid = m["bracket_id"]
        res = m["actual_result"]

        # Vainqueur
        if res == "H":
            winner_id    = int(m["home_team_id"])
            winner_label = m["home_team_label"]
            winner_rank  = m["home_fifa_ranking"]
        else:
            winner_id    = int(m["away_team_id"])
            winner_label = m["away_team_label"]
            winner_rank  = m["away_fifa_ranking"]

        targets = []

        # Match suivant pour le vainqueur
        if bid in NEXT_ROUND:
            next_bid, side = NEXT_ROUND[bid]
            targets.append((next_bid, side, winner_id, winner_label, winner_rank))

        # Pour les demi-finales : le perdant va en 3e place
        if bid in SF_LOSER_NEXT:
            if res == "H":
                loser_id    = int(m["away_team_id"])
                loser_label = m["away_team_label"]
                loser_rank  = m["away_fifa_ranking"]
            else:
                loser_id    = int(m["home_team_id"])
                loser_label = m["home_team_label"]
                loser_rank  = m["home_fifa_ranking"]
            next_bid, side = SF_LOSER_NEXT[bid]
            targets.append((next_bid, side, loser_id, loser_label, loser_rank))

        for next_bid, side, tid, label, rank in targets:
            if side == "home":
                col_id = "home_team_id"; col_label = "home_team_label"; col_rank = "home_fifa_ranking"
            else:
                col_id = "away_team_id"; col_label = "away_team_label"; col_rank = "away_fifa_ranking"

            if dry_run:
                print(f"  [DRY] Propage {label} -> {next_bid} ({side})")
            else:
                c.execute(f"""
                    UPDATE wc2026_fixtures
                    SET {col_id}    = ?,
                        {col_label} = ?,
                        {col_rank}  = ?
                    WHERE bracket_id = ?
                      AND ({col_id} IS NULL OR {col_id} != ?)
                """, (tid, label, rank, next_bid, tid))
                if c.rowcount > 0:
                    print(f"  >> {label} -> {next_bid} ({side})")
                    propagated += 1

    if not dry_run:
        conn.commit()
        print(f"\n  {propagated} propagations effectuees")


# ══════════════════════════════════════════════════════════════════
# 4. AFFICHAGE DE L'ETAT DU BRACKET
# ══════════════════════════════════════════════════════════════════

def show_bracket_state(conn):
    df = pd.read_sql_query("""
        SELECT bracket_id, match_date,
               home_team_label, away_team_label,
               actual_home_goals, actual_away_goals,
               actual_home_penalties, actual_away_penalties,
               actual_result, pred_home_goals, pred_away_goals
        FROM wc2026_fixtures
        WHERE bracket_id IS NOT NULL
        ORDER BY match_date, fixture_id
    """, conn)

    stages = [
        ("32es de finale",   [f"M{i}" for i in range(1, 17)]),
        ("16es de finale",   ["R8_1","R8_2","R8_3","R8_4","R8_5","R8_6","R8_7","R8_8"]),
        ("Quarts de finale", ["QF1","QF2","QF3","QF4"]),
        ("Demi-finales",     ["SF1","SF2"]),
        ("3e place",         ["3RD"]),
        ("Finale",           ["FIN"]),
    ]

    print(f"\n{'='*80}")
    print("  Etat du bracket WC2026")
    print(f"{'='*80}")

    for stage_name, bids in stages:
        rows = df[df["bracket_id"].isin(bids)]
        if len(rows) == 0: continue
        print(f"\n  -- {stage_name} --")
        for _, r in rows.iterrows():
            home = r["home_team_label"] or "TBD"
            away = r["away_team_label"] or "TBD"
            if r["actual_result"]:
                pen = ""
                if r["actual_home_penalties"] is not None:
                    pen = f" (pen {int(r['actual_home_penalties'])}-{int(r['actual_away_penalties'])})"
                statut = f"OK  {int(r['actual_home_goals'])}-{int(r['actual_away_goals'])}{pen} -> {r['actual_result']}"
            elif r["pred_home_goals"] is not None:
                statut = f"Predit {r['pred_home_goals']:.0f}-{r['pred_away_goals']:.0f}"
            elif home != "TBD":
                statut = "Equipes connues"
            else:
                statut = "TBD"
            print(f"  {(r['bracket_id'] or '?'):<6} {r['match_date']:<12} {home:<22} vs {away:<22}  {statut}")


# ══════════════════════════════════════════════════════════════════
# POINT D'ENTREE
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    dry = "--dry" in sys.argv

    if dry:
        print("=== MODE DRY RUN (aucune ecriture en base) ===\n")

    print("=" * 65)
    print("  Mise a jour resultats knockout WC2026")
    print("=" * 65)

    conn = get_connection()
    ensure_columns(conn)

    print("\n-- Resultats --")
    update_results(conn, dry_run=dry)

    print("\n-- Propagation des vainqueurs --")
    propagate_winners(conn, dry_run=dry)

    show_bracket_state(conn)

    conn.close()

    if not dry:
        print("\nMise a jour terminee.")
        print("   -> Lancer ensuite : python predict_knockout_real.py")