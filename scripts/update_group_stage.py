import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "../data", "wc2026.db")


# ════════════════════════════════════════════════════════════
# AU FUR ET À MESURE
# Format : fixture_id: (home_goals, away_goals)
# ══════════════════════════════════════════════════════════════════

ACTUAL_RESULTS = {

    # ── Groupe A ──────────────────────────────────────────────────
    537327: (2, 0),   # 11/06  Mexico          vs South Africa
    537328: (2, 1),   # 12/06  South Korea     vs Czechia
    537329: (1, 1),   # 18/06  Czechia         vs South Africa
    537330: (1, 0),   # 19/06  Mexico          vs South Korea
    537331: (0, 3),   # 25/06  Czechia         vs Mexico
    537332: (1, 0),   # 25/06  South Africa    vs South Korea

    # ── Groupe B ──────────────────────────────────────────────────
    537333: (1, 1),   # 12/06  Canada          vs Bosnia-Herzegovina
    537334: (1, 1),   # 13/06  Qatar           vs Switzerland
    537335: (4, 1),   # 18/06  Switzerland     vs Bosnia-Herzegovina
    537336: (6, 0),   # 18/06  Canada          vs Qatar
    537337: (2, 1),   # 24/06  Switzerland     vs Canada
    537338: (3, 1),   # 24/06  Bosnia-Herzegovina vs Qatar

    # ── Groupe C ──────────────────────────────────────────────────
    537339: (1, 1),   # 13/06  Brazil          vs Morocco
    537340: (0, 1),   # 14/06  Haiti           vs Scotland
    537341: (3, 0),   # 20/06  Brazil          vs Haiti
    537342: (0, 1),   # 19/06  Scotland        vs Morocco
    537343: (0, 3),   # 24/06  Scotland        vs Brazil
    537344: (4, 2),   # 24/06  Morocco         vs Haiti

    # ── Groupe D ──────────────────────────────────────────────────
    537345: (4, 1),   # 13/06  United States   vs Paraguay
    537346: (2, 0),   # 14/06  Australia       vs Turkey
    537347: (0, 1),   # 20/06  Turkey          vs Paraguay
    537348: (2, 0),   # 19/06  United States   vs Australia
    537349: (3, 2),   # 26/06  Turkey          vs United States
    537350: (0, 0),   # 26/06  Paraguay        vs Australia

    # ── Groupe E ──────────────────────────────────────────────────
    537351: (7, 1),   # 14/06  Germany         vs Curaçao
    537352: (1, 0),   # 14/06  Ivory Coast     vs Ecuador
    537353: (2, 1),   # 20/06  Germany         vs Ivory Coast
    537354: (0, 0),   # 21/06  Ecuador         vs Curaçao
    537355: (2, 1),   # 25/06  Ecuador         vs Germany
    537356: (0, 2),   # 25/06  Curaçao         vs Ivory Coast

    # ── Groupe F ──────────────────────────────────────────────────
    537357: (2, 2),   # 14/06  Netherlands     vs Japan
    537358: (5, 1),   # 15/06  Sweden          vs Tunisia
    537359: (5, 1),   # 20/06  Netherlands     vs Sweden
    537360: (0, 4),   # 21/06  Tunisia         vs Japan
    537361: (1, 3),   # 25/06  Tunisia         vs Netherlands
    537362: (1, 1),   # 25/06  Japan           vs Sweden

    # ── Groupe G ──────────────────────────────────────────────────
    537363: (1, 1),   # 15/06  Belgium         vs Egypt
    537364: (2, 2),   # 16/06  Iran            vs New Zealand
    537365: (0, 0),   # 21/06  Belgium         vs Iran
    537366: (1, 3),   # 22/06  New Zealand     vs Egypt
    537367: (1, 5),   # 27/06  New Zealand     vs Belgium
    537368: (1, 1),   # 27/06  Egypt           vs Iran

    # ── Groupe H ──────────────────────────────────────────────────
    537369: (0, 0),   # 15/06  Spain           vs Cape Verde Islands
    537370: (1, 1),   # 15/06  Saudi Arabia    vs Uruguay
    537371: (4, 0),   # 21/06  Spain           vs Saudi Arabia
    537372: (2, 2),   # 21/06  Uruguay         vs Cape Verde Islands
    537373: (0, 1),   # 27/06  Uruguay         vs Spain
    537374: (0, 0),   # 27/06  Cape Verde Islands vs Saudi Arabia

    # ── Groupe I ──────────────────────────────────────────────────
    537391: (3, 1),   # 16/06  France          vs Senegal
    537392: (1, 4),   # 16/06  Iraq            vs Norway
    537393: (3, 0),   # 22/06  France          vs Iraq
    537394: (3, 2),   # 23/06  Norway          vs Senegal
    537395: (1, 4),   # 26/06  Norway          vs France
    537396: (5, 0),   # 26/06  Senegal         vs Iraq

    # ── Groupe J ──────────────────────────────────────────────────
    537397: (3, 0),   # 17/06  Argentina       vs Algeria
    537398: (3, 1),   # 17/06  Austria         vs Jordan
    537399: (2, 0),   # 22/06  Argentina       vs Austria
    537400: (1, 2),   # 23/06  Jordan          vs Algeria
    537401: (1, 3),   # 28/06  Jordan          vs Argentina
    537402: (3, 3),   # 28/06  Algeria         vs Austria

    # ── Groupe K ──────────────────────────────────────────────────
    537403: (1, 1),   # 17/06  Portugal        vs Congo DR
    537404: (1, 3),   # 18/06  Uzbekistan      vs Colombia
    537405: (5, 0),   # 23/06  Portugal        vs Uzbekistan
    537406: (1, 0),   # 24/06  Colombia        vs Congo DR
    537407: (0, 0),   # 27/06  Colombia        vs Portugal
    537408: (3, 1),   # 27/06  Congo DR        vs Uzbekistan

    # ── Groupe L ──────────────────────────────────────────────────
    537409: (4, 2),   # 17/06  England         vs Croatia
    537410: (1, 0),   # 17/06  Ghana           vs Panama
    537411: (0, 0),   # 23/06  England         vs Ghana
    537412: (0, 1),   # 23/06  Panama          vs Croatia
    537413: (0, 2),   # 27/06  Panama          vs England
    537414: (2, 1),   # 27/06  Croatia         vs Ghana
}


