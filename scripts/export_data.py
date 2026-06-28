import os, sys, json
import pandas as pd
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), "src/collect"))
from init_db import get_connection

DATA_DIR   = os.path.join(os.path.dirname(__file__), "../data")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "../models")

def safe_float(v, d=4):
    if v is None: return None
    try: return round(float(v), d)
    except: return None

def safe_int(v):
    if v is None: return None
    try: return int(v)
    except: return None

def write_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(',',':'), default=str)
    size_kb = os.path.getsize(path) / 1024
    print(f"  ✅ {filename:<25} {size_kb:>7.0f} KB")
    return size_kb


# ══════════════════════════════════════════════════════════════════
# predictions.json
# ══════════════════════════════════════════════════════════════════

def export_predictions(conn, metrics):
    c = conn.cursor()
 
    c.execute("SELECT COUNT(*) FROM matches")
    nb_train = c.fetchone()[0]
    c.execute("SELECT MIN(match_date), MAX(match_date) FROM matches")
    d_min, d_max = c.fetchone()
 
    # Équipes depuis real_group_standings en priorité, fallback group_standings
    try:
        c.execute("""
            SELECT rgs.team_id, rgs.team_label, rgs.group_name,
                   rgs.fifa_ranking, t.confederation, t.country_code
            FROM real_group_standings rgs
            LEFT JOIN teams t ON t.team_id = rgs.team_id
            ORDER BY rgs.group_name, rgs.position
        """)
    except Exception:
        c.execute("""
            SELECT gs.team_id, gs.team_label, gs.group_name,
                   gs.fifa_ranking, t.confederation, t.country_code
            FROM group_standings gs
            LEFT JOIN teams t ON t.team_id = gs.team_id
            ORDER BY gs.group_name, gs.position
        """)
    teams = [
        {"id": r[0], "name": r[1], "group": r[2],
         "ranking": r[3], "confederation": r[4], "code": r[5]}
        for r in c.fetchall()
    ]
 
    # Comptage global des matchs
    c.execute("SELECT COUNT(*) FROM wc2026_fixtures WHERE actual_result IS NOT NULL")
    played = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM wc2026_fixtures")
    total = c.fetchone()[0]
 
    c.execute("""
        SELECT stage, COUNT(*) as nb,
               SUM(CASE WHEN actual_result IS NOT NULL THEN 1 ELSE 0 END) as played
        FROM wc2026_fixtures GROUP BY stage ORDER BY MIN(match_date)
    """)
    stages = [{"stage": r[0], "total": r[1], "played": r[2]} for r in c.fetchall()]
 
    # ── Bilan de performance sur les matchs réels ──────────────────
    live_performance = _compute_live_performance(c)
 
    return {
        "generated_at": datetime.now().isoformat(),
        "model": {
            "nb_train_matches":  nb_train,
            "train_period":      f"{d_min} → {d_max}",
            "accuracy":          metrics.get("accuracy"),
            "baseline_accuracy": metrics.get("baseline_accuracy"),
            "log_loss":          metrics.get("log_loss"),
            "baseline_log_loss": metrics.get("baseline_log_loss"),
            "mae_home":          metrics.get("mae_home"),
            "mae_away":          metrics.get("mae_away"),
        },
        "tournament": {
            "total_fixtures": total,
            "played":         played,
            "stages":         stages,
        },
        "teams":            teams,
        "live_performance": live_performance,
    }
 
 
