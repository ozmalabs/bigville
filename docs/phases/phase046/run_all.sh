#!/usr/bin/env bash
# Phase 046 validation, from scratch trees built from git archive HEAD plus this phase's files and hunks.
# Stages run one after another. Logs and measurement files go to this report directory. Status: logs/status.txt.
set -u
PHASE_DIR=/home/matt/ozmadev/bigville/docs/phases/phase046
REPO=/home/matt/ozmadev/bigville
TREE=/tmp/p046
HEAD_TREE=/tmp/p046_head
LOG=$PHASE_DIR/logs
MEAS=$PHASE_DIR/measure
mkdir -p "$LOG" "$MEAS"
: > "$LOG/status.txt"
status() { echo "[$(date +%T)] $*" >> "$LOG/status.txt"; }

rm -rf "$TREE" "$HEAD_TREE"
python3 "$PHASE_DIR/build_clean_tree.py" --dest "$TREE" > "$LOG/build_p046.log" 2>&1
python3 "$PHASE_DIR/build_clean_tree.py" --dest "$HEAD_TREE" --head-only > "$LOG/build_head.log" 2>&1
status "built trees: $(head -1 "$LOG/build_p046.log")"

cd "$TREE" || exit 1
timeout 600 python3 domains/bigville_entities.py > "$LOG/selftest_p046.log" 2>&1
status "selftest p046 exit $?"
timeout 600 python3 -m domains.check > "$LOG/check_bigville.log" 2>&1
status "domains.check bigville exit $?"
timeout 600 python3 -m domains.check --pack test_hamlet > "$LOG/check_test_hamlet.log" 2>&1
status "domains.check test_hamlet exit $?"

rm -rf /tmp/p046_exp_bigville /tmp/p046_exp_test_hamlet
timeout 900 python3 tools/export_pack.py --pack bigville --out /tmp/p046_exp_bigville > "$LOG/export_bigville.log" 2>&1
timeout 900 python3 tools/export_pack.py --pack test_hamlet --out /tmp/p046_exp_test_hamlet > "$LOG/export_test_hamlet.log" 2>&1
diff -r /tmp/p046_exp_bigville "$TREE/packs/bigville" > "$LOG/export_diff_bigville.log" 2>&1
status "export diff bigville exit $? (0 = every exported file identical)"
diff -r /tmp/p046_exp_test_hamlet "$TREE/packs/test_hamlet" > "$LOG/export_diff_test_hamlet.log" 2>&1
status "export diff test_hamlet exit $?"

cd "$TREE" || exit 1
timeout 1500 python3 -m pytest -q -p no:cacheprovider tests/test_phase046_detraining.py > "$LOG/focused_p046.log" 2>&1
status "focused p046 exit $?"
timeout 1500 python3 -m pytest -q -p no:cacheprovider tests/test_phase032_training.py tests/test_phase044_births.py \
    tests/test_phase045_dependants.py tests/test_phase043_care.py tests/test_phase069_body.py tests/test_phase070_locus.py \
    tests/test_phase071_attend.py tests/test_simple_life.py tests/test_scenario_runner.py \
    tests/test_bigville_world_persistence.py tests/test_bigville_game_persistence.py > "$LOG/focused_common_p046.log" 2>&1
status "focused common p046 exit $?"

cd "$HEAD_TREE" || exit 1
PYTHONHASHSEED=0 timeout 1500 python3 docs/phases/phase058/measure_behaviour.py --label head60 --turns 60 \
    --out "$MEAS/behaviour_head60.json" > "$LOG/measure_head60.log" 2>&1
status "measure head60 exit $?"
cd "$TREE" || exit 1
PYTHONHASHSEED=0 timeout 1500 python3 docs/phases/phase058/measure_behaviour.py --label p046_60 --turns 60 \
    --out "$MEAS/behaviour_p046_60.json" > "$LOG/measure_p046_60.log" 2>&1
status "measure p046_60 exit $?"

status "full suite p046 start"
# The no-path run collects the docs/phases/*/files/tests copies too; HEAD already errors on them
# (basename clash with tests/test_phase044_births.py and test_phase045_dependants.py), so the suite is tests/.
timeout 5400 python3 -m pytest -q -p no:cacheprovider tests > "$LOG/full_p046.log" 2>&1
status "full p046 exit $?"
status "ALL DONE"
