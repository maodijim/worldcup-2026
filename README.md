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
