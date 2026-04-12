#!/usr/bin/env python3
"""
00_runall.py

Run the whole pipeline: generate raw and normalized tables (script 01) then run the KFA analysis and graph (script 02).

Usage:
    python examples/exemplo1_00_runall.py           # runs both scripts
    python examples/exemplo1_00_runall.py --skip-generate   # skips script 01
    python examples/exemplo1_00_runall.py --skip-analysis   # skips script 02
    python examples/exemplo1_00_runall.py --python /path/to/python  # use a specific Python executable
"""
import argparse
import subprocess
import sys
from pathlib import Path

def run_script(python_exec, script_path):
    print(f"\n--- Running: {script_path.name} ---")
    try:
        subprocess.run([python_exec, str(script_path)], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Script {script_path.name} failed with exit code {e.returncode}")
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-generate', action='store_true', help='Skip script 01 (generate raw and norm tables)')
    parser.add_argument('--skip-analysis', action='store_true', help='Skip script 02 (KFA analysis and graph)')
    parser.add_argument('--python', default=sys.executable, help='Python executable to run the scripts (default: current interpreter)')
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent

    script01 = repo_root / 'exemplo1_01_biberplus_tagger_generate_tables_raw_and_norm1000.py'
    script02 = repo_root / 'exemplo1_02_biber_kfa_analysis_graph.py'

    if not args.skip_generate:
        if not script01.exists():
            print(f"Warning: {script01} not found — skipping generation step.")
        else:
            run_script(args.python, script01)

    if not args.skip_analysis:
        if not script02.exists():
            print(f"Warning: {script02} not found — skipping analysis step.")
        else:
            run_script(args.python, script02)

    print('\nAll requested steps finished.')

if __name__ == '__main__':
    main()
