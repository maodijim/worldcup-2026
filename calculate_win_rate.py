import argparse
import csv
import os
import urllib.request
from datetime import datetime
from math import exp, factorial

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"
    )
}

DEFAULT_TOP_N_TEAMS = 90


def fetch_url(url):
    """Fetches a URL and returns its text content."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as response:
        return response.read().decode("utf-8")


def poisson_pmf(lmbda, k):
    """Poisson probability mass function."""
    if lmbda < 0 or k < 0:
        return 0.0
    return exp(-lmbda) * (lmbda**k) / factorial(k)


def collect_data(output_filename, top_n_teams=DEFAULT_TOP_N_TEAMS, matches_per_team=20):
    """Collects Elo match data and saves it to CSV."""
    print("Step 1: Fetching team name and tournament name mappings...")
    try:
        teams_tsv = fetch_url("https://www.eloratings.net/en.teams.tsv")
        tournaments_tsv = fetch_url("https://www.eloratings.net/en.tournaments.tsv")
    except Exception as e:
        print(f"Error fetching mappings: {e}")
        return False

    team_map = {}
    for line in teams_tsv.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            team_map[parts[0]] = parts[1]

    tournament_map = {}
    for line in tournaments_tsv.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            tournament_map[parts[0]] = parts[1]

    print("Step 2: Fetching current live rankings (World.tsv)...")
    try:
        world_tsv = fetch_url("https://www.eloratings.net/World.tsv")
    except Exception as e:
        print(f"Error fetching live rankings: {e}")
        return False

    top_teams = []
    lines = world_tsv.strip().split("\n")
    for line in lines[:top_n_teams]:
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 4:
            code = parts[2]
            rating = parts[3]
            name = team_map.get(code, code)
            top_teams.append({"code": code, "name": name, "rating": rating})

    if len(top_teams) < 2:
        print("Error: Could not parse enough teams from World.tsv.")
        return False

    print(f"\nTop {top_n_teams} Elo Ranked Teams found:")
    for idx, team in enumerate(top_teams, 1):
        print(f" {idx:2d}. {team['name']} (Code: {team['code']}, Rating: {team['rating']})")

    csv_data = []

    print(
        f"\nStep 3: Fetching and parsing the last {matches_per_team} matches "
        f"for each top {top_n_teams} team..."
    )
    total_teams = len(top_teams)
    for idx, team in enumerate(top_teams, 1):
        safe_name = team["name"].replace(" ", "_")
        team_tsv_url = f"https://www.eloratings.net/{safe_name}.tsv"
        print(f" [{idx}/{total_teams}] Fetching matches for {team['name']} ({team_tsv_url})...")

        try:
            team_tsv_content = fetch_url(team_tsv_url)
        except Exception as e:
            print(f"  Warning: Could not fetch data for {team['name']}: {e}")
            continue

        match_lines = [l for line in team_tsv_content.strip().split("\n") if (l := line.strip())]
        last_matches = match_lines[-matches_per_team:]
        print(f"  Found {len(match_lines)} total matches. Processing last {len(last_matches)} matches...")

        for m_line in last_matches:
            parts = m_line.split("\t")
            if len(parts) < 7:
                continue

            year, month, day = parts[0], parts[1], parts[2]
            date_str = f"{year}-{month}-{day}"

            team1_code = parts[3]
            team2_code = parts[4]
            team1_score = parts[5]
            team2_score = parts[6]

            tournament_code = parts[7] if len(parts) > 7 else ""
            tournament_name = tournament_map.get(tournament_code, tournament_code if tournament_code else "Friendly")

            team1_name = team_map.get(team1_code, team1_code)
            team2_name = team_map.get(team2_code, team2_code)

            if team1_code == team["code"]:
                tracked_score = team1_score
                opp_score = team2_score
                opponent_name = team2_name
            else:
                tracked_score = team2_score
                opp_score = team1_score
                opponent_name = team1_name

            result_str = f"{team['name']} {tracked_score} - {opp_score} {opponent_name}"

            csv_data.append(
                {
                    "Tracked Team": team["name"],
                    "Tracked Team Rating": team["rating"],
                    "Date": date_str,
                    "Opponent": opponent_name,
                    "Tracked Team Score": tracked_score,
                    "Opponent Score": opp_score,
                    "Result": result_str,
                    "Tournament": tournament_name,
                }
            )

    print(f"\nStep 4: Saving collected data to {output_filename}...")
    fields = [
        "Tracked Team",
        "Tracked Team Rating",
        "Date",
        "Opponent",
        "Tracked Team Score",
        "Opponent Score",
        "Result",
        "Tournament",
    ]

    try:
        with open(output_filename, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(csv_data)
        print(f"Success! Saved {len(csv_data)} matches to {output_filename}.")
        return True
    except Exception as e:
        print(f"Error saving CSV: {e}")
        return False


def load_team_stats(input_csv):
    """Loads per-team scoring/conceding averages from a collected CSV.

    Recency weighting is enabled by default when a team has at least 5 matches:
    the most recent 5 matches are boosted and all matches use exponential decay.
    """
    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"CSV file not found: {input_csv}")

    recency_decay = 0.08
    recent_5_boost = 1.8
    recency_min_matches = 5
    recent_window = 5

    team_rows = {}
    team_ratings = {}
    total_weighted_goals = 0.0
    total_weight = 0.0

    with open(input_csv, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"Tracked Team", "Tracked Team Score", "Opponent Score"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"CSV is missing required columns: {sorted(required)}")

        for row in reader:
            team = (row.get("Tracked Team") or "").strip()
            if not team:
                continue

            try:
                goals_for = int(row["Tracked Team Score"])
                goals_against = int(row["Opponent Score"])
            except (TypeError, ValueError):
                continue

            date_text = (row.get("Date") or "").strip()
            try:
                parsed_date = datetime.strptime(date_text, "%Y-%m-%d")
            except ValueError:
                parsed_date = datetime.min

            if team not in team_rows:
                team_rows[team] = []
                team_ratings[team] = None
            team_rows[team].append(
                {
                    "parsed_date": parsed_date,
                    "goals_for": goals_for,
                    "goals_against": goals_against,
                }
            )

            # Elo rating is optional (older CSVs lack it); take the last valid value seen.
            try:
                team_ratings[team] = float(row["Tracked Team Rating"])
            except (TypeError, ValueError, KeyError):
                pass

    if not team_rows:
        raise ValueError("No valid match rows found in CSV.")

    team_stats = {}
    for team, matches_rows in team_rows.items():
        matches_rows.sort(key=lambda x: x["parsed_date"])
        matches = len(matches_rows)
        if matches == 0:
            continue
        use_recency_weights = matches >= recency_min_matches
        weighted_scored_sum = 0.0
        weighted_conceded_sum = 0.0
        weight_sum = 0.0

        for idx, row in enumerate(matches_rows):
            if use_recency_weights:
                age = (matches - 1) - idx
                weight = exp(-recency_decay * age)
                if idx >= matches - recent_window:
                    weight *= recent_5_boost
            else:
                weight = 1.0

            weighted_scored_sum += weight * row["goals_for"]
            weighted_conceded_sum += weight * row["goals_against"]
            weight_sum += weight
            total_weighted_goals += weight * row["goals_for"]
            total_weight += weight

        if weight_sum == 0:
            continue

        team_stats[team] = {
            "avg_scored": weighted_scored_sum / weight_sum,
            "avg_conceded": weighted_conceded_sum / weight_sum,
            "matches": matches,
            "rating": team_ratings.get(team),
        }

    if total_weight <= 0:
        raise ValueError("No valid weighted rows found in CSV.")
    overall_avg_goals = total_weighted_goals / total_weight

    return team_stats, overall_avg_goals


def load_recent_matches(input_csv, teams, last_n=5):
    """Loads last N matches for each requested team from the collected CSV."""
    recent = {team: [] for team in teams}
    with open(input_csv, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            team = (row.get("Tracked Team") or "").strip()
            if team not in recent:
                continue
            try:
                goals_for = int(row["Tracked Team Score"])
                goals_against = int(row["Opponent Score"])
            except (TypeError, ValueError, KeyError):
                continue

            date_text = (row.get("Date") or "").strip()
            try:
                parsed_date = datetime.strptime(date_text, "%Y-%m-%d")
            except ValueError:
                # Keep malformed dates as the earliest so valid dated rows win.
                parsed_date = datetime.min

            if goals_for > goals_against:
                result = "W"
            elif goals_for < goals_against:
                result = "L"
            else:
                result = "D"

            recent[team].append(
                {
                    "date": date_text,
                    "parsed_date": parsed_date,
                    "opponent": (row.get("Opponent") or "").strip(),
                    "goals_for": goals_for,
                    "goals_against": goals_against,
                    "result": result,
                }
            )

    for team in recent:
        recent[team].sort(key=lambda x: x["parsed_date"])
        recent[team] = recent[team][-last_n:]
    return recent


def calculate_poisson_win_rates(input_csv, team_a, team_b, max_goals=10, elo_weight=0.5):
    """Calculates win/draw rates for team_a vs team_b using a Poisson model.

    Expected goals (lambdas) blend two estimates:
      * a goal-stat model from attacking/defensive averages, and
      * an Elo model that splits the match's expected total goals toward the
        favorite according to its Elo win expectation.
    ``elo_weight`` in [0, 1] controls the mix (0 = pure stats, 1 = pure Elo).
    """
    team_stats, overall_avg_goals = load_team_stats(input_csv)
    available_teams = sorted(team_stats.keys())

    if team_a not in team_stats:
        raise ValueError(
            f"Team '{team_a}' is not available in collected data. Available teams: {', '.join(available_teams)}"
        )
    if team_b not in team_stats:
        raise ValueError(
            f"Team '{team_b}' is not available in collected data. Available teams: {', '.join(available_teams)}"
        )
    if team_a == team_b:
        raise ValueError("Please provide two different teams.")
    if overall_avg_goals <= 0:
        raise ValueError("Overall average goals is zero; cannot build Poisson model.")

    a = team_stats[team_a]
    b = team_stats[team_b]

    # Neutral-ground expected goals from attacking/defensive averages.
    lambda_stat_a = (a["avg_scored"] * b["avg_conceded"]) / overall_avg_goals
    lambda_stat_b = (b["avg_scored"] * a["avg_conceded"]) / overall_avg_goals

    rating_a = a.get("rating")
    rating_b = b.get("rating")
    use_elo = elo_weight > 0 and rating_a is not None and rating_b is not None

    if use_elo:
        # Elo win expectation on neutral ground (standard logistic, 400-point scale).
        we_a = 1.0 / (1.0 + 10 ** (-(rating_a - rating_b) / 400.0))
        # Keep the scoring environment from the stat model; let Elo decide the split.
        expected_total = lambda_stat_a + lambda_stat_b
        lambda_elo_a = expected_total * we_a
        lambda_elo_b = expected_total * (1.0 - we_a)
        lambda_a = (1.0 - elo_weight) * lambda_stat_a + elo_weight * lambda_elo_a
        lambda_b = (1.0 - elo_weight) * lambda_stat_b + elo_weight * lambda_elo_b
    else:
        if elo_weight > 0:
            print(
                "Note: Elo ratings missing for one or both teams "
                "(re-run --action collect to add them); using goal-stat model only."
            )
        lambda_a = lambda_stat_a
        lambda_b = lambda_stat_b

    win_a = 0.0
    win_b = 0.0
    draw = 0.0

    for goals_a in range(max_goals + 1):
        p_a = poisson_pmf(lambda_a, goals_a)
        for goals_b in range(max_goals + 1):
            p_b = poisson_pmf(lambda_b, goals_b)
            p = p_a * p_b
            if goals_a > goals_b:
                win_a += p
            elif goals_a < goals_b:
                win_b += p
            else:
                draw += p

    total = win_a + win_b + draw
    if total <= 0:
        raise ValueError("Could not compute probabilities. Try a higher --max-goals value.")

    # Normalize probabilities to account for truncated tail mass above max_goals.
    win_a /= total
    win_b /= total
    draw /= total

    print(f"Input CSV: {input_csv}")
    print(f"Teams: {team_a} vs {team_b}")
    if use_elo:
        print(
            f"Model: Elo-blend (elo_weight={elo_weight:.2f}) | "
            f"Elo {team_a}={rating_a:.0f}, {team_b}={rating_b:.0f}, "
            f"Elo win expectation {team_a}={we_a * 100:.1f}%"
        )
    else:
        print("Model: goal-stat only")
    print(f"Model lambdas (expected goals): {team_a}={lambda_a:.3f}, {team_b}={lambda_b:.3f}")
    print(f"{team_a} win rate: {win_a * 100:.2f}%")
    print(f"Draw rate: {draw * 100:.2f}%")
    print(f"{team_b} win rate: {win_b * 100:.2f}%")

    recent = load_recent_matches(input_csv, teams=[team_a, team_b], last_n=5)
    for team in (team_a, team_b):
        print(f"\n{team} last 5 matches:")
        matches = recent.get(team, [])
        if not matches:
            print("  No matches found in CSV.")
            continue
        for m in matches:
            print(
                f"  {m['date']}: {m['result']} vs {m['opponent']} "
                f"({m['goals_for']}-{m['goals_against']})"
            )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Collect Elo match data and/or compute Poisson win rates."
    )
    parser.add_argument(
        "--action",
        choices=["collect", "win-rate"],
        default="collect",
        help="Action to run: collect data or compute two-team win rate.",
    )
    parser.add_argument(
        "--output-csv",
        default=None,
        help="Output CSV path for collect action. If omitted, uses top_<N>_teams_matches.csv.",
    )
    parser.add_argument(
        "--top-n-teams",
        type=int,
        default=DEFAULT_TOP_N_TEAMS,
        help="Number of top Elo teams to collect for --action collect.",
    )
    parser.add_argument(
        "--matches-per-team",
        type=int,
        default=20,
        help="Number of recent matches to collect per team for --action collect.",
    )
    parser.add_argument(
        "--input-csv",
        default="top_90_teams_matches.csv",
        help="Input CSV path for win-rate action.",
    )
    parser.add_argument("--team-a", help="First team name for win-rate action.")
    parser.add_argument("--team-b", help="Second team name for win-rate action.")
    parser.add_argument(
        "--max-goals",
        type=int,
        default=10,
        help="Max goals per team used in Poisson matrix (win-rate action).",
    )
    parser.add_argument(
        "--elo-weight",
        type=float,
        default=0.5,
        help="Blend weight in [0, 1] for the Elo model vs. goal stats "
        "(0 = pure stats, 1 = pure Elo). win-rate action.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.action == "collect":
        if args.top_n_teams < 2:
            parser.error("--top-n-teams must be >= 2")
        if args.matches_per_team < 1:
            parser.error("--matches-per-team must be >= 1")
        output_csv = args.output_csv or f"top_{args.top_n_teams}_teams_matches.csv"
        ok = collect_data(
            output_csv,
            top_n_teams=args.top_n_teams,
            matches_per_team=args.matches_per_team,
        )
        raise SystemExit(0 if ok else 1)

    if not args.team_a or not args.team_b:
        parser.error("--team-a and --team-b are required for --action win-rate")
    if args.max_goals < 1:
        parser.error("--max-goals must be >= 1")
    if not 0.0 <= args.elo_weight <= 1.0:
        parser.error("--elo-weight must be between 0 and 1")

    try:
        calculate_poisson_win_rates(
            input_csv=args.input_csv,
            team_a=args.team_a,
            team_b=args.team_b,
            max_goals=args.max_goals,
            elo_weight=args.elo_weight,
        )
    except Exception as e:
        print(f"Error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