def _compute_live_performance(c):
    """
    Calcule le bilan de performance du modèle sur les matchs réels WC2026
    (phase de groupes + knockout).
    Compare pred_result / pred_home_goals / pred_away_goals vs actual_*.
    """
    # Phase de groupes : pred_result existe déjà
    c.execute("""
        SELECT stage,
               actual_result,
               pred_result,
               actual_home_goals, actual_away_goals,
               pred_home_goals,   pred_away_goals
        FROM wc2026_fixtures
        WHERE actual_result IS NOT NULL
          AND stage = 'GROUP_STAGE'
          AND pred_result IS NOT NULL
    """)
    group_rows = c.fetchall()
 
    # Knockout : pred_result n'existe pas, on le déduit de pred_home_goals vs pred_away_goals
    # actual_result est H ou A uniquement (jamais D)
    try:
        c.execute("""
            SELECT f.stage,
                   f.actual_result,
                   CASE
                     WHEN kf.pred_score_a > kf.pred_score_b THEN 'H'
                     WHEN kf.pred_score_a < kf.pred_score_b THEN 'A'
                     ELSE NULL
                   END as pred_result,
                   f.actual_home_goals, f.actual_away_goals,
                   kf.pred_score_a,     kf.pred_score_b
            FROM wc2026_fixtures f
            JOIN knockout_fixtures kf ON kf.match_id = f.bracket_id
            WHERE f.actual_result IS NOT NULL
              AND f.stage != 'GROUP_STAGE'
              AND f.bracket_id IS NOT NULL
        """)
        knockout_rows = c.fetchall()
    except Exception:
        knockout_rows = []
 
    all_rows = group_rows + knockout_rows
 
    if not all_rows:
        return None
 
    total_played   = len(all_rows)
    correct_result = 0
    correct_score  = 0
    by_stage       = {}
 
    for stage, act_res, pred_res, act_h, act_a, pred_h, pred_a in all_rows:
        # Résultat correct
        res_ok = (pred_res == act_res) if pred_res else False
        # Score exact correct
        try:
            score_ok = (int(round(pred_h)) == int(act_h) and
                        int(round(pred_a)) == int(act_a))
        except (TypeError, ValueError):
            score_ok = False
 
        if res_ok:   correct_result += 1
        if score_ok: correct_score  += 1
 
        if stage not in by_stage:
            by_stage[stage] = {"stage": stage, "played": 0, "correct_result": 0, "correct_score": 0}
        by_stage[stage]["played"]         += 1
        by_stage[stage]["correct_result"] += int(res_ok)
        by_stage[stage]["correct_score"]  += int(score_ok)
 
    # Calcul des accuracies par stage
    stage_list = []
    for s in by_stage.values():
        s["accuracy_result"] = round(s["correct_result"] / s["played"], 3) if s["played"] else 0
        s["accuracy_score"]  = round(s["correct_score"]  / s["played"], 3) if s["played"] else 0
        stage_list.append(s)
 
    return {
        "total_played":    total_played,
        "correct_result":  correct_result,
        "accuracy_result": round(correct_result / total_played, 3) if total_played else 0,
        "correct_score":   correct_score,
        "accuracy_score":  round(correct_score  / total_played, 3) if total_played else 0,
        "by_stage":        stage_list,
    }


# ══════════════════════════════════════════════════════════════════
# groups.json
# ══════════════════════════════════════════════════════════════════

