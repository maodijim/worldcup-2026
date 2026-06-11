# worldcup-2026

## Script Usage

Run data collection (fetches top teams and saves recent matches to CSV):

```bash
python3 calculate_win_rate.py --action collect --output-csv top_90_teams_matches.csv
```

Calculate win rates for two teams using Poisson distribution from collected CSV:

```bash
python3 calculate_win_rate.py --action win-rate --team-a Spain --team-b France --input-csv top_90_teams_matches.csv
```

Show all options:

```bash
python3 calculate_win_rate.py --help
```

Example output
```bash
python3 calculate_win_rate.py --action win-rate --team-a Mexico --team-b "South Africa" --input-csv top_90_teams_matches.csv
Input CSV: top_90_teams_matches.csv
Teams: Mexico vs South Africa
Model: Elo-blend (elo_weight=0.50) | Elo Mexico=1875, South Africa=1517, Elo win expectation Mexico=88.7%
Model lambdas (expected goals): Mexico=0.978, South Africa=0.419
Mexico win rate: 48.54%
Draw rate: 35.96%
South Africa win rate: 15.50%

Mexico last 5 matches:
  2026-03-28: D vs Portugal (0-0)
  2026-03-31: D vs Belgium (1-1)
  2026-05-22: W vs Ghana (2-0)
  2026-05-30: W vs Australia (1-0)
  2026-06-04: W vs Serbia (5-1)

South Africa last 5 matches:
  2026-01-04: L vs Cameroon (1-2)
  2026-03-27: D vs Panama (1-1)
  2026-03-31: L vs Panama (1-2)
  2026-05-29: D vs Nicaragua (0-0)
  2026-06-06: D vs Jamaica (1-1)
```
