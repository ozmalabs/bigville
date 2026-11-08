#!/usr/bin/env bash
# Scratch-tree validation for the 044/045 rebase. Stages run one after another (no load from parallel runs).
set -u
RB=/tmp/rb
LOG=$RB/logs
MEAS=$RB/measure
mkdir -p "$LOG" "$MEAS"

FOCUSED_COMMON="tests/test_phase043_care.py tests/test_phase057_tui.py tests/test_phase063_marks.py tests/test_phase065_impairment.py tests/test_phase069_body.py tests/test_phase070_locus.py tests/test_phase071_attend.py tests/test_simple_life.py tests/test_scenario_runner.py"

run_focused() { # tree stage_label extra_tests
  local tree=$1 label=$2 extra=$3
  cd "$tree" || exit 1
  echo "[$(date +%T)] focused $label start" >> "$LOG/status.txt"
  timeout 1500 python3 -m pytest -q -p no:cacheprovider $extra $FOCUSED_COMMON > "$LOG/focused_$label.log" 2>&1
  echo "focused $label exit $?" >> "$LOG/status.txt"
}

run_measure() { # tree label
  local tree=$1 label=$2
  cd "$tree" || exit 1
  echo "[$(date +%T)] measure $label start" >> "$LOG/status.txt"
  PYTHONHASHSEED=0 timeout 1500 python3 docs/phases/phase058/measure_behaviour.py --label "$label" --turns 60 \
      --out "$MEAS/behaviour_$label.json" > "$LOG/measure_$label.log" 2>&1
  echo "measure $label exit $?" >> "$LOG/status.txt"
}

run_focused "$RB/p044" p044 "tests/test_phase044_births.py"
run_focused "$RB/p045" p045 "tests/test_phase044_births.py tests/test_phase045_dependants.py"
run_focused /tmp/rb_head head ""
run_measure /tmp/rb_head head
run_measure "$RB/p044" p044
run_measure "$RB/p045" p045

echo "[$(date +%T)] full suite p045 start" >> "$LOG/status.txt"
cd "$RB/p045" || exit 1
timeout 5400 python3 -m pytest -q -p no:cacheprovider > "$LOG/full_p045.log" 2>&1
echo "full p045 exit $?" >> "$LOG/status.txt"
echo "[$(date +%T)] ALL DONE" >> "$LOG/status.txt"