def export_groups(conn):
    standings = pd.read_sql_query("""
        SELECT team_id, group_name, position, team_label, fifa_ranking,
               points, played, won, drawn, lost,
               goals_for, goals_against, goal_diff, qualified,
               prob_1st, prob_2nd, prob_3rd, prob_4th, prob_qualify
        FROM group_standings ORDER BY group_name, position
    """, conn)
 
    # Stats réelles depuis real_group_standings (peut ne pas exister)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='real_group_standings'")
    has_real = c.fetchone() is not None
 
    real_map = {}
    if has_real:
        real_standings = pd.read_sql_query("""
            SELECT team_id, group_name, position, points, played,
                   won, drawn, lost, goals_for, goals_against, goal_diff, qualified
            FROM real_group_standings ORDER BY group_name, position
        """, conn)
        for _, r in real_standings.iterrows():
            real_map[int(r["team_id"])] = {
                "pos":    safe_int(r["position"]),
                "pts":    safe_int(r["points"]),
                "played": safe_int(r["played"]),
                "w":      safe_int(r["won"]),
                "d":      safe_int(r["drawn"]),
                "l":      safe_int(r["lost"]),
                "gf":     safe_int(r["goals_for"]),
                "ga":     safe_int(r["goals_against"]),
                "gd":     safe_int(r["goal_diff"]),
                "qual":   r["qualified"],
            }
 
    # Vrais meilleurs 3èmes
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='real_third_place'")
    has_real_thirds = c.fetchone() is not None
 
    real_thirds_list = []
    if has_real_thirds:
        real_thirds = pd.read_sql_query("""
            SELECT rank, group_name, team_id, team_label,
                   points, goal_diff, goals_for, fifa_ranking, qualified
            FROM real_third_place ORDER BY rank
        """, conn)
        real_thirds_list = [
            {
                "rank":      safe_int(r["rank"]),
                "group":     r["group_name"],
                "id":        safe_int(r["team_id"]),
                "name":      r["team_label"],
                "pts":       safe_int(r["points"]),
                "gd":        safe_int(r["goal_diff"]),
                "gf":        safe_int(r["goals_for"]),
                "fifa_rank": safe_int(r["fifa_ranking"]),
                "qualified": bool(r["qualified"]),
            }
            for _, r in real_thirds.iterrows()
        ]
 
    # Colonnes disponibles dans wc2026_fixtures
    c.execute("PRAGMA table_info(wc2026_fixtures)")
    cols = {r[1] for r in c.fetchall()}
    has_score_freq = "pred_score_freq" in cols
 
    freq_col = ", pred_score_freq" if has_score_freq else ""
    fixtures = pd.read_sql_query(f"""
        SELECT fixture_id, group_name, match_date,
               home_team_id, away_team_id,
               home_team_label, away_team_label,
               pred_home_goals, pred_away_goals, pred_result,
               pred_proba_home, pred_proba_draw, pred_proba_away,
               actual_home_goals, actual_away_goals, actual_result
               {freq_col}
        FROM wc2026_fixtures
        WHERE stage='GROUP_STAGE' AND home_team_id IS NOT NULL
        ORDER BY group_name, match_date
    """, conn)
 
    # Meilleurs 3èmes prédits
    try:
        thirds = pd.read_sql_query("""
            SELECT rank, group_name, team_id, team_label,
                   points, goal_diff, goals_for, fifa_ranking, prob_best3
            FROM best_third_place ORDER BY rank
        """, conn)
    except Exception:
        thirds = pd.DataFrame()
 
    groups = {}
    for grp in sorted(standings["group_name"].unique()):
        teams = []
        for _, r in standings[standings["group_name"] == grp].iterrows():
            tid = int(r["team_id"])
            teams.append({
                "id":     tid,
                "name":   r["team_label"],
                "rank":   safe_int(r["fifa_ranking"]),
                "pos":    safe_int(r["position"]),
                "qual":   r["qualified"],
                "pts":    safe_int(r["points"]),
                "played": safe_int(r["played"]),
                "w":      safe_int(r["won"]),
                "d":      safe_int(r["drawn"]),
                "l":      safe_int(r["lost"]),
                "gf":     safe_int(r["goals_for"]),
                "ga":     safe_int(r["goals_against"]),
                "gd":     safe_int(r["goal_diff"]),
                "p1":     safe_float(r["prob_1st"], 3),
                "p2":     safe_float(r["prob_2nd"], 3),
                "p3":     safe_float(r["prob_3rd"], 3),
                "p4":     safe_float(r["prob_4th"], 3),
                "pq":     safe_float(r["prob_qualify"], 3),
                # Stats réelles (null si pas encore disponibles)
                "real":   real_map.get(tid, None),
            })
 
        matches = []
        for _, m in fixtures[fixtures["group_name"] == grp].iterrows():
            match = {
                "id":       safe_int(m["fixture_id"]),
                "date":     m["match_date"],
                "home":     m["home_team_label"],
                "away":     m["away_team_label"],
                "home_id":  safe_int(m["home_team_id"]),
                "away_id":  safe_int(m["away_team_id"]),
                "pred_h":   safe_int(m["pred_home_goals"]),
                "pred_a":   safe_int(m["pred_away_goals"]),
                "pred_res": m["pred_result"],
                "act_h":    safe_int(m["actual_home_goals"]),
                "act_a":    safe_int(m["actual_away_goals"]),
                "act_res":  m["actual_result"],
                "ph":       safe_float(m["pred_proba_home"], 3),
                "pd":       safe_float(m["pred_proba_draw"], 3),
                "pa":       safe_float(m["pred_proba_away"], 3),
            }
            if has_score_freq:
                match["score_freq"] = safe_float(m.get("pred_score_freq"), 1)
            matches.append(match)
 
        groups[grp] = {"teams": teams, "matches": matches}
 
    best_thirds = [
        {
            "rank":      safe_int(r["rank"]),
            "group":     r["group_name"],
            "id":        safe_int(r["team_id"]),
            "name":      r["team_label"],
            "pts":       safe_int(r["points"]),
            "gd":        safe_int(r["goal_diff"]),
            "gf":        safe_int(r["goals_for"]),
            "fifa_rank": safe_int(r["fifa_ranking"]),
            "prob":      safe_float(r["prob_best3"], 3),
        }
        for _, r in thirds.iterrows()
    ] if len(thirds) > 0 else []
 
    return {
        "groups":            groups,
        "best_thirds":       best_thirds,        # prédits
        "best_thirds_real":  real_thirds_list,   # réels ([] si pas encore dispo)
    }