# ══════════════════════════════════════════════════════════════════
# MISE À JOUR EN BASE
# ══════════════════════════════════════════════════════════════════

def compute_result(hg, ag):
    if hg > ag:   return "H"
    elif hg < ag: return "A"
    else:          return "D"


def update(dry_run=False):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    # Vérifier que les colonnes existent
    for col in ["actual_home_goals", "actual_away_goals", "actual_result"]:
        try:
            c.execute(f"ALTER TABLE wc2026_fixtures ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass 

    updated = skipped = missing = 0

    for fid, score in ACTUAL_RESULTS.items():
        if score is None:
            skipped += 1
            continue

        hg, ag = score
        res = compute_result(hg, ag)

        # Vérifier que le fixture existe
        c.execute("SELECT home_team_label, away_team_label, match_date FROM wc2026_fixtures WHERE fixture_id = ?", (fid,))
        row = c.fetchone()
        if not row:
            print(f"⚠️  fixture_id {fid} introuvable en base")
            missing += 1
            continue

        home, away, date = row
        if dry_run:
            print(f"  [DRY] {date}  {home:<25} {hg} - {ag}  {away:<25}  → {res}")
        else:
            c.execute("""
                UPDATE wc2026_fixtures
                SET actual_home_goals = ?,
                    actual_away_goals = ?,
                    actual_result     = ?
                WHERE fixture_id = ?
            """, (hg, ag, res, fid))
            updated += 1

    if not dry_run:
        conn.commit()
        print(f"\n✅ {updated} matchs mis à jour")
        print(f"   {skipped} matchs ignorés (pas encore joués)")
        if missing:
            print(f"   ⚠️  {missing} fixture_id introuvables")

        c.execute("""
            SELECT group_name, match_date, home_team_label, actual_home_goals,
                   actual_away_goals, away_team_label, actual_result
            FROM wc2026_fixtures
            WHERE actual_result IS NOT NULL
            ORDER BY match_date, group_name
        """)
        rows = c.fetchall()
        print(f"\n{'─'*70}")
        print(f"  {'Grp':<4} {'Date':<11} {'Domicile':<22} {'Score':^7} {'Extérieur':<22} Res")
        print(f"{'─'*70}")
        for grp, date, home, hg, ag, away, res in rows:
            print(f"  {(grp or '?'):<4} {date:<11} {home:<22} {hg} - {ag:>1}  {away:<22} {res}")

    conn.close()


if __name__ == "__main__":
    import sys
    dry = "--dry" in sys.argv
    if dry:
        print("=== MODE DRY RUN (aucune écriture en base) ===\n")
    update(dry_run=dry)