# ══════════════════════════════════════════════════════════════════
# bracket.json
# ══════════════════════════════════════════════════════════════════

def export_bracket(conn):
    # Vérifier quelles colonnes actual_* existent dans knockout_fixtures
    import sqlite3
    c = conn.cursor()
    c.execute("PRAGMA table_info(knockout_fixtures)")
    ko_cols = {r[1] for r in c.fetchall()}
    has_actual = "actual_score_a" in ko_cols
 
    if has_actual:
        fixtures = pd.read_sql_query("""
            SELECT match_id, round,
                   team_a_id, team_a_name, team_b_id, team_b_name,
                   pred_score_a, pred_score_b,
                   prob_a_wins, prob_b_wins, score_freq,
                   winner_id, winner_name,
                   actual_score_a, actual_score_b,
                   actual_pen_a, actual_pen_b,
                   actual_result
            FROM knockout_fixtures ORDER BY match_id
        """, conn)
    else:
        fixtures = pd.read_sql_query("""
            SELECT match_id, round,
                   team_a_id, team_a_name, team_b_id, team_b_name,
                   pred_score_a, pred_score_b,
                   prob_a_wins, prob_b_wins, score_freq,
                   winner_id, winner_name
            FROM knockout_fixtures ORDER BY match_id
        """, conn)
 
    # Probabilités de progression — fallback real_group_standings si group_standings absent
    try:
        probs = pd.read_sql_query("""
            SELECT kp.team_id, kp.team_name, kp.group_name, kp.fifa_ranking,
                   kp.prob_r16, kp.prob_r8, kp.prob_qf, kp.prob_sf,
                   kp.prob_final, kp.prob_champion,
                   COALESCE(kp.prob_qualify, gs.prob_qualify) as prob_qualify
            FROM knockout_probabilities kp
            LEFT JOIN group_standings gs USING(team_id)
            ORDER BY kp.prob_champion DESC
        """, conn)
    except Exception:
        try:
            probs = pd.read_sql_query("""
                SELECT kp.team_id, kp.team_name, kp.group_name, kp.fifa_ranking,
                       kp.prob_r16, kp.prob_r8, kp.prob_qf, kp.prob_sf,
                       kp.prob_final, kp.prob_champion,
                       rgs.prob_qualify
                FROM knockout_probabilities kp
                LEFT JOIN real_group_standings rgs USING(team_id)
                ORDER BY kp.prob_champion DESC
            """, conn)
        except Exception:
            probs = pd.read_sql_query("""
                SELECT team_id, team_name, group_name, fifa_ranking,
                       prob_r16, prob_r8, prob_qf, prob_sf,
                       prob_final, prob_champion, NULL as prob_qualify
                FROM knockout_probabilities
                ORDER BY prob_champion DESC
            """, conn)
 
    bracket = []
    for _, m in fixtures.iterrows():
        entry = {
            "id":    m["match_id"],
            "round": m["round"],
            "team_a": {
                "id":    safe_int(m["team_a_id"]),
                "name":  m["team_a_name"],
                "score": safe_int(m["pred_score_a"]),
            },
            "team_b": {
                "id":    safe_int(m["team_b_id"]),
                "name":  m["team_b_name"],
                "score": safe_int(m["pred_score_b"]),
            },
            "prob_a":     safe_float(m["prob_a_wins"], 3),
            "prob_b":     safe_float(m["prob_b_wins"], 3),
            "score_freq": safe_float(m["score_freq"], 1),
            "winner": {
                "id":   safe_int(m["winner_id"]),
                "name": m["winner_name"],
            },
            # Résultats réels
            "actual": {
                "score_a": safe_int(m["actual_score_a"]) if has_actual else None,
                "score_b": safe_int(m["actual_score_b"]) if has_actual else None,
                "pen_a":   safe_int(m["actual_pen_a"])   if has_actual else None,
                "pen_b":   safe_int(m["actual_pen_b"])   if has_actual else None,
                "result":  m["actual_result"]             if has_actual else None,
            },
        }
        bracket.append(entry)
 
    probabilities = [
        {
            "id":    safe_int(r["team_id"]),
            "name":  r["team_name"],
            "group": r["group_name"],
            "rank":  safe_int(r["fifa_ranking"]),
            "pq":    safe_float(r["prob_qualify"], 3),
            "r16":   safe_float(r["prob_r16"], 3),
            "r8":    safe_float(r["prob_r8"], 3),
            "qf":    safe_float(r["prob_qf"], 3),
            "sf":    safe_float(r["prob_sf"], 3),
            "fin":   safe_float(r["prob_final"], 3),
            "champ": safe_float(r["prob_champion"], 3),
        }
        for _, r in probs.iterrows()
    ]
 
    return {"bracket": bracket, "probabilities": probabilities}


# ══════════════════════════════════════════════════════════════════
# training.json
# ══════════════════════════════════════════════════════════════════

def export_training(conn):
    matches = pd.read_sql_query("""
        SELECT m.match_date, m.competition, m.season, m.stage,
               m.neutral_venue,
               th.team_name as home_team, ta.team_name as away_team,
               m.home_goals, m.away_goals, m.result_90
        FROM matches m
        JOIN teams th ON th.team_id = m.home_team_id
        JOIN teams ta ON ta.team_id = m.away_team_id
        ORDER BY m.match_date DESC
    """, conn)

    comp_dist = (matches.groupby("competition").size()
                 .reset_index(name="count")
                 .sort_values("count", ascending=False))

    return {
        "total": len(matches),
        "matches": [
            {"date":r["match_date"],"competition":r["competition"],
             "season":r["season"] or "","stage":r["stage"] or "",
             "home":r["home_team"],"away":r["away_team"],
             "home_goals":safe_int(r["home_goals"]),
             "away_goals":safe_int(r["away_goals"]),
             "result":r["result_90"],"neutral":bool(r["neutral_venue"])}
            for _, r in matches.iterrows()
        ],
        "by_competition": comp_dist.to_dict(orient="records"),
        "result_dist":    matches["result_90"].value_counts().to_dict(),
    }


# ══════════════════════════════════════════════════════════════════
# model.json
# ══════════════════════════════════════════════════════════════════

def export_model(conn, metrics, features_meta):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM matches")
    nb = c.fetchone()[0]
    c.execute("SELECT MIN(match_date), MAX(match_date) FROM matches")
    d_min, d_max = c.fetchone()

    features = features_meta.get("features", [])
    fi_raw   = features_meta.get("feature_importance", [])

    FEATURE_LABELS = {
        "ranking_gap":           "Écart de ranking FIFA",
        "ranking_gap_adj":       "Écart de ranking ajusté (confédération)",
        "home_rank_adj":         "Ranking ajusté domicile",
        "away_rank_adj":         "Ranking ajusté extérieur",
        "home_top20_ratio":      "Ratio matchs vs top 20 domicile",
        "away_top20_ratio":      "Ratio matchs vs top 20 extérieur",
        "home_fifa_ranking":     "Ranking FIFA domicile",
        "away_fifa_ranking":     "Ranking FIFA extérieur",
        "home_form5_pts":        "Points domicile (5 matchs)",
        "home_form5_scored":     "Buts marqués domicile (5 matchs)",
        "home_form5_conceded":   "Buts encaissés domicile (5 matchs)",
        "home_form10_pts":       "Points domicile (10 matchs)",
        "home_form10_scored":    "Buts marqués domicile (10 matchs)",
        "home_form10_conceded":  "Buts encaissés domicile (10 matchs)",
        "away_form5_pts":        "Points extérieur (5 matchs)",
        "away_form5_scored":     "Buts marqués extérieur (5 matchs)",
        "away_form5_conceded":   "Buts encaissés extérieur (5 matchs)",
        "away_form10_pts":       "Points extérieur (10 matchs)",
        "away_form10_scored":    "Buts marqués extérieur (10 matchs)",
        "away_form10_conceded":  "Buts encaissés extérieur (10 matchs)",
        "h2h_home_wins":         "% victoires domicile H2H",
        "h2h_draws":             "% nuls H2H",
        "h2h_away_wins":         "% victoires extérieur H2H",
        "h2h_home_goals_avg":    "Buts domicile H2H (moyenne)",
        "h2h_away_goals_avg":    "Buts extérieur H2H (moyenne)",
        "h2h_matches":           "Nombre de matchs H2H",
        "neutral_venue":         "Terrain neutre",
        "competition_weight":    "Importance de la compétition",
        "is_knockout":           "Phase éliminatoire",
    }

    feature_importance = [
        {"feature":    fi["feature"],
         "importance": safe_float(fi["importance"], 4),
         "label":      FEATURE_LABELS.get(fi["feature"], fi["feature"])}
        for fi in sorted(fi_raw, key=lambda x: x["importance"], reverse=True)
    ]

    return {
        "summary": {
            "algorithm":        "XGBoost + calibration isotonique",
            "nb_matches":       nb,
            "period":           f"{d_min} → {d_max}",
            "accuracy":         metrics.get("accuracy"),
            "baseline_accuracy":metrics.get("baseline_accuracy"),
            "log_loss":         metrics.get("log_loss"),
            "baseline_log_loss":metrics.get("baseline_log_loss"),
            "mae_home":         metrics.get("mae_home"),
            "mae_away":         metrics.get("mae_away"),
            "nb_simulations":   10000,
            "nb_features":      len(features),
        },
        "feature_importance": feature_importance,
        "features": [
            {"category":"Classement FIFA","count":2,
             "description":"Ranking FIFA domicile/extérieur."},
            {"category":"Classement ajusté","count":3,
             "description":"Ranking FIFA + pénalité confédération. Iran #21 AFC → #41 effectif."},
            {"category":"Expérience élite","count":2,
             "description":"Ratio de matchs joués contre le top 20 ajusté sur les 20 derniers matchs."},
            {"category":"Forme récente","count":12,
             "description":"Points, buts marqués/encaissés sur 5 et 10 derniers matchs. Pondérés par confédération et récence."},
            {"category":"Head-to-head","count":6,
             "description":"Historique des 5 dernières confrontations directes."},
            {"category":"Contexte","count":3,
             "description":"Terrain neutre, poids de la compétition (CdM=1.0 → amicaux=0.3), phase éliminatoire."},
        ],
        "data_sources": [
            {"name":"FIFA World Cup 2022",             "type":"Tournoi"},
            {"name":"Qualifications CdM 2026",         "type":"Qualifications"},
            {"name":"UEFA Euro 2024 + qualifications", "type":"Tournoi"},
            {"name":"Copa América 2024",               "type":"Tournoi"},
            {"name":"AFCON 2023 + 2025",               "type":"Tournoi"},
            {"name":"AFC Asian Cup 2023",              "type":"Tournoi"},
            {"name":"Gold Cup 2023 + 2025",            "type":"Tournoi"},
            {"name":"UEFA Nations League 2022 + 2024", "type":"Nations League"},
            {"name":"CONCACAF Nations League",         "type":"Nations League"},
            {"name":"Matchs amicaux 2023-2026",        "type":"Amicaux"},
        ],
    }

# ══════════════════════════════════════════════════════════════════
# wc2026_matches.json
# ══════════════════════════════════════════════════════════════════

def export_fixtures(conn):
    c = conn.cursor()
    # Vérifier que les colonnes FIFA ranking existent
    c.execute("PRAGMA table_info(wc2026_fixtures)")
    cols = {r[1] for r in c.fetchall()}
    home_rank_col = "home_fifa_ranking" if "home_fifa_ranking" in cols else "NULL"
    away_rank_col = "away_fifa_ranking" if "away_fifa_ranking" in cols else "NULL"

    rows = pd.read_sql_query(f"""
        SELECT fixture_id,
               group_name,
               stage,
               match_date,
               home_team_id,
               away_team_id,
               home_team_label,
               away_team_label,
               {home_rank_col} AS home_fifa_ranking,
               {away_rank_col} AS away_fifa_ranking
        FROM wc2026_fixtures
        ORDER BY match_date, fixture_id
    """, conn)

    matches = [
        {
            "fixture_id":        safe_int(r["fixture_id"]),
            "group_name":        r["group_name"],
            "stage":             r["stage"],
            "match_date":        r["match_date"],
            "home_team_id":      safe_int(r["home_team_id"]),
            "away_team_id":      safe_int(r["away_team_id"]),
            "home_team_label":   r["home_team_label"],
            "away_team_label":   r["away_team_label"],
            "home_fifa_ranking": safe_int(r["home_fifa_ranking"]),
            "away_fifa_ranking": safe_int(r["away_fifa_ranking"]),
        }
        for _, r in rows.iterrows()
    ]

    return {"total": len(matches), "matches": matches}


# ══════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("="*55)
    print("  Export JSON — WC2026 Predictor")
    print("="*55)

    os.makedirs(DATA_DIR, exist_ok=True)

    metrics_path  = os.path.join(MODELS_DIR, "metrics.json")
    features_path = os.path.join(MODELS_DIR, "features.json")

    metrics = {}
    if os.path.exists(metrics_path):
        with open(metrics_path) as f:
            metrics = json.load(f)
        print(f"  Métriques : accuracy={metrics.get('accuracy')}"
              f"  log_loss={metrics.get('log_loss')}")
    else:
        print("  ⚠️  models/metrics.json introuvable")

    features_meta = {}
    if os.path.exists(features_path):
        with open(features_path) as f:
            features_meta = json.load(f)
        print(f"  Features  : {len(features_meta.get('features',[]))} features")
    else:
        print("  ⚠️  models/features.json introuvable")

    conn = get_connection()

    print("\n📦 Génération des fichiers JSON :")
    print(f"  {'Fichier':<25} {'Taille':>8}")
    print(f"  {'─'*35}")

    write_json("predictions.json",   export_predictions(conn, metrics))
    write_json("groups.json",        export_groups(conn))
    write_json("bracket.json",       export_bracket(conn))
    write_json("training.json",      export_training(conn))
    write_json("model.json",         export_model(conn, metrics, features_meta))
    write_json("wc2026_matches.json", export_fixtures(conn))

    conn.close()

    total_kb = sum(
        os.path.getsize(os.path.join(DATA_DIR, f)) / 1024
        for f in ["predictions.json","groups.json","bracket.json",
                  "training.json","model.json","wc2026_matches.json"]
        if os.path.exists(os.path.join(DATA_DIR, f))
    )
    print(f"\n  Total : {total_kb:.0f} KB")
    print(f"  → {DATA_DIR}")
    print("\n🎉 Export terminé